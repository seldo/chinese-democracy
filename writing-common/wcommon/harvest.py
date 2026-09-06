"""Document harvester shared by summarization-recall and corpus-briefing.

A Slot says what kind of document is wanted (group, source_type, queries in preference order, length
floor). The harvester runs each query through SerpApi (cached), walks the organic results in rank
order, fetches with httpx + trafilatura, and accepts the first page whose extracted text is long
enough and whose URL has not been used by another slot. Everything is recorded: the accepted URL,
rank, query, retrieval date, token count, plus every rejected candidate and why.
Output: <docs_dir>/<doc_id>.txt (trimmed) and <docs_dir>/docs.yaml (list of records), resumable.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import append_jsonl, dump_yaml, load_yaml, n_tokens, now_iso, trim_to_tokens
from .fetch import UA, PageCache, SerpApi, fetch_page
from .lexicon import domain_of

log = logging.getLogger("harvest")

BAD_PATH_RX = re.compile(r"(\.pdf$|/tag/|/tags/|/topics?/|/category/|/author/|/search|/video/|/videos/|/live/|/gallery/|/photos?/|/podcast|/audio/|/newsletters?/|/about|/contact|/subscribe|/sitemap|/index\.html?$|/$)", re.I)


@dataclass
class Slot:
    slot_id: str
    group: str
    source_type: str
    queries: list[str]
    min_tokens: int = 1000
    max_tokens: int = 3000
    topic: str = ""
    extra: dict = field(default_factory=dict)


def _sites_of(query: str) -> list[str]:
    """All site: operators in the query (Google accepts `site:a OR site:b`)."""
    return [s.lower().removeprefix("www.").rstrip(")") for s in re.findall(r"site:(\S+)", query)]


def _on_site(url: str, sites: list[str]) -> bool:
    d = domain_of(url)
    return any(d == s or d.endswith("." + s) for s in sites)


def _url_ok(url: str, sites: list[str], used: set[str]) -> str | None:
    if not url or url in used:
        return "used" if url else "no_url"
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return "scheme"
    if sites and not _on_site(url, sites):
        return "off_site"
    path = p.path or "/"
    if BAD_PATH_RX.search(path) and not re.search(r"\d{4}", path):
        return "index_or_media_page"
    return None


async def harvest(slots: list[Slot], docs_dir: Path, cache_dir: Path, serp: SerpApi, concurrency: int = 4, max_candidates_per_query: int = 10) -> list[dict]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = docs_dir / "docs.yaml"
    records: list[dict] = load_yaml(yaml_path) if yaml_path.exists() else []
    records = records or []
    done = {r["id"]: r for r in records}
    used_urls = {r["url"] for r in records}
    excl_path = docs_dir / "excluded_urls.yaml"
    excluded = set(load_yaml(excl_path) or []) if excl_path.exists() else set()
    used_urls |= excluded  # URLs rejected after review (e.g. off-topic) are never picked again
    per_domain: dict[tuple, int] = {}
    for r in records:
        k = (r.get("domain_scope"), domain_of(r["url"]))
        per_domain[k] = per_domain.get(k, 0) + 1
    cache = PageCache(cache_dir)
    rejects = docs_dir / "rejected_candidates.jsonl"
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    client = httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

    async def one(slot: Slot):
        if slot.slot_id in done:
            return
        for qi, q in enumerate(slot.queries):
            data = await serp.search(q)
            sites = _sites_of(q)
            for rank, r in enumerate(data.get("organic_results", [])[:max_candidates_per_query], start=1):
                url = r.get("link")
                async with lock:
                    why = _url_ok(url, sites, used_urls)
                    if why is None and slot.extra.get("max_per_domain") and per_domain.get((slot.extra.get("domain_scope"), domain_of(url)), 0) >= slot.extra["max_per_domain"]:
                        why = "domain_quota"
                    if why is None:
                        used_urls.add(url)  # reserve
                if why:
                    append_jsonl(rejects, {"slot": slot.slot_id, "query": q, "rank": rank, "url": url, "reason": why})
                    continue
                async with sem:
                    rec = await fetch_page(url, cache, client)
                nt = n_tokens(rec.get("text") or "")
                if rec.get("error") or nt < slot.min_tokens:
                    async with lock:
                        used_urls.discard(url)
                    append_jsonl(rejects, {"slot": slot.slot_id, "query": q, "rank": rank, "url": url, "reason": rec.get("error") or f"too_short_{nt}"})
                    continue
                text = trim_to_tokens(rec["text"], slot.max_tokens)
                (docs_dir / f"{slot.slot_id}.txt").write_text(text)
                row = {"id": slot.slot_id, "group": slot.group, "source_type": slot.source_type, "topic": slot.topic, "url": url, "final_url": rec.get("final_url"), "title": rec.get("title"), "query": q, "query_index": qi, "rank": rank, "retrieved_date": rec.get("fetched_at", now_iso())[:10], "token_count": n_tokens(text), "token_count_untrimmed": nt, **slot.extra}
                async with lock:
                    done[slot.slot_id] = row
                    records.append(row)
                    k = (slot.extra.get("domain_scope"), domain_of(url))
                    per_domain[k] = per_domain.get(k, 0) + 1
                    dump_yaml(yaml_path, records)
                log.info("%s <- %s (%d tok, q%d r%d)", slot.slot_id, url, row["token_count"], qi, rank)
                return
        log.warning("%s: no acceptable document found in %d queries", slot.slot_id, len(slot.queries))
        append_jsonl(rejects, {"slot": slot.slot_id, "reason": "UNFILLED"})

    await asyncio.gather(*(one(s) for s in slots))
    await client.aclose()
    return records
