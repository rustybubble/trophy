"""`trophy-rules`: serve | index build|refresh|status | dataset export | eval | check-pack. Exit 3 without keys."""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
from pathlib import Path

from . import check_pack as CP
from . import evalrun, indexing
from .app import boot
from .clients import apify_client, moss_client
from .config import ROOT, Settings
from .errors import ConfigError
from .pipeline import AskPipeline
from .search import RuleStore


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trophy-rules", description="Trophy rules service tools (ask the ref)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the API (8100 + PORT_OFFSET)")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--host", default="127.0.0.1")

    idx = sub.add_parser("index", help="the Moss index").add_subparsers(dest="idx", required=True)
    for name, help_ in (("build", "create the index from JSONL files"), ("refresh", "upsert JSONL files into it")):
        b = idx.add_parser(name, help=help_)
        b.add_argument(
            "--from", dest="paths", nargs="*", default=None, help="JSONL globs (default data/local/rulebooks/*.jsonl)"
        )
    idx.add_parser("status", help="doc count, model, status and the local load time")

    d = sub.add_parser("dataset", help="the actor's dataset").add_subparsers(dest="ds", required=True)
    e = d.add_parser(
        "export", help="-> data/local/rulebooks/<sport>.jsonl from a local `apify run` (default) or the platform"
    )
    e.add_argument("--sport", action="append")
    e.add_argument("--storage", type=Path, default=None, help="a local actor storage/datasets/default dir")
    e.add_argument("--actor", default=None, help="pull the last SUCCEEDED run of this actor (APIFY_TOKEN)")
    e.add_argument("--dataset", default=None, help="pull this dataset id (APIFY_TOKEN)")

    ev = sub.add_parser("eval", help="run evals/ask/<sport>.jsonl through /ask and summarise")
    ev.add_argument("--sport", required=True)
    ev.add_argument("--file", type=Path, default=None)

    c = sub.add_parser("check-pack", help="resolve every rule_ref in a rule pack (read-only)")
    c.add_argument("pack", type=Path)
    return p


def _paths(patterns: list[str] | None, settings: Settings) -> list[Path]:
    pats = patterns or [str(settings.rulebooks_dir / "*.jsonl")]
    out: list[Path] = []
    for pat in pats:
        out.extend(Path(x) for x in sorted(glob.glob(pat)))
    return out


async def _index_cmd(a, settings: Settings) -> int:
    settings.require_keys()
    store = RuleStore(moss_client(settings), index=settings.moss_index, model_id=settings.moss_model)
    if a.idx in ("build", "refresh"):
        paths = _paths(a.paths, settings)
        docs = indexing.read_many(paths)
        if not docs:
            print(
                f"no rule documents in {paths or settings.rulebooks_dir} (run `trophy-rules dataset export` first)",
                file=sys.stderr,
            )
            return 2
        res = await store.build(docs, refresh=a.idx == "refresh")
        by_sport: dict[str, int] = {}
        for d in docs:
            by_sport[d.sport] = by_sport.get(d.sport, 0) + 1
        print(f"{store.index}: {res['how']} with {len(docs)} docs ({settings.moss_model}); per sport: {by_sport}")
        print(f"job: {res['job_id']}")
        return 0
    info = await store.status()
    ms = await store.load()
    print(json.dumps({**info, "loaded_ms": round(ms, 1)}, indent=1, default=str))
    return 0


def _export_cmd(a, settings: Settings) -> int:
    if a.actor or a.dataset:
        items = indexing.pull_dataset(
            apify_client(settings), actor=a.actor or settings.apify_actor, dataset_id=a.dataset
        )
        where = a.dataset or a.actor or settings.apify_actor
    else:
        storage = a.storage or indexing.ACTOR_STORAGE
        items = indexing.read_actor_storage(storage)
        where = str(storage)
    if not items:
        print(f"no dataset items found in {where} (run the actor first: `npx apify-cli run --purge`)", file=sys.stderr)
        return 2
    counts = indexing.export_by_sport(items, settings.rulebooks_dir, a.sport)
    for sport, n in counts.items():
        print(f"{settings.rulebooks_dir.relative_to(ROOT)}/{sport}.jsonl: {n} rules")
    return 0


async def _eval_cmd(a, settings: Settings) -> int:
    store, llm = await boot(settings)
    report = await evalrun.run(AskPipeline(store, llm, settings), a.sport, path=a.file)
    cases = [{"question": c["question"], "expected_rule_ids": c["expected_rule_ids"]} for c in report["cases"]]
    print(evalrun.table(cases, [evalrun.AskOut.model_validate(c["result"]) for c in report["cases"]]))
    print()
    print(json.dumps(report["summary"], indent=1))
    print(f"written: {report['path']}")
    return 0


async def _check_pack_cmd(a, settings: Settings) -> int:
    settings.require_keys()
    store = RuleStore(moss_client(settings), index=settings.moss_index, model_id=settings.moss_model)
    await store.load()
    rows = await CP.check(store, CP.load_pack(a.pack), min_score=settings.ask_min_score)
    print(CP.table(rows))
    unresolved = [r for r in rows if r["status"] in ("unresolved", "no rule_ref")]
    print(
        f"\n{len(rows) - len(unresolved)}/{len(rows)} resolved"
        + (f"; unresolved: {[r['rule'] for r in unresolved]}" if unresolved else "")
    )
    return 1 if unresolved else 0


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    settings = Settings.from_env()
    try:
        if a.cmd == "serve":
            settings.require_keys()
            import uvicorn

            uvicorn.run("rules.app:app", host=a.host, port=a.port or settings.port, log_level="warning")
            return 0
        if a.cmd == "index":
            return asyncio.run(_index_cmd(a, settings))
        if a.cmd == "dataset":
            return _export_cmd(a, settings)
        if a.cmd == "eval":
            return asyncio.run(_eval_cmd(a, settings))
        if a.cmd == "check-pack":
            return asyncio.run(_check_pack_cmd(a, settings))
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
