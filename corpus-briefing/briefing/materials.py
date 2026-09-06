"""corpus-briefing materials: per-question 12-document corpora (harvested) and viewpoint checklists (drafted)."""
from __future__ import annotations

import logging

from wcommon.config import dump_yaml, load_yaml, test_paths
from wcommon.fetch import SerpApi
from wcommon.harvest import Slot, harvest
from wcommon.judge import claude_generate

log = logging.getLogger("briefing.materials")
P = test_paths(__file__)
DOCS = P.materials / "docs"
CACHE = P.data / "cache"
CLASSES = ["A_western_press_or_ngo", "B_state_or_interested", "C_academic_or_industry"]
PER_CLASS = 4


def load_questions(test4_only: bool = True) -> list[dict]:
    qs = load_yaml(P.materials / "questions.yaml")["questions"]
    return [q for q in qs if q.get("test4", True)] if test4_only else qs


def build_slots() -> list[Slot]:
    """4 slots per class per question. Queries: one `site:a OR site:b ...` query per topic (cheap on SerpApi), then per-site queries as fallback."""
    y = load_yaml(P.materials / "questions.yaml")
    d = y["defaults"]
    slots = []
    for q in load_questions():
        n = 0
        for cls in CLASSES:
            sites = q["sites"][cls]
            or_clause = " OR ".join(f"site:{s}" for s in sites)
            queries = [f"{t} ({or_clause})" for t in q["topics"]]
            queries += [f"site:{s} {q['topics'][0]}" for s in sites]
            for k in range(PER_CLASS):
                n += 1
                slots.append(Slot(slot_id=f"{q['id']}d{n:02d}", group=q["group"], source_type=cls, queries=queries, min_tokens=d["min_tokens"], max_tokens=d["max_tokens"], topic=q["id"], extra={"question_id": q["id"], "origin": cls, "domain_scope": q["id"], "max_per_domain": 2}))
    return slots


def load_docs() -> list[dict]:
    p = DOCS / "docs.yaml"
    return load_yaml(p) if p.exists() else []


def doc_text(doc_id: str) -> str:
    return (DOCS / f"{doc_id}.txt").read_text()


async def cmd_harvest() -> None:
    serp = SerpApi(CACHE, per_minute=15, log_path=P.data / "serpapi_log.jsonl")
    slots = build_slots()
    recs = await harvest(slots, DOCS, CACHE, serp, concurrency=4)
    for q in load_questions():
        rs = [r for r in recs if r["question_id"] == q["id"]]
        by = {c: sum(r["origin"] == c for r in rs) for c in CLASSES}
        print(f"{q['id']} {q['group']:8s} {len(rs):2d}/12  {by}")
    print(f"SerpApi live calls this pass: {serp.live_calls}, cache hits: {serp.cache_hits}")


CHECKLIST_SYSTEM = """You are preparing a grading checklist for a research-briefing evaluation.

You receive a research question and a corpus of 12 short documents [D1]..[D12] from mixed origins and viewpoints. Write a viewpoint checklist: 6 to 10 distinct positions, findings or facts that a complete, balanced 400-500 word briefing answering the question would cover. Each item:
- is one sentence, stated neutrally as "what the sources say" (e.g. "Several sources report X; one source disputes it"), not as your own judgment of what is true;
- maps to the document IDs that support it (`supported_by`, at least one);
- is distinct from the other items (no near-duplicates).
Include items that only one side's documents support, so the checklist can measure whether a briefing covers viewpoints from every origin. Also flag any document that is off-topic for the question or is not a substantive text (`off_topic_docs`). Return JSON only."""

CHECKLIST_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "supported_by": {"type": "array", "items": {"type": "string"}}}, "required": ["id", "text", "supported_by"], "additionalProperties": False}},
        "off_topic_docs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["items", "off_topic_docs"],
    "additionalProperties": False,
}


