"""The referee's checks through the engine (interfaces-v1 section 20): run_check resolves the moment, runs the session
check over the fused 3D track and replies on reply_to; request_check answers honestly; ask_logged keeps the referee's
fields. On the SYNTHETIC 3D fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from trophy_engine.ask import TrackStore
from trophy_engine.checks.library import load_field, load_library
from trophy_engine.engine import Engine
from trophy_engine.loop import make_check_runner
from trophy_engine.state import MemoryState

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis_3d"
GAME = "g_synth001"


def engine_with_track() -> tuple[Engine, MemoryState, list[tuple[str, dict]]]:
    st = MemoryState()
    eng = Engine(st, modules_dir=ROOT / "sports")
    eng.create_game(GAME, "table_tennis", t0_ms=0)
    eng.start_game(GAME, "A")
    store = TrackStore(load_library(ROOT / "sports" / "table_tennis" / "checks"), sport="table_tennis")
    store.set_field(load_field(FIX / "field.json"))
    store.extend(json.loads(line) for line in (FIX / "game_01.track3d.jsonl").read_text().splitlines() if line.strip())
    replies: list[tuple[str, dict]] = []
    eng.check_runner = make_check_runner(store)
    eng.reply = lambda stream, payload: replies.append((stream, payload))
    return eng, st, replies


def ctl(eng: Engine, cmd: str, args: dict) -> None:
    eng.handle_ctl({"cmd": cmd, "game_id": GAME, "args": args, "by_cam_id": "c_judge1"})


def test_run_check_answers_on_the_reply_stream_with_the_checks_own_result():
    eng, _, replies = engine_with_track()
    labels = json.loads((FIX / "game_01.labels3d.json").read_text())
    t = next(b["t_s"] for b in labels.get("bounces", []) if b.get("surface", "table") == "table")
    ctl(
        eng, "run_check", {"check": "in_out", "args": {"t_game_s": t}, "reply_to": "reply:r1", "question": "was it out"}
    )
    stream, rep = replies[-1]
    assert stream == "reply:r1" and rep["check"] == "in_out" and "error" not in rep, rep
    assert rep["verdict"] in ("in", "out", "edge") and 0 <= rep["p"] <= 1
    assert rep["inputs"]["t_s"] == t and rep["calibrated"] in (True, False) and rep["latency_ms"] >= 0


def test_run_check_errors_are_honest():
    eng, _, replies = engine_with_track()
    ctl(eng, "run_check", {"check": "ball_speed", "args": {"t_game_s": 1.0}, "reply_to": "reply:r2"})
    assert replies[-1][1]["error"] == "no_such_check"
    ctl(eng, "run_check", {"check": "in_out", "args": {"ref": "last"}, "reply_to": "reply:r3"})  # no calls yet
    assert replies[-1][1]["error"] == "no_data"
    eng.check_runner = None  # the one-camera path has no 3D track
    ctl(eng, "run_check", {"check": "in_out", "args": {"t_game_s": 1.0}, "reply_to": "reply:r4"})
    assert replies[-1][1]["error"] == "no_data"
    ctl(
        eng,
        "request_check",
        {"question": "how fast was that", "check_hint": "ball_speed(rally)", "reply_to": "reply:r5"},
    )
    assert replies[-1][1]["error"].startswith("failed:")


def test_ask_logged_keeps_the_referees_fields():
    eng, st, _ = engine_with_track()
    ctl(
        eng,
        "ask_logged",
        {"question": "was that out", "answer": "Out by 3 cm.", "citations": [], "latency_ms": 812,
         "speech": "Out, by three centimetres.", "kind": "check", "check": "in_out", "p": 0.97, "calibrated": False},
    )  # fmt: skip
    row = st.rows("ask")[-1]
    assert (row["speech"], row["kind"], row["check"], row["p"], row["calibrated"]) == (
        "Out, by three centimetres.", "check", "in_out", 0.97, False,
    )  # fmt: skip
    assert row["by_cam_id"] == "c_judge1"
