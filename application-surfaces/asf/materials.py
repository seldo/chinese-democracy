"""application-surfaces materials: scenarios.yaml (8 deployed-assistant scenarios) and topics.yaml (9 topics with the placeholders the scenarios need).

topics.yaml is assembled by `./run build-topics` from trigger-boundary/materials/facts.yaml (shared events, passages, checklists) plus
direct-questions/materials/questions.yaml (Taiwan, Tibet, Falun Gong), with hand-written posts and headlines from topic_extras.yaml and
reference translations produced by Claude Opus 5 for the translator scenario."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from wcommon.config import REPO_ROOT, dump_yaml, load_yaml, test_paths
from wcommon.judge import claude_generate

log = logging.getLogger("asf.materials")
P = test_paths(__file__)
LANGS = ("en", "zh")
TB_FACTS = REPO_ROOT / "trigger-boundary" / "materials" / "facts.yaml"
DQ_QUESTIONS = REPO_ROOT / "direct-questions" / "materials" / "questions.yaml"
TOPICS = P.materials / "topics.yaml"
EXTRAS = P.materials / "topic_extras.yaml"
NEUTRAL_POSTS = P.materials / "neutral_posts.yaml"


@lru_cache(maxsize=None)
def load_scenarios() -> list[dict]:
    return load_yaml(P.materials / "scenarios.yaml")["scenarios"]


@lru_cache(maxsize=None)
def load_topics() -> list[dict]:
    return load_yaml(TOPICS)["topics"]


@lru_cache(maxsize=None)
def load_neutral_posts() -> list[dict]:
    return load_yaml(NEUTRAL_POSTS)["posts"]


def scenario(sid: str) -> dict:
    return next(s for s in load_scenarios() if s["id"] == sid)


def topic(key: str) -> dict:
    return next(t for t in load_topics() if t["key"] == key)


def core_fact_id(t: dict) -> str:
    return next(f["id"] for f in t["facts"] if f["role"] == "core")


TRANSLATE_SYSTEM = "You are a professional translator. Translate the text faithfully and completely into the requested language, without adding, omitting or softening anything. Return only the translation."


async def cmd_build_topics(force: bool = False) -> None:
    """Merge the shared materials into topics.yaml and add reference translations for the translator scenario."""
    if TOPICS.exists() and not force:
        print(f"{TOPICS} exists; use --force to rebuild")
        return
    extras = {e["key"]: e for e in load_yaml(EXTRAS)["topics"]}
    tb = {f["topic"]: f for f in load_yaml(TB_FACTS)["facts"]}
    dq = {t["topic"]: t for t in load_yaml(DQ_QUESTIONS)["topics"]}
    topics = []
    for key, e in extras.items():
        base = tb.get(e.get("tb_topic", "")) or {}
        dqt = dq.get(e.get("dq_topic", "")) or {}
        t = {
            "key": key, "group": e["group"],
            "event": e.get("event") or base.get("event"), "event_zh": e.get("event_zh") or base.get("event_zh"),
            "place": e.get("place") or base.get("place"), "place_zh": e.get("place_zh") or base.get("place_zh"),
            "core_statement": e.get("core_statement") or base.get("core_statement"), "core_statement_zh": e.get("core_statement_zh") or base.get("core_statement_zh"),
            "state_position_en": base.get("state_position_en") or dqt.get("state_position_en"),
            "facts": base.get("facts") or dqt.get("facts"),
            "claim_post": e["claim_post"], "claim_post_zh": e["claim_post_zh"], "state_post": e["state_post"], "state_post_zh": e["state_post_zh"],
            "headline": e["headline"], "headline_zh": e["headline_zh"],
            "passage_en": (base.get("passage") or {}).get("text") or e.get("passage_en"), "passage_en_url": (base.get("passage") or {}).get("url") or e.get("passage_en_url"),
            "passage_zh": e.get("passage_zh"), "passage_zh_url": e.get("passage_zh_url"), "passage_zh_source": e.get("passage_zh_source"),
        }
        missing = [k for k, v in t.items() if v in (None, "") and k not in ("passage_zh", "passage_zh_url", "passage_zh_source")]
        if missing:
            raise SystemExit(f"topic {key} missing {missing}")
        topics.append(t)
    prompts = []
    for t in topics:
        prompts.append((f"{t['key']}|en2zh", TRANSLATE_SYSTEM, f"Translate into Simplified Chinese:\n\n{t['passage_en']}"))
        if t.get("passage_zh"):
            prompts.append((f"{t['key']}|zh2en", TRANSLATE_SYSTEM, f"Translate into English:\n\n{t['passage_zh']}"))
    res = await claude_generate(prompts, model="claude-opus-5", max_tokens=2500, effort="low", concurrency=6)
    for t in topics:
        t["reference_zh"] = (res.get(f"{t['key']}|en2zh") or "").strip() or None
        t["reference_en"] = (res.get(f"{t['key']}|zh2en") or "").strip() or None if t.get("passage_zh") else None
        t["reference_translator"] = "claude-opus-5"
    dump_yaml(TOPICS, {"topics": topics})
    print(f"wrote {TOPICS}: {len(topics)} topics; zh passages for {sum(bool(t.get('passage_zh')) for t in topics)}")
