"""The 3D check library (D-31): loading under the allowlist, the gate on the synthetic fixtures, the eventer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trophy_engine.check_test.checks import run_check_test
from trophy_engine.checks.api import Field, Track
from trophy_engine.checks.events import TrackEventer
from trophy_engine.checks.library import LibraryError, check_source, load_field, load_library, read_track
from trophy_engine.synth.track3d import generate

ROOT = Path(__file__).resolve().parents[3]
CHECKS = ROOT / "sports" / "table_tennis" / "checks"
FIX = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis_3d"


@pytest.fixture(scope="module")
def lib():
    return load_library(CHECKS)


@pytest.fixture(scope="module")
def fld():
    return load_field(FIX / "field.json")


@pytest.fixture(scope="module")
def game(fld):
    return read_track(FIX / "game_01.track3d.jsonl", fld), json.loads((FIX / "game_01.labels3d.json").read_text())


def test_golden_library_loads_and_is_uncalibrated(lib) -> None:
    assert set(lib.names()) >= {"phases", "bounces", "in_out", "contacts", "net_touch", "serve_toss", "rally_summary"}
    assert lib.calibrated is False  # the handwritten golden; a Droid run + approve sets true


def test_allowlist_refuses_io_and_imports() -> None:
    bad = "import os\nPARAMS = {}\ndef check(track, field, params=None, **q):\n    return open('x')\n"
    errs = check_source(bad, "x.py")
    assert any("import 'os'" in e for e in errs) and any("open()" in e for e in errs)
    assert check_source("PARAMS = {}\n", "y.py")  # no check()


def test_field_adapter_defaults_without_uncertainty() -> None:
    f = Field.from_json(
        {"sport": "table_tennis", "corners_m": [[-1.37, -0.76, 0], [1.37, -0.76, 0], [1.37, 0.76, 0], [-1.37, 0.76, 0]]}
    )
    assert f.calibrated is False and f.floor_z_m == pytest.approx(-0.76)
    t = Track.from_rows([{"t_s": 0.0, "xyz_m": [0, 0, 0.2], "conf": 0.9}], f)
    assert t.calibrated is False and t[0].sigma == f.sigma_default_m


def test_result_is_uncalibrated_unless_everything_is(lib, fld, game) -> None:
    tr, _ = game
    r = lib.run("rally_summary", tr, fld)
    assert r["calibrated"] is False  # golden library
    assert r["check"] == "rally_summary" and "ms" in r


def test_gate_passes_on_the_committed_fixtures() -> None:
    res = run_check_test(CHECKS, FIX)
    failed = [t for t in res.tests if not t["pass"]]
    assert res.passed, failed
    assert any(t["name"].endswith("in_out:accuracy") for t in res.tests)
    assert any(t["name"].endswith("calls:winners") for t in res.tests)


def test_eventer_incremental_matches_batch_and_is_deterministic(lib, fld, game) -> None:
    tr, labels = game
    a = TrackEventer(lib, fld, game_id="g_synth001").feed_all(tr)
    b = TrackEventer(lib, fld, game_id="g_synth001").feed_all(tr)
    assert a == b and len(a) > 20
    types = {e["type"] for e in a}
    assert {"serve_toss", "bounce", "contact", "ball_dead"} <= types
    # every rally in the labels produced a serve_toss and a ball_dead
    hints = {e.get("rally_no_hint") for e in a if e["type"] == "ball_dead"}
    assert hints == {r["rally_no"] for r in labels["rallies"]}
    # within one push events are time-ordered; across pushes a later-confirmed event may carry an earlier time


def test_no_wrong_auto_call_on_a_fresh_seed(tmp_path: Path, lib) -> None:
    generate(tmp_path, "g", seed=11, n_rallies=7)
    res = run_check_test(CHECKS, tmp_path)
    io = [t for t in res.tests if t["name"].endswith("in_out:accuracy")]
    assert io and "0 wrong at AUTO" in io[0]["after"], io


def test_library_run_unknown_check(lib, fld, game) -> None:
    with pytest.raises(LibraryError):
        lib.run("nope", game[0], fld)


@pytest.mark.parametrize(
    "line",
    [
        "from typing import get_type_hints",
        "from dataclasses import dataclass",
        "import statistics\nx = statistics.sys",
        "import trophy_engine.checks.api as a",
        "from trophy_engine.checks.api import math",  # imported there, not in its __all__
    ],
)
def test_check_loader_refuses_the_escapes_from_review(line: str) -> None:
    """Review blocker 2, for Droid-written checks."""
    src = f"{line}\n\nPARAMS = {{}}\n\n\ndef check(track, field, params=None, **q):\n    return None\n"
    assert check_source(src, "x.py")
