"""D-43 on the engine side: the Droid decides house rules (auto-apply, re-judge, revert, veto) and writes interpreters
for annotated sports (request on start, load the gated commit, promote). The compiler is simulated by writing the rows
it would write (MemoryState); the gated pack lives in a real git repository like the Droid's sandbox."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from trophy_engine.engine import Engine
from trophy_engine.rejudge import read_session, replay_doc
from trophy_engine.state import MemoryState

ROOT = Path(__file__).resolve().parents[3]
TT = ROOT / "sports" / "table_tennis"
GAME = "g_droid001"


def clock():
    t = {"t": 1_000.0}

    def now():
        t["t"] += 1
        return t["t"]

    return now


def bounce(t: float, side: str, surface: str = "table") -> dict:
    return {
        "schema": "trophy.event.v1",
        "id": f"e{t}",
        "game_id": GAME,
        "t_game_s": t,
        "sport": "table_tennis",
        "type": "bounce",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.95,
        "side": side,
        "pos_m": {"x": -0.5 if side == "A" else 0.5, "y": 0.1, "z": 0.0},
        "sigma_m": 0.015,
        "payload": {
            "surface": surface,
            "side": side,
            "d_lines_m": {"end_A": 0.87, "end_B": 1.87, "side_left": 0.66, "side_right": 0.86},
            "p_in": 0.0 if surface == "floor" else 1.0,
        },
    }


def tt_session(eng: Engine) -> None:
    """Rally 1: A serves, B's side, off the table on B -> point A. Rally 2: double bounce on A -> point B."""
    for e in [bounce(10.0, "A"), bounce(10.4, "B"), bounce(10.9, "B", "floor")]:
        eng.feed(e)
    for e in [bounce(20.0, "A"), bounce(20.4, "B"), bounce(20.8, "A"), bounce(21.2, "A")]:
        eng.feed(e)


def let_on_double_bounce() -> dict:
    pack = yaml.safe_load((TT / "rules.yaml").read_text())
    pack["rules"].insert(
        0,
        {
            "id": "double_bounce_let",
            "name": "House rule: a double bounce is replayed",
            "tier": "AUTO",
            "kind": "point",
            "when": "ev.type == 'bounce' && ev.payload.surface == 'table' && rally.last_bounce_side == ev.side",
            "check": "code",
            "outcome": "let",
            "text": "Let: double bounce, replay the point",
            "speech": "Let.",
            "house_rule": True,
        },
    )
    return pack


def gated(tmp: Path, sport: str, pack: dict) -> tuple[Path, str]:
    repo = tmp / f"ws_{sport}_{len(list(tmp.iterdir()))}"
    (repo / "sports" / sport).mkdir(parents=True)
    p = repo / "sports" / sport / "rules.yaml"
    p.write_text(yaml.safe_dump(pack, sort_keys=False))
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "gated"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return repo, commit


def tt_engine(tmp: Path) -> tuple[Engine, MemoryState]:
    st = MemoryState()
    eng = Engine(st, now_ms=clock(), sessions_dir=tmp / "sessions")
    eng.create_game(GAME, "table_tennis", t0_ms=0)
    eng.start_game(GAME, "A")
    return eng, st


def submit(eng: Engine, st: MemoryState, text: str) -> dict:
    eng.handle_ctl({"cmd": "submit_house_rule", "game_id": GAME, "args": {"text": text}, "by_cam_id": "c_j"})
    return sorted(st.rows("house_rule"), key=lambda r: r["created_at_ms"])[-1]


def compiler_ready(st: MemoryState, tmp: Path, rv: str, pack: dict, applies: bool, passed: bool = True) -> None:
    repo, commit = gated(tmp, "table_tennis", pack)
    st.set_house_rule_status(
        {
            "rule_version": rv,
            "status": "ready",
            "pack_path": f"{repo}/sports/table_tennis/rules.yaml@{commit}",
            "results": {"passed": passed, "tests": [{"name": "module:load", "pass": True}], "calls_changed": []},
            "decision": {"applies": applies, "rationale": "a double bounce replays the point", "decided_by": "droid"},
        }
    )


def tick(eng: Engine) -> None:
    eng.poll_droid()
    eng.drain()


def scoring(st: MemoryState) -> dict[str, int]:
    return {r["team_id"]: r["points"] for r in st.rows("score")}


