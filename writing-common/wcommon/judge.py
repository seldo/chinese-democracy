"""Claude judge plumbing shared by all four tests.

- `JudgeRequest`: one blind scoring call (system, user, JSON schema). Keys are opaque item/sample ids.
- `run_sync`: small passes (calibration, checklist drafting) with bounded concurrency.
- `run_batch`: the full judge pass through the Message Batches API (50% price). Resumable: batch ids
  are persisted in <state_path>; results are appended to <out_path> as {key, result, usage, batch_id}.
  Requests the batch judge refuses (safety classifier) are re-run synchronously with the server-side
  refusal fallback so a judge refusal never becomes missing data.
The judge never receives the model name or the item group label; callers must not put them in the prompt.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from .config import append_jsonl, load_judge_config, read_jsonl

log = logging.getLogger("judge")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5", "claude-fable-5-1")  # Sonnet 5 rejects the `fallbacks` parameter


def supports_fallback(model: str) -> bool:
    return model in FALLBACK_MODELS


async def create_message(client: anthropic.AsyncAnthropic, **kw):
    """messages.create with the server-side refusal fallback when the model supports it."""
    if supports_fallback(kw.get("model", "")):
        return await client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kw)
    return await client.messages.create(**kw)


@dataclass
class JudgeRequest:
    key: str
    system: str
    user: str
    schema: dict
    max_tokens: int = 4096
    effort: str = "low"
    meta: dict = field(default_factory=dict)


def _cfg() -> dict:
    return load_judge_config()


def judge_model() -> str:
    return _cfg()["model"]


def params(req: JudgeRequest) -> dict:
    return dict(
        model=judge_model(),
        max_tokens=req.max_tokens,
        system=[{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": req.user}],
        output_config={"effort": req.effort, "format": {"type": "json_schema", "schema": req.schema}},
    )


def parse(msg) -> dict:
    text = next((b.text for b in msg.content if b.type == "text"), "")
    return json.loads(text)


def usage_of(msg) -> dict:
    u = msg.usage
    return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0, "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0, "model": getattr(msg, "model", None)}


def usage_cost(u: dict, batch: bool) -> float:
    c = _cfg()
    cost = (u.get("input_tokens", 0) * c["price_input_per_m"] + u.get("cache_read_input_tokens", 0) * c["price_input_per_m"] * c.get("cache_read_multiplier", 0.1) + u.get("cache_creation_input_tokens", 0) * c["price_input_per_m"] * c.get("cache_write_multiplier", 1.25) + u.get("output_tokens", 0) * c["price_output_per_m"]) / 1e6
    return cost * (c.get("batch_discount", 0.5) if batch else 1.0)


def cid(key: str) -> str:
    return "r_" + hashlib.sha1(key.encode()).hexdigest()[:40]


async def _call_sync(client: anthropic.AsyncAnthropic, sem: asyncio.Semaphore, req: JudgeRequest, fallback: bool = True) -> tuple[dict, dict]:
    async with sem:
        last = None
        for attempt in range(6):
            try:
                msg = await create_message(client, **params(req))
                if msg.stop_reason == "refusal":
                    return {"_refused_by_judge": True, "_served_by": msg.model}, usage_of(msg)
                try:
                    d = parse(msg)
                except Exception as e:
                    d = {"_parse_error": str(e)}
                d["_served_by"] = msg.model
                return d, usage_of(msg)
            except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError, anthropic.APITimeoutError) as e:
                last = e
                log.warning("judge retry %d for %s: %s", attempt + 1, req.key, str(e)[:120])
                await asyncio.sleep(min(60, 2**attempt + 1))
        return {"_error": f"failed repeatedly: {last}"}, {}


async def run_sync(reqs: list[JudgeRequest], out_path: Path | None = None, concurrency: int = 6, skip_done: bool = True) -> dict[str, dict]:
    """Run requests synchronously. Returns {key: {"result":..., "usage":...}}. Appends to out_path if given."""
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(concurrency)
    done: dict[str, dict] = {}
    if out_path and skip_done:
        for r in read_jsonl(out_path):
            done[r["key"]] = r
    todo = [r for r in reqs if r.key not in done]
    log.info("judge sync: %d requests (%d already done)", len(todo), len(done))

    async def one(req: JudgeRequest):
        res, usage = await _call_sync(client, sem, req)
        row = {"key": req.key, "result": res, "usage": usage, "batch_id": "sync", "meta": req.meta, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if out_path:
            append_jsonl(out_path, row)
        done[req.key] = row

    await asyncio.gather(*(one(r) for r in todo))
    return done


def _load_state(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {"batches": []}


def _save_state(p: Path, st: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1))


def judged_keys(out_path: Path) -> set[str]:
    return {r["key"] for r in read_jsonl(out_path)}


def _collect(client: anthropic.Anthropic, b: dict, by_key: dict[str, JudgeRequest], out_path: Path) -> None:
    info = client.messages.batches.retrieve(b["id"])
    if info.processing_status != "ended":
        return
    by_cid = {cid(k): k for k in b["keys"]}
    n = 0
    refused = []
    for res in client.messages.batches.results(b["id"]):
        key = by_cid.get(res.custom_id)
        if key is None:
            continue
        req = by_key.get(key)
        if res.result.type == "succeeded":
            msg = res.result.message
            if msg.stop_reason == "refusal":
                refused.append(key)
                continue
            try:
                data = parse(msg)
            except Exception as e:
                data = {"_parse_error": str(e)}
            data["_served_by"] = msg.model
            row = {"key": key, "result": data, "usage": usage_of(msg), "batch_id": b["id"], "meta": req.meta if req else {}, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
        else:
            row = {"key": key, "result": {"_error": res.result.type}, "usage": {}, "batch_id": b["id"], "meta": req.meta if req else {}, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
        append_jsonl(out_path, row)
        n += 1
    b["collected"] = True
    b["collected_rows"] = n
    b["refused_keys"] = refused
    log.info("collected batch %s: %d rows, %d refused by judge (re-run with fallback)", b["id"], n, len(refused))


async def run_batch(reqs: list[JudgeRequest], state_path: Path, out_path: Path, wait: bool = True, chunk: int = 10000, poll_s: int = 60) -> None:
    """Submit every request whose key is not judged or pending, then poll until all batches are collected."""
    client = anthropic.Anthropic()
    by_key = {r.key: r for r in reqs}
    st = _load_state(state_path)
    for b in st["batches"]:
        if not b.get("collected"):
            _collect(client, b, by_key, out_path)
    _save_state(state_path, st)
    await _rerun_refused(st, by_key, out_path)
    _save_state(state_path, st)
    pending = {k for b in st["batches"] if not b.get("collected") for k in b["keys"]}
    already = judged_keys(out_path) | pending
    todo = [r for r in reqs if r.key not in already]
    log.info("judge batch: %d to submit, %d already judged, %d pending", len(todo), len(already - pending), len(pending))
    for i in range(0, len(todo), chunk):
        part = todo[i : i + chunk]
        b = client.messages.batches.create(requests=[Request(custom_id=cid(r.key), params=MessageCreateParamsNonStreaming(**params(r))) for r in part])
        st["batches"].append({"id": b.id, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "n_requests": len(part), "keys": [r.key for r in part], "collected": False})
        _save_state(state_path, st)
        log.info("submitted batch %s with %d requests", b.id, len(part))
    if not wait:
        print("Batches submitted; re-run to collect.")
        return
    while any(not b.get("collected") for b in st["batches"]):
        for b in st["batches"]:
            if b.get("collected"):
                continue
            info = client.messages.batches.retrieve(b["id"])
            if info.processing_status == "ended":
                _collect(client, b, by_key, out_path)
                _save_state(state_path, st)
            else:
                rc = info.request_counts
                log.info("batch %s: %s (processing=%d succeeded=%d errored=%d)", b["id"], info.processing_status, rc.processing, rc.succeeded, rc.errored)
        if any(not b.get("collected") for b in st["batches"]):
            await asyncio.sleep(poll_s)
    await _rerun_refused(st, by_key, out_path)
    _save_state(state_path, st)


async def _rerun_refused(st: dict, by_key: dict[str, JudgeRequest], out_path: Path) -> None:
    already = judged_keys(out_path)
    keys = [k for b in st["batches"] if b.get("collected") for k in b.get("refused_keys", []) if k not in already and k in by_key]
    if not keys:
        return
    log.info("re-running %d judge-refused requests synchronously with fallback", len(keys))
    await run_sync([by_key[k] for k in keys], out_path, concurrency=4, skip_done=True)


def judge_spend(out_path: Path) -> float:
    total = 0.0
    for r in read_jsonl(out_path):
        u = r.get("usage") or {}
        if u:
            total += usage_cost(u, batch=(r.get("batch_id") not in (None, "sync")))
    return total


def load_judged(out_path: Path) -> dict[str, dict]:
    """{key: row}, first occurrence wins (append-only file; a re-run never overwrites)."""
    out: dict[str, dict] = {}
    for r in read_jsonl(out_path):
        out.setdefault(r["key"], r)
    return out


def result_ok(res: dict | None) -> bool:
    return bool(res) and not any(k in res for k in ("_error", "_parse_error", "_refused_by_judge"))


# ---------------------------------------------------------------- generation with Claude (materials drafting)
async def claude_generate(prompts: list[tuple[str, str, str]], schema: dict | None = None, model: str | None = None, max_tokens: int = 8192, effort: str = "medium", concurrency: int = 4) -> dict[str, Any]:
    """Draft materials with Claude. prompts = [(key, system, user)]. Returns {key: parsed json or text}.
    Uses the judge model by default. Not blind (materials, not scoring)."""
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(concurrency)
    model = model or judge_model()
    out: dict[str, Any] = {}

    async def one(key: str, system: str, user: str):
        async with sem:
            for attempt in range(6):
                try:
                    kw: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}], output_config={"effort": effort})
                    if schema:
                        kw["output_config"]["format"] = {"type": "json_schema", "schema": schema}
                    msg = await create_message(client, **kw)
                    if msg.stop_reason == "refusal":
                        out[key] = {"_refused": True}
                        return
                    text = next((b.text for b in msg.content if b.type == "text"), "")
                    out[key] = json.loads(text) if schema else text
                    return
                except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError, anthropic.APITimeoutError) as e:
                    log.warning("claude_generate retry %d for %s: %s", attempt + 1, key, str(e)[:120])
                    await asyncio.sleep(min(60, 2**attempt + 1))
                except json.JSONDecodeError as e:
                    out[key] = {"_parse_error": str(e)}
                    return
            out[key] = {"_error": "failed repeatedly"}

    await asyncio.gather(*(one(*p) for p in prompts))
    return out
