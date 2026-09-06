"""Blind the judge: strip every organization/place/group string from code before judging."""
from __future__ import annotations

import re

from .common import load_condition_meta, load_conditions

_terms: list[str] | None = None


def redaction_terms() -> list[str]:
    global _terms
    if _terms is None:
        meta = load_condition_meta()
        terms = set(meta.get("redaction_terms", []))
        for c in load_conditions():
            if c.organization:
                terms.add(c.organization)
        # longest first so multi-word phrases win over their parts
        _terms = sorted(terms, key=len, reverse=True)
    return _terms


def _is_cjk(t: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in t)


def _pattern() -> re.Pattern:
    parts = []
    for t in redaction_terms():
        esc = re.escape(t).replace(r"\ ", r"[\s_\-]*")
        parts.append(esc if _is_cjk(t) else r"\b" + esc + r"\b")  # no word boundaries for CJK
    return re.compile("|".join(parts), re.IGNORECASE)


_PAT: re.Pattern | None = None


def redact(text: str) -> tuple[str, int]:
    global _PAT
    if _PAT is None:
        _PAT = _pattern()
    out, n = _PAT.subn("ORG", text or "")
    return out, n
