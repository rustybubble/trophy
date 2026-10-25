"""Question -> route. Deterministic phrases first (no model, ~0 ms), then the fast Claude model for the rest.

The route names a session check from the catalog, a rule-pack question, the score, an explanation of the last call,
or nothing. Time arguments are resolved from the game context the phone sends (the newest call's time), otherwise
left as `ref: last` for the engine to resolve over its track.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .catalog import CHECKS, catalog_text
from .llm import JSONCompleter

RECENT_CALL_S = 90.0  # "that" means the newest call only if it is this fresh


@dataclass
class Route:
    intent: str  # check | rule | score | explain | none
    check: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    source: str = "regex"  # regex | claude
    hint: str | None = None  # suggested signature for a check that does not exist yet
    reason: str = ""


def clean(s: str) -> str:
    s = re.sub(r"^(hey |ok |okay )?(trophy|ref|referee)[,.!]?\s*", "", s.strip(), flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


_RULES: list[tuple[str, str, str | None]] = [
    # (regex over the lower-cased question, intent, check)
    (r"\b(what'?s|what is|whats) the (score|count)\b|^score\??$|\bwho'?s (winning|ahead|serving)\b", "score", None),
    (
        r"\bwhy\b.*\b(call|out|in|fault|point|that)\b|\bexplain\b|\bwhat was that call\b|\bwhat did you call\b",
        "explain",
        None,
    ),
    (r"\bedge\b", "check", "edge_hit"),
    (r"\b(touch|clip|hit|graze|catch)\w*\s+the\s+net\b|\bnet ball\b|\bwas (that|it) (a )?net\b", "check", "net_touch"),
    (r"\b(twice|two bounces|double[- ]bounce|bounced two)\b", "check", "double_bounce"),
    (
        r"\b(serve|toss)\b.*\b(legal|ok|okay|good|fair|high|low|vertical|angle|straight)\b|\bwas (that|the) serve\b",
        "check",
        "serve_toss",
    ),
    (r"\b(which|whose) side\b|\bland(ed)? on (my|their|our|his|her|a|b|team a|team b)\b", "check", "bounce_side"),
    (r"\b(how long|how many (shots|hits)|longest|fastest|speed|how fast)\b", "check", "rally_summary"),
    (
        r"\b(was|is|did) (that|it|the ball|that ball)( go| land)? (out|in|good|long|wide|on the line|on the table)\b|"
        r"\bin or out\b|\bout or in\b|^(out|in)\??$|\b(was|is) (that|it) (out|in)\b",
        "check",
        "in_out",
    ),
]

ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["check", "rule", "score", "explain", "none"]},
        "check": {
            "type": "string",
            "description": "A catalog check name when intent=check and one applies; else 'new' when the question "
            "needs a geometry check the catalog lacks; else empty",
        },
        "hint": {
            "type": "string",
            "description": "When check='new': a one-line signature for the Droid, e.g. 'ball_speed(rally) -> max m/s'",
        },
        "reason": {"type": "string", "description": "<= 12 words"},
    },
    "required": ["intent", "check", "hint", "reason"],
    "additionalProperties": False,
}

ROUTER_SYSTEM = (
    "You route a judge's spoken question at a pickup table-tennis game to one action. Actions: 'check' when the "
    "question is about what the ball or a player physically did and a geometry check over the tracked ball can "
    "answer it; 'rule' when it asks what the rules say in general; 'score' for the score or who serves; 'explain' "
    "when it asks why the referee made a call; 'none' for anything else (chit-chat, unrelated). For 'check', name the "
    "catalog check that answers it, or 'new' with a signature hint when no catalog check fits. Never answer the "
    "question yourself.\n\nCatalog:\n" + catalog_text()
)


def _time_args(spec_args: tuple[str, ...], ctx: dict[str, Any]) -> dict[str, Any]:
    """Resolve 'that' to the newest call's time when fresh; otherwise let the engine resolve `ref`."""
    args: dict[str, Any] = {}
    now = ctx.get("t_game_s")
    calls = ctx.get("last_calls") or []
    newest = calls[0] if calls else None
    fresh = (
        newest is not None
        and isinstance(newest.get("t_game_s"), int | float)
        and (now is None or float(now) - float(newest["t_game_s"]) <= RECENT_CALL_S)
    )
    if "t" in spec_args:
        if fresh:
            args["t_game_s"] = float(newest["t_game_s"])
            args["ref"] = f"call:{newest.get('id', '')}"
        else:
            args["ref"] = "last"
    if "rally" in spec_args:
        args["ref"] = "last_rally"
        if isinstance(ctx.get("rally_no"), int):
            args["rally_no"] = ctx["rally_no"]
        if fresh and isinstance(newest.get("rally_no"), int):
            args["rally_no"] = newest["rally_no"]
    if "window" in spec_args:
        args["ref"] = "last_rally"
        if fresh:
            t = float(newest["t_game_s"])
            args["t0_s"], args["t1_s"] = round(t - 8.0, 3), round(t + 0.5, 3)
    return args


def route_regex(question: str, ctx: dict[str, Any]) -> Route | None:
    q = clean(question).lower().rstrip(".!?")
    if not q:
        return Route("none", reason="empty")
    for pattern, intent, check in _RULES:
        if re.search(pattern, q):
            if check:
                return Route("check", check, _time_args(CHECKS[check].args, ctx), "regex", reason=pattern[:40])
            return Route(intent, source="regex", reason=pattern[:40])
    return None


async def route(question: str, ctx: dict[str, Any], llm: JSONCompleter | None) -> tuple[Route, float]:
    """Returns (route, router_ms). Deterministic first; the fast Claude model only for what the rules miss."""
    r = route_regex(question, ctx)
    if r is not None:
        return r, 0.0
    if llm is None:
        return Route("rule", source="regex", reason="no router model; treated as a rules question"), 0.0
    data, ms = await llm.complete(
        system=ROUTER_SYSTEM, user=f"Question: {clean(question)}", schema=ROUTE_SCHEMA, label="route", fast=True
    )
    intent = str(data.get("intent", "none"))
    check = str(data.get("check") or "").strip()
    if intent == "check":
        if check in CHECKS:
            return Route(
                "check", check, _time_args(CHECKS[check].args, ctx), "claude", reason=data.get("reason", "")
            ), ms
        hint = str(data.get("hint") or "").strip() or f"new_check(rally) for: {clean(question)[:80]}"
        return Route("check", None, {"ref": "last_rally"}, "claude", hint=hint, reason=data.get("reason", "")), ms
    if intent not in ("rule", "score", "explain", "none"):
        intent = "none"
    return Route(intent, source="claude", reason=str(data.get("reason", ""))), ms
