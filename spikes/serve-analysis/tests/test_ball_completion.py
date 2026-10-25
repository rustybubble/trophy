import numpy as np
import pytest

from trophy.replay.ball_completion import complete_ball_track


def test_short_gaps_filled_and_evidence_separate():
    t = np.arange(30)/30
    p = np.c_[t*.1, t*2-1, .3 + .1*np.sin(t*3)]
    p[10:13] = np.nan
    before = p.copy()
    q, status, _ = complete_ball_track(t, p)
    assert np.isfinite(q).all()
    assert status[11] == 'interpolated'
    assert np.isnan(p[11]).all()
    np.testing.assert_equal(p, before)
    assert abs(q[11, 1]-(t[11]*2-1)) < .02


def test_long_gaps_and_unsupported_edges_stay_missing():
    t = np.arange(120)/30
    p = np.full((120, 3), np.nan)
    p[30:40] = [.1, -.5, .2]
    p[100:110] = [.1, .5, .2]
    q, status, _ = complete_ball_track(t, p, max_gap_s=.5, extrapolate_s=.2)
    assert np.isnan(q[0]).all() and np.isnan(q[70]).all()
    assert status[29] == 'extrapolated'
    assert status[70] == 'unavailable'


def test_impact_turn_does_not_overshoot_or_go_through_table():
    t = np.arange(31)/30
    p = np.c_[np.zeros(31), 1-np.abs(t-.5)*2, np.abs(t-.5)]
    q, status, report = complete_ball_track(t, p)
    assert 15 in report['impact_candidates']
    assert q[:, 1].max() <= 1+1e-9
    assert q[:, 2].min() >= .02
    assert len(status) == 31


def test_invalid_times_rejected():
    with pytest.raises(ValueError, match='increasing'):
        complete_ball_track([0, .1, .1], np.zeros((3, 3)))
