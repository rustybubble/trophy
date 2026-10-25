"""Hop 5 of `make e2e` (scripts/e2e_calls.py) on hand-written SYNTHETIC rows: no stack, no footage."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from e2e_calls import check_calls  # noqa: E402

T0 = 1_800_000_000_000.0
GAME = {"game_id": "g_synth001", "t0_ms": T0}


def call(n: int, t: float, team: str = "A", **kw) -> dict:
    c = {
        "schema": "trophy.call.v1",
        "id": f"01JSYNTHCALL{n:014d}",
        "game_id": "g_synth001",
        "t_game_s": t,
        "rule_id": "double_bounce",
        "rule_version": "table_tennis@1",
        "rally_no": n,
        "kind": "point",
        "outcome": f"point_{team}",
        "team_id": team,
        "points": 1,
        "p": 0.95,
        "p_source": "geometry",
        "tier": "AUTO",
        "shown": "auto",
        "text": f"[Synthetic] Point {team}",
        "speech": f"Point {team}.",
        "cue": {"beep": "short", "flash": team},
        "event_ids": [f"e{n}"],
        "evidence": [],
        "status": "final",
        "created_at_ms": T0 + 1000 * t + 300,
    }
    return {**c, **kw}


def rally(n: int, team: str) -> dict:
    return {"rally_no": n, "status": "closed", "winner_team_id": team}


def score(a: int, b: int) -> list[dict]:
    return [{"team_id": "A", "points": a}, {"team_id": "B", "points": b}]


def results(calls, rallies, scores, **kw) -> dict:
    return {name: (ok, detail) for name, ok, detail in check_calls(GAME, calls, rallies, scores, **kw)}


def test_a_consistent_game_passes_every_check() -> None:
    calls = [call(1, 3.0, "A"), call(2, 9.0, "B"), call(3, 15.0, "A")]
    r = results(calls, [rally(1, "A"), rally(2, "B"), rally(3, "A")], score(2, 1))
    assert all(ok for ok, _ in r.values()), r
    assert r["calls are timely"][1]["p50_ms"] == 300.0


def test_no_calls_fails_rather_than_passing_vacuously() -> None:
    r = results([], [], score(0, 0))
    assert not any(ok for ok, _ in r.values())


def test_contract_violations_are_reported() -> None:
    bad = call(1, 3.0, tier="SURE")
    quiet = call(2, 9.0, speech="  ")
    r = results([bad, quiet], [rally(1, "A"), rally(2, "A")], score(2, 0))
    ok, detail = r["calls match the contract"]
    assert not ok and {b["id"] for b in detail["bad"]} == {bad["id"], quiet["id"]}


def test_gate_violations() -> None:
    low = call(1, 3.0, p=0.80)  # AUTO below 0.90
    foul = call(2, 5.0, kind="foul_flag", points=0)  # judgment fouls are capped at BETA
    ai = call(3, 7.0, p_source="decide:ensemble", points=0)  # AI never makes the call alone
    players = call(4, 9.0, tier="PLAYERS", shown="challengeable", points=0)
    r = results([low, foul, ai, players], [rally(1, "A")], score(1, 0))
    ok, detail = r["confidence gate"]
    assert not ok and len(detail["violations"]) == 4


def test_score_must_match_the_scoring_calls_and_their_rallies() -> None:
    calls = [call(1, 3.0, "A"), call(2, 9.0, "B")]
    assert not results(calls, [rally(1, "A"), rally(2, "B")], score(2, 1))["rally scoring"][0]  # phantom point
    assert not results(calls, [rally(1, "A"), rally(2, "A")], score(1, 1))["rally scoring"][0]  # wrong winner
    assert not results(calls, [rally(1, "A")], score(1, 1))["rally scoring"][0]  # rally never closed


def test_voided_and_overturned_calls_do_not_count() -> None:
    calls = [call(1, 3.0, "A"), call(2, 9.0, "B", status="overturned"), call(3, 12.0, "B", status="voided")]
    ok, detail = results(calls, [rally(1, "A")], score(1, 0))["rally scoring"]
    assert ok and detail["points_from_calls"] == {"A": 1}


def test_slow_calls_fail_the_latency_check() -> None:
    calls = [call(1, 3.0, created_at_ms=T0 + 3000 + 2500), call(2, 9.0, "B", created_at_ms=T0 + 9000 + 1800)]
    ok, detail = results(calls, [rally(1, "A"), rally(2, "B")], score(1, 1))["calls are timely"]
    assert not ok and detail["p50_ms"] == 2150.0 and detail["max_ms"] == 2500.0


def test_edge_calls_near_the_disputed_ball_are_listed() -> None:
    edge = call(1, 6.5, kind="edge_call", outcome="edge_good", tier="BETA", shown="challengeable", p=0.71)
    detail = results([edge], [rally(1, "A")], score(1, 0), edge_window_s=(4.0, 10.0))["calls are timely"][1]
    assert detail["edge_calls_near_disputed_ball"] == [
        {"t_game_s": 6.5, "outcome": "edge_good", "tier": "BETA", "p": 0.71}
    ]
