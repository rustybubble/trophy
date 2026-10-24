"""Grounded coach tips (interfaces-v1 §19): Claude writes 2-3 tips from the stats alone; each tip is
checked by the grounding validator; a rejected tip is replaced by a template tip (labelled "template")."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from . import grounding
from .llm import ClaudeJSON

COACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tips": {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "one or two sentences, second person, using only the stats",
                    },
                    "facts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "stat names the tip relies on",
                    },
                },
                "required": ["text", "facts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tips"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are a friendly coach for a pickup game. Write 2 or 3 short tips for the given side using ONLY the "
    "numbers and names in the stats table. Every number you write must appear in the stats exactly; name no "
    "people, teams, injuries, seasons or history beyond the table; no gendered pronouns. Second person, plain text."
)


class Tip(BaseModel):
    text: str
    facts: list[str]
    source: str  # "claude" | "template"
    violations: list[dict[str, str]] = []


class CoachResult(BaseModel):
    tips: list[Tip]
    validated: bool
    claude_ms: float


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def template_tips(side: str, stats: dict[str, Any], n: int) -> list[Tip]:
    """Grounded by construction: each tip restates one stat for the side."""
    out = []
    for name, value in list(stats.items())[:n]:
        pretty = name.replace("_", " ")
        out.append(
            Tip(
                text=f"{side}: your {pretty} is {_fmt(value)}. Keep an eye on it next game.",
                facts=[name],
                source="template",
            )
        )
    while len(out) < n:
        out.append(Tip(text=f"{side}: no more stats were detected for this game.", facts=[], source="template"))
    return out


async def coach(
    llm: ClaudeJSON, *, sport: str, side: str, stats: dict[str, Any], sides: list[str] | None = None
) -> CoachResult:
    facts = grounding.build_facts(stats, side=side, sides=sides)
    table = "\n".join(f"- {k}: {_fmt(v)}" for k, v in stats.items())
    user = f"Sport: {sport}\nSide: {side}\nStats (auto-detected):\n{table}"
    data, ms = await llm.complete(system=SYSTEM, user=user, schema=COACH_SCHEMA, label="coach")
    tips: list[Tip] = []
    fallbacks = iter(template_tips(side, stats, 3))
    for raw in data.get("tips", [])[:3]:
        text = str(raw.get("text", ""))
        facts_used = [str(f) for f in raw.get("facts", []) if str(f) in stats]
        verdict = grounding.check(text, facts)
        if verdict["ok"]:
            tips.append(Tip(text=text.strip(), facts=facts_used, source="claude"))
        else:
            t = next(fallbacks)
            tips.append(t.model_copy(update={"violations": verdict["violations"]}))
    while len(tips) < 2:
        tips.append(next(fallbacks))
    return CoachResult(tips=tips, validated=all(t.source == "claude" for t in tips), claude_ms=ms)
