"""contacts: racket hits. A hit is a jump between the mean velocity over the two steps before a sample and the two
steps after the next one (|dv| >= `hit_dv_m_s`; the hit itself falls inside the skipped step), at or beyond
`near_end_m` of an end line and at least `min_height_m` above
the surface (a bounce is a jump too, but at surface level). The serve hit is the first contact of a rally.

verdict: [{t_s, side, pos_m, kind, height_m, dv_m_s}]
"""

from __future__ import annotations

import math

from trophy_engine.checks.api import Field, Track, merge_params, result

PARAMS = {
    "min_conf": 0.3,
    "hit_dv_m_s": 2.5,  # velocity jump (two-step means before vs after) that marks a hit
    "hit_h_jump_m_s": 1.5,  # or: horizontal speed goes from under hit_h_before_m_s to over this (a serve hit)
    "hit_h_before_m_s": 0.7,
    "near_end_m": 0.45,  # |x| >= half length - this
    "min_height_m": 0.08,  # relative to the surface: below this a jump is a bounce, not a hit
    "min_dt_s": 0.15,
}


def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    tr = track.window(t0, t1).good(p["min_conf"])
    out = []
    for i in range(2, len(tr) - 3):
        a = tr.mean_velocity(i - 2, i)
        b = tr.mean_velocity(i + 1, i + 3)  # the hit is inside step i -> i+1; the ball at i is still pre-hit
        if a == (0.0, 0.0, 0.0) or b == (0.0, 0.0, 0.0):
            continue
        dv = math.sqrt(sum((bb - aa) ** 2 for aa, bb in zip(a, b, strict=False)))
        s = tr[i]
        near_end = abs(s.x - field.cx_m) >= field.half_l - p["near_end_m"]
        h_before, h_after = math.hypot(a[0], a[1]), math.hypot(b[0], b[1])
        jump = dv >= p["hit_dv_m_s"] or (h_before <= p["hit_h_before_m_s"] and h_after >= p["hit_h_jump_m_s"])
        if jump and near_end and s.z - field.surface_z_m >= p["min_height_m"]:
            if out and s.t - out[-1]["t_s"] < p["min_dt_s"]:
                if dv > out[-1]["dv_m_s"]:
                    out[-1] = _entry(field, s, dv)
                continue
            out.append(_entry(field, s, dv))
    text = f"{len(out)} racket contacts"
    return result("contacts", out, t_s=out[-1]["t_s"] if out else None, evidence={"n": len(out)}, text=text)


def _entry(field: Field, s, dv):
    return {
        "t_s": s.t,
        "side": field.side(s.x),
        "pos_m": [s.x, s.y, s.z],
        "kind": "racket",
        "height_m": s.z - field.surface_z_m,
        "dv_m_s": dv,
    }
