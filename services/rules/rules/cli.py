"""`rules` CLI: `rules index build --sport table_tennis`, `rules index load-local <path.jsonl>`, `rules serve`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import indexing
from .clients import apify_client, moss_client
from .config import Settings
from .errors import ConfigError
from .search import MossStore


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rules", description="Trophy rules service tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    idx = sub.add_parser("index", help="build Moss indexes").add_subparsers(dest="idx", required=True)
    b = idx.add_parser("build", help="pull the Apify actor's dataset (APIFY_TOKEN) and build one Moss index per sport")
    b.add_argument(
        "--sport", action="append", help="limit to a sport (repeatable); default: every sport in the dataset"
    )
    b.add_argument("--actor", default=None, help="actor id/name (default APIFY_RULEBOOK_ACTOR)")
    b.add_argument("--dataset", default=None, help="a dataset id instead of the actor's last run")
    b.add_argument("--local", type=Path, default=None, help="read a local JSON/JSONL export instead of Apify")
    ll = idx.add_parser("load-local", help="build Moss indexes from a local JSONL export of the actor's dataset")
    ll.add_argument("path", type=Path)
    ll.add_argument("--sport", action="append")
    s = sub.add_parser("serve", help="run the API")
    s.add_argument("--port", type=int, default=None)
    return p


async def _build(settings: Settings, docs, sports) -> dict[str, int]:
    store = MossStore(moss_client(settings), model_id=settings.moss_model)
    return await indexing.build(store, docs, sports)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    a = _parser().parse_args(argv)
    settings = Settings.from_env()
    try:
        if a.cmd == "index":
            if a.idx == "load-local" or a.local:
                path = a.path if a.idx == "load-local" else a.local
                docs = indexing.read_jsonl(path)
            else:
                docs = indexing.pull_dataset(
                    apify_client(settings), actor=a.actor or settings.apify_actor, dataset_id=a.dataset
                )
            if not docs:
                print("no rule documents found", file=sys.stderr)
                return 2
            counts = asyncio.run(_build(settings, docs, a.sport))
            for sport, n in counts.items():
                print(f"rules-{sport}: {n} clauses indexed ({settings.moss_model})")
            return 0
        if a.cmd == "serve":
            import uvicorn

            uvicorn.run("rules.app:app", host="127.0.0.1", port=a.port or settings.port, log_level="info")
            return 0
    except ConfigError as e:
        print(f"not configured: {e}", file=sys.stderr)
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
