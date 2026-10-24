"""Rule documents in, Moss indexes out: from the actor's Apify dataset or a local JSONL export."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .search import MossStore, RuleDoc


def docs_from_items(items: Iterable[dict]) -> list[RuleDoc]:
    out = []
    for it in items:
        if not it.get("rule_id") or not it.get("text") or not it.get("sport"):
            continue
        out.append(
            RuleDoc(
                sport=it["sport"],
                rule_id=str(it["rule_id"]),
                title=it.get("title") or "",
                text=it["text"],
                url=it.get("url") or "",
            )
        )
    return out


def read_jsonl(path: Path) -> list[RuleDoc]:
    text = path.read_text("utf8")
    if path.suffix == ".json":
        return docs_from_items(json.loads(text))
    return docs_from_items(json.loads(line) for line in text.splitlines() if line.strip())


def pull_dataset(apify, *, actor: str | None, dataset_id: str | None) -> list[RuleDoc]:
    """The actor's last successful run's default dataset (or a dataset id) via apify-client 3.x."""
    if dataset_id:
        ds = apify.dataset(dataset_id)
    else:
        run = apify.actor(actor).last_run(status="SUCCEEDED")  # apify_client._literals.ActorJobStatus
        ds = run.dataset()
    return docs_from_items(ds.iterate_items(clean=True))


async def build(store: MossStore, docs: list[RuleDoc], sports: list[str] | None = None) -> dict[str, int]:
    """One Moss index per sport (`rules-<sport>`); returns the doc count per sport."""
    wanted = set(sports or {d.sport for d in docs})
    counts = {}
    for sport in sorted(wanted):
        counts[sport] = await store.build_rules(sport, docs)
    return counts
