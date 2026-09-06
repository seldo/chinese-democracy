"""Generic one-shot generation runner for summarization-recall, copyedit-drift and corpus-briefing.

A Job is (model, item_id, sample_idx, messages, max_tokens, meta). Rows are appended to
<raw_dir>/<model_key>.jsonl (append-only). Resume skips (item_id, sample_idx) tuples already present
with a non-error finish_reason. Readers deduplicate on that tuple and keep the first occurrence.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Model, append_jsonl, read_jsonl
from .fireworks import FireworksClient, reasoning_tokens

log = logging.getLogger("gen")
SEED_BASE = 1000


@dataclass
class Job:
    model: Model
    item_id: str
    sample_idx: int
    messages: list[dict]
    max_tokens: int
    meta: dict = field(default_factory=dict)


def raw_path(raw_dir: Path, model: Model) -> Path:
    return raw_dir / f"{model.key}.jsonl"


def load_raw(raw_dir: Path, model: Model, include_errors: bool = False) -> list[dict]:
    """Deduplicated rows for one model (first occurrence per (item_id, sample_idx))."""
    seen: set[tuple[str, int]] = set()
    out = []
    for r in read_jsonl(raw_path(raw_dir, model)):
        if not include_errors and r.get("finish_reason") == "error":
            continue
        k = (r["item_id"], r["sample_idx"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def done_keys(raw_dir: Path, model: Model) -> set[tuple[str, int]]:
    return {(r["item_id"], r["sample_idx"]) for r in load_raw(raw_dir, model)}


def new_run_id(scope: str) -> str:
    return f"{scope}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"


async def run_jobs(jobs: list[Job], raw_dir: Path, run_id: str, client: FireworksClient, temperature: float = 0.6, progress_every: int = 25) -> dict[str, dict]:
    models = {j.model.key: j.model for j in jobs}
    stats = {k: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0, "errors": 0, "length_truncated": 0} for k in models}
    done = {k: done_keys(raw_dir, m) for k, m in models.items()}
    per_model: dict[str, list[Job]] = {k: [] for k in models}
    for j in jobs:
        if (j.item_id, j.sample_idx) not in done[j.model.key]:
            per_model[j.model.key].append(j)
    todo: list[Job] = []  # interleave across models so the global concurrency budget is spread
    for i in range(max((len(v) for v in per_model.values()), default=0)):
        for v in per_model.values():
            if i < len(v):
                todo.append(v[i])
    log.info("%d generations to run (%d already present)", len(todo), len(jobs) - len(todo))
    if not todo:
        return stats
    lock = asyncio.Lock()
    prog = {"n": 0, "t0": time.time()}

    async def one(j: Job):
        r = await client.chat(j.model.fireworks_id, j.messages, max_tokens=j.max_tokens, temperature=temperature, seed=SEED_BASE + j.sample_idx)
        usage = r.usage or {}
        pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        rt = reasoning_tokens(usage, r.reasoning)
        row = {
            "run_id": run_id, "model_key": j.model.key, "model_id": j.model.fireworks_id, "item_id": j.item_id, "sample_idx": j.sample_idx, "seed": SEED_BASE + j.sample_idx,
            "messages": j.messages, "reasoning": r.reasoning, "response": r.content, "finish_reason": r.finish_reason, "usage": usage, "reasoning_tokens": rt,
            "latency_ms": r.latency_ms, "timestamp": datetime.now(timezone.utc).isoformat(), "error": r.error, "cost_usd": j.model.cost(pt, ct), "meta": j.meta,
        }
        async with lock:
            append_jsonl(raw_path(raw_dir, j.model), row)
            st = stats[j.model.key]
            st["calls"] += 1
            st["prompt_tokens"] += pt
            st["completion_tokens"] += ct
            st["reasoning_tokens"] += rt or 0
            st["cost_usd"] += row["cost_usd"]
            st["errors"] += bool(r.error)
            st["length_truncated"] += r.finish_reason == "length"
            prog["n"] += 1
            if prog["n"] % progress_every == 0 or prog["n"] == len(todo):
                spent = sum(x["cost_usd"] for x in stats.values())
                log.info("%d/%d done, %.0fs elapsed, $%.2f this run, %d retries", prog["n"], len(todo), time.time() - prog["t0"], spent, client.retries)

    await asyncio.gather(*(one(j) for j in todo))
    return stats


def print_stats(stats: dict[str, dict]) -> None:
    print(f"\n{'model':26s} {'calls':>6s} {'errors':>6s} {'len_trunc':>9s} {'in_tok/call':>11s} {'out_tok/call':>12s} {'reas_tok/call':>13s} {'$/call':>8s} {'$ this run':>10s}")
    for k, s in stats.items():
        n = max(s["calls"], 1)
        print(f"{k:26s} {s['calls']:6d} {s['errors']:6d} {s['length_truncated']:9d} {s['prompt_tokens']/n:11.0f} {s['completion_tokens']/n:12.0f} {s['reasoning_tokens']/n:13.0f} {s['cost_usd']/n:8.4f} {s['cost_usd']:10.2f}")


def spend(raw_dir: Path, models: list[Model]) -> dict[str, float]:
    """Fireworks spend per model from recorded usage, including errors and duplicates (money was spent)."""
    return {m.key: sum(r.get("cost_usd", 0.0) for r in read_jsonl(raw_path(raw_dir, m))) for m in models}


def projection(raw_dir: Path, models: list[Model], full_calls_per_model: int) -> tuple[float, dict[str, dict]]:
    out, total = {}, 0.0
    for m in models:
        rows = load_raw(raw_dir, m)
        if not rows:
            continue
        per_call = sum(r["cost_usd"] for r in rows) / len(rows)
        remaining = max(0, full_calls_per_model - len(rows))
        out[m.key] = {"rows": len(rows), "per_call": per_call, "remaining": remaining, "projected_remaining_usd": per_call * remaining, "projected_full_usd": per_call * full_calls_per_model}
        total += per_call * remaining
    return total, out


def print_projection(raw_dir: Path, models: list[Model], full_calls_per_model: int, threshold: float) -> float:
    total, per = projection(raw_dir, models, full_calls_per_model)
    spent = sum(spend(raw_dir, models).values())
    print(f"\n{'model':26s} {'rows':>6s} {'$/call':>8s} {'remaining':>10s} {'$ remaining':>12s} {'$ full run':>11s}")
    for k, v in per.items():
        print(f"{k:26s} {v['rows']:6d} {v['per_call']:8.4f} {v['remaining']:10d} {v['projected_remaining_usd']:12.2f} {v['projected_full_usd']:11.2f}")
    print(f"\nFireworks spent so far on this test: ${spent:.2f}. Projected remaining: ${total:.2f}. Approval threshold: ${threshold:.0f}.")
    return total


def is_refusal_like(text: str | None) -> bool:
    """Cheap keyword screen for outputs that decline the task; the judge makes the final call."""
    if not text:
        return False
    t = text.strip().lower()[:400]
    cues = ("i can't", "i cannot", "i can’t", "i'm unable", "i am unable", "i won't", "i will not", "i'm not able", "i am not able", "as an ai", "i'm sorry, but", "i apologize, but", "not able to help with", "cannot assist", "can't assist", "unable to assist")
    return any(c in t for c in cues) and len(text) < 1200
