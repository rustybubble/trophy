"""net_touch: what happened at the net. For each crossing of the net plane the clearance over the net cord (ball
bottom minus net height); `touch` when the clearance is within sigma of zero or below. An approach to within
`window_m` of the plane that reverses without crossing is `into` (the ball came back on the hitter's side).

verdict: [{t_s, kind: touch|into, from_side, clearance_m, p, sigma_m}]; `over` crossings are in evidence only.
"""

from __future__ import annotations

from trophy_engine.checks.api import Field, Track, interp_crossing, merge_params, motion_sigma, phi, result

PARAMS = {
    "min_conf": 0.3,
    "window_m": 0.15,  # a reversal within this of the net plane is 'into'
    "touch_p": 0.5,  # report a touch when P(clearance <= 0) is at least this
    "min_dt_s": 0.2,
    "back_s": 0.35,  # a below-cord crossing that returns within this went into the net
}


def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    tr = track.window(t0, t1).good(p["min_conf"])
    out = []
    overs = []
    net_x = field.net_x_m
    for i in range(len(tr) - 1):
        a, b = tr[i], tr[i + 1]
        if not tr.contiguous(i, i + 1):
            continue  # not one flight: the ball was lost and found again elsewhere
        if (a.x - net_x) * (b.x - net_x) < 0:
            t, x, y, z = interp_crossing(a, b, net_x, "x")
            sig = motion_sigma(a.sigma, tr.speed(i), field.skew_sigma_s)
            clearance = (z - field.ball_r_m) - (field.surface_z_m + field.net_height_m)
            p_touch = 1.0 - phi(clearance / sig)
            from_side = field.side(a.x)
            if p_touch >= p["touch_p"]:
                # below the cord and straight back to the side it came from: it went into the net
                came_back = any(
                    (tr[j].x - net_x) * (a.x - net_x) > 0 and tr.contiguous(i, j)
                    for j in range(i + 2, len(tr))
                    if tr[j].t - t <= p["back_s"]
                )
                kind = "into" if came_back and clearance < 0 else "touch"
                out.append(
                    {
                        "t_s": t,
                        "kind": kind,
                        "from_side": from_side,
                        "clearance_m": clearance,
                        "p": p_touch,
                        "sigma_m": sig,
                    }
                )
            else:
                overs.append({"t_s": t, "clearance_m": clearance, "p_touch": p_touch})
    for i in tr.vx_reversals():
        s = tr[i]
        if abs(s.x - net_x) <= p["window_m"] and s.z - field.surface_z_m <= field.net_height_m + 0.1:
            sig = motion_sigma(s.sigma, tr.speed(i), field.skew_sigma_s)
            out.append(
                {
                    "t_s": s.t,
                    "kind": "into",
                    "from_side": field.side(s.x),
                    "clearance_m": s.z - field.ball_r_m - field.surface_z_m - field.net_height_m,
                    "p": phi((p["window_m"] - abs(s.x - net_x)) / sig),
                    "sigma_m": sig,
                }
            )
    out.sort(key=lambda e: e["t_s"])
    dedup = []
    for e in out:
        if dedup and e["t_s"] - dedup[-1]["t_s"] < p["min_dt_s"]:
            continue
        dedup.append(e)
    text = f"{len(dedup)} net events, {len(overs)} clean crossings"
    return result(
        "net_touch",
        dedup,
        t_s=dedup[-1]["t_s"] if dedup else None,
        evidence={"overs": overs, "n": len(dedup)},
        text=text,
    )
