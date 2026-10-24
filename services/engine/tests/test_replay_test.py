"""replay_test: the golden module passes on the synthetic fixtures; a broken module fails with a readable table."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from trophy_engine.replay_test.checks import format_table, run_replay
from trophy_engine.replay_test.cli import main

ROOT = Path(__file__).resolve().parents[3]
TT = ROOT / "sports" / "table_tennis"
SAMPLES = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis"


def test_golden_passes() -> None:
    res = run_replay(TT, SAMPLES)
    assert res.passed, format_table(res)
    assert res.calls_changed == []
    assert res.engine.startswith("events-only")
    for name, counts in res.events.items():
        assert counts["bounce"] >= 6, (name, counts)
        assert counts["ball_dead"] == 1


def test_results_json_matches_contract(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    assert main(["--module", str(TT), "--samples", str(SAMPLES), "--json", str(out), "--quiet"]) == 0
    res = json.loads(out.read_text())
    from trophy.contracts import DroidRunResults  # generated from droidrun.schema.json

    DroidRunResults.model_validate(res)
    assert res["passed"] is True
    assert all(t["pass"] for t in res["tests"])


def test_broken_module_fails_readably(tmp_path: Path) -> None:
    cand = tmp_path / "table_tennis"
    shutil.copytree(TT, cand)
    cfg = (cand / "config.yaml").read_text().replace("min_vy_px_s: 40", "min_vy_px_s: 100000")
    (cand / "config.yaml").write_text(cfg)
    res = run_replay(cand, SAMPLES, baseline_dir=TT)
    assert not res.passed
    table = format_table(res)
    assert "bounce:count" in table and "FAIL" in table
    counts = [t for t in res.tests if t["name"].endswith("bounce:count")]
    assert counts and all(t["before"] and not t["pass"] for t in counts)


def test_exception_in_events_is_a_failed_check(tmp_path: Path) -> None:
    cand = tmp_path / "table_tennis"
    shutil.copytree(TT, cand)
    (cand / "events.py").write_text("def events(observations, state):\n    raise ValueError('boom')\n")
    res = run_replay(cand, SAMPLES)
    assert not res.passed
    assert any(t["name"].endswith("events:runs") and "boom" in t["after"] for t in res.tests)


def test_wrong_event_type_is_rejected(tmp_path: Path) -> None:
    cand = tmp_path / "table_tennis"
    shutil.copytree(TT, cand)
    (cand / "events.py").write_text(
        "def events(observations, state):\n    return [{'schema': 'trophy.event.v1', 'type': 'shot'}]\n"
    )
    res = run_replay(cand, SAMPLES)
    assert any(t["name"].endswith("events:schema") and not t["pass"] for t in res.tests)