def test_submit_snapshots_the_session_and_the_pack_for_the_droid(tmp_path: Path) -> None:
    eng, st = tt_engine(tmp_path)
    tt_session(eng)
    hr = submit(eng, st, "a double bounce is a let")
    assert hr["status"] == "pending" and hr["base_rule_version"] == "1"
    assert Path(hr["base_pack_path"]).read_text() == (TT / "rules.yaml").read_text()
    doc = read_session(Path(hr["session_path"]))
    assert len(doc["events"]) == 7 and doc["first_server"] == "A"
    # the gate replays this file: the same plays the live engine called, and the house rule changes rally 2
    base = replay_doc(doc, yaml.safe_load((TT / "rules.yaml").read_text()), TT)
    assert base.score == {"A": 1, "B": 1}
    cand = replay_doc(doc, let_on_double_bounce(), TT)
    assert cand.score == {"A": 1, "B": 0}


def test_droid_decision_applies_rejudges_and_one_tap_reverts(tmp_path: Path) -> None:
    eng, st = tt_engine(tmp_path)
    tt_session(eng)
    assert scoring(st) == {"A": 1, "B": 1}
    hr = submit(eng, st, "a double bounce is a let")
    rv = hr["rule_version"]
    tick(eng)  # still pending: nothing happens
    assert st.tables["house_rule"][rv]["status"] == "pending"
    compiler_ready(st, tmp_path, rv, let_on_double_bounce(), applies=True)
    tick(eng)
    row = st.tables["house_rule"][rv]
    assert row["status"] == "applied", row.get("error")
    d = row["decision"]
    assert d["decided_by"] == "droid" and d["applies"] and d["calls_changed"] == 1 and d["rejudged_rallies"] == 2
    assert row["results"]["calls_changed"][0]["after"] == "let"
    assert scoring(st) == {"A": 1, "B": 0}
    calls = st.rows("call")
    old = next(c for c in calls if c.get("rule_id") == "double_bounce")
    new = next(c for c in calls if c.get("supersedes") == old["id"])
    assert old["status"] == "overturned" and new["outcome"] == "let" and new["speech"] == ""
    assert any(c["text"].startswith("House rule applied") and "1 call changed" in c["speech"] for c in calls)
    g = eng.games[GAME]
    assert g.rule_version == rv and g.rules.by_id("double_bounce_let") is not None
    # new plays are judged under the rule too
    for e in [bounce(30.0, "A"), bounce(30.4, "B"), bounce(30.8, "B")]:
        eng.feed(e)
    assert scoring(st) == {"A": 1, "B": 0}
    # one tap: back to the previous pack and calls
    eng.handle_ctl({"cmd": "revert_house_rule", "game_id": GAME, "args": {"rule_version": rv}})
    assert st.tables["house_rule"][rv]["status"] == "reverted"
    assert st.tables["call"][old["id"]]["status"] == "final" and st.tables["call"][new["id"]]["status"] == "voided"
    assert g.rule_version == "1" and g.rules.by_id("double_bounce_let") is None
    assert scoring(st)["A"] == 1 and scoring(st)["B"] == 1  # the let during the rule's time stays a let
    assert any("House rule undone" in c["text"] for c in st.rows("call"))


def test_rules_stack_and_a_stale_base_is_refused(tmp_path: Path) -> None:
    eng, st = tt_engine(tmp_path)
    tt_session(eng)
    first, second = submit(eng, st, "a double bounce is a let"), submit(eng, st, "first to 5")
    compiler_ready(st, tmp_path, first["rule_version"], let_on_double_bounce(), applies=True)
    tick(eng)
    assert st.tables["house_rule"][first["rule_version"]]["status"] == "applied"
    # the second run started from the pack before the first rule: applying it would drop the first rule
    pack = yaml.safe_load((TT / "rules.yaml").read_text())
    pack["scoring"]["params"]["points_to_win"] = 5
    compiler_ready(st, tmp_path, second["rule_version"], pack, applies=True)
    tick(eng)
    row = st.tables["house_rule"][second["rule_version"]]
    assert row["status"] == "failed" and "stale" in row["error"]
    # submitted now, it starts from the applied pack
    third = submit(eng, st, "first to 5")
    assert third["base_rule_version"] == first["rule_version"]
    assert "double_bounce_let" in Path(third["base_pack_path"]).read_text()


def test_droid_says_it_does_not_apply_and_the_judge_can_veto(tmp_path: Path) -> None:
    eng, st = tt_engine(tmp_path)
    tt_session(eng)
    hr = submit(eng, st, "players must wear hats")
    compiler_ready(st, tmp_path, hr["rule_version"], let_on_double_bounce(), applies=False)
    tick(eng)
    row = st.tables["house_rule"][hr["rule_version"]]
    assert row["status"] == "rejected" and row["decision"]["decided_by"] == "droid"
    assert eng.games[GAME].rule_version == "1" and scoring(st) == {"A": 1, "B": 1}
    # a veto while compiling: the ready result that follows is ignored
    hr2 = submit(eng, st, "a double bounce is a let")
    eng.handle_ctl({"cmd": "reject_house_rule", "game_id": GAME, "args": {"rule_version": hr2["rule_version"]}})
    compiler_ready(st, tmp_path, hr2["rule_version"], let_on_double_bounce(), applies=True)
    tick(eng)
    assert eng.games[GAME].rule_version == "1"


