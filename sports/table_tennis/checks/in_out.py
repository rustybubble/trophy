"""in_out: was the ball in at this instant? The bounce nearest `t_s` (within `search_s`), its signed distance to
the nearest line, p_in = Phi(d / sigma) with sigma inflated by speed * timing skew, and the edge split within
`edge_band_m`: top edge (good), side face (out) or clearly on the surface.

verdict: "in" | "out" | "edge" | "no_bounce"; p = P(in); evidence has the line, margin, sigma and edge probabilities.
"""

from __future__ import annotations

from trophy_engine.checks.api import Field, Track, edge_probs, merge_params, motion_sigma, phi, refine_bounce, result

PARAMS = {
    "min_conf": 0.3,
    "search_s": 0.4,  # look for a low point within this of the asked time
    "surface_band_m": 0.045,
    "floor_band_m": 0.15,
    "edge_band_m": 0.03,
    "side_face_z_m": [-0.06, 0.012],
    "side_face_x_m": 0.06,
    "side_face_slack_m": 0.02,
    "min_descent_m_s": 0.4,
    "net_zone_m": 0.12,  # a low point this close to the net plane, above the surface, is the net
    "timing_sigma_s": 0.008,  # how well the bounce instant is known between 30 Hz samples; adds speed * this to sigma
}


def check(track: Track, field: Field, params=None, t_s=None, **q):
    p = merge_params(PARAMS, params)
    if t_s is None:
        t_s = track.t1
    tr = track.window(t_s - p["search_s"], t_s + p["search_s"]).good(p["min_conf"])
    cands = []
    rev_x, rev_y = set(tr.reversals(0)), set(tr.reversals(1))

    def at_face(i, x, y, z_rel) -> bool:
        if not (p["side_face_z_m"][0] <= z_rel <= p["side_face_z_m"][1]):
            return False
        name, d = field.d_min(x, y)
        return (
            d <= p["side_face_slack_m"]
            and -d <= p["side_face_x_m"]
            and i in (rev_x if name.startswith("end") else rev_y)
        )

    for i in tr.local_minima_z():
        if min(tr.step_velocity(k)[2] for k in (i - 2, i - 1, i) if k > 0) > -p["min_descent_m_s"]:
            continue
        smp = tr[i]
        if abs(smp.x - field.net_x_m) <= p["net_zone_m"] and smp.z - field.surface_z_m >= 0.03:
            continue  # the net stopped it
        if abs(smp.z - field.floor_z_m) <= p["floor_band_m"] + 0.1:
            plane = field.floor_z_m
        elif smp.z - field.surface_z_m <= 0.13:
            plane = field.surface_z_m
        else:
            continue  # a low point in the air is a racket hit, not a bounce
        t, x, y, z, dt_sig, solved, v_in = refine_bounce(tr, i, plane)
        z_rel = z - field.surface_z_m
        on_floor = abs(z - field.floor_z_m) <= p["floor_band_m"]
        if not solved and not on_floor and abs(z_rel) > p["surface_band_m"]:
            continue
        cands.append(
            (
                abs(t - t_s),
                i,
                t,
                x,
                y,
                z,
                at_face(i, x, y, smp.z - field.surface_z_m),
                dt_sig,
                v_in if solved else tr.speed(i),
            )
        )
    for i in rev_x | rev_y:
        s = tr[i]
        if at_face(i, s.x, s.y, s.z - field.surface_z_m):
            cands.append((abs(s.t - t_s), i, s.t, s.x, s.y, s.z, True, p["timing_sigma_s"], tr.speed(i)))
    if not cands:
        return result(
            "in_out",
            "no_bounce",
            p=None,
            t_s=t_s,
            evidence={"searched_s": p["search_s"]},
            text="no bounce near that time",
        )
    cands.sort(key=lambda c: (c[0], c[1]))
    _, i, t, x, y, z, reversal, dt_sig, v_in = cands[0]
    smp = tr[i]
    sig = motion_sigma(smp.sigma, v_in, field.skew_sigma_s + dt_sig)
    lines = field.lines(x, y)
    line, d_min = min(lines.items(), key=lambda kv: kv[1])
    z_rel = z - field.surface_z_m
    if abs(z - field.floor_z_m) <= p["floor_band_m"]:
        p_in = 0.0
        verdict = "out"
        edge = None
    else:
        p_in = phi(d_min / sig)
        edge = edge_probs(d_min, sig, p["edge_band_m"], z_rel, sig)
        side_face = reversal and d_min < 0 and z_rel <= p["side_face_z_m"][1]
        if side_face:
            p_in = min(p_in, 0.5 * (1.0 - phi((field.surface_z_m - z) / sig)))
        verdict = "edge" if edge is not None and edge["surface"] < 0.5 else ("in" if p_in >= 0.5 else "out")
    cm = abs(d_min) * 100
    text = f"{verdict}: {cm:.1f} cm {'inside' if d_min >= 0 else 'outside'} {line}, sigma {sig * 100:.1f} cm"
    return result(
        "in_out",
        verdict,
        p=p_in,
        t_s=t,
        sigma_m=sig,
        evidence={
            "pos_m": [x, y, z],
            "line": line,
            "margin_m": d_min,
            "d_lines_m": lines,
            "edge": edge,
            "side": field.side(x),
            "z_rel_m": z_rel,
            "reversal": reversal,
        },
        text=text,
    )
