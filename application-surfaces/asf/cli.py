"""CLI for application-surfaces: ./run build-topics | smoke | dry | full | judge | analyze | spend"""
from __future__ import annotations

import argparse
import asyncio
import logging


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="run")
    p.add_argument("--models", type=lambda v: [x for x in v.split(",") if x])
    p.add_argument("--no-trace", action="store_true")
    p.add_argument("--concurrency", type=int, default=12)
    p.add_argument("--per-model", type=int, default=3)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-topics")
    b.add_argument("--force", action="store_true")
    sub.add_parser("smoke")
    sub.add_parser("dry")
    f = sub.add_parser("full")
    f.add_argument("--yes", action="store_true")
    j = sub.add_parser("judge")
    j.add_argument("--no-wait", action="store_true")
    j.add_argument("--yes", action="store_true")
    j.add_argument("--sync", type=int, default=0, help="judge synchronously with this concurrency instead of the Batches API (2x price)")
    sub.add_parser("analyze")
    sub.add_parser("spend")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for n in ("httpx", "httpx2", "alembic", "phoenix", "openai", "anthropic", "urllib3", "charset_normalizer"):
        logging.getLogger(n).setLevel(logging.WARNING)
    from wcommon.tracing import setup_tracing

    setup_tracing(not args.no_trace, project="application-surfaces")
    if args.cmd == "build-topics":
        from . import materials

        asyncio.run(materials.cmd_build_topics(force=args.force))
    else:
        from . import pipeline

        pipeline.dispatch(args)


if __name__ == "__main__":
    main()