def test_a_play_a_person_ruled_on_keeps_its_ruling(tmp_path: Path) -> None:
    eng, st = tt_engine(tmp_path)
    tt_session(eng)
    db = next(c for c in st.rows("call") if c.get("rule_id") == "double_bounce")
    eng.handle_ctl({"cmd": "undo_last_call", "game_id": GAME, "args": {}})
    assert st.tables["call"][db["id"]]["status"] == "voided"
    hr = submit(eng, st, "a double bounce is a let")
    compiler_ready(st, tmp_path, hr["rule_version"], let_on_double_bounce(), applies=True)
    tick(eng)
    row = st.tables["house_rule"][hr["rule_version"]]
    assert row["status"] == "applied" and row["decision"]["calls_changed"] == 0
    assert not any(c.get("supersedes") for c in st.rows("call"))


# ---------------------------------------------------------------- annotated sports and interpreters


BADMINTON_RULES = {
    "sport": "badminton",
    "family": "flight",
    "version": 1,
    "teams": [{"team_id": "A", "name": "Near"}, {"team_id": "B", "name": "Far"}],
    "field": {"frame": "court centre, +x toward B", "landmarks": []},
    "scoring": {"template": "rally", "params": {"points_to_win": 21, "win_by": 2, "serves_per_turn": 1}},
    "rules": [
        {
            "id": "shuttle_out",
            "name": "Shuttle lands out",
            "tier": "AUTO",
            "kind": "point",
            "when": "ev.type == 'bounce' && ev.payload.p_in < 0.5",
            "check": "code",
            "outcome": "out",
            "team": "ev.side",
            "points": 1,
            "text": "Out. Point {team}",
            "speech": "Out. {at_fault}.",
        },
        {
            "id": "shuttle_in",
            "name": "Shuttle lands in",
            "tier": "AUTO",
            "kind": "point",
            "when": "ev.type == 'bounce' && ev.payload.p_in >= 0.5",
            "check": "code",
            "outcome": "point",
            "team": "opponent(ev.side)",
            "points": 1,
            "text": "Point {team}",
            "speech": "Point, {team}.",
        },
    ],
}


def annotated(t: float, typ: str, sport: str, **kw) -> dict:
    ev = {
        "schema": "trophy.event.v1",
        "id": f"a{t}",
        "game_id": GAME,
        "t_game_s": t,
        "sport": sport,
        "type": typ,
        "source": "annotated",
        "cams": [],
        "conf": 1.0,
    }
    ev.update(kw)
    return ev


def landing(t: float, side: str, p_in: float) -> dict:
    return annotated(
        t, "bounce", "badminton", side=side,
        payload={"surface": "court", "side": side, "d_lines_m": {}, "p_in": p_in},
    )  # fmt: skip


