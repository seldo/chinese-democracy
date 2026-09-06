"""Shared config: repo root, .env, models.yaml, per-test paths, JSONL helpers, token counting."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

COMMON_ROOT = Path(__file__).resolve().parent.parent  # writing-common/
REPO_ROOT = COMMON_ROOT.parent  # chinese-democracy/
load_dotenv(REPO_ROOT / ".env")
LEXICON_DIR = COMMON_ROOT / "lexicon"
DECISIONS_MD = REPO_ROOT / "DECISIONS.md"


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v.strip().strip('"').strip("'") if isinstance(v, str) else v


@dataclass(frozen=True)
class Model:
    key: str
    family: str
    origin: str  # "china" | "west"
    fireworks_id: str
    price_input_per_m: float
    price_output_per_m: float
    reasoning: bool

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.price_input_per_m + completion_tokens * self.price_output_per_m) / 1e6


def _models_yaml() -> dict:
    return yaml.safe_load((COMMON_ROOT / "models.yaml").read_text())


def load_models(only: list[str] | None = None) -> list[Model]:
    ms = [Model(**{k: m[k] for k in Model.__dataclass_fields__}) for m in _models_yaml()["models"]]
    if only:
        ms = [m for m in ms if m.key in only]
    return ms


def load_judge_config() -> dict[str, Any]:
    return _models_yaml()["judge"]


@dataclass(frozen=True)
class TestPaths:
    """Standard layout inside one test folder: data/raw, data/judged, results/{figures,examples}."""
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def judged(self) -> Path:
        return self.root / "data" / "judged"

    @property
    def materials(self) -> Path:
        return self.root / "materials"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def figures(self) -> Path:
        return self.root / "results" / "figures"

    @property
    def examples(self) -> Path:
        return self.root / "results" / "examples"

    def ensure(self) -> "TestPaths":
        for p in (self.raw, self.judged, self.materials, self.figures, self.examples):
            p.mkdir(parents=True, exist_ok=True)
        return self


def test_paths(module_file: str) -> TestPaths:
    """Call as test_paths(__file__) from a test package; the test root is the package's parent."""
    return TestPaths(Path(module_file).resolve().parent.parent).ensure()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a torn final line from an interrupted write; the row is redone on resume
    return out


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def dump_yaml(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=110))


_enc = None


def n_tokens(text: str | None) -> int:
    """Approximate token count (tiktoken o200k_base). Used for trimming and reporting, not billing."""
    global _enc
    if not text:
        return 0
    if _enc is None:
        import tiktoken

        _enc = tiktoken.get_encoding("o200k_base")
    return len(_enc.encode(text, disallowed_special=()))


def trim_to_tokens(text: str, max_tokens: int) -> str:
    """Cut at the last paragraph boundary that keeps the text under max_tokens (falls back to sentence, then hard cut)."""
    if n_tokens(text) <= max_tokens:
        return text
    paras = text.split("\n\n")
    out: list[str] = []
    for p in paras:
        cand = "\n\n".join(out + [p])
        if n_tokens(cand) > max_tokens:
            break
        out.append(p)
    if out and n_tokens("\n\n".join(out)) >= max_tokens * 0.6:
        return "\n\n".join(out)
    import re

    sents = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for s in sents:
        cand = " ".join(out + [s])
        if n_tokens(cand) > max_tokens:
            break
        out.append(s)
    if out:
        return " ".join(out)
    import tiktoken

    enc = tiktoken.get_encoding("o200k_base")
    return enc.decode(enc.encode(text, disallowed_special=())[:max_tokens])


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
