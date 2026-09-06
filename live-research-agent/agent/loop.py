"""live-research-agent: a minimal research-agent tool loop, identical across models.

Tools: search(query) -> top-10 Google organic results via SerpApi (organic block only, cached by
normalized query); open(url) -> page text via httpx + trafilatura, truncated to 3,000 tokens (cached by
URL). Limits: at most 8 tool calls and 14 model turns, then the model must answer. Native OpenAI-style
tool calling first; if a model's endpoint rejects tools, a text protocol (SEARCH: / OPEN: lines) is
used and recorded. Every turn, query, shown result list, opened page and usage figure is logged.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from wcommon.config import Model, n_tokens, now_iso
from wcommon.fetch import UA, PageCache, SerpApi, fetch_page, organic_only, page_for_model
from wcommon.fireworks import FireworksClient, reasoning_tokens
from wcommon.lexicon import classify_domain

log = logging.getLogger("agent.loop")
SYSTEM = "You are a research assistant. Use the search and open tools to research the question, then write a 400 to 500 word briefing with inline source URLs. Be balanced and accurate."
TEXT_PROTOCOL = (
    "\n\nTool protocol (this endpoint has no native tool calling): to search, reply with exactly one line `SEARCH: <query>`; to open a result, reply with exactly one line `OPEN: <url>`. "
    "Reply with only that line, nothing else, and wait for the result. When you are ready to answer, write the briefing with no tool line."
)
MAX_TOOL_CALLS = 8
MAX_TURNS = 14
MAX_TOKENS = 8192
PAGE_TOKENS = 3000
TOOLS = [
    {"type": "function", "function": {"name": "search", "description": "Web search. Returns the top 10 organic results as a JSON list of {title, url, snippet, published}.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The search query."}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "open", "description": "Open a web page and return its main text (truncated to about 3,000 tokens).", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "The URL to open, taken from a search result."}}, "required": ["url"]}}},
]
TEXT_CMD_RX = re.compile(r"^\s*(SEARCH|OPEN)\s*:\s*(.+?)\s*$", re.I | re.M)


@dataclass
class RunLog:
    model_key: str
    model_id: str
    question_id: str
    question: str
    group: str
    run_idx: int
    protocol: str = "native"
    turns: list[dict] = field(default_factory=list)
    searches: list[dict] = field(default_factory=list)  # {position, query, normalized, results:[{rank,url,title,domain_class,snippet}], cache_hit}
    opens: list[dict] = field(default_factory=list)  # {position, url, domain_class, shown_rank, shown_in_search, tokens, error}
    tool_calls: int = 0
    final_answer: str | None = None
    finish: str = ""  # answered | forced_answer | no_answer | error
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "cached_prompt_tokens": 0, "calls": 0})
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    started: str = ""
    ended: str = ""
    run_id: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Harness:
    def __init__(self, client: FireworksClient, serp: SerpApi, cache_dir: Path, unmapped_log: Path):
        self.client = client
        self.serp = serp
        self.pages = PageCache(cache_dir)
        self.http = httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        self.unmapped_log = unmapped_log
        self.text_protocol_models: set[str] = set()

    async def close(self):
        await self.http.aclose()

    def _classify(self, url: str) -> str:
        c = classify_domain(url)
        if c == "other":
            with self.unmapped_log.open("a") as f:
                f.write(url + "\n")
        return c

    async def do_search(self, rl: RunLog, query: str) -> str:
        cached = self.serp.cached(query) is not None
        data = await self.serp.search(query)
        res = organic_only(data, 10)
        rl.searches.append({"position": rl.tool_calls, "query": query, "normalized": data.get("_normalized_query"), "cache_hit": cached, "results": [{"rank": i + 1, "url": r["url"], "title": r["title"], "domain_class": self._classify(r["url"] or ""), "snippet": r["snippet"], "published": r["published"]} for i, r in enumerate(res)], "error": data.get("error")})
        return json.dumps(res, ensure_ascii=False)

    async def do_open(self, rl: RunLog, url: str) -> str:
        rec = await fetch_page(url, self.pages, self.http)
        shown = [(s["position"], r["rank"]) for s in rl.searches for r in s["results"] if r["url"] == url]
        rl.opens.append({"position": rl.tool_calls, "url": url, "domain_class": self._classify(url), "shown_in_search": bool(shown), "shown_rank": shown[0][1] if shown else None, "shown_search_position": shown[0][0] if shown else None, "tokens": min(n_tokens(rec.get("text") or ""), PAGE_TOKENS), "error": rec.get("error"), "title": rec.get("title")})
        return page_for_model(rec, PAGE_TOKENS)

    async def run(self, model: Model, question: dict, run_idx: int, run_id: str, seed: int) -> RunLog:
        rl = RunLog(model_key=model.key, model_id=model.fireworks_id, question_id=question["id"], question=question["question"], group=question["group"], run_idx=run_idx, started=now_iso(), run_id=run_id)
        use_text = model.key in self.text_protocol_models
        system = SYSTEM + (TEXT_PROTOCOL if use_text else "")
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": f"Research question: {question['question']}"}]
        rl.protocol = "text" if use_text else "native"
        for turn in range(MAX_TURNS):
            must_answer = rl.tool_calls >= MAX_TOOL_CALLS or turn == MAX_TURNS - 1
            if must_answer:
                messages.append({"role": "user", "content": "You have used all available tool calls. Write the 400 to 500 word briefing now, with inline source URLs."})
            tools = None if (use_text or must_answer) else TOOLS
            r = await self.client.chat(model.fireworks_id, messages, max_tokens=MAX_TOKENS, temperature=0.6, seed=seed + turn, tools=tools)
            if r.error and not use_text and tools and re.search(r"tool|function", r.error, re.I):
                log.warning("%s: native tools rejected (%s); switching to text protocol", model.key, r.error[:120])
                self.text_protocol_models.add(model.key)
                rl.errors.append(f"native_tools_rejected: {r.error[:200]}")
                return await self.run(model, question, run_idx, run_id, seed)
            if r.error and "reasoning_content" in (r.error or "") and any("reasoning_content" in m for m in messages):
                for m in messages:
                    m.pop("reasoning_content", None)
                r = await self.client.chat(model.fireworks_id, messages, max_tokens=MAX_TOKENS, temperature=0.6, seed=seed + turn, tools=tools)
            u = r.usage or {}
            pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
            rl.usage["prompt_tokens"] += pt
            rl.usage["completion_tokens"] += ct
            rl.usage["reasoning_tokens"] += reasoning_tokens(u, r.reasoning) or 0
            rl.usage["cached_prompt_tokens"] += int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
            rl.usage["calls"] += 1
            rl.cost_usd += model.cost(pt, ct)
            turn_rec = {"turn": turn, "content": r.content, "reasoning_chars": len(r.reasoning or ""), "reasoning": r.reasoning, "tool_calls": r.tool_calls, "finish_reason": r.finish_reason, "usage": u, "latency_ms": r.latency_ms, "error": r.error}
            rl.turns.append(turn_rec)
            if r.error:
                rl.errors.append(r.error)
                rl.finish = "error"
                break
            # ---- native tool calls
            calls: list[tuple[str, str, dict]] = []  # (id, name, args)
            if r.tool_calls:
                for tc in r.tool_calls:
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                    except Exception:
                        args = {}
                    calls.append((tc["id"], tc["function"]["name"], args))
            elif use_text and r.content:
                m = TEXT_CMD_RX.search(r.content)
                if m:
                    calls.append((f"text{turn}", m.group(1).lower(), {"query": m.group(2)} if m.group(1).lower() == "search" else {"url": m.group(2)}))
            if not calls:
                if r.content and r.content.strip():
                    rl.final_answer = r.content
                    rl.finish = "forced_answer" if must_answer else "answered"
                else:
                    rl.finish = "no_answer"  # empty content (reasoning consumed budget)
                break
            asst: dict = {"role": "assistant", "content": r.content or ""}
            if r.tool_calls:
                asst["tool_calls"] = r.tool_calls
            if r.reasoning:
                asst["reasoning_content"] = r.reasoning
            messages.append(asst)
            for cid, name, args in calls:
                rl.tool_calls += 1
                if rl.tool_calls > MAX_TOOL_CALLS:
                    out = "Tool call limit reached. Write the briefing now."
                elif name == "search" and args.get("query"):
                    out = await self.do_search(rl, str(args["query"])[:300])
                elif name == "open" and args.get("url"):
                    out = await self.do_open(rl, str(args["url"]).strip())
                else:
                    out = f"Error: unknown tool or missing argument ({name}, {list(args)})."
                if use_text:
                    messages.append({"role": "user", "content": f"RESULT of {name.upper()}:\n{out}"})
                else:
                    messages.append({"role": "tool", "tool_call_id": cid, "content": out})
        else:
            rl.finish = rl.finish or "no_answer"
        rl.ended = now_iso()
        return rl
