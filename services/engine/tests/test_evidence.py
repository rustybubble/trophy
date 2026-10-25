"""The evidence vocabulary (rally.*, ev.side_p/n_cams, params.evidence_*), the judge's label_rally, and the recorded
real-play fixtures: the hand-written pack must FAIL the gate on them (five points for one rally), which is the test
the Droid's correction has to make pass."""

from __future__ import annotations

import json
from pathlib import Path

from _handwritten import handwritten_modules_dir

from trophy_engine.engine import Engine
from trophy_engine.rally import RALLY_FIELDS, RallyState
from trophy_engine.replay_test.checks import run_replay
from trophy_engine.state import MemoryState
from trophy_engine.vocabulary import render

MODULES = handwritten_modules_dir()
TT = MODULES / "table_tennis"  # the hand-written pack, frozen as a fixture

ROOT = Path(__file__).resolve().parents[3]
SHIPPED = ROOT / "sports" / "table_tennis"  # Droid-written (D-42)
SYNTH = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis"
RECORDED = ROOT / "evals" / "fixtures" / "recorded" / "table_tennis"
GAME = "g_6ghx0t5z"


def _engine(**kw) -> Engine:
    eng = Engine(MemoryState(), modules_dir=MODULES, dead_after_point_s=3.0, server_from_first_hit=True, **kw)
    eng.create_game(GAME, "table_tennis", t0_ms=0)
    eng.start_game(GAME, "A")
    return eng


def _live_events() -> list[dict]:
    return [json.loads(line) for line in (RECORDED / f"{GAME}_rally1_live.l2.jsonl").read_text().splitlines() if line]


def test_rally_fields_documented_and_timed() -> None:
    r = RallyState(rally_no=1, server_side="A", t_start_s=10.0)
    assert list(r.view(10.0)) == list(RALLY_FIELDS)
    assert r.view(10.0)["t_since_last_bounce_s"] == -1.0
    payload = {"side": "A", "surface": "table"}
    bounce = {"type": "bounce", "t_game_s": 11.0, "side": "A", "side_p": 0.6, "payload": payload}
    r.apply(bounce)
    r.apply({"type": "contact", "t_game_s": 11.3, "side": "A", "payload": {"side": "A", "kind": "racket"}})
    v = r.view(11.9)
    assert v["last_bounce_side_p"] == 0.6 and v["hits_since_last_bounce"] == 1 and v["hit_since_last_bounce"]
    assert abs(v["t_since_last_bounce_s"] - 0.9) < 1e-6 and abs(v["t_since_last_contact_s"] - 0.6) < 1e-6
    r.apply({"type": "bounce", "t_game_s": 12.0, "side": "B", "payload": {"side": "B", "surface": "table"}})
    assert r.view(12.0)["hits_since_last_bounce"] == 0


def test_vocabulary_renders_from_code() -> None:
    md = render(SHIPPED)
    for key in RALLY_FIELDS:
        assert f"`rally.{key}`" in md
    assert "`ev.side_p`" in md and "`params.evidence_min_cams`" in md and "ev.type == 'bounce'" in md


def test_recorded_rally_replays_as_five_points_with_the_handwritten_pack() -> None:
    eng = _engine()
    calls = []
    for ev in _live_events():
        calls += [c for c in eng.handle_event(ev) if c.get("points")]
    sc = eng.games[GAME].score()
    assert (sc.points["A"], sc.points["B"]) == (2, 3)
    assert [c["rule_id"] for c in calls] == ["net_into_own_side"] + ["double_bounce"] * 4


def test_side_p_and_n_cams_reach_the_rules_and_the_rally() -> None:
    eng = _engine()
    g = eng.games[GAME]
    b = next(e for e in _live_events() if e["type"] == "bounce" and abs(e["pos_m"]["x"]) < 0.05)
    eng.handle_event(b)
    assert g.rally is not None and 0.5 < g.rally.last_bounce_side_p < 0.95  # 4 cm from the net, 3.5 cm sigma


