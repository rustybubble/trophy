"""bounces: every bounce in a window, with where it landed and how sure we are.

A bounce is a local minimum of z. Refined with a parabola through the three samples around it, mapped to the
surface: within `surface_band_m` of the table top and not clearly off it -> `table` (with edge probabilities
inside `edge_band_m` of a line); within `floor_band_m` of the floor -> `floor`. A low point that is also an x
reversal near the end of the table at or below the top is a `side_face` hit (out). A low point far above the
surface is a racket hit, which `contacts` reports, not this check.

verdict: [{t_s, pos_m, sigma_m, side, surface, d_lines_m, p_in, edge|None, conf}]
"""

from __future__ import annotations

import math

from trophy_engine.checks.api import Field, Track, edge_probs, merge_params, motion_sigma, phi, refine_bounce, result

PARAMS = {
    "min_conf": 0.3,
    "surface_band_m": 0.045,  # |z - surface| below this: a table-level low point (when the flight solver cannot place it)  # noqa: E501
    "floor_band_m": 0.15,  # z within this of the floor: a floor bounce
    "plane_margin_m": 0.04,  # a table-level low point farther outside the lines than this is not on the table
    "edge_band_m": 0.03,  # report edge probabilities within this of a line
    "side_face_z_m": [-0.06, 0.012],  # z relative to the surface where an x-reversal at the end is a side-face hit
    "side_face_x_m": 0.06,  # at most this far outside the line
    "side_face_slack_m": 0.02,  # or this far inside it (noise): a ball below the top cannot be on the table
    "min_dt_s": 0.08,  # two low points closer than this are one bounce
    "min_descent_m_s": 0.4,  # the ball must be falling at least this fast into a bounce
    "net_zone_m": 0.12,  # a low point this close to the net plane, above the surface, is the net
    "timing_sigma_s": 0.008,  # how well the bounce instant is known between 30 Hz samples; adds speed * this to sigma
}


def _at_face(field: Field, p, i, x, y, z_rel, rev_x, rev_y) -> bool:
    """A velocity reversal normal to the nearest line, at or just outside it (within sigma), at or below the top:
    the ball hit the table's face."""
    z_lo, z_hi = p["side_face_z_m"]
    if not (z_lo <= z_rel <= z_hi):
        return False
    name, d_min = field.d_min(x, y)
    if d_min > p["side_face_slack_m"] or -d_min > p["side_face_x_m"]:
        return False
    return i in (rev_x if name.startswith("end") else rev_y)


def _entry(field: Field, p, t, x, y, z, sigma, speed, conf, surface, dt_sigma=None, solved=False):
    sig = motion_sigma(sigma, speed, field.skew_sigma_s + (p["timing_sigma_s"] if dt_sigma is None else dt_sigma))
    lines = field.lines(x, y)
    name, d_min = min(lines.items(), key=lambda kv: kv[1])
    p_in = phi(d_min / sig)
    edge = edge_probs(d_min, sig, p["edge_band_m"], z - field.surface_z_m, sig) if surface != "floor" else None
    if surface == "side_face":
        p_in = min(p_in, 0.5 * (1.0 - phi((field.surface_z_m - z) / sig)))
    return {
        "t_s": t,
        "pos_m": [x, y, z],
        "sigma_m": sig,
        "side": field.side(x),
        "surface": surface,
        "d_lines_m": lines,
        "nearest_line": name,
        "d_min_m": d_min,
        "p_in": p_in,
        "edge": edge,
        "conf": conf,
        "solved": solved,
    }


def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    tr = track.window(t0, t1).good(p["min_conf"])
    out = []
    z_lo, z_hi = p["side_face_z_m"]
    rev_x, rev_y = set(tr.reversals(0)), set(tr.reversals(1))
    for i in tr.local_minima_z():
        vin = min(tr.step_velocity(k)[2] for k in (i - 2, i - 1, i) if k > 0)
        if vin > -p["min_descent_m_s"]:
            continue
        smp = tr[i]
        speed = tr.speed(i)
        if abs(smp.x - field.net_x_m) <= p["net_zone_m"] and smp.z - field.surface_z_m >= 0.03:
            continue  # stopped by the net (net_touch reports it), not a bounce
        # which plane the ball was heading for: the floor, the table top, or neither (a hit in the air)
        if abs(smp.z - field.floor_z_m) <= p["floor_band_m"] + 0.1:
            plane, surface = field.floor_z_m, "floor"
        elif smp.z - field.surface_z_m <= 0.13:
            plane, surface = field.surface_z_m, "table"
        else:
            continue
        t, x, y, z, dt_sig, solved, v_in = refine_bounce(tr, i, plane)
        speed = v_in if solved else speed
        z_rel = z - field.surface_z_m
        _, d_min = field.d_min(x, y)
        if surface == "floor":
            if solved or abs(z - field.floor_z_m) <= p["floor_band_m"]:
                out.append(_entry(field, p, t, x, y, z, smp.sigma, speed, smp.conf, "floor", dt_sig))
        elif (solved or abs(z_rel) <= p["surface_band_m"]) and d_min >= -p["plane_margin_m"]:
            side_face = _at_face(field, p, i, x, y, smp.z - field.surface_z_m, rev_x, rev_y)
            out.append(
                _entry(field, p, t, x, y, z, smp.sigma, speed, smp.conf, "side_face" if side_face else "table", dt_sig)
            )
    # a reversal into the table's face at or below the top that is not a z-minimum is also a side-face hit
    for i in sorted(rev_x | rev_y):
        smp = tr[i]
        z_rel = smp.z - field.surface_z_m
        nxt = tr[i + 1] if i + 1 < len(tr) else smp
        outside_after = field.d_min(nxt.x, nxt.y)[1] < 0 and nxt.z - field.surface_z_m <= p["side_face_z_m"][1]
        if (
            _at_face(field, p, i, smp.x, smp.y, z_rel, rev_x, rev_y)
            and outside_after
            and not any(abs(b["t_s"] - smp.t) < p["min_dt_s"] for b in out)
        ):
            out.append(_entry(field, p, smp.t, smp.x, smp.y, smp.z, smp.sigma, tr.speed(i), smp.conf, "side_face"))
    out.sort(key=lambda b: b["t_s"])
    dedup = []
    for b in out:
        if dedup and b["t_s"] - dedup[-1]["t_s"] < p["min_dt_s"]:
            if (b["solved"], -b["pos_m"][2]) > (dedup[-1]["solved"], -dedup[-1]["pos_m"][2]):
                dedup[-1] = b
            continue
        dedup.append(b)
    n_table = sum(1 for b in dedup if b["surface"] == "table")
    text = f"{len(dedup)} bounces ({n_table} on the table)"
    sig = min((b["sigma_m"] for b in dedup), default=math.nan)
    return result(
        "bounces",
        dedup,
        t_s=dedup[-1]["t_s"] if dedup else None,
        sigma_m=None if math.isnan(sig) else sig,
        evidence={"n": len(dedup), "n_table": n_table},
        text=text,
    )
