"""trigger-boundary materials: facts.yaml (12 facts with placeholders, checklists and a source passage) and forms.yaml (11 request forms)."""
from __future__ import annotations

from functools import lru_cache

from wcommon.config import load_yaml, test_paths

P = test_paths(__file__)
LANGS = ("en", "zh")
GROUPS = ("china", "control")


@lru_cache(maxsize=None)
def load_facts() -> list[dict]:
    return load_yaml(P.materials / "facts.yaml")["facts"]


@lru_cache(maxsize=None)
def load_forms() -> list[dict]:
    return load_yaml(P.materials / "forms.yaml")["forms"]


def fact(fid: str) -> dict:
    return next(f for f in load_facts() if f["id"] == fid)


def form(form_id: str) -> dict:
    return next(f for f in load_forms() if f["id"] == form_id)


def core_fact_id(f: dict) -> str:
    return next(x["id"] for x in f["facts"] if x["role"] == "core")


def placeholders(f: dict, lang: str) -> dict:
    """Template values for one fact in one language. English placeholders are always available; Chinese ones fall back to English."""
    d = {k: v for k, v in f.items() if isinstance(v, str)}
    d["passage"] = f["passage"]["text"] if lang == "en" else f["passage"].get("text_zh") or f["passage"]["text"]
    return d


def render(template: str, f: dict, lang: str) -> str:
    return template.format(**placeholders(f, lang))


def turns(form_id: str, f: dict, lang: str) -> tuple[str | None, list[str]]:
    """(system prompt or None, list of rendered user turns) for one form, fact and language."""
    fm = form(form_id)
    system = fm.get(f"system_{lang}")
    return (render(system, f, lang) if system else None), [render(t, f, lang) for t in fm[f"turns_{lang}"]]
