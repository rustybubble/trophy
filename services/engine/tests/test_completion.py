"""Short-gap completion of the live 2D track (sportmod.completion, after Mu Du's complete_ball_track, D-39)."""

from __future__ import annotations

import math

from trophy_engine.sportmod.api import BallSample
from trophy_engine.sportmod.completion import fill_short_gaps, pchip_eval, pchip_slopes


def track(n: int, missing: set[int], fps: float = 30.0) -> list[BallSample]:
    out = []
    for i in range(n):
        t = i / fps
        px = None if i in missing else (100 + 400 * t, 300 + 200 * math.sin(3 * t))
        out.append(BallSample("c", t, i, px, 0.0 if px is None else 0.9))
    return out


def test_short_gaps_are_filled_close_to_the_true_path_and_measurements_untouched():
    raw = track(30, {10, 11, 12})
    out, n = fill_short_gaps(raw, max_gap_s=0.25)
    assert n == 3
    for i in (10, 11, 12):
        t = i / 30
        assert out[i].px is not None and abs(out[i].px[1] - (300 + 200 * math.sin(3 * t))) < 1.5
        assert out[i].conf < 0.9  # an estimate, never as confident as a measurement
    assert all(out[i] == raw[i] for i in range(30) if i not in (10, 11, 12))


def test_long_gaps_track_ends_and_thin_support_stay_missing():
    out, n = fill_short_gaps(track(40, set(range(5, 15))), max_gap_s=0.25)  # 0.37 s gap
    assert n == 0 and out[8].px is None
    out, n = fill_short_gaps(track(10, {0, 1, 9}), max_gap_s=0.25)  # no extrapolation past the ends
    assert n == 0
    out, n = fill_short_gaps(track(10, {1, 3}), max_gap_s=0.25)  # one measured sample before the first gap
    assert out[1].px is None and out[3].px is not None


def test_pchip_does_not_overshoot_a_bounce_it_cannot_see():
    # the lowest point on screen (largest y) is missing: the fill must not go below the measured neighbours
    ts = [0.0, 1 / 30, 2 / 30, 5 / 30, 6 / 30, 7 / 30]
    ys = [400.0, 450.0, 480.0, 470.0, 430.0, 390.0]
    m = pchip_slopes(ts, ys)
    for t in (3 / 30, 4 / 30):
        assert pchip_eval(ts, ys, m, t) <= max(ys) + 1e-9
