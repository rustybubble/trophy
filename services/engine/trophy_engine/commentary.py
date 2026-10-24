"""Broadcast commentary per moment (interfaces-v1 §19): a play-by-play line and a colour line, written by Claude
from the moment's facts and checked by a grounding validator (every number and every named side in a line must
appear in the facts). A rejected line is replaced by a template line and marked ``source: template`` (the spec's
fallback). The Claude writer REQUIRES ``ANTHROPIC_API_KEY``; the template writer never pretends to be Claude.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def facts_for(moment: dict[str, Any], team_names: dict[str, str]) -> dict[str, Any]:
    team = moment.get("team_id")
    return {
        "kind": moment["kind"],
        "label": moment["label"],
        "team": team_names.get(team or "", team) if team else None,
        "score_after": moment.get("score_after", ""),
        "rally_no": moment.get("rally_no"),
        "shots": next((int(t.split(":")[1]) for t in moment.get("tags", []) if t.startswith("shots:")), None),
        "reasons": [r for r in moment.get("reasons", []) if "crowd audio" not in r],
        "names": sorted(set(team_names.values())),
    }


def grounded(line: str, facts: dict[str, Any]) -> bool:
    """Every number in the line must be a fact number; every team name mentioned must be the moment's team."""
    allowed_numbers = set(NUM_RE.findall(json.dumps(facts, ensure_ascii=False)))
    for n in NUM_RE.findall(line):
        if n not in allowed_numbers:
            return False
    for name in facts.get("names", []):
        other_team = name and name.lower() in line.lower() and name != facts.get("team")
        if other_team and facts["kind"] not in ("challenge", "house_rule"):
            return False
    return bool(line.strip()) and len(line) <= 160


def template_lines(facts: dict[str, Any]) -> dict[str, str]:
    team = facts.get("team") or "the player"
    score = facts.get("score_after", "")
    k = facts["kind"]
    if k == "point":
        pbp = f"Point, {team}. {score}."
        colour = (
            "A long rally finally ends." if any("long rally" in r for r in facts["reasons"]) else f"{team} takes it."
        )
    elif k == "serve_fault":
        pbp = f"Fault on the serve. {score}."
        colour = "The toss has to come up straight and high."
    elif k == "edge":
        pbp = f"Edge ball. {score}."
        colour = "Nothing you can do about an edge."
    elif k == "basket":
        pbp = f"Basket, {team}. {score}."
        colour = "Good look."
    else:
        pbp = facts.get("label", "")
        colour = ""
    return {"pbp": pbp, "colour": colour}


@dataclass
class TemplateCommentator:
    source: str = "template"

    def lines(self, facts: dict[str, Any]) -> dict[str, str]:
        return template_lines(facts)


@dataclass
class ClaudeCommentator:
    api_key: str
    model: str = "claude-opus-5-5"
    http_client: Any = None  # httpx2.Client
    source: str = "claude"

    def lines(self, facts: dict[str, Any]) -> dict[str, str]:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key, http_client=self.http_client, max_retries=0, timeout=6.0)
        schema = {
            "type": "object",
            "properties": {"pbp": {"type": "string"}, "colour": {"type": "string"}},
            "required": ["pbp", "colour"],
            "additionalProperties": False,
        }
        msg = client.messages.create(
            model=self.model,
            max_tokens=300,
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "low"},
            system=(
                "You write two short broadcast lines for a pickup-game moment: 'pbp' (play-by-play, <= 15 words) and "
                "'colour' (<= 15 words). Use only the facts given: no names, numbers or events that are not in them."
            ),
            messages=[{"role": "user", "content": f"FACTS: {json.dumps(facts)}"}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = json.loads(text)
        return {"pbp": str(data.get("pbp", "")), "colour": str(data.get("colour", ""))}


def commentary_rows(moment: dict[str, Any], team_names: dict[str, str], writer, now_ms: float) -> list[dict[str, Any]]:
    """Two rows per moment. A line that fails grounding (or a writer error) becomes the template line."""
    facts = facts_for(moment, team_names)
    try:
        lines = writer.lines(facts)
        source = writer.source
    except Exception:  # noqa: BLE001 - the writer is a network call; commentary must never block the game
        lines, source = {}, "template"
    tpl = template_lines(facts)
    rows = []
    for voice in ("pbp", "colour"):
        text = lines.get(voice, "")
        ok = bool(text) and grounded(text, facts)
        rows.append(
            {
                "moment_id": moment["moment_id"],
                "game_id": moment["game_id"],
                "voice": voice,
                "text": text if ok else tpl[voice],
                "facts": facts,
                "validated": ok,
                "source": source if ok else "template",
                "created_at_ms": now_ms,
            }
        )
    return rows
