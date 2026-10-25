"""Hop 5 of `make e2e`: are the engine's calls on the CC BY clip well-formed, gated and consistent with the score?

Pure checks over the game's Spacetime rows (each row's `json` is the contract object), so they run offline in tests
(tests/test_e2e_calls.py) and live from scripts/e2e.py behind `--calls-hop`. Off by default until flight and the
engine are on main. The clip is unlabelled, so nothing here measures accuracy: it checks that the calls obey the
contract, the confidence gate (D-4, D-17) and rally scoring, and it reports how long each call took to post.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError
from trophy.contracts import Call

AUTO_P = 0.90  # the gate's AUTO threshold (CLAUDE.md, services/engine gate.py)
COUNTED = ("final", "upheld", "challenged")  # call statuses whose points stand
POST_P50_MAX_MS = 1500.0  # C3 target is "spoken <= 1.5 s after the rally ends"; this is posted, a lower bound

Check = tuple[str, bool, dict[str, Any]]


def _scoring(c: dict[str, Any]) -> bool:
    return bool(c.get("points")) and c.get("status") in COUNTED and bool(c.get("team_id"))


def check_calls(
    game: dict[str, Any],
    calls: Iterable[dict[str, Any]],
    rallies: Iterable[dict[str, Any]],
    scores: Iterable[dict[str, Any]],
    edge_window_s: tuple[float, float] | None = None,
) -> list[Check]:
    """Return (name, ok, detail) for each hop-5 check. ``calls`` exclude the e2e's own TEST call."""
    calls, rallies, scores = list(calls), list(rallies), list(scores)
    out: list[Check] = []

    bad = []
    for c in calls:
        try:
            Call.model_validate(c)
        except ValidationError as e:
            bad.append({"id": c.get("id"), "errors": [err["msg"] for err in e.errors()][:3]})
        else:
            if not c["speech"].strip():
                bad.append({"id": c["id"], "errors": ["empty speech: nothing to say aloud"]})
    out.append(("calls match the contract", bool(calls) and not bad, {"calls": len(calls), "bad": bad[:5]}))

    gate = []
    for c in calls:
        tier, p = c.get("tier"), float(c.get("p", 0))
        if tier == "AUTO" and p < AUTO_P:
            gate.append({"id": c.get("id"), "why": f"AUTO at p={p:.2f} < {AUTO_P}"})
        if tier == "AUTO" and c.get("kind") == "foul_flag":
            gate.append({"id": c.get("id"), "why": "foul_flag is capped at BETA (D-17)"})
        if tier == "AUTO" and c.get("p_source") == "decide:ensemble":
            gate.append({"id": c.get("id"), "why": "AI votes never make an AUTO call alone"})
        if (tier == "PLAYERS") != (c.get("shown") == "evidence"):
            gate.append({"id": c.get("id"), "why": f"tier {tier} shown {c.get('shown')}"})
    tiers = {t: sum(c.get("tier") == t for c in calls) for t in ("AUTO", "BETA", "PLAYERS")}
    out.append(("confidence gate", bool(calls) and not gate, {"tiers": tiers, "violations": gate[:5]}))

    closed = {int(r["rally_no"]): r for r in rallies if r.get("status") != "open"}
    pts = [c for c in calls if _scoring(c)]
    mismatched = []
    for c in pts:
        r = closed.get(int(c.get("rally_no") or 0))
        if r is None or r.get("winner_team_id") != c["team_id"]:
            mismatched.append({"id": c.get("id"), "rally_no": c.get("rally_no"), "team_id": c["team_id"]})
    want: dict[str, int] = {}
    for c in pts:
        want[c["team_id"]] = want.get(c["team_id"], 0) + int(c["points"])
    have = {s["team_id"]: int(s.get("points", 0)) for s in scores}
    teams = set(want) | {t for t, n in have.items() if n}
    score_ok = all(want.get(t, 0) == have.get(t, 0) for t in teams)
    out.append(
        (
            "rally scoring",
            bool(pts) and not mismatched and score_ok,
            {
                "scoring_calls": len(pts),
                "closed_rallies": len(closed),
                "points_from_calls": want,
                "score_table": have,
                "rally_mismatches": mismatched[:5],
            },
        )
    )

    t0_ms = float(game.get("t0_ms") or 0)
    lat = sorted(
        float(c["created_at_ms"]) - (t0_ms + 1000.0 * float(c["t_game_s"]))
        for c in calls
        if t0_ms and c.get("created_at_ms") is not None and c.get("t_game_s") is not None
    )
    p50 = statistics.median(lat) if lat else None
    detail: dict[str, Any] = {
        "n": len(lat),
        "p50_ms": round(p50, 1) if p50 is not None else None,
        "max_ms": round(lat[-1], 1) if lat else None,
        "measures": "event time -> call row created (posted, not spoken); the C3 spoken-latency run is separate",
    }
    if edge_window_s is not None:
        lo, hi = edge_window_s
        detail["edge_calls_near_disputed_ball"] = [
            {"t_game_s": c["t_game_s"], "outcome": c.get("outcome"), "tier": c.get("tier"), "p": c.get("p")}
            for c in calls
            if c.get("kind") == "edge_call" and lo <= float(c.get("t_game_s", -1)) <= hi
        ]
    out.append(("calls are timely", p50 is not None and p50 <= POST_P50_MAX_MS, detail))
    return out
