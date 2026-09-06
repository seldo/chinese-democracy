"""CLI for live-research-agent: ./run dry | full [--runs N --yes] | judge | analyze | freeze | spend"""
from __future__ import annotations

import argparse
import logging


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="run")
    p.add_argument("--models", type=lambda v: [x for x in v.split(",") if x])
    p.add_argument("--no-trace", action="store_true")
    p.add_argument("--concurrency", type=int, default=8, help="concurrent agent runs")
    p.add_argument("--per-model", type=int, default=2)
    p.add_argument("--serp-per-minute", type=float, default=12.0)
    p.add_argument("--runs", type=int, default=5, help="runs per (model, question) for `full`")
    p.add_argument("--serp-budget", type=int, default=None, help="hard ceiling on live SerpApi searches in this process; runs stop starting once reached")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dry")
    f = sub.add_parser("full")
    f.add_argument("--yes", action="store_true")
    j = sub.add_parser("judge")
    j.add_argument("--no-wait", action="store_true")
    sub.add_parser("analyze")
    sub.add_parser("freeze")
    sub.add_parser("spend")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for n in ("httpx", "httpx2", "alembic", "phoenix", "openai", "anthropic", "trafilatura", "urllib3", "charset_normalizer"):
        logging.getLogger(n).setLevel(logging.WARNING)
    from wcommon.tracing import setup_tracing

    setup_tracing(not args.no_trace, project="live-research-agent")
    from . import pipeline

    pipeline.dispatch(args)


if __name__ == "__main__":
    main()
