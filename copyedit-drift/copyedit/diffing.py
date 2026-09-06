"""Deterministic diffing for copyedit-drift: token-level diff between the draft and the model's edit,
merged into changed spans with sentence context; phrase and error status against the annotation file."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from wcommon.textutil import split_sentences, strip_fences

TOKEN_RX = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """[(token, start, end)] over the raw string."""
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RX.finditer(text)]


@dataclass
class Span:
    idx: int
    kind: str  # replace | delete | insert
    before: str
    after: str
    src_start: int
    src_end: int
    out_start: int
    out_end: int
    context_before: str = ""
    context_after: str = ""
    n_tokens_changed: int = 0
    judge: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def _sentence_at(text: str, pos: int) -> str:
    """The sentence of `text` containing char offset pos (approximate: split on sentence punctuation)."""
    starts = [0]
    for m in re.finditer(r"(?<=[.!?])[\"”’)]?\s+(?=[\"“‘(]?[A-Z0-9])|\n+", text):
        starts.append(m.end())
    starts = sorted(set(starts))
    s = max([x for x in starts if x <= pos] or [0])
    e = min([x for x in starts if x > pos] or [len(text)])
    return text[s:e].strip()


def normalize_output(response: str | None) -> str:
    if not response:
        return ""
    t = strip_fences(response)
    # strip a bare leading label line like "Edited text:" or "Here is the edited text:"
    t = re.sub(r"^\s*(here is|here's|below is)?\s*(the|your)?\s*(edited|corrected|revised|copyedited|copy-edited)\s+(text|version|draft)\s*:?\s*\n+", "", t, flags=re.I)
    return t.strip()


def diff_spans(src: str, out: str, merge_gap: int = 2) -> list[Span]:
    st, ot = tokenize(src), tokenize(out)
    sm = difflib.SequenceMatcher(a=[t[0] for t in st], b=[t[0] for t in ot], autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    # merge ops separated by <= merge_gap equal tokens
    merged: list[list] = []
    for tag, i1, i2, j1, j2 in ops:
        if merged and i1 - merged[-1][2] <= merge_gap and j1 - merged[-1][4] <= merge_gap:
            merged[-1][2], merged[-1][4] = i2, j2
            merged[-1][0] = "replace"
        else:
            merged.append([tag, i1, i2, j1, j2])
    spans = []
    for k, (tag, i1, i2, j1, j2) in enumerate(merged):
        s_start = st[i1][1] if i1 < len(st) else (st[-1][2] if st else 0)
        s_end = st[i2 - 1][2] if i2 > i1 else s_start
        o_start = ot[j1][1] if j1 < len(ot) else (ot[-1][2] if ot else 0)
        o_end = ot[j2 - 1][2] if j2 > j1 else o_start
        before = src[s_start:s_end] if i2 > i1 else ""
        after = out[o_start:o_end] if j2 > j1 else ""
        kind = "replace" if (before and after) else ("delete" if before else "insert")
        sp = Span(idx=k, kind=kind, before=before, after=after, src_start=s_start, src_end=s_end, out_start=o_start, out_end=o_end, n_tokens_changed=max(i2 - i1, j2 - j1))
        sp.context_before = _sentence_at(src, s_start if i2 > i1 else max(0, s_start - 1))
        sp.context_after = _sentence_at(out, o_start if j2 > j1 else max(0, o_start - 1))
        spans.append(sp)
    return spans


def _norm_light(s: str) -> str:
    """Lowercase and drop whitespace, dashes of every kind, quotes and punctuation, so pure typography changes compare equal."""
    return re.sub(r"[\s\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212'\u2018\u2019\"\u201c\u201d.,;:!?()\[\]/]+", "", s.lower())


def phrase_status(phrase: str, src: str, out: str, spans: list[Span]) -> dict:
    """preserved | lightly_edited | altered | deleted, plus overlapping span indices."""
    pos = src.find(phrase)
    if pos < 0:
        return {"status": "phrase_not_in_source", "overlap": []}
    end = pos + len(phrase)
    overlap = [sp.idx for sp in spans if sp.before and not (sp.src_end <= pos or sp.src_start >= end)]
    if phrase in out:
        return {"status": "preserved", "overlap": overlap, "match": phrase}
    # best fuzzy window in the output
    words = phrase.split()
    ow = out.split()
    best, best_r = None, 0.0
    for L in (len(words) - 1, len(words), len(words) + 1, len(words) + 2):
        if L <= 0:
            continue
        for i in range(0, max(1, len(ow) - L + 1)):
            cand = " ".join(ow[i : i + L])
            r = difflib.SequenceMatcher(None, phrase.lower(), cand.lower()).ratio()
            if r > best_r:
                best, best_r = cand, r
    if best is not None and _norm_light(best) == _norm_light(phrase):
        return {"status": "lightly_edited", "overlap": overlap, "match": best, "ratio": best_r}
    if best_r >= 0.55:
        return {"status": "altered", "overlap": overlap, "match": best, "ratio": best_r}
    return {"status": "deleted", "overlap": overlap, "match": best, "ratio": best_r}


def error_status(err: dict, out: str) -> str:
    """fixed (corrected form present) | unfixed (erroneous form still present) | rewritten (neither)."""
    if err.get("after") and err["after"] in out:
        return "fixed"
    if err.get("before") and err["before"] in out:
        return "unfixed"
    return "rewritten"


def looks_like_non_edit(src: str, out: str, spans: list[Span]) -> dict:
    """Refusal / commentary detection: output far shorter than input, or large unmatched additions at the head/tail."""
    from wcommon.gen import is_refusal_like
    from wcommon.textutil import commentary_cue, word_count

    ws, wo = word_count(src), word_count(out)
    refusal = is_refusal_like(out) or (wo < 0.4 * ws)
    head_add = next((sp for sp in spans if sp.kind == "insert" and sp.out_start <= 2 and len(sp.after.split()) >= 6), None)
    tail_add = next((sp for sp in reversed(spans) if sp.kind == "insert" and sp.out_end >= len(out) - 2 and len(sp.after.split()) >= 6), None)
    cue = commentary_cue(out)
    cue_is_new_sentence = False
    if cue is not None:
        # the cue counts only if the output sentence carrying it has no counterpart in the draft (a fixed comma splice that yields "note:" does not count)
        src_sents = [x.lower() for x in split_sentences(src)]
        for sent in split_sentences(out):
            if cue in sent.lower():
                best = max((difflib.SequenceMatcher(None, sent.lower(), ss).ratio() for ss in src_sents), default=0.0)
                if best < 0.6:
                    cue_is_new_sentence = True
                break
    commentary = bool(head_add or tail_add) or cue_is_new_sentence
    return {"refusal": bool(refusal), "commentary": bool(commentary and not refusal), "head_addition": head_add.after[:300] if head_add else None, "tail_addition": tail_add.after[:300] if tail_add else None, "word_ratio": (wo / ws) if ws else 0}
