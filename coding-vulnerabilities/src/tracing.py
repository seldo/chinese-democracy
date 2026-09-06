"""Optional OpenInference -> Phoenix tracing. Never fails the run if Phoenix is down."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("tracing")


def setup_tracing(enabled: bool, project: str = "context-eval") -> bool:
    if not enabled:
        return False
    try:
        # Silence exporter connection noise if Phoenix isn't running.
        logging.getLogger("opentelemetry.exporter.otlp").setLevel(logging.CRITICAL)
        logging.getLogger("opentelemetry.sdk.trace.export").setLevel(logging.CRITICAL)
        logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)
        from phoenix.otel import register

        endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
        tracer_provider = register(project_name=project, endpoint=f"{endpoint}/v1/traces", batch=True, set_global_tracer_provider=True, verbose=False)
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor

            OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        except Exception as e:  # pragma: no cover
            log.warning("openai instrumentor unavailable: %s", e)
        try:
            from openinference.instrumentation.anthropic import AnthropicInstrumentor

            AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
        except Exception as e:  # pragma: no cover
            log.warning("anthropic instrumentor unavailable: %s", e)
        log.info("tracing enabled -> %s (project %s)", endpoint, project)
        return True
    except Exception as e:
        log.warning("tracing disabled: %s", e)
        return False
