"""Rule documents in and out: the actor's local run or platform dataset -> data/local/rulebooks/*.jsonl -> Moss."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .config import ROOT
from .models import RuleDoc

ACTOR_STORAGE = ROOT / "actors" / "rulebook-scraper" / "storage" / "datasets" / "default"


def docs_from_items(items: Iterable[dict]) -> list[RuleDoc]:
    out = []
    for it in items:
        if not isinstance(it, dict) or not it.get("rule_id") or not it.get("text") or not it.get("sport"):
            continue
        out.append(RuleDoc.model_validate({k: v for k, v in it.items() if k in RuleDoc.model_fields}))
    return out


def read_jsonl(path: Path) -> list[RuleDoc]:
    text = path.read_text("utf8")
    if path.suffix == ".json":
        data = json.loads(text)
        return docs_from_items(data if isinstance(data, list) else [data])
    return docs_from_items(json.loads(line) for line in text.splitlines() if line.strip())


def read_many(paths: Iterable[Path]) -> list[RuleDoc]:
    docs: list[RuleDoc] = []
    for p in paths:
        docs.extend(read_jsonl(p))
    seen: set[str] = set()
    uniq = []
    for d in docs:
        if d.rule_id not in seen:
            seen.add(d.rule_id)
            uniq.append(d)
    return uniq


def read_actor_storage(storage: Path = ACTOR_STORAGE) -> list[dict]:
    """Items from a local `apify run` (one JSON file per item under storage/datasets/default)."""
    items = []
    for p in sorted(storage.glob("*.json")):
        if p.name.startswith("__"):
            continue
        data = json.loads(p.read_text("utf8"))
        items.extend(data if isinstance(data, list) else [data])
    return items


def pull_dataset(apify, *, actor: str | None, dataset_id: str | None) -> list[dict]:
    """The actor's last successful run's default dataset (or a dataset id) via apify-client 3.x."""
    ds = apify.dataset(dataset_id) if dataset_id else apify.actor(actor).last_run(status="SUCCEEDED").dataset()
    return list(ds.iterate_items(clean=True))


def export_by_sport(items: Iterable[dict], out_dir: Path, sports: list[str] | None = None) -> dict[str, int]:
    """Write data/local/rulebooks/<sport>.jsonl (one item per line, deduplicated by rule_id); returns counts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_sport: dict[str, dict[str, dict]] = {}
    for it in items:
        sport = it.get("sport")
        if not sport or (sports and sport not in sports) or not it.get("rule_id"):
            continue
        by_sport.setdefault(sport, {})[it["rule_id"]] = it
    counts = {}
    for sport, rows in sorted(by_sport.items()):
        p = out_dir / f"{sport}.jsonl"
        with p.open("w", encoding="utf8") as f:
            for row in rows.values():
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        counts[sport] = len(rows)
    return counts
