"""Web fetching (httpx + trafilatura) and SerpApi search, both cached on disk.

Cache layout under <cache_dir>: pages/<sha1(url)>.json {url, final_url, status, title, text, fetched_at}
and searches/<sha1(normalized query)>.json (full SerpApi response). Search calls go through a token
bucket so the SerpApi hourly cap is never approached (spec: ~12/min is plenty).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from .config import env, n_tokens, now_iso, trim_to_tokens

log = logging.getLogger("fetch")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


class PageCache:
    def __init__(self, cache_dir: Path):
        self.dir = cache_dir / "pages"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, url: str) -> Path:
        return self.dir / f"{_h(url)}.json"

    def get(self, url: str) -> dict | None:
        p = self.path(url)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, url: str, rec: dict) -> None:
        self.path(url).write_text(json.dumps(rec, ensure_ascii=False))


def extract_text(html: str, url: str) -> tuple[str | None, str | None]:
    import trafilatura

    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False, include_links=False, favor_precision=True, output_format="txt")
    title = None
    try:
        meta = trafilatura.extract_metadata(html, default_url=url)
        title = meta.title if meta else None
    except Exception:
        pass
    return text, title


async def fetch_page(url: str, cache: PageCache, client: httpx.AsyncClient | None = None, timeout: float = 30.0, refresh: bool = False) -> dict:
    """Returns {url, final_url, status, title, text, error, fetched_at}. Never raises."""
    if not refresh:
        c = cache.get(url)
        if c is not None:
            return c
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    rec: dict[str, Any] = {"url": url, "final_url": None, "status": None, "title": None, "text": None, "error": None, "fetched_at": now_iso()}
    try:
        r = await client.get(url)
        rec["status"] = r.status_code
        rec["final_url"] = str(r.url)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ("html" in ctype or "xml" in ctype or "text" in ctype or not ctype):
            text, title = extract_text(r.text, url)
            rec["text"], rec["title"] = text, title
            if not text:
                rec["error"] = "no_extractable_text"
        elif r.status_code == 200 and "pdf" in ctype:
            rec["error"] = "pdf_not_supported"
        else:
            rec["error"] = f"http_{r.status_code}" if r.status_code != 200 else f"content_type_{ctype[:40]}"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    finally:
        if own:
            await client.aclose()
    cache.put(url, rec)
    return rec


class TokenBucket:
    def __init__(self, per_minute: float):
        self.interval = 60.0 / per_minute
        self.next_ok = 0.0
        self.lock = asyncio.Lock()

    async def take(self) -> None:
        async with self.lock:
            now = time.monotonic()
            wait = max(0.0, self.next_ok - now)
            self.next_ok = max(now, self.next_ok) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)


class SerpApi:
    """Google organic results via SerpApi. engine=google, gl=us, hl=en, num=10, safe=off, no location, no freshness filter."""

    def __init__(self, cache_dir: Path, per_minute: float = 12.0, log_path: Path | None = None, max_live: int | None = None):
        self.max_live = max_live  # hard ceiling on live (uncached) searches for this process; None = unlimited
        self.key = env("SERPAPI_KEY")
        if not self.key:
            raise RuntimeError("SERPAPI_KEY not set")
        self.dir = cache_dir / "searches"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bucket = TokenBucket(per_minute)
        self.log_path = log_path
        self.live_calls = 0
        self.cache_hits = 0

    @property
    def exhausted(self) -> bool:
        return self.max_live is not None and self.live_calls >= self.max_live

    def _path(self, q: str) -> Path:
        return self.dir / f"{_h(normalize_query(q))}.json"

    def cached(self, q: str) -> dict | None:
        p = self._path(q)
        return json.loads(p.read_text()) if p.exists() else None

    async def search(self, q: str) -> dict:
        c = self.cached(q)
        if c is not None:
            self.cache_hits += 1
            return c
        if self.max_live is not None and self.live_calls >= self.max_live:
            return {"error": "serpapi_budget_exhausted", "organic_results": [], "_query": q, "_normalized_query": normalize_query(q), "_fetched_at": now_iso()}
        await self.bucket.take()
        params = {"engine": "google", "q": q, "gl": "us", "hl": "en", "num": 10, "safe": "off", "api_key": self.key}
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(4):
                try:
                    r = await client.get("https://serpapi.com/search.json", params=params)
                    if r.status_code == 200:
                        data = r.json()
                        break
                    log.warning("serpapi HTTP %s: %s", r.status_code, r.text[:200])
                except Exception as e:
                    log.warning("serpapi error: %s", e)
                await asyncio.sleep(3 * (attempt + 1))
            else:
                data = {"error": "serpapi_failed", "organic_results": []}
            self.live_calls += 1
        data["_query"] = q
        data["_normalized_query"] = normalize_query(q)
        data["_fetched_at"] = now_iso()
        if "error" not in data:
            self._path(q).write_text(json.dumps(data, ensure_ascii=False))
        if self.log_path:
            with self.log_path.open("a") as f:
                f.write(json.dumps({"query": q, "normalized": normalize_query(q), "fetched_at": data["_fetched_at"], "n_organic": len(data.get("organic_results", [])), "error": data.get("error")}) + "\n")
        return data


def organic_only(data: dict, n: int = 10) -> list[dict]:
    """The block shown to the agent: title, url, snippet, published date (if any). Nothing else from the response."""
    out = []
    for r in data.get("organic_results", [])[:n]:
        out.append({"title": r.get("title"), "url": r.get("link"), "snippet": r.get("snippet"), "published": r.get("date")})
    return out


def page_for_model(rec: dict, max_tokens: int = 3000) -> str:
    if rec.get("text"):
        return trim_to_tokens(rec["text"], max_tokens)
    return f"[could not fetch page: {rec.get('error')}]"


def token_count(rec: dict) -> int:
    return n_tokens(rec.get("text") or "")