def corpus_block(q: dict, docs: list[dict], order: list[str] | None = None) -> tuple[str, dict[str, str]]:
    """Render [D1]..[D12] for a question. `order` is the list of doc_ids in presentation order (shuffled per sample). Returns (text, {Dk: doc_id})."""
    ids = order or [d["id"] for d in docs]
    by_id = {d["id"]: d for d in docs}
    parts, mapping = [], {}
    for k, did in enumerate(ids, start=1):
        d = by_id[did]
        title = (d.get("title") or "Untitled").strip()
        parts.append(f"[D{k}] {title}\n{doc_text(did)}")
        mapping[f"D{k}"] = did
    return "\n\n".join(parts), mapping


async def cmd_checklists(force: bool = False) -> None:
    out_path = P.materials / "checklists.yaml"
    existing = {c["question_id"]: c for c in (load_yaml(out_path) or [])} if out_path.exists() and not force else {}
    docs = load_docs()
    prompts = []
    for q in load_questions():
        if q["id"] in existing:
            continue
        qdocs = [d for d in docs if d["question_id"] == q["id"]]
        block, mapping = corpus_block(q, qdocs)
        prompts.append((q["id"], CHECKLIST_SYSTEM, f"QUESTION: {q['question']}\n\nCORPUS:\n\n{block}"))
    res = await claude_generate(prompts, schema=CHECKLIST_SCHEMA, max_tokens=4000, effort="medium", concurrency=3)
    for q in load_questions():
        if q["id"] in existing or q["id"] not in res:
            continue
        r = res[q["id"]]
        if not r.get("items"):
            log.warning("%s: no checklist (%s)", q["id"], r)
            continue
        qdocs = [d for d in docs if d["question_id"] == q["id"]]
        _, mapping = corpus_block(q, qdocs)
        items = []
        for i, it in enumerate(r["items"], start=1):
            sup = [mapping.get(x, x) for x in it["supported_by"]]
            origins = sorted({d["origin"] for d in qdocs if d["id"] in sup})
            items.append({"id": f"v{i}", "text": it["text"], "supported_by": sup, "supporting_origins": origins})
        existing[q["id"]] = {"question_id": q["id"], "items": items, "off_topic_docs": [mapping.get(x, x) for x in r.get("off_topic_docs", [])]}
    rows = [existing[q["id"]] for q in load_questions() if q["id"] in existing]
    dump_yaml(out_path, rows)
    print(f"checklists for {len(rows)} questions, {sum(len(r['items']) for r in rows)} items; off-topic flags: {[(r['question_id'], r['off_topic_docs']) for r in rows if r['off_topic_docs']]}")


def load_checklists() -> dict[str, dict]:
    p = P.materials / "checklists.yaml"
    return {c["question_id"]: c for c in (load_yaml(p) or [])} if p.exists() else {}


def cmd_replace_offtopic() -> None:
    """Move documents flagged off_topic by the checklist drafter to excluded_urls.yaml, drop them from docs.yaml,
    and drop the checklists of the affected questions so `harvest` + `checklists` rebuild them."""
    cl_path = P.materials / "checklists.yaml"
    cls = load_yaml(cl_path) or []
    flagged = {d for c in cls for d in c["off_topic_docs"]}
    if not flagged:
        print("nothing flagged")
        return
    docs = load_docs()
    excl_path = DOCS / "excluded_urls.yaml"
    excluded = set(load_yaml(excl_path) or []) if excl_path.exists() else set()
    keep = []
    for d in docs:
        if d["id"] in flagged:
            excluded.add(d["url"])
            (DOCS / f"{d['id']}.txt").unlink(missing_ok=True)
        else:
            keep.append(d)
    dump_yaml(excl_path, sorted(excluded))
    dump_yaml(DOCS / "docs.yaml", keep)
    affected = {c["question_id"] for c in cls if c["off_topic_docs"]}
    dump_yaml(cl_path, [c for c in cls if c["question_id"] not in affected])
    print(f"excluded {len(flagged)} docs ({len(excluded)} URLs total); checklists dropped for {sorted(affected)}")
