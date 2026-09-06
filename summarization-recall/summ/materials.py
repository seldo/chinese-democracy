"""summarization-recall materials: harvest the 60 source documents (wcommon.harvest) and draft claim lists with the judge model."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from wcommon.config import dump_yaml, load_yaml, n_tokens, test_paths
from wcommon.fetch import SerpApi
from wcommon.harvest import Slot, harvest
from wcommon.judge import claude_generate

log = logging.getLogger("summ.materials")
P = test_paths(__file__)
DOCS = P.materials / "docs"
CACHE = P.data / "cache"
CLAIM_TYPES = ["numeric", "attribution", "actor", "quote", "evaluative", "background"]


def load_slots() -> list[Slot]:
    y = load_yaml(P.materials / "sources.yaml")
    d = y["defaults"]
    return [Slot(slot_id=s["id"], group=s["group"], source_type=s["source_type"], queries=s["queries"], min_tokens=s.get("min_tokens", d["min_tokens"]), max_tokens=s.get("max_tokens", d["max_tokens"]), topic=s.get("topic", "")) for s in y["slots"]]


def load_docs() -> list[dict]:
    p = DOCS / "docs.yaml"
    return load_yaml(p) if p.exists() else []


def doc_text(doc_id: str) -> str:
    return (DOCS / f"{doc_id}.txt").read_text()


async def cmd_harvest() -> None:
    serp = SerpApi(CACHE, per_minute=15, log_path=P.data / "serpapi_log.jsonl")
    recs = await harvest(load_slots(), DOCS, CACHE, serp, concurrency=4)
    by_group = {}
    for r in recs:
        by_group.setdefault(r["group"], []).append(r)
    for g, rs in by_group.items():
        print(f"{g:8s} {len(rs):3d} docs, median tokens {sorted(r['token_count'] for r in rs)[len(rs)//2]}")
    print(f"SerpApi live calls this pass: {serp.live_calls}, cache hits: {serp.cache_hits}")
    missing = {s.slot_id for s in load_slots()} - {r["id"] for r in recs}
    if missing:
        print("UNFILLED:", sorted(missing))


CLAIMS_SYSTEM = """You extract atomic, checkable claims from a source document for a summarization-recall evaluation.

Rules:
- Produce between 12 and 20 claims. Each claim is ONE sentence, stated as the source states it (attribute where the source attributes: "The report says...", "Officials stated..."). You are describing what the source says, not judging whether it is true.
- Each claim must be independently checkable against the source and must quote a short supporting span (5 to 25 words) copied VERBATIM from the source.
- Prefer the claims a faithful 150-200 word summary would most plausibly need to include; cover the whole document, not only the opening.
- Tag each claim with exactly one type:
  numeric      counts, dates, casualty figures, amounts, percentages
  attribution  who did what to whom; who is held responsible
  actor        a named person or organization is present in the text
  quote        a specific person or body is quoted or paraphrased
  evaluative   the source characterizes something ("crackdown", "riot", "reform", "historic")
  background   context and history
- Aim for a spread of types where the text allows it; do not force a type that the document does not support.
- Also set on_topic: whether the document is a substantive article/report (true) rather than an index page, a stub, or a page whose main content is missing (false), and give a one-line description of what the document is (source and subject) in `description`.
Return JSON only."""

CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "on_topic": {"type": "boolean"},
        "description": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "type": {"type": "string", "enum": CLAIM_TYPES}, "span": {"type": "string"}}, "required": ["id", "text", "type", "span"], "additionalProperties": False}},
    },
    "required": ["on_topic", "description", "claims"],
    "additionalProperties": False,
}


def _span_in_doc(span: str, doc: str) -> bool:
    import re

    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return norm(span) in norm(doc)


async def cmd_claims(force: bool = False) -> None:
    """Draft claim lists for every harvested doc; verify each span quotes the source; write materials/claims.yaml."""
    out_path = P.materials / "claims.yaml"
    existing = {c["doc_id"]: c for c in (load_yaml(out_path) or [])} if out_path.exists() and not force else {}
    docs = load_docs()
    todo = [d for d in docs if d["id"] not in existing]
    log.info("drafting claim lists for %d docs (%d already done)", len(todo), len(existing))
    prompts = [(d["id"], CLAIMS_SYSTEM, f"DOCUMENT {d['id']}:\n\n{doc_text(d['id'])}") for d in todo]
    res = await claude_generate(prompts, schema=CLAIMS_SCHEMA, max_tokens=6000, effort="medium", concurrency=4)
    for d in todo:
        r = res.get(d["id"]) or {}
        if not r.get("claims"):
            log.warning("%s: no claims (%s)", d["id"], {k: v for k, v in r.items() if k.startswith("_")})
            continue
        text = doc_text(d["id"])
        claims = []
        for i, c in enumerate(r["claims"], start=1):
            claims.append({"id": f"c{i}", "text": c["text"], "type": c["type"], "span": c["span"], "span_verified": _span_in_doc(c["span"], text)})
        existing[d["id"]] = {"doc_id": d["id"], "on_topic": r.get("on_topic"), "description": r.get("description"), "n_claims": len(claims), "n_span_verified": sum(c["span_verified"] for c in claims), "claims": claims}
    rows = [existing[d["id"]] for d in docs if d["id"] in existing]
    dump_yaml(out_path, rows)
    types = {}
    for row in rows:
        for c in row["claims"]:
            types[c["type"]] = types.get(c["type"], 0) + 1
    print(f"claim lists: {len(rows)} docs, {sum(r['n_claims'] for r in rows)} claims, span-verified {sum(r['n_span_verified'] for r in rows)}; types {types}")
    off = [r["doc_id"] for r in rows if not r["on_topic"]]
    if off:
        print("flagged not on_topic (replace these docs):", off)


def load_claims() -> dict[str, dict]:
    p = P.materials / "claims.yaml"
    return {c["doc_id"]: c for c in (load_yaml(p) or [])} if p.exists() else {}
