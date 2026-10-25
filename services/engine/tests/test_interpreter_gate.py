"""The interpreter gate (D-43): an annotated sport's rules.yaml must reproduce every labelled call; a house rule's gate
re-judges the live session against the pack in force so calls_changed is real. Fixtures are SYNTHETIC."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from trophy_engine.rejudge import write_session
from trophy_engine.replay_test import run_replay
from trophy_engine.replay_test.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[3]
TT = ROOT / "sports" / "table_tennis"
ANN = ROOT / "evals" / "fixtures" / "annotated"
SAMPLES = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis"
LET = {
    "id": "serve_net_let",
    "name": "Serve clips the net",
    "tier": "AUTO",
    "kind": "point",
    "when": "ev.type == 'net' && ev.payload.kind == 'touch' && has(ev.payload.serve) && ev.payload.serve",
    "check": "code",
    "outcome": "let",
    "text": "Let",
    "speech": "Let.",
}


def tt_with(tmp: Path, *rules: dict) -> Path:
    d = tmp / "table_tennis"
    shutil.copytree(TT, d, ignore=shutil.ignore_patterns("checks", "__pycache__"))
    pack = yaml.safe_load((d / "rules.yaml").read_text())
    pack["rules"] = [*rules, *pack["rules"]]
    (d / "rules.yaml").write_text(yaml.safe_dump(pack, sort_keys=False))
    return d


def test_fixtures_are_labelled_synthetic() -> None:
    for f in ANN.glob("*/SYNTHETIC_*"):
        text = f.read_text()
        assert "SYNTHETIC" in text, f


def test_golden_table_tennis_has_no_let_so_the_gate_fails_on_it() -> None:
    res = run_replay(TT, SAMPLES, annotated_dir=ANN / "table_tennis")
    assert not res.passed
    failed = {t["name"] for t in res.tests if not t["pass"]}
    assert "SYNTHETIC_let_out_fault:call:2@5.3s" in failed  # the let
    assert all(t["pass"] for t in res.tests if t["name"].startswith("rally_"))  # the golden l1 fixtures still pass


def test_a_let_rule_reproduces_every_label_and_the_golden_fixtures(tmp_path: Path) -> None:
    res = run_replay(tt_with(tmp_path, LET), SAMPLES, annotated_dir=ANN / "table_tennis", baseline_dir=TT)
    assert res.passed, [t for t in res.tests if not t["pass"]]
    assert {c["after"] for c in res.calls_changed} >= {"let"}


def test_badminton_interpreter_gate(tmp_path: Path) -> None:
    d = tmp_path / "badminton"
    d.mkdir()
    shutil.copy(ROOT / "sports" / "badminton" / "config.yaml", d / "config.yaml")
    # no rules.yaml yet: module:load fails, the gate says why
    res = run_replay(d, None, annotated_dir=ANN / "badminton")
    assert not res.passed and res.tests[0]["name"] == "module:load"
    rule = {"tier": "AUTO", "kind": "point", "check": "code", "points": 1, "text": "x", "speech": "x"}
    pack = {
        "sport": "badminton", "family": "flight", "version": 1,
        "teams": [{"team_id": "A", "name": "Near"}, {"team_id": "B", "name": "Far"}],
        "field": {"frame": "centre", "landmarks": []},
        "scoring": {"template": "rally", "params": {"points_to_win": 21, "win_by": 2, "cap": 30}},
        "rules": [
            {**rule, "id": "let", "name": "let", "outcome": "let", "points": 0,
             "when": "ev.type == 'net' && ev.payload.kind == 'touch' && !ev.payload.serve"},
            {**rule, "id": "into", "name": "into", "when": "ev.type == 'net' && ev.payload.kind == 'into'",
             "outcome": "fault", "team": "opponent(ev.payload.from_side)"},
            {**rule, "id": "out", "name": "out", "when": "ev.type == 'bounce' && ev.payload.p_in < 0.5",
             "outcome": "out", "team": "ev.side"},
            {**rule, "id": "in", "name": "in", "when": "ev.type == 'bounce' && ev.payload.p_in >= 0.5",
             "outcome": "point", "team": "opponent(ev.side)"},
        ],
    }  # fmt: skip
    (d / "rules.yaml").write_text(yaml.safe_dump(pack, sort_keys=False))
    res = run_replay(d, None, annotated_dir=ANN / "badminton")
    assert res.passed, [t for t in res.tests if not t["pass"]]
    # the serve that clips the net is legal in badminton: a let on it would be an extra call
    pack["rules"][0]["when"] = "ev.type == 'net' && ev.payload.kind == 'touch'"
    (d / "rules.yaml").write_text(yaml.safe_dump(pack, sort_keys=False))
    res = run_replay(d, None, annotated_dir=ANN / "badminton")
    assert not res.passed


def test_house_rule_gate_reports_calls_changed_on_this_session(tmp_path: Path) -> None:
    events = [json.loads(x) for x in (ANN / "table_tennis" / "SYNTHETIC_let_out_fault.events.jsonl").open()]
    game = {"game_id": "g_live0001", "sport": "table_tennis", "teams": [{"team_id": "A"}, {"team_id": "B"}],
            "params": {}}  # fmt: skip
    write_session(tmp_path / "session.json", game=game, first_server="A", events=events, rule_version="1",
                  dead_after_point_s=2.0, server_from_first_hit=False)  # fmt: skip
    cand = tt_with(tmp_path, LET)
    out = tmp_path / "r.json"
    code = cli_main(
        ["--module", str(cand), "--baseline", str(TT), "--session", str(tmp_path / "session.json"),
         "--annotated", str(ANN / "table_tennis"), "--samples", str(SAMPLES), "--house-rule", "--json", str(out),
         "--quiet"]
    )  # fmt: skip
    res = json.loads(out.read_text())
    assert code == 0 and res["passed"]
    session_changes = [c for c in res["calls_changed"] if ":" not in c["before"]]
    assert session_changes and session_changes[0]["after"] == "let" and session_changes[0]["t_s"] == 5.0
    # a house rule that breaks a labelled outcome is shown, not gated
    res2 = run_replay(TT, SAMPLES, annotated_dir=ANN / "table_tennis", house_rule=True)
    assert res2.passed
    assert any("not gated" in t["detail"] for t in res2.tests)
