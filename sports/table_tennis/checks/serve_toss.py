"""serve_toss: the serve from the open palm to the hit (D-22). Release = where the ball was held (the mean of the
still samples before it rose faster than `toss_vz_m_s`); apex = the vertex of a least-squares parabola through the
samples around the highest one; contact = the last sample before the ball's horizontal speed jumps past
`hit_h_speed_m_s`. height = apex.z - release.z; angle = max(release->apex, apex->contact) from vertical, each from
a least-squares line through that leg's samples. Legal when height > `min_toss_m` and angle < `max_angle_deg`;
p is the probability of legality given sigma.

verdict: {"legal": bool, "height_m", "angle_deg", "too_low": bool, "angled": bool} | "no_serve"
"""

from __future__ import annotations

import math

from trophy_engine.checks.api import Field, Track, angle_from_vertical, line_fit, merge_params, phi, quad_fit, result

PARAMS = {
    "min_conf": 0.3,
    "toss_vz_m_s": 0.7,
    "hit_dv_m_s": 2.5,  # velocity jump (two-step means before vs after the kink step) that marks the hit
    "hit_h_speed_m_s": 1.5,  # or the horizontal speed jumps from under hit_h_before_m_s to over this
    "hit_h_before_m_s": 0.7,
    "min_toss_m": 0.1524,  # 6 in (house value, D-22); ittf_strict 0.16
    "max_angle_deg": 30.0,
    "window_s": 2.0,  # how far after t_start the hit must come
    "lookback_s": 0.6,
    "hit_below_release_m": 0.15,  # the hit comes before the ball falls this far under the release height
    "still_s": 0.25,  # the held samples averaged for the release point
}


