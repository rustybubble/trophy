"""`GET /clauses`: the top-k official clauses as Markdown, for the Droid workspace's `context/clauses.md` (§18)."""

from __future__ import annotations

from .models import RuleHit


def render_markdown(hits: list[RuleHit], *, sport: str, q: str, moss_ms: float) -> str:
    lines = [
        f"# Official clauses: {sport.replace('_', ' ')}",
        "",
        f"Retrieved by Moss for: _{q}_ ({len(hits)} clauses, {moss_ms:.0f} ms). Cite a clause by its id, "
        'e.g. `rule_ref: "ITTF 2.6.2"`. Quote at most 25 words.',
        "",
    ]
    for h in hits:
        lines += [f"## [{h.rule_id}] {h.title}".rstrip(), "", h.text, "", f"Source: {h.source} <{h.url}>", ""]
    if not hits:
        lines += ["_No clause matched._", ""]
    return "\n".join(lines)
