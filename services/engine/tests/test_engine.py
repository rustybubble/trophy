"""The rule engine on the synthetic table-tennis fixtures and on hand-written event sequences."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from trophy_engine.engine import Engine
from trophy_engine.gate import gate
from trophy_engine.scoring import ScoringParams, replay_score
from trophy_engine.sportmod.l1 import read_l1, read_labels
from trophy_engine.sportmod.loader import load_module
from trophy_engine.state import MemoryState

ROOT = Path(__file__).resolve().parents[3]
TT = ROOT / "sports" / "table_tennis"
SAMPLES = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis"
GAME = "g_synth001"


def events_for(sample: str) -> list[dict]:
    mod = load_module(TT)
    obs = read_l1(SAMPLES / f"{sample}.l1.jsonl")
    return list(mod.events(iter(obs), mod.state(GAME)))


def new_engine(**kw) -> tuple[Engine, MemoryState]:
    st = MemoryState()
    clock = {"t": 1_000.0}

    def now():
        clock["t"] += 1
        return clock["t"]

    eng = Engine(st, now_ms=now, **kw)
    eng.create_game(GAME, "table_tennis", t0_ms=0, params={"synthetic": True, "label": "SYNTHETIC"})
    eng.start_game(GAME, "A")
    return eng, st


def point_call(ev_t: float, side: str, **extra) -> dict:
    return {
        "schema": "trophy.event.v1",
        "id": f"e{ev_t}",
        "game_id": GAME,
        "t_game_s": ev_t,
        "sport": "table_tennis",
        "type": "bounce",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.95,
        "side": side,
        "pos_m": {"x": -0.5 if side == "A" else 0.5, "y": 0.1, "z": 0.0},
        "sigma_m": 0.015,
        "payload": {
            "surface": extra.pop("surface", "table"),
            "side": side,
            "d_lines_m": {"end_A": 0.87, "end_B": 1.87, "side_left": 0.66, "side_right": 0.86},
            "p_in": 1.0,
            "edge": extra.pop("edge", None),
            **extra,
        },
    }


def floor(ev_t: float, side: str) -> dict:
    e = point_call(ev_t, side, surface="floor")
    e["payload"]["p_in"] = 0.0
    e["payload"]["d_lines_m"] = {"end_A": -0.9, "end_B": 3.6, "side_left": 0.7, "side_right": 0.8}
    return e


# ---------------------------------------------------------------- scoring


def test_rally_scoring_11_win_by_2_and_serve_rotation() -> None:
    sp = ScoringParams()
    calls = []
    t = 0.0

    def pt(team):
        nonlocal t
        t += 1
        calls.append(
            {"kind": "point", "status": "final", "team_id": team, "points": 1, "t_game_s": t, "created_at_ms": t}
        )

    gs = replay_score(calls, sp, "A")
    assert gs.server == "A" and gs.serving_points_left == 2
    pt("A")
    assert replay_score(calls, sp, "A").server == "A"
    pt("B")
    assert replay_score(calls, sp, "A").server == "B"  # serve changes every 2 points
    for _ in range(9):
        pt("A")
        pt("B")
    gs = replay_score(calls, sp, "A")
    assert gs.points == {"A": 10, "B": 10} and not gs.game_over
    assert gs.game_point_for == []  # win by 2: nobody is at game point at deuce
    pt("A")  # 11-10: deuce, serve alternates every point
    gs = replay_score(calls, sp, "A")
    assert gs.points == {"A": 11, "B": 10} and not gs.game_over
    assert gs.game_point_for == ["A"] and gs.match_point_for == ["A"]
    srv1 = gs.server
    pt("B")  # 11-11
    assert replay_score(calls, sp, "A").server != srv1
    pt("A")
    pt("A")  # 13-11
    gs = replay_score(calls, sp, "A")
    assert gs.game_over and gs.winner == "A" and gs.games == {"A": 1, "B": 0} and gs.match_over


def test_first_to_7_win_by_1_is_a_param_change() -> None:
    sp = ScoringParams(points_to_win=7, win_by=1)
    calls = [
        {"kind": "point", "status": "final", "team_id": "B", "points": 1, "t_game_s": i, "created_at_ms": i}
        for i in range(7)
    ]
    calls += [
        {"kind": "point", "status": "final", "team_id": "A", "points": 1, "t_game_s": 10 + i, "created_at_ms": 10 + i}
        for i in range(6)
    ]
    gs = replay_score(calls, sp, "A")
    assert gs.game_over and gs.winner == "B"


def test_voided_and_overturned_calls_do_not_count() -> None:
    calls = [
        {"kind": "point", "status": "final", "team_id": "A", "points": 1, "t_game_s": 1, "created_at_ms": 1},
        {"kind": "point", "status": "voided", "team_id": "A", "points": 1, "t_game_s": 2, "created_at_ms": 2},
        {"kind": "point", "status": "overturned", "team_id": "A", "points": 1, "t_game_s": 3, "created_at_ms": 3},
        {
            "kind": "point",
            "status": "final",
            "team_id": "B",
            "points": 1,
            "t_game_s": 3.5,
            "created_at_ms": 4,
            "supersedes": "x",
        },
        {"kind": "info", "status": "final", "team_id": "A", "points": 1, "t_game_s": 5, "created_at_ms": 5},
    ]
    assert replay_score(calls, ScoringParams(), "A").points == {"A": 1, "B": 1}


# ---------------------------------------------------------------- gate


@pytest.mark.parametrize(
    "p,tier,kind,untrusted,expect",
    [
        (0.95, "AUTO", "point", False, ("AUTO", "auto")),
        (0.7, "AUTO", "point", False, ("BETA", "challengeable")),
        (0.4, "AUTO", "point", False, ("BETA", "replay")),
        (0.95, "BETA", "edge_call", False, ("BETA", "challengeable")),
        (0.95, "AUTO", "foul_flag", False, ("BETA", "challengeable")),
        (0.95, "AUTO", "point", True, ("BETA", "challengeable")),
        (0.95, "PLAYERS", "foul_flag", False, ("PLAYERS", "evidence")),
    ],
)
def test_gate(p, tier, kind, untrusted, expect) -> None:
    assert gate(p, tier, kind, untrusted) == expect


# ---------------------------------------------------------------- engine on synthetic rallies


@pytest.mark.parametrize("sample", ["rally_01", "rally_02"])
def test_synthetic_rally_is_scored_for_the_labelled_winner(sample: str) -> None:
    eng, st = new_engine()
    labels = read_labels(SAMPLES / f"{sample}.labels.json")
    calls = []
    for ev in events_for(sample):
        calls += eng.feed(ev)
    points = [c for c in calls if c.get("points")]
    assert len(points) == 1, [c["text"] for c in calls]
    assert points[0]["team_id"] == labels["rally_winner"]
    assert points[0]["rally_no"] == 1
    for c in calls:
        assert c["schema"] == "trophy.call.v1" and c["text"] and c["speech"] and c["cue"]["beep"]
    scores = {r["team_id"]: r["points"] for r in st.rows("score")}
    assert scores[labels["rally_winner"]] == 1
    rallies = st.rows("rally")
    assert rallies[0]["status"] == "closed" and rallies[0]["winner_team_id"] == labels["rally_winner"]
    moments = st.rows("moment")
    assert len(moments) == 1 and moments[0]["kind"] == "point" and "no crowd audio" in " ".join(moments[0]["reasons"])


def test_calls_validate_against_the_contract() -> None:
    from trophy.contracts import Call

    eng, _ = new_engine()
    for ev in events_for("rally_01"):
        for c in eng.feed(ev):
            Call.model_validate(c)


def test_serve_must_bounce_on_the_servers_side_first() -> None:
    eng, _ = new_engine()
    calls = eng.feed(point_call(1.0, "B"))  # A serves, first bounce on B's side
    assert calls and calls[0]["outcome"] == "fault" and calls[0]["team_id"] == "B"


def test_double_bounce_and_net_and_ball_dead() -> None:
    eng, _ = new_engine()
    assert eng.feed(point_call(1.0, "A")) == []
    assert eng.feed(point_call(1.4, "B")) == []
    calls = eng.feed(point_call(1.9, "B"))  # B let it bounce twice
    assert calls[-1]["outcome"] == "point" and calls[-1]["team_id"] == "A"
    # next rally: net into own side
    eng.feed(point_call(5.0, "A"))
    net = {
        "schema": "trophy.event.v1",
        "id": "n1",
        "game_id": GAME,
        "t_game_s": 5.3,
        "sport": "table_tennis",
        "type": "net",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.6,
        "side": "A",
        "payload": {"kind": "into", "from_side": "A"},
    }
    calls = eng.feed(net)
    assert calls[-1]["outcome"] == "net" and calls[-1]["team_id"] == "B"
    # next rally (two points played, so B serves): silence after a bounce on A's side -> A loses
    eng.feed(point_call(9.0, "B"))
    eng.feed(point_call(9.4, "A"))
    dead = {
        "schema": "trophy.event.v1",
        "id": "d1",
        "game_id": GAME,
        "t_game_s": 10.8,
        "sport": "table_tennis",
        "type": "ball_dead",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.7,
        "payload": {"reason": "lost", "last_side": "A"},
    }
    calls = eng.feed(dead)
    assert calls[-1]["team_id"] == "B" and calls[-1]["tier"] == "BETA"


def test_edge_ball_is_a_beta_edge_call_and_triggers_decide() -> None:
    class Rec:
        reqs: list = []

        def submit(self, req):
            self.reqs.append(req)

    dec = Rec()
    eng, st = new_engine(decider=dec)
    eng.feed(point_call(1.0, "A"))
    ev = point_call(1.4, "B", edge={"top_edge": 0.45, "side_face": 0.4, "surface": 0.15})
    ev["payload"]["d_lines_m"] = {"end_A": 2.7, "end_B": 0.01, "side_left": 0.6, "side_right": 0.9}
    calls = eng.feed(ev)
    edge = [c for c in calls if c["kind"] == "edge_call"]
    assert edge and edge[0]["tier"] == "BETA" and edge[0]["shown"] == "challengeable" and "overlay" in edge[0]
    assert dec.reqs and dec.reqs[0]["options"] == ["top_edge", "side_face"] and dec.reqs[0]["call_id"] == edge[0]["id"]
    assert abs(dec.reqs[0]["p_geometry"]["top_edge"] - edge[0]["p"]) < 1e-6


def test_undo_adjust_challenge_overturn_and_set_server() -> None:
    eng, st = new_engine()
    eng.feed(point_call(1.0, "A"))
    eng.feed(point_call(1.4, "B"))
    calls = eng.feed(floor(2.0, "A"))  # B's side was the last bounce... floor after B's bounce: B at fault
    pt = calls[-1]
    assert pt["team_id"] == "A"
    score = lambda: {r["team_id"]: r["points"] for r in st.rows("score")}  # noqa: E731
    assert score() == {"A": 1, "B": 0}
    eng.handle_ctl({"cmd": "undo_last_call", "game_id": GAME, "args": {}})
    assert score() == {"A": 0, "B": 0}
    eng.handle_ctl({"cmd": "adjust_score", "game_id": GAME, "args": {"team_id": "B", "delta": 2}})
    assert score() == {"A": 0, "B": 2}
    assert eng.games[GAME].score().server == "B"  # two points played -> the serve rotated
    eng.handle_ctl({"cmd": "set_server", "game_id": GAME, "args": {"team_id": "A"}})
    eng.feed(point_call(5.0, "A"))
    eng.feed(point_call(5.4, "B"))
    pt = eng.feed(floor(6.0, "A"))[-1]
    assert score() == {"A": 1, "B": 2}
    eng.handle_ctl({"cmd": "challenge", "game_id": GAME, "args": {"call_id": pt["id"]}, "by_cam_id": "c_x"})
    ch = st.rows("challenge")[0]
    assert ch["status"] == "open" and st.tables["call"][pt["id"]]["status"] == "challenged"
    assert score() == {"A": 1, "B": 2}  # provisional while challenged
    eng.handle_ctl(
        {
            "cmd": "resolve_challenge",
            "game_id": GAME,
            "args": {
                "challenge_id": ch["challenge_id"],
                "result": "overturned",
                "replacement": {"outcome": "point", "team_id": "B"},
            },
        }
    )
    assert score() == {"A": 0, "B": 3}
    rep = [c for c in st.rows("call") if c.get("supersedes") == pt["id"]]
    assert rep and rep[0]["p_source"] == "manual"
    m = [m for m in st.rows("moment") if m.get("call_id") == pt["id"]][0]
    assert "overturned on challenge" in m["reasons"]
    eng.handle_ctl({"cmd": "set_server", "game_id": GAME, "args": {"team_id": "B"}})
    assert eng.games[GAME].score().server == "B"


def test_house_rule_submit_and_approve_hot_loads_the_pack(tmp_path: Path) -> None:
    eng, st = new_engine()
    eng.handle_ctl(
        {
            "cmd": "submit_house_rule",
            "game_id": GAME,
            "args": {"text": "first to 7, win by 1", "source": "typed"},
            "by_cam_id": "c_j",
        }
    )
    hr = st.rows("house_rule")[0]
    assert hr["status"] == "pending" and hr["backend"] == "droid"
    import yaml

    pack = yaml.safe_load((TT / "rules.yaml").read_text())
    pack["scoring"]["params"].update({"points_to_win": 7, "win_by": 1})
    commit, p = _gated_sandbox(tmp_path, pack)
    st.set_house_rule_status({"rule_version": hr["rule_version"], "status": "ready", "pack_path": f"{p}@{commit}"})
    eng.handle_ctl({"cmd": "approve_house_rule", "game_id": GAME, "args": {"rule_version": hr["rule_version"]}})
    assert st.tables["house_rule"][hr["rule_version"]]["status"] == "approved"
    g = eng.games[GAME]
    assert g.scoring.points_to_win == 7 and g.rule_version == hr["rule_version"]
    assert any("House rule added" in c["text"] for c in st.rows("call"))
    for i in range(7):  # 4 s apart: a point's trailing ball is dead for DEAD_AFTER_POINT_S (blocker 4)
        eng.feed(point_call(10 + i * 4, "A"))
        eng.feed(point_call(10.5 + i * 4, "B"))
        eng.feed(floor(11 + i * 4, "A"))
    assert g.score().game_over and g.score().winner == "A"
    assert st.rows("call")[-1]["rule_version"] == hr["rule_version"]
    assert g.game["status"] == "ended"
    assert any(m.get("is_best_play") for m in st.rows("moment"))


def test_approve_without_a_ready_pack_fails_loudly() -> None:
    eng, st = new_engine()
    eng.handle_ctl({"cmd": "submit_house_rule", "game_id": GAME, "args": {"text": "x", "source": "typed"}})
    rv = st.rows("house_rule")[0]["rule_version"]
    eng.handle_ctl({"cmd": "approve_house_rule", "game_id": GAME, "args": {"rule_version": rv}})
    assert st.tables["house_rule"][rv]["status"] == "failed"


def test_post_call_latency_p50_under_100ms() -> None:
    import time

    eng, _ = new_engine()
    evs = events_for("rally_02")
    lat = []
    for ev in evs:
        t0 = time.perf_counter()
        eng.feed(ev)
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    p50 = lat[len(lat) // 2]
    assert p50 <= 100, f"p50 {p50:.1f} ms"
    Path("/tmp/trophy_engine_latency.json").write_text(json.dumps({"p50_ms": p50, "max_ms": lat[-1], "n": len(lat)}))


def test_serve_toss_rules_from_d22() -> None:
    """The 6 in / 30° serve rules (STRETCH for perception, but the engine and pack handle serve_toss observations)."""
    eng, _ = new_engine()

    def toss(t, height, angle, sigma_h=0.01, sigma_a=0.05):
        return {
            "schema": "trophy.event.v1",
            "id": f"s{t}",
            "game_id": GAME,
            "t_game_s": t,
            "sport": "table_tennis",
            "type": "serve_toss",
            "source": "synthetic",
            "cams": ["c_syn001"],
            "conf": 0.9,
            "side": "A",
            "payload": {
                "server_side": "A",
                "release": {"t_s": t - 0.4, "pos_m": {"x": -1.5, "y": 0.0, "z": 0.2}},
                "apex": {"t_s": t - 0.2, "pos_m": {"x": -1.5, "y": 0.0, "z": 0.2 + height}},
                "contact": {"t_s": t, "pos_m": {"x": -1.5, "y": 0.0, "z": 0.25}},
                "height_m": height,
                "sigma_height_m": sigma_h,
                "rise_angle_rad": angle,
                "fall_angle_rad": angle,
                "angle_from_vertical_rad": angle,
                "sigma_angle_rad": sigma_a,
                "palm_still_s": 0.5,
                "observable_plane": "xz",
            },
        }

    low = eng.feed(toss(1.0, 0.10, 0.1))
    assert (
        low and low[-1]["outcome"] == "illegal_toss_height" and low[-1]["team_id"] == "B" and low[-1]["tier"] == "AUTO"
    )
    assert low[-1]["speech"] == "Fault. Toss too low." and low[-1]["overlay"]["serve_toss_event_id"] == "s1.0"
    near = eng.feed(toss(5.0, 0.148, 0.1))  # 4 mm under the limit with σ 1 cm -> BETA
    assert near[-1]["outcome"] == "illegal_toss_height" and near[-1]["tier"] == "BETA" and 0.5 < near[-1]["p"] < 0.9
    angled = eng.feed(toss(9.0, 0.25, 0.7))
    assert angled[-1]["outcome"] == "illegal_toss_angle" and angled[-1]["speech"] == "Fault. Toss not vertical."
    legal = eng.feed(toss(13.0, 0.25, 0.1))
    assert legal == []


def test_droid_net_let_house_rule_replays_the_point(tmp_path: Path) -> None:
    """The rule the live Droid wrote on 2026-10-24 (run 01M5QYE04446M2RC8A2K1JFJ1V): a net-clipping serve is a let."""
    import yaml

    pack = yaml.safe_load((TT / "rules.yaml").read_text())
    rule = {
        "id": "serve_net_let",
        "name": "Serve clips the net and lands in",
        "tier": "AUTO",
        "kind": "edge_call",
        "when": "params.net_let_on_serve && ev.type == 'net' && ev.payload.kind == 'touch' && rally.phase == 'serve'",
        "check": "code",
        "outcome": "let",
        "text": "Let: serve clipped the net",
        "speech": "Let. Replay the point.",
        "requires": ["net"],
        "house_rule": True,
    }
    idx = next(i for i, r in enumerate(pack["rules"]) if r["id"] == "net_into_own_side")
    pack["rules"].insert(idx, rule)
    mod = tmp_path / "table_tennis"
    shutil.copytree(TT, mod)
    (mod / "rules.yaml").write_text(yaml.safe_dump(pack))
    st = MemoryState()
    eng = Engine(st, now_ms=lambda: 1.0)
    eng.create_game(GAME, "table_tennis", t0_ms=0, module_dir=mod)
    eng.start_game(GAME, "A")
    eng.feed(point_call(1.0, "A"))  # serve bounces on the server's side
    touch = {
        "schema": "trophy.event.v1",
        "id": "nt",
        "game_id": GAME,
        "t_game_s": 1.2,
        "sport": "table_tennis",
        "type": "net",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.8,
        "side": "A",
        "payload": {"kind": "touch", "from_side": "A"},
    }
    calls = eng.feed(touch)
    assert (
        calls
        and calls[-1]["outcome"] == "let"
        and calls[-1]["speech"] == "Let. Replay the point."
        and "points" not in calls[-1]
    )
    assert eng.games[GAME].rally is None  # the rally ended; the point is replayed
    assert {r["team_id"]: r["points"] for r in st.rows("score")} == {"A": 0, "B": 0}
    assert st.rows("rally")[-1]["summary"]["let"] is True
    # the same touch in a rally (not a serve) is not a let under this rule
    eng.feed(point_call(5.0, "A"))
    eng.feed(point_call(5.4, "B"))
    assert eng.feed({**touch, "id": "nt2", "t_game_s": 5.6}) == []


def _bounce(t: float, side: str, surface: str = "table") -> dict:
    return {
        "schema": "trophy.event.v1",
        "id": f"tb{t}",
        "game_id": GAME,
        "t_game_s": t,
        "sport": "table_tennis",
        "type": "bounce",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.95,
        "side": side,
        "payload": {"surface": surface, "side": side},
    }


def _fresh() -> Engine:
    eng = Engine(MemoryState(), modules_dir=ROOT / "sports")
    eng.create_game(GAME, "table_tennis", t0_ms=0)
    eng.start_game(GAME, "A")
    return eng


def test_trailing_floor_bounces_after_a_point_score_nothing():
    """Review blocker 4: serve, B bounce, three floor bounces -> 1-0, not 2-1."""
    eng = _fresh()
    for ev in [_bounce(1.0, "A"), _bounce(1.4, "B"), _bounce(2.0, "B", "floor"), _bounce(2.3, "A", "floor"),
               _bounce(2.6, "B", "floor")]:  # fmt: skip
        eng.feed(ev)
    assert dict(eng.games[GAME].score().points) == {"A": 1, "B": 0}


def test_a_bounce_after_a_double_bounce_does_not_start_a_rally():
    """Review blocker 4: a double bounce plus a third bounce -> 1-0, not 1-1."""
    eng = _fresh()
    for ev in [_bounce(1.0, "A"), _bounce(1.4, "B"), _bounce(1.8, "B"), _bounce(2.1, "B")]:
        eng.feed(ev)
    assert dict(eng.games[GAME].score().points) == {"A": 1, "B": 0}
    # the ball is live again after a ball_dead (or the dead window): the next rally scores normally
    eng.feed({**_bounce(2.5, "B"), "id": "dead", "type": "ball_dead", "payload": {"reason": "lost", "last_side": "B"}})
    for ev in [_bounce(4.0, "B"), _bounce(4.4, "A"), _bounce(4.8, "A")]:  # B serves (2 points each), A double bounce
        eng.feed(ev)
    assert dict(eng.games[GAME].score().points) == {"A": 1, "B": 1}


def test_floor_bounces_before_the_serve_are_ignored():
    eng = _fresh()
    assert eng.feed(_bounce(0.5, "A", "floor")) == [] and eng.feed(_bounce(0.8, "A", "floor")) == []
    assert eng.games[GAME].rally is None


def _gated_sandbox(tmp_path: Path, pack: dict) -> tuple[str, Path]:
    """A Droid-like sandbox: its own git repo with the gated rules.yaml committed (as the compiler records it)."""
    import subprocess

    import yaml

    repo = tmp_path / "workspace"
    (repo / "sports" / "table_tennis").mkdir(parents=True)
    p = repo / "sports" / "table_tennis" / "rules.yaml"
    p.write_text(yaml.safe_dump(pack))
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "gated"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return commit, p


def test_approval_loads_the_gated_commit_and_ignores_args_and_unready_rows(tmp_path: Path) -> None:
    """Review blocker 7."""
    import yaml

    eng, st = new_engine()
    eng.handle_ctl({"cmd": "submit_house_rule", "game_id": GAME, "args": {"text": "first to 7"}, "by_cam_id": "c_j"})
    rv = st.rows("house_rule")[0]["rule_version"]
    pack = yaml.safe_load((TT / "rules.yaml").read_text())
    pack["scoring"]["params"].update({"points_to_win": 7, "win_by": 1})
    commit, p = _gated_sandbox(tmp_path, pack)
    # 1. a pack_path in the command's args is ignored: the row is still pending, so nothing is approved
    evil = tmp_path / "evil.yaml"
    evil.write_text(yaml.safe_dump({**pack, "scoring": {**pack["scoring"], "params": {"points_to_win": 1}}}))
    eng.handle_ctl(
        {"cmd": "approve_house_rule", "game_id": GAME, "args": {"rule_version": rv, "pack_path": f"{evil}@{commit}"}}
    )
    assert st.tables["house_rule"][rv]["status"] == "failed" and eng.games[GAME].scoring.points_to_win == 11
    # 2. no commit -> refused, even when ready
    st.set_house_rule_status({"rule_version": rv, "status": "ready", "pack_path": str(p)})
    eng.handle_ctl({"cmd": "approve_house_rule", "game_id": GAME, "args": {"rule_version": rv}})
    assert st.tables["house_rule"][rv]["status"] == "failed"
    # 3. ready + gated commit -> the COMMITTED pack loads, not the working tree edited after the gate
    p.write_text(yaml.safe_dump({**pack, "scoring": {**pack["scoring"], "params": {"points_to_win": 1}}}))
    st.set_house_rule_status({"rule_version": rv, "status": "ready", "pack_path": f"{p}@{commit}"})
    eng.handle_ctl({"cmd": "approve_house_rule", "game_id": GAME, "args": {"rule_version": rv}})
    assert st.tables["house_rule"][rv]["status"] == "approved"
    assert eng.games[GAME].scoring.points_to_win == 7


def test_a_failing_moment_write_never_leaves_a_rally_open() -> None:
    """Review blocker 3: Spacetime refusing upsert_moment / set_best_play must not wedge scoring."""

    class Flaky(MemoryState):
        def upsert_moment(self, m):  # noqa: ANN001
            raise RuntimeError("Spacetime HTTP 530")

        def set_best_play(self, *a):  # noqa: ANN002
            raise RuntimeError("Spacetime HTTP 530")

    st = Flaky()
    eng = Engine(st, modules_dir=ROOT / "sports", dead_after_point_s=0)
    eng.create_game(GAME, "table_tennis", t0_ms=0)
    eng.start_game(GAME, "A")
    for t, side in [(1.0, "A"), (1.4, "B"), (1.9, "B")]:  # B double bounce -> point A
        eng.feed(point_call(t, side))
    assert eng.games[GAME].rally is None
    for t, side in [(5.0, "A"), (5.4, "B"), (5.9, "B")]:  # the next rally scores too
        eng.feed(point_call(t, side))
    assert dict(eng.games[GAME].score().points) == {"A": 2, "B": 0}
    eng.handle_ctl({"cmd": "end_game", "game_id": GAME, "args": {}})  # best play write fails quietly
