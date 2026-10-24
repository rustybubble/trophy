"""`trophy-rules check-pack sports/<sport>/rules.yaml`: resolve every `rule_ref` and print a table (read-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .rule_ref import resolve
from .search import RuleStore


def load_pack(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text("utf8"))
    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"{path} is not a rule pack (no `rules:`)")
    return data


async def check(store: RuleStore, pack: dict[str, Any], *, min_score: float) -> list[dict[str, Any]]:
    sport = str(pack.get("sport", ""))
    rows = []
    for rule in pack.get("rules", []):
        ref = rule.get("rule_ref")
        row: dict[str, Any] = {"rule": rule.get("id"), "rule_ref": ref}
        if not ref:
            row.update(status="no rule_ref")
            rows.append(row)
            continue
        exact = await resolve(store, sport=sport, rule_ref=ref, min_score=min_score)
        if exact is None:
            text = " ".join(str(rule.get(k, "")) for k in ("name", "text", "speech") if rule.get(k))
            exact = await resolve(store, sport=sport, text=text, min_score=min_score)
        if exact is None:
            row.update(status="unresolved")
        else:
            row.update(status=exact.how, clause=exact.rule_id, title=exact.title, score=round(exact.score, 3))
        rows.append(row)
    return rows


def table(rows: list[dict[str, Any]]) -> str:
    out = ["| rule | rule_ref | clause | title | score | how |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            f"| {r.get('rule')} | {r.get('rule_ref') or '-'} | {r.get('clause') or '-'} | {r.get('title') or '-'} | "
            f"{r.get('score') if r.get('score') is not None else '-'} | {r.get('status')} |"
        )
    return "\n".join(out)
