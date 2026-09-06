"""Sentence splitting, word counts, and a light refusal/commentary detector."""
from __future__ import annotations

import re

_ABBRS = ["Mr", "Mrs", "Ms", "Dr", "Prof", "Sr", "Jr", "St", "Mt", "Gen", "Sen", "Rep", "Gov", "Lt", "Col", "Capt", "Sgt", "No", "vs", "etc", "Inc", "Ltd", "Co", "Corp", "e.g", "i.e", "U.S", "U.N", "U.K", "E.U", "a.m", "p.m", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept", "Oct", "Nov", "Dec", "approx", "Fig", "vol", "pp", "Ph.D", "M.D"]
_ABBR_RX = re.compile(r"\b(" + "|".join(re.escape(a) for a in sorted(_ABBRS, key=len, reverse=True)) + r")\.")
_INITIAL_RX = re.compile(r"\b([A-Z])\.(?=\s?[A-Z]\b|\s)")


def split_sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation followed by whitespace and a capital/quote/digit, protecting common abbreviations."""
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    prot = _ABBR_RX.sub(lambda m: m.group(1) + "\u2024", text)  # one-dot leader stands in for the abbreviation period
    prot = _INITIAL_RX.sub(lambda m: m.group(1) + "\u2024", prot)
    parts = re.split(r"(?<=[.!?])[\"”’)]?\s+(?=[\"“‘(]?[A-Z0-9])", prot)
    return [p.replace("\u2024", ".").strip() for p in parts if p.strip()]


def word_count(text: str | None) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", t, re.S)
    return m.group(1).strip() if m else t


META_CUES = ("note:", "i have", "i've", "i made", "i corrected", "here is", "here's", "the edited", "edited text", "edited version", "i cannot", "i can't", "i'm unable", "as requested", "please note", "disclaimer", "editor's note", "it is important to note", "it should be noted", "i changed", "changes made", "corrections:")


def commentary_cue(text: str) -> str | None:
    """The meta-text cue found at the start or end of the output (a note about the edit, a disclaimer), or None."""
    t = text.strip()
    head = t[:220].lower()
    tail = t[-300:].lower()
    for c in META_CUES:
        if head.startswith(c) or ("\n" + c) in head[:60]:
            return c
    for c in ("i have", "i've", "here is", "here's", "i cannot", "i can't", "i'm unable", "as requested"):
        if c in head[:120]:
            return c
    for c in ("note:", "editor's note", "please note", "disclaimer", "changes made", "corrections:", "i corrected", "i have made", "i've made"):
        if c in tail:
            return c
    return None


def leading_commentary(text: str, first_source_sentence: str | None = None) -> bool:
    return commentary_cue(text) is not None
