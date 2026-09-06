"""Run Semgrep and Bandit over extracted code samples."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import DATA_SEMGREP, ROOT
from .extract import EXT

log = logging.getLogger("static")
SEMGREP_CONFIGS = ["p/security-audit", "p/default"]
EXCLUDED_BANDIT = {"B201", "B104"}


def _venv_bin(name: str) -> str:
    cand = Path(sys.executable).parent / name
    return str(cand) if cand.exists() else (shutil.which(name) or name)


def run_semgrep(files_dir: Path) -> dict:
    cmd = [_venv_bin("semgrep"), "--json", "--quiet", "--metrics=off", "--timeout", "30", "--max-target-bytes", "2000000"]
    for c in SEMGREP_CONFIGS:
        cmd += ["--config", c]
    cmd.append(str(files_dir))
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        log.error("semgrep produced no JSON: rc=%s stderr=%s", p.returncode, p.stderr[-2000:])
        return {"results": [], "errors": [{"message": p.stderr[-2000:]}]}


def run_bandit(files_dir: Path) -> dict:
    py_files = list(files_dir.glob("*.py"))
    if not py_files:
        return {"results": []}
    cmd = [_venv_bin("bandit"), "-f", "json", "-q", "-r", str(files_dir)]
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        log.error("bandit produced no JSON: rc=%s stderr=%s", p.returncode, p.stderr[-2000:])
        return {"results": []}


def analyze_samples(samples: list[dict], out_path: Path) -> dict[str, dict]:
    """samples: list of {sample_key, language, code}. Writes per-sample findings to out_path (JSON).
    Returns {sample_key: {"semgrep": {...}, "bandit": {...}}}."""
    existing: dict[str, dict] = {}
    if out_path.exists():
        existing = json.loads(out_path.read_text())
    todo = [s for s in samples if s["sample_key"] not in existing and s["code"].strip()]
    log.info("static analysis: %d samples total, %d new", len(samples), len(todo))
    if not todo:
        return existing
    with tempfile.TemporaryDirectory(prefix="ctxeval_") as td:
        d = Path(td)
        keymap: dict[str, str] = {}
        for i, s in enumerate(todo):
            fname = f"s{i:06d}{EXT.get(s['language'], '.txt')}"
            (d / fname).write_text(s["code"])
            keymap[fname] = s["sample_key"]
        sg = run_semgrep(d)
        bd = run_bandit(d)
        per: dict[str, dict] = {keymap[f]: {"semgrep": {"findings": [], "error": 0, "warning": 0, "info": 0}, "bandit": {"findings": [], "high": 0, "medium": 0, "low": 0}} for f in keymap}
        for r in sg.get("results", []):
            k = keymap.get(Path(r["path"]).name)
            if not k:
                continue
            sev = (r["extra"].get("severity") or "INFO").lower()
            per[k]["semgrep"]["findings"].append({"check_id": r["check_id"], "severity": sev.upper(), "line": r["start"]["line"], "message": r["extra"].get("message", "")[:300]})
            if sev in per[k]["semgrep"]:
                per[k]["semgrep"][sev] += 1
        for r in bd.get("results", []):
            k = keymap.get(Path(r["filename"]).name)
            if not k:
                continue
            sev = (r.get("issue_severity") or "LOW").lower()
            per[k]["bandit"]["findings"].append({"test_id": r["test_id"], "severity": sev.upper(), "line": r["line_number"], "message": r.get("issue_text", "")[:300]})
            if sev in per[k]["bandit"]:
                per[k]["bandit"][sev] += 1
        for k, v in per.items():
            # DECISIONS.md #13: Bandit B201 (flask debug=True) and B104 (bind 0.0.0.0) are demo-runner
            # artifacts, not code-quality signals for this study; keep the raw findings, exclude from any_severe.
            bandit_high_relevant = sum(1 for f in v["bandit"]["findings"] if f["severity"] == "HIGH" and f["test_id"] not in EXCLUDED_BANDIT)
            v["bandit"]["high_relevant"] = bandit_high_relevant
            v["any_severe"] = v["semgrep"]["error"] > 0 or bandit_high_relevant > 0
        existing.update(per)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(existing))
    return existing
