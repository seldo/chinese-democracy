"""Shared config loading, paths, and pricing helpers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_RAW = ROOT / "data" / "raw"
DATA_JUDGED = ROOT / "data" / "judged"
DATA_SEMGREP = ROOT / "data" / "semgrep"
RESULTS = ROOT / "results"
for _p in (DATA_RAW, DATA_JUDGED, DATA_SEMGREP, RESULTS / "figures", RESULTS / "examples"):
    _p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Model:
    key: str
    family: str
    origin: str
    fireworks_id: str
    price_input_per_m: float
    price_output_per_m: float
    reasoning: bool

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.price_input_per_m + completion_tokens * self.price_output_per_m) / 1e6


@dataclass(frozen=True)
class Condition:
    id: str
    group: str
    organization: str | None
    system_prompt: str | None


@dataclass(frozen=True)
class Task:
    id: str
    category: str
    language: str
    prompt: str
    rubric: list[str]


def load_models(only: list[str] | None = None) -> list[Model]:
    y = yaml.safe_load((ROOT / "models.yaml").read_text())
    ms = [Model(**{k: m[k] for k in Model.__dataclass_fields__}) for m in y["models"]]
    if only:
        ms = [m for m in ms if m.key in only]
    return ms


def load_judge_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "models.yaml").read_text())["judge"]


def load_conditions() -> list[Condition]:
    y = yaml.safe_load((ROOT / "conditions" / "conditions.yaml").read_text())
    tmpl = y["template"]
    out = []
    for c in y["conditions"]:
        org = c.get("organization")
        sp = c.get("system_prompt") or (None if org is None else tmpl.replace("{ORGANIZATION}", org))
        out.append(Condition(id=c["id"], group=c["group"], organization=org, system_prompt=sp))
    return out


def load_condition_meta() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "conditions" / "conditions.yaml").read_text())


def load_tasks(only: list[str] | None = None) -> list[Task]:
    y = yaml.safe_load((ROOT / "tasks" / "tasks.yaml").read_text())
    ts = [Task(id=t["id"], category=t["category"], language=t["language"], prompt=t["prompt"].strip(), rubric=t["rubric"]) for t in y["tasks"]]
    if only:
        ts = [t for t in ts if t.id in only]
    return ts


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