def test_weak_evidence_params_keep_single_camera_bounces_out() -> None:
    eng = _engine()
    g = eng.games[GAME]
    g.params["evidence_min_cams"] = 2
    g.params["evidence_min_conf"] = 0.9
    weak = next(e for e in _live_events() if e["type"] == "bounce" and len(e["cams"]) == 1 and e["conf"] < 0.9)
    assert eng.handle_event(weak) == [] and g.rally is None and len(g.events) == 1  # recorded, not judged
    strong = next(e for e in _live_events() if e["type"] == "bounce" and len(e["cams"]) == 2)
    eng.handle_event(strong)
    assert g.rally is not None


def test_label_rally_fixes_the_score_exports_the_sample_and_files_a_correction(tmp_path: Path) -> None:
    eng = _engine()
    eng.labelled_dir = tmp_path
    spoken: list[dict] = []
    eng.announce = spoken.append
    for ev in _live_events():
        eng.handle_event(ev)
    g = eng.games[GAME]
    assert g.score().points == {"A": 2, "B": 3}
    eng.handle_ctl({"cmd": "label_rally", "game_id": GAME, "args": {"winner": "B"}, "by_cam_id": "judge1"})
    assert g.score().points == {"A": 0, "B": 1}
    assert sum(1 for c in g.calls if c["status"] == "voided") == 5
    assert spoken[-1]["rule_id"] == "label_rally" and "Correction" in spoken[-1]["speech"]
    hr = next(iter(g.house_rules.values()))
    assert hr["source"] == "correction" and hr["status"] == "pending" and hr["evidence"]["winner"] == "B"
    sample = hr["evidence"]["sample"]
    labels = json.loads((tmp_path / "table_tennis" / f"{sample}.labels.json").read_text())
    assert labels["rally_winner"] == "B" and labels["synthetic"] is False
    assert labels["engine"]["dead_after_point_s"] == 3.0
    assert labels["end_ball_dead"]["last_side"] == "A" and len(labels["called"]) == 5
    first = labels["called"][0]
    assert first["rule_id"] == "net_into_own_side"
    assert first["event"]["n_cams"] == 1 and first["event"]["conf"] == 0.6
    doubles = [c for c in labels["called"] if c["rule_id"] == "double_bounce"]
    assert any(c["rally_before"]["hits_since_last_bounce"] >= 1 for c in doubles)  # a hit between the two bounces
    n = sum(1 for line in (tmp_path / "table_tennis" / f"{sample}.l2.jsonl").read_text().splitlines() if line)
    assert n == len(_live_events())
    # the exported sample is a gate sample: the hand-written pack fails its winner row, as it should
    res = run_replay(TT, tmp_path / "table_tennis")
    rows = {t["name"]: t for t in res.tests}
    assert not res.passed and rows[f"{sample}:calls:winner"]["pass"] is False


def test_gate_fails_the_handwritten_pack_on_the_recorded_fixtures() -> None:
    res = run_replay(TT, RECORDED)
    rows = {t["name"]: t for t in res.tests}
    assert rows[f"{GAME}_rally1_live:calls:winner"]["pass"] is False
    assert rows[f"{GAME}_rally1:calls:winner"]["pass"] is False
    assert rows[f"{GAME}_rally1:ball_dead:present"]["pass"] is True  # the tracked-ball dead-ball logic on real pixels
    assert "rules:coverage" in rows and not res.passed


def test_shipped_droid_pack_scores_the_recorded_rally_as_one_point_to_b() -> None:
    """The acceptance test of D-42: the Droid-written pack passes the gate on the synthetic rallies and on the recorded
    real rally, and the recorded rally is exactly one point to B."""
    head = (SHIPPED / "rules.yaml").read_text().splitlines()[0]
    assert "FACTORY DROID" in head
    rec = run_replay(SHIPPED, RECORDED)
    assert rec.passed, [t for t in rec.tests if not t["pass"]]
    rows = {t["name"]: t for t in rec.tests}
    assert rows[f"{GAME}_rally1_live:calls:winner"]["after"].startswith("B (1 point calls")
    assert rows[f"{GAME}_rally1:calls:winner"]["after"].startswith("B (1 point calls")
    syn = run_replay(SHIPPED, SYNTH)
    assert syn.passed, [t for t in syn.tests if not t["pass"]]
