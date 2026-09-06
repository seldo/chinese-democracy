"""Async Fireworks chat client (OpenAI-compatible) with bounded concurrency, backoff, retry logging,
reasoning-trace capture and optional tool calling. Ported from coding-vulnerabilities/src/fireworks_client.py."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from .config import env

log = logging.getLogger("fireworks")
BASE_URL = "https://api.fireworks.ai/inference/v1"


@dataclass
class ChatResult:
    content: str | None
    reasoning: str | None
    finish_reason: str | None
    usage: dict[str, Any]
    latency_ms: int
    tool_calls: list[dict] | None = None
    message: dict[str, Any] = field(repr=False, default_factory=dict)
    raw: dict[str, Any] = field(repr=False, default_factory=dict)
    error: str | None = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.error is None


def reasoning_tokens(usage: dict, reasoning: str | None) -> int | None:
    for k in ("completion_tokens_details", "output_tokens_details"):
        d = usage.get(k) or {}
        if d.get("reasoning_tokens") is not None:
            return int(d["reasoning_tokens"])
    if reasoning:
        return len(reasoning) // 4  # estimate
    return None


class FireworksClient:
    def __init__(self, retry_log: Path, global_concurrency: int = 8, per_model_concurrency: int = 4, max_attempts: int = 8, timeout: float = 600.0):
        key = env("FIREWORKS_API_KEY")
        if not key:
            raise RuntimeError("FIREWORKS_API_KEY not set")
        self.client = AsyncOpenAI(api_key=key, base_url=BASE_URL, timeout=timeout, max_retries=0)
        self.global_sem = asyncio.Semaphore(global_concurrency)
        self.per_model_concurrency = per_model_concurrency
        self.model_sems: dict[str, asyncio.Semaphore] = {}
        self.max_attempts = max_attempts
        self.retry_log = retry_log
        self.retries = 0

    def _sem(self, model: str) -> asyncio.Semaphore:
        if model not in self.model_sems:
            self.model_sems[model] = asyncio.Semaphore(self.per_model_concurrency)
        return self.model_sems[model]

    def _log_retry(self, model: str, attempt: int, reason: str, delay: float) -> None:
        self.retries += 1
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} model={model} attempt={attempt} delay={delay:.1f}s reason={reason}\n"
        self.retry_log.parent.mkdir(parents=True, exist_ok=True)
        with self.retry_log.open("a") as f:
            f.write(line)
        log.warning("retry %s", line.strip())

    async def chat(self, model: str, messages: list[dict], *, max_tokens: int, temperature: float, seed: int | None = None, tools: list[dict] | None = None, extra: dict | None = None) -> ChatResult:
        kwargs: dict[str, Any] = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        if seed is not None:
            kwargs["seed"] = seed
        if tools:
            kwargs["tools"] = tools
        if extra:
            kwargs.update(extra)
        async with self._sem(model), self.global_sem:  # per-model cap first so waiting tasks never hold a global slot
            last_err = None
            for attempt in range(1, self.max_attempts + 1):
                t0 = time.perf_counter()
                try:
                    resp = await self.client.chat.completions.create(**kwargs)
                    latency = int((time.perf_counter() - t0) * 1000)
                    d = resp.model_dump()
                    choice = d["choices"][0]
                    msg = choice["message"]
                    reasoning = msg.get("reasoning_content") or msg.get("reasoning")
                    return ChatResult(content=msg.get("content"), reasoning=reasoning, finish_reason=choice.get("finish_reason"), usage=d.get("usage") or {}, latency_ms=latency, tool_calls=msg.get("tool_calls"), message=msg, raw=d, attempts=attempt)
                except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                    last_err = f"{type(e).__name__}: {str(e)[:200]}"
                except APIStatusError as e:
                    last_err = f"HTTP {e.status_code}: {str(e)[:300]}"
                    if e.status_code < 500 and e.status_code != 429:
                        return ChatResult(content=None, reasoning=None, finish_reason="error", usage={}, latency_ms=int((time.perf_counter() - t0) * 1000), error=last_err, attempts=attempt)
                except Exception as e:  # unknown; retryable but bounded
                    last_err = f"{type(e).__name__}: {str(e)[:200]}"
                delay = min(60.0, (2**attempt) * 0.5) + random.uniform(0, 1.0)
                self._log_retry(model, attempt, last_err or "unknown", delay)
                await asyncio.sleep(delay)
            return ChatResult(content=None, reasoning=None, finish_reason="error", usage={}, latency_ms=0, error=f"gave up after {self.max_attempts}: {last_err}", attempts=self.max_attempts)