def check(track: Track, field: Field, params=None, t_start=None, **q):
    p = merge_params(PARAMS, params)
    if t_start is None:
        t_start = track.t0
    tr = track.window(t_start - p["lookback_s"], t_start + p["window_s"]).good(p["min_conf"])
    s = tr.samples
    # release: the sample at t_start (phases' last still sample) when it rises right after; else the first rise
    i_rel = None
    j = tr.index_at(t_start)
    if (
        s
        and abs(s[j].t - t_start) <= 0.05
        and any(tr.step_velocity(k)[2] >= p["toss_vz_m_s"] for k in range(j + 1, min(len(s), j + 4)))
    ):
        i_rel = j
    else:
        for i in range(1, len(s)):
            if s[i].t >= t_start - 0.1 and tr.step_velocity(i)[2] >= p["toss_vz_m_s"]:
                i_rel = i - 1
                break
    if i_rel is None:
        return result("serve_toss", "no_serve", t_s=t_start, evidence={}, text="no toss found")
    held = [x for x in s[: i_rel + 1] if s[i_rel].t - x.t <= p["still_s"]] or [s[i_rel]]
    rel = (sum(x.x for x in held) / len(held), sum(x.y for x in held) / len(held), sum(x.z for x in held) / len(held))
    t_rel = s[i_rel].t
    sigma = s[i_rel].sigma
    # apex: the highest sample after the release before z falls back toward the release height
    i_apex = i_rel
    for i in range(i_rel + 1, len(s)):
        if s[i].z >= s[i_apex].z:
            i_apex = i
        elif s[i].z < s[i_apex].z - 0.02:
            break
    lo, hi = max(i_rel + 1, i_apex - 2), min(len(s) - 1, i_apex + 2)
    fit = quad_fit([x.t for x in s[lo : hi + 1]], [x.z for x in s[lo : hi + 1]]) if hi - lo >= 2 else None
    if fit is not None and fit[2] < 0 and s[lo].t <= fit[0] <= s[hi].t:
        t_apex, z_apex = fit[0], fit[1]
        x_apex, y_apex, _ = tr.at(t_apex)
    else:
        t_apex, x_apex, y_apex, z_apex = s[i_apex].t, s[i_apex].x, s[i_apex].y, s[i_apex].z
    # contact: the last sample before the velocity kink. The jump between the two steps before a sample and the
    # two after the next grows as the window slides onto the kink and peaks at the sample just before it, so take
    # the first local maximum above the threshold (the serve's own bounce comes later and is not reached).
    # the paddle meets the ball near palm height: search from the apex down to `hit_below_release_m` under the
    # release height, take the first clear kink, else the strongest one in that window
    i_hit = None
    best = None
    strongest = None
    for i in range(i_apex + 1, len(s) - 3):
        if s[i].z < rel[2] - p["hit_below_release_m"]:
            break
        a = tr.mean_velocity(i - 2, i)
        b = tr.mean_velocity(i + 1, i + 3)
        if a == (0.0, 0.0, 0.0) or b == (0.0, 0.0, 0.0):
            continue
        dv = math.sqrt(sum((bb - aa) ** 2 for aa, bb in zip(a, b, strict=False)))
        h_before, h_after = math.hypot(a[0], a[1]), math.hypot(b[0], b[1])
        if strongest is None or dv > strongest[0]:
            strongest = (dv, i)
        hit = dv >= p["hit_dv_m_s"] or (h_before <= p["hit_h_before_m_s"] and h_after >= p["hit_h_speed_m_s"])
        if best is not None and dv < best[0]:
            break
        if hit or best is not None:
            best = (dv, i)
    if best is not None:
        i_hit = best[1]
    elif strongest is not None:
        i_hit = strongest[1]
    if i_hit is None:
        i_hit = len(s) - 1
    hit = s[i_hit]
    height = z_apex - rel[2]
    # each leg: horizontal travel from lines x(t), y(t) through the leg's samples; vertical extent from the fitted
    # apex and the release / contact heights (x(z) regressions break down near the apex, where z is flat)
    # the toss is one free flight, so its horizontal velocity is constant: fit it over every toss sample at once
    toss = s[i_rel + 1 : i_hit + 1]
    n_rise = max(1, i_apex - i_rel)
    fx = line_fit([q.t for q in toss], [q.x for q in toss])
    fy = line_fit([q.t for q in toss], [q.y for q in toss])
    v_h = math.hypot(fx[1], fy[1]) if fx and fy else 0.0
    rise = angle_from_vertical(v_h * (t_apex - t_rel), 0.0, height)
    fall = angle_from_vertical(v_h * (hit.t - t_apex), 0.0, max(z_apex - hit.z, 0.02))
    angle = max(rise, fall)
    sigma_h = math.sqrt(
        sigma * sigma / max(len(held), 1) + (sigma / 2) ** 2
    )  # mean of the held samples + the fitted apex
    sigma_a = sigma / max(height, 0.05) / math.sqrt(max(n_rise, 2) / 2)
    too_low = height <= p["min_toss_m"]
    angled = angle > math.radians(p["max_angle_deg"])
    p_legal = phi((height - p["min_toss_m"]) / sigma_h) * phi((math.radians(p["max_angle_deg"]) - angle) / sigma_a)
    verdict = {
        "legal": not (too_low or angled),
        "height_m": height,
        "angle_deg": math.degrees(angle),
        "too_low": too_low,
        "angled": angled,
    }
    text = f"toss {height * 100:.1f} cm, {math.degrees(angle):.0f} deg from vertical: {'legal' if verdict['legal'] else 'illegal'}"  # noqa: E501
    return result(
        "serve_toss",
        verdict,
        p=p_legal,
        t_s=hit.t,
        sigma_m=sigma,
        evidence={
            "server_side": field.side(rel[0]),
            "release": {"t_s": t_rel, "pos_m": list(rel)},
            "apex": {"t_s": t_apex, "pos_m": [x_apex, y_apex, z_apex]},
            "contact": {"t_s": hit.t, "pos_m": [hit.x, hit.y, hit.z]},
            "rise_angle_rad": rise,
            "fall_angle_rad": fall,
            "sigma_height_m": sigma_h,
            "sigma_angle_rad": sigma_a,
            "held_samples": len(held),
        },
        text=text,
    )