def test_annotated_sport_without_interpreter_requests_one_and_loads_the_gated_result(tmp_path: Path) -> None:
    sports, approved = tmp_path / "sports", tmp_path / "modules"
    (sports / "badminton").mkdir(parents=True)
    (sports / "badminton" / "config.yaml").write_text("sport: badminton\nversion: 1\n")
    st = MemoryState()
    eng = Engine(st, modules_dir=sports, approved_dir=approved, now_ms=clock())
    g = eng.create_game(GAME, "badminton", t0_ms=0)
    assert g.needs_interpreter and g.pack["rules"] == []
    eng.start_game(GAME, "A")
    (run,) = st.rows("droid_run")
    assert run["kind"] == "interpreter" and run["status"] == "queued"
    assert run["trigger"] == {"source": "sport_module", "text": "no approved interpreter for badminton",
                              "requested_by": "engine"}  # fmt: skip
    # plays before the interpreter exists: no calls yet
    for e in [annotated(1.0, "contact", "badminton", side="A", payload={"side": "A", "kind": "racket"}),
              landing(1.8, "B", 0.0), landing(5.0, "A", 1.0)]:  # fmt: skip
        assert eng.feed(e) == []
    tick(eng)  # still queued
    assert g.interpreter_run == run["run_id"]
    repo, commit = gated(tmp_path, "badminton", BADMINTON_RULES)
    st.set_droid_run_status(
        {"run_id": run["run_id"], "status": "ready", "commit": commit, "workspace": str(repo),
         "results": {"passed": True, "tests": [{"name": "x", "pass": True}] * 3, "calls_changed": []}}
    )  # fmt: skip
    tick(eng)
    assert not g.needs_interpreter and g.interpreter_run is None and g.rule_version == run["run_id"]
    calls = [c for c in st.rows("call") if c.get("rule_id") in ("shuttle_out", "shuttle_in")]
    assert [(c["outcome"], c["team_id"], c["at_fault"]["team_id"]) for c in calls] == [
        ("out", "B", "A"),
        ("point", "B", "A"),
    ]
    assert calls[0]["source"] == "annotated"
    assert st.tables["droid_run"][run["run_id"]]["status"] == "approved"
    (mod,) = st.rows("sport_module")
    assert mod["approved_by"] == "gate" and mod["commit"] == commit
    v1 = approved / "badminton" / "v1"
    assert (v1 / "rules.yaml").is_file() and (v1 / "config.yaml").is_file()
    assert json.loads((v1 / "sport_module.json").read_text())["run_id"] == run["run_id"]
    # the next game of this sport uses the approved interpreter and asks for nothing
    g2 = eng.create_game("g_droid002", "badminton", t0_ms=0)
    assert not g2.needs_interpreter and g2.module.path == v1
    # the judge can ask for a new one
    eng.handle_ctl({"cmd": "regenerate_interpreter", "game_id": GAME, "args": {}})
    assert [r["trigger"]["source"] for r in st.rows("droid_run")].count("user") == 1


def test_a_failed_interpreter_run_is_announced_and_cleared(tmp_path: Path) -> None:
    (tmp_path / "badminton").mkdir()
    (tmp_path / "badminton" / "config.yaml").write_text("sport: badminton\n")
    st = MemoryState()
    eng = Engine(st, modules_dir=tmp_path, now_ms=clock())
    eng.create_game(GAME, "badminton", t0_ms=0)
    eng.start_game(GAME, "A")
    (run,) = st.rows("droid_run")
    st.set_droid_run_status({"run_id": run["run_id"], "status": "failed", "error": "checks still failing"})
    tick(eng)
    g = eng.games[GAME]
    assert g.interpreter_run is None and g.needs_interpreter
    assert any("couldn't write" in c["text"] for c in st.rows("call"))


def test_annotated_basketball_scores_two_and_three_from_the_pack(tmp_path: Path) -> None:
    d = tmp_path / "basketball"
    d.mkdir()
    (d / "config.yaml").write_text("sport: basketball\n")
    rules = {
        "sport": "basketball",
        "family": "possession",
        "version": 1,
        "teams": [{"team_id": "A", "name": "Red"}, {"team_id": "B", "name": "Blue"}],
        "field": {"frame": "half court", "landmarks": []},
        "scoring": {"template": "cumulative", "params": {"points_to_win": 1000, "win_by": 1}},
        "rules": [
            {"id": "three", "name": "Three", "tier": "AUTO", "kind": "basket", "check": "code", "outcome": "made_3",
             "when": "ev.type == 'shot' && ev.payload.made && ev.payload.behind_arc_p >= 0.5",
             "team": "ev.team_id", "points": 3, "text": "Three, {team}"},
            {"id": "two", "name": "Two", "tier": "AUTO", "kind": "basket", "check": "code", "outcome": "made_2",
             "when": "ev.type == 'shot' && ev.payload.made && ev.payload.behind_arc_p < 0.5",
             "team": "ev.team_id", "points": 2, "text": "Two, {team}"},
        ],
    }  # fmt: skip
    (d / "rules.yaml").write_text(yaml.safe_dump(rules))
    st = MemoryState()
    eng = Engine(st, modules_dir=tmp_path, now_ms=clock(), dead_after_point_s=0)
    g = eng.create_game(GAME, "basketball", t0_ms=0)
    assert g.module.annotated and not g.needs_interpreter
    eng.start_game(GAME, "A")

    def shot(t: float, team: str, arc: float, made: bool = True) -> dict:
        return annotated(t, "shot", "basketball", team_id=team, payload={
            "shooter_track_id": "p1", "release_pos_m": [0, 0], "behind_arc_p": arc, "made": made})  # fmt: skip

    for e in [shot(1, "A", 0.9), shot(5, "B", 0.1), shot(9, "A", 0.2, made=False), shot(12, "A", 0.1)]:
        eng.feed(e)
    assert scoring(st) == {"A": 5, "B": 2}
    assert not st.rows("droid_run")
