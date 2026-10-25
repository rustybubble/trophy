"""Post-game data written live (interfaces-v1 §19): one ``moment`` per point, serve fault, edge call, challenge,
basket, bookmark and approved house rule, with a ``highlight_score`` from event features only (there is no crowd
audio, and every moment says so in ``reasons``), and ★ Play of the game chosen at end_game.
"""

from __future__ import annotations

from typing import Any

from trophy.ids import new_ulid

NO_AUDIO = "scored from event features only (no crowd audio)"


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def highlight(features: dict[str, Any]) -> tuple[float, list[str]]:
    """Weights are heuristics, listed so the UI can show why a moment was picked."""
    score = 0.05
    reasons: list[str] = []
    shots = int(features.get("shots", 0))
    if shots >= 8:
        score += min(0.35, 0.05 * (shots - 6))
        reasons.append(f"long rally ({shots} shots)")
    if features.get("game_point"):
        score += 0.25
        reasons.append("game point")
    if features.get("match_point"):
        score += 0.15
        reasons.append("match point")
    if features.get("game_winner"):
        score += 0.2
        reasons.append("won the game")
    p = features.get("p")
    if p is not None and abs(float(p) - 0.5) < 0.2:
        score += 0.2
        reasons.append(f"close call ({round(float(p) * 100)}%)")
    if features.get("overturned"):
        score += 0.3
        reasons.append("overturned on challenge")
    if features.get("challenged"):
        score += 0.1
        reasons.append("challenged")
    if features.get("near_limit_serve"):
        score += 0.2
        reasons.append("serve near the limit")
    if features.get("three"):
        score += 0.2
        reasons.append("three-pointer")
    if features.get("edge"):
        score += 0.15
        reasons.append("edge ball")
    reasons.append(NO_AUDIO)
    return round(_clamp(score), 3), reasons


def moment_kind(call: dict[str, Any]) -> str | None:
    k = call.get("kind")
    out = str(call.get("outcome", ""))
    if k == "basket":
        return "basket"
    if k == "edge_call":
        return "edge"
    if k == "violation" and out.startswith("illegal_toss"):
        return "serve_fault"
    if k in ("point", "violation") and call.get("points"):
        return "point"
    return None


def moment_from_call(
    call: dict[str, Any],
    *,
    rally: dict[str, Any],
    score_after: str,
    game_point: bool,
    match_point: bool,
    game_winner: bool,
    team_name: str,
) -> dict[str, Any] | None:
    kind = moment_kind(call)
    if kind is None:
        return None
    t = float(call["t_game_s"])
    t_start = float(rally.get("t_start_s", t - 2.0))
    feats = {
        "shots": rally.get("shots", 0),
        "game_point": game_point,
        "match_point": match_point,
        "game_winner": game_winner,
        "p": call.get("p"),
        "edge": kind == "edge",
        "near_limit_serve": kind == "serve_fault" and call.get("tier") == "BETA",
        "three": call.get("outcome") == "made_3",
    }
    score, reasons = highlight(feats)
    label = {
        "point": f"Point {team_name}",
        "serve_fault": call.get("text", "Serve fault"),
        "edge": call.get("text", "Edge ball"),
        "basket": call.get("text", "Basket"),
    }[kind]
    tags = [kind, str(call.get("rule_id", ""))]
    if call.get("tier") == "BETA":
        tags.append("close")
    if rally.get("shots", 0) >= 8:
        tags.append("long_rally")
    return {
        "moment_id": new_ulid(),
        "game_id": call["game_id"],
        "kind": kind,
        "t_game_s": t,
        "t_start_s": round(max(0.0, t_start - 0.5), 3),
        "t_end_s": round(t + 1.0, 3),
        "label": str(label)[:80],
        "team_id": call.get("team_id"),
        "track_id": None,
        "call_id": call["id"],
        "rally_no": call.get("rally_no"),
        "score_after": score_after,
        "tags": tags,
        "highlight_score": score,
        "reasons": reasons,
        "is_best_play": False,
        "thumb_t_s": t,
    }


def rescore_for_challenge(moment: dict[str, Any], result: str) -> dict[str, Any]:
    feats = {"challenged": True, "overturned": result == "overturned", "p": None}
    base, _ = highlight(feats)
    m = dict(moment)
    m["highlight_score"] = round(_clamp(float(m.get("highlight_score", 0)) + base - 0.05), 3)
    m["reasons"] = (
        [r for r in m.get("reasons", []) if r != NO_AUDIO]
        + (["overturned on challenge"] if result == "overturned" else ["challenged"])
        + [NO_AUDIO]
    )
    m["tags"] = list(dict.fromkeys(list(m.get("tags", [])) + ["challenge", result]))
    return m


def best_play(moments: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [m for m in moments if m.get("kind") in ("point", "basket", "edge", "serve_fault")]
    if not scored:
        return None
    return max(scored, key=lambda m: (float(m.get("highlight_score", 0)), float(m.get("t_game_s", 0))))
