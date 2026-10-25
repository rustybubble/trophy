"""rally_summary: informational numbers for a window: duration, peak speed, how many table-level low points
(shots are counted by `contacts`). Never a decision.

verdict: {"duration_s", "max_speed_m_s", "n_low_points", "samples"}
"""

from __future__ import annotations

from trophy_engine.checks.api import Field, Track, merge_params, result

PARAMS = {"min_conf": 0.3, "surface_band_m": 0.07}


def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    tr = track.window(t0, t1).good(p["min_conf"])
    if len(tr) < 2:
        return result(
            "rally_summary",
            {"duration_s": 0.0, "max_speed_m_s": 0.0, "n_low_points": 0, "samples": len(tr)},
            text="no track",
        )
    vmax = max(tr.speed(i) for i in range(len(tr)))
    lows = [i for i in tr.local_minima_z() if abs(tr[i].z - field.surface_z_m) <= p["surface_band_m"]]
    v = {"duration_s": tr.t1 - tr.t0, "max_speed_m_s": vmax, "n_low_points": len(lows), "samples": len(tr)}
    return result(
        "rally_summary",
        v,
        t_s=tr.t1,
        text=f"{v['duration_s']:.1f} s, peak {vmax:.1f} m/s, {len(lows)} table-level low points",
    )
