"""Fallback preserves real source identity and cannot supply an invented point."""

import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "tools/fuse_tt_tracks.py"
spec = importlib.util.spec_from_file_location("tt_fusion", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(seq, x=None, score=None):
    return dict(
        seq=seq,
        pts=seq * 256,
        time_base="1/15360",
        x=x,
        y=x,
        score=score,
        status="missing" if x is None else "observed_2d",
    )


def test_observed_neural_positions_never_moved():
    neural = [row(0, 5, 0.7), row(1, None)]
    color = [row(0, 200, 0.9), row(1, 10, 0.8)]
    result, n = module.fuse(neural, color)
    assert result[0]["x"] == 5
    assert result[1]["x"] == 10 and result[1]["status"] == "color_candidate_2d"
    assert n == 1 and neural[1]["x"] is None


def test_absence_stays_missing_no_prediction():
    result, n = module.fuse([row(0), row(1)], [row(0), row(1, 10, 0.3)])
    assert all(r["x"] is None for r in result) and n == 0


def test_timestamp_identity_mismatch_rejected():
    wrong = row(0, 10, 0.9)
    wrong["pts"] = 999
    with pytest.raises(ValueError, match="identity"):
        module.fuse([row(0)], [wrong])


def test_missing_source_frame_rejected():
    with pytest.raises(ValueError, match="counts"):
        module.fuse([row(0)], [])
