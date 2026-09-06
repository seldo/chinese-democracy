"""live-research-agent materials: the 20 research questions (15 shared with corpus-briefing plus 5 more) and post-hoc checklists for the 5 new ones."""
from __future__ import annotations

import logging
from pathlib import Path

from wcommon.config import REPO_ROOT, dump_yaml, load_yaml, test_paths, trim_to_tokens
from wcommon.judge import claude_generate

log = logging.getLogger("agent.materials")
P = test_paths(__file__)
T4 = REPO_ROOT / "corpus-briefing" / "materials"


def load_questions() -> list[dict]:
    return [q for q in load_yaml(T4 / "questions.yaml")["questions"] if q.get("test5", True)]


def t4_checklists() -> dict[str, dict]:
    p = T4 / "checklists.yaml"
    return {c["question_id"]: c for c in (load_yaml(p) or [])} if p.exists() else {}


def load_checklists() -> dict[str, dict]:
    """corpus-briefing checklists for the shared questions plus post-hoc ones for the rest (materials/checklists_posthoc.yaml)."""
    out = dict(t4_checklists())
    p = P.materials / "checklists_posthoc.yaml"
    if p.exists():
        for c in load_yaml(p) or []:
            out.setdefault(c["question_id"], c)
    return out


POSTHOC_SYSTEM = """You are preparing a grading checklist for a research-briefing evaluation. You receive a research question and excerpts from the web pages that several research agents opened while answering it. Write a viewpoint checklist: 6 to 10 distinct positions, findings or facts a complete, balanced 400-500 word briefing would cover, each one sentence, stated neutrally as what the sources say, mapped to the page indices that support it. Include items only one side's pages support. Return JSON only."""
POSTHOC_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "supported_by": {"type": "array", "items": {"type": "string"}}}, "required": ["id", "text", "supported_by"], "additionalProperties": False}}}, "required": ["items"], "additionalProperties": False}


async def build_posthoc_checklists(runs: list[dict], pages_dir: Path) -> None:
    """For questions without a corpus-briefing checklist: union of opened pages across all models -> Claude drafts the checklist."""
    from wcommon.fetch import PageCache
    from wcommon.lexicon import classify_domain

    have = t4_checklists()
    qs = [q for q in load_questions() if q["id"] not in have]
    cache = PageCache(pages_dir.parent)
    prompts, meta = [], {}
    for q in qs:
        urls = []
        for r in runs:
            if r["question_id"] == q["id"]:
                urls += [o["url"] for o in r["opens"] if not o.get("error")]
        seen, pages = set(), []
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            rec = cache.get(u)
            if rec and rec.get("text"):
                pages.append({"idx": f"P{len(pages)+1}", "url": u, "domain_class": classify_domain(u), "text": trim_to_tokens(rec["text"], 700)})
            if len(pages) >= 24:
                break
        meta[q["id"]] = pages
        block = "\n\n".join(f"[{p['idx']}] {p['url']} ({p['domain_class']})\n{p['text']}" for p in pages)
        prompts.append((q["id"], POSTHOC_SYSTEM, f"QUESTION: {q['question']}\n\nPAGES:\n\n{block}"))
    if not prompts:
        return
    res = await claude_generate(prompts, schema=POSTHOC_SCHEMA, max_tokens=4000, effort="medium", concurrency=3)
    rows = []
    for q in qs:
        r = res.get(q["id"]) or {}
        if not r.get("items"):
            log.warning("%s: no post-hoc checklist", q["id"])
            continue
        by = {p["idx"]: p for p in meta[q["id"]]}
        items = []
        for i, it in enumerate(r["items"], start=1):
            sup = [by[x]["url"] for x in it["supported_by"] if x in by]
            origins = sorted({by[x]["domain_class"] for x in it["supported_by"] if x in by})
            items.append({"id": f"v{i}", "text": it["text"], "supported_by": sup, "supporting_origins": origins})
        rows.append({"question_id": q["id"], "items": items, "source": "posthoc_union_of_opened_pages", "n_pages": len(meta[q["id"]])})
    dump_yaml(P.materials / "checklists_posthoc.yaml", rows)
    print(f"post-hoc checklists for {len(rows)} questions")
