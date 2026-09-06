"""Framing lexicons (both directions) and the live-research-agent domain map."""
from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

from .config import LEXICON_DIR, load_yaml


@lru_cache(maxsize=None)
def phrases(name: str) -> tuple[str, ...]:
    return tuple(load_yaml(LEXICON_DIR / f"{name}.yaml")["phrases"])


@lru_cache(maxsize=None)
def _patterns(name: str) -> list[tuple[str, re.Pattern]]:
    out = []
    for p in phrases(name):
        esc = re.escape(p).replace(r"\ ", r"[\s\-]+")
        out.append((p, re.compile(rf"(?<![\w-]){esc}(?![\w-])", re.IGNORECASE)))
    return out


def count_hits(text: str | None, name: str) -> dict[str, int]:
    """{phrase: count} for phrases with at least one hit."""
    if not text:
        return {}
    hits = {}
    for p, rx in _patterns(name):
        n = len(rx.findall(text))
        if n:
            hits[p] = n
    return hits


def total_hits(text: str | None, name: str) -> int:
    return sum(count_hits(text, name).values())


@lru_cache(maxsize=None)
def _domain_map() -> list[tuple[str, str]]:
    y = load_yaml(LEXICON_DIR / "domains.yaml")["classes"]
    pairs = [(d.lower(), cls) for cls, ds in y.items() for d in ds]
    pairs.sort(key=lambda x: -len(x[0]))  # longest suffix wins
    return pairs


def domain_of(url: str) -> str:
    try:
        host = urlparse(url if "://" in url else "http://" + url).hostname or ""
    except Exception:
        return ""
    return host.lower().removeprefix("www.")


def classify_domain(url: str) -> str:
    host = domain_of(url)
    if not host:
        return "other"
    for d, cls in _domain_map():
        if d.startswith("."):
            if host.endswith(d) or ("." + host).endswith(d):
                return cls
        elif host == d or host.endswith("." + d):
            return cls
    return "other"


DOMAIN_CLASSES = ["prc_state", "other_state_media", "western_wire_press", "ngo", "academic", "government_non_prc", "wikipedia", "other"]
