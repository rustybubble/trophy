import random

import pytest

from trophy import ids
from trophy.timebase import ClockFit, t_game_s, t_srv_ms_from_game


def test_ids_formats():
    assert ids.is_game_id(ids.new_game_id())
    assert ids.is_cam_id(ids.new_cam_id())
    assert ids.PLAYER_ID_RE.match(ids.new_player_id())
    assert len(ids.new_join_key()) == 22
    assert ids.is_ulid(ids.new_ulid())
    assert not ids.is_game_id("g_ILOU0000")  # excluded Crockford letters


def test_game_time_roundtrip():
    assert t_game_s(t_srv_ms_from_game(12.5, 1_000.0), 1_000.0) == pytest.approx(12.5)


def _simulate(fit: ClockFit, offset_ms: float, drift_ppm: float, n: int, seed: int = 1, span_ms: float = 60_000):
    """Phone clock = server clock - offset, drifting; asymmetric random network delays."""
    rng = random.Random(seed)
    t_srv = 1.7e12
    for _ in range(n):
        t_srv += span_ms / n
        up, down = rng.uniform(2, 40), rng.uniform(2, 40)

        def phone(ts):
            return ts - offset_ms - drift_ppm * 1e-6 * (ts - 1.7e12)

        t0 = phone(t_srv)
        t1 = t_srv + up
        t2 = t1 + 0.3
        t3 = phone(t2 + down)
        fit.add(t0, t1, t2, t3)
    return phone


def test_clock_fit_offset_only():
    fit = ClockFit()
    phone = _simulate(fit, offset_ms=5_000.0, drift_ppm=0.0, n=40)
    t_srv = 1.7e12 + 30_000
    err = abs(fit.to_srv(phone(t_srv)) - t_srv)
    assert err < 10, err
    assert fit.sync_err_ms < 25


def test_clock_fit_tracks_drift():
    fit = ClockFit(window=128)
    phone = _simulate(fit, offset_ms=-1234.0, drift_ppm=80.0, n=120, span_ms=120_000)
    t_srv = 1.7e12 + 120_000
    assert abs(fit.to_srv(phone(t_srv)) - t_srv) < 10
    assert fit.drift_ppm == pytest.approx(80.0, abs=40)  # phone runs slow -> server-minus-phone grows


def test_clock_fit_rejects_garbage():
    fit = ClockFit()
    assert fit.add(10, 5, 4, 20) is None  # t2 < t1
    assert not fit.ready
