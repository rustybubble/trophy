"""tools/c3_timings.py on hand-written SYNTHETIC rows (no stack, no footage): every number here is made up."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from c3_timings import compute, main, percentile  # noqa: E402

T0 = 1_800_000_000_000.0
G = "g_synth001"


def call(n: int, t: float, posted_after_ms: float, tier: str = "AUTO", **kw) -> dict:
    return {
        "id": f"c{n}",
        "game_id": G,
        "t_game_s": t,
        "rally_no": n,
        "kind": "point",
        "outcome": "point_A",
        "team_id": "A",
        "points": 1,
        "p": 0.95 if tier == "AUTO" else 0.7,
        "p_source": "geometry",
        "tier": tier,
        "created_at_ms": T0 + 1000 * t + posted_after_ms,
        **kw,
    }


def synthetic_game() -> dict:
    calls = [call(1, 10.0, 200), call(2, 20.0, 400, tier="BETA"), call(3, 30.0, 300)]
    calls.append(call(99, 35.0, 5, p_source="manual", points=0))  # the e2e TEST call: excluded
    c2 = T0 + 20_400
    return {
        "game": [{"game_id": G, "t0_ms": T0, "params": {"synthetic": True}}],
        "rally": [{"rally_no": n, "status": "closed", "t_end_s": t} for n, t in ((1, 10.0), (2, 20.0), (3, 30.0))],
        "call": calls,
        "challenge": [
            {"challenge_id": "h1", "call_id": "c2", "created_at_ms": c2 + 3000},
            {"challenge_id": "h9", "call_id": "c99", "created_at_ms": T0 + 36_000},  # on the TEST call: excluded
        ],
        "ai_vote": [
            {"call_id": "c2", "backend": "claude", "created_at_ms": c2 + 2500},
            {"call_id": "c2", "backend": "gemini", "created_at_ms": c2 + 1800},
            {"call_id": "c2", "backend": "bitdeer", "created_at_ms": c2 + 3200, "error": "timeout"},
            {"call_id": "c2", "backend": "geometry", "created_at_ms": c2},
        ],
        "house_rule": [
            {"rule_version": "hr1", "status": "approved", "created_at_ms": T0 + 40_000, "updated_at_ms": T0 + 100_000}
        ],
        "droid_run": [
            {
                "run_id": "r1",
                "status": "approved",
                "trigger": {"source": "house_rule", "rule_version": "hr1"},
                "finished_at_ms": T0 + 85_000,
            }
        ],
        "ask": [
            {"ask_id": "a1", "kind": "check", "latency_ms": 1400.0},
            {"ask_id": "a2", "kind": "rule", "latency_ms": 2200.0},
            {"ask_id": "a3", "kind": "pending", "latency_ms": 45_000.0},
        ],
    }


ACKS = [
    {"game_id": G, "call_id": "c1", "cam_id": "c_a", "t_ack_srv_ms": T0 + 10_250},
    {"game_id": G, "call_id": "c1", "cam_id": "c_b", "t_ack_srv_ms": T0 + 10_300},  # second phone: later
    {"game_id": G, "call_id": "c2", "cam_id": "c_a", "t_ack_srv_ms": T0 + 20_450},
    {"game_id": G, "call_id": "c3", "cam_id": "c_a", "t_ack_srv_ms": T0 + 30_380},
    {"game_id": "g_other000", "call_id": "c3", "t_ack_srv_ms": T0},  # another game: ignored
]
CLIPS = [
    {"call_id": "c2", "seg": 7, "uploaded_at_ms": T0 + 20_400 + 3000 + 900},
    {"call_id": "c2", "seg": 8, "uploaded_at_ms": T0 + 20_400 + 3000 + 1500},
]
LOG = [
    'engine | {"svc": "engine", "game_id": "g_synth001", "msg": "call", "rule": "x", "ms": 4.2}',
    'engine | {"svc": "engine", "game_id": "g_synth001", "msg": "call", "rule": "y", "ms": 6.0}',
    "gateway | not json",
]


def by_name(rep: dict) -> dict:
    return {m["name"]: m for m in rep["metrics"]}


def test_percentile_interpolates() -> None:
    assert percentile([5.0], 95) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([0.0, 10.0], 95) == pytest.approx(9.5)


def test_every_c3_metric_on_a_synthetic_game() -> None:
    rep = compute(synthetic_game(), ACKS, CLIPS, LOG)
    m = by_name(rep)
    assert rep["synthetic"] is True and rep["label"].startswith("SYNTHETIC")
    assert rep["counts"]["engine_calls"] == 3  # the manual TEST call is excluded

    shown = m["rally end -> shown on the first phone (C3 spoken-call target)"]
    assert (shown["n"], shown["p50_ms"], shown["max_ms"], shown["verdict"]) == (3, 380.0, 450.0, "meets")
    assert m["rally end -> scoring call posted"]["p50_ms"] == 300.0
    assert m["call posted -> shown on the first phone (call_ack)"]["p50_ms"] == 50.0

    replay = m["challenge -> replay ready (first clip uploaded)"]
    assert (replay["n"], replay["p50_ms"], replay["verdict"]) == (1, 900.0, "meets")

    assert m["BETA call posted -> claude vote row"]["p50_ms"] == 2500.0
    assert m["BETA call posted -> gemini vote row"]["p50_ms"] == 1800.0
    assert m["BETA call posted -> bitdeer vote row"]["verdict"] == "not measured"  # its only vote errored
    assert m["votes never delayed a call: votes created before their call"]["verdict"] == "PASS"

    assert m["house rule pending -> ready (Droid: plan, edit, gate)"]["p50_ms"] == 45_000.0
    assert m["house rule ready -> approved (the judge's click)"]["p50_ms"] == 15_000.0
    hr = m["house rule pending -> approved and hot-loaded"]
    assert (hr["p50_ms"], hr["verdict"]) == (60_000.0, "meets")

    ask = m["ask -> answer returned (gateway /api/ask round trip)"]
    assert (ask["n"], ask["p50_ms"], ask["max_ms"]) == (2, 1800.0, 2200.0)  # the pending answer is excluded
    assert m["engine: event -> calls computed (log)"]["n"] == 2


def test_a_vote_older_than_its_call_fails_the_never_delayed_check() -> None:
    rows = synthetic_game()
    rows["ai_vote"][0]["created_at_ms"] = rows["call"][1]["created_at_ms"] - 100  # the call waited for Claude
    m = by_name(compute(rows))["votes never delayed a call: votes created before their call"]
    assert (m["n"], m["max_ms"], m["verdict"]) == (1, 100.0, "FAIL")


def test_slow_calls_miss_the_target() -> None:
    late = [{**a, "t_ack_srv_ms": a["t_ack_srv_ms"] + 2000} for a in ACKS]
    m = by_name(compute(synthetic_game(), late))["rally end -> shown on the first phone (C3 spoken-call target)"]
    assert m["verdict"] == "misses" and m["p50_ms"] == 2380.0


def test_no_rows_prints_not_measured_with_n_zero() -> None:
    rep = compute({"game": [{"game_id": G, "t0_ms": T0}]})
    assert rep["synthetic"] is False
    assert all(m["n"] == 0 and m["verdict"] == "not measured" for m in rep["metrics"])


def test_cli_reads_a_snapshot_and_writes_the_report(tmp_path, capsys) -> None:
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"rows": synthetic_game(), "acks": ACKS, "clips": CLIPS}), "utf8")
    out = tmp_path / "report.json"
    assert main(["--snapshot", str(snap), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "SYNTHETIC" in printed and "not measured" in printed
    assert json.loads(out.read_text("utf8"))["game_id"] == G
