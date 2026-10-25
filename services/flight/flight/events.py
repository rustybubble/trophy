"""Events read off the 3D track: bounce, hit, dead ball, serve toss. Measurements only; no rule decides here."""

from __future__ import annotations

import numpy as np

from .field import BALL_RADIUS_M, LENGTH_M, on_table, side_of, signed_line_distances
from .lift import kink_time, surface_point

EDGE_BAND_M = 0.04


def _fit_parabola_time_to_z(ts, zs, z_target):
    """Fit z(t) = a t^2 + b t + c on the samples and return the root nearest the samples' time span."""
    ts, zs = np.asarray(ts, float), np.asarray(zs, float)
    t0 = ts.mean()
    coef = np.polyfit(ts - t0, zs, 2 if len(ts) >= 3 else 1)
    roots = (
        np.roots(np.r_[coef[:-1], coef[-1] - z_target])
        if len(coef) == 3
        else np.array([-(coef[1] - z_target) / coef[0]])
    )
    roots = roots[np.isreal(roots)].real + t0
    if len(roots) == 0:
        return None
    return float(roots[np.argmin(np.abs(roots - ts[-1 if zs[-1] < zs[0] else 0]))])


def detect_bounces(
    track3d: list[dict],
    z_max_m: float = 0.10,
    window: int = 3,
    cams=None,
    tracks2d=None,
) -> list[dict]:
    """Local minima of z near the surface where vertical velocity flips from down to up."""
    if len(track3d) < 2 * window + 1:
        return []
    t = np.array([r["t_s"] for r in track3d])
    P = np.array([r["xyz_m"] for r in track3d])
    out = []
    i = window
    while i < len(track3d) - window:
        z = P[:, 2]
        if z[i] < z_max_m and z[i] <= z[i - window : i + window + 1].min():
            down = z[i - 1] - z[i - window] < 0 or z[i] - z[i - 1] < 0
            up = z[i + window] - z[i + 1] > 0 or z[i + 1] - z[i] > 0
            if down and up:
                before = slice(max(0, i - window), i + 1)
                after = slice(i, min(len(t), i + window + 1))
                tb = _fit_parabola_time_to_z(t[before], z[before], BALL_RADIUS_M)
                ta = _fit_parabola_time_to_z(t[after], z[after], BALL_RADIUS_M)
                cands = [x for x in (tb, ta) if x is not None and abs(x - t[i]) < 0.1]
                tbounce = float(np.mean(cands)) if cands else float(t[i])
                speed = float(
                    np.linalg.norm(
                        (P[min(i + 2, len(P) - 1), :2] - P[max(i - 2, 0), :2])
                        / max(1e-6, t[min(i + 2, len(P) - 1)] - t[max(i - 2, 0)])
                    )
                )
                t_source = "z_fit"
                if cams and tracks2d:
                    # A kink time is trusted only when it agrees with the z-fit within 25 ms; if the cameras
                    # disagree with each other by more than 15 ms, the one nearer the z-fit wins.
                    kinks = [k for k in (kink_time(tracks2d.get(c, []), tbounce) for c in cams) if k is not None]
                    kinks = [k for k in kinks if abs(k - tbounce) < 0.025]
                    if len(kinks) >= 2 and max(kinks) - min(kinks) > 0.015:
                        kinks = [min(kinks, key=lambda k: abs(k - tbounce))]
                    if kinks:
                        tbounce = float(np.mean(kinks))
                        t_source = "kink"
                xy = np.array([np.interp(tbounce, t, P[:, 0]), np.interp(tbounce, t, P[:, 1])])
                sigma = float(track3d[i].get("sigma_m", 0.05))
                source = "track3d_interp"
                if cams and tracks2d:
                    sp = surface_point(cams, tracks2d, tbounce, BALL_RADIUS_M, speed_mps=speed)
                    if sp is not None:
                        xy, cov = sp[0][:2], sp[1]
                        sigma = float(np.sqrt(np.trace(cov[:2, :2]) / 2))
                        source = "surface_plane"
                d = signed_line_distances(xy[0], xy[1])
                near_edge = min(d.values()) < EDGE_BAND_M
                out.append(
                    {
                        "type": "bounce",
                        "t_s": tbounce,
                        "xyz_m": [float(xy[0]), float(xy[1]), BALL_RADIUS_M],
                        "side": side_of(xy[0]),
                        "on_table": on_table(xy[0], xy[1]),
                        "d_lines_m": {k: float(v) for k, v in d.items()},
                        "near_edge": bool(near_edge),
                        "sample_index": int(i),
                        "sigma_m": sigma,
                        "xy_source": source,
                        "speed_mps": speed,
                        "t_source": t_source,
                    }
                )
                i += window
        i += 1
    return out


def detect_hits(
    track3d: list[dict],
    bounces: list[dict],
    min_x_m: float = LENGTH_M / 2 - 0.3,
    impulse_mps: float = 2.5,
) -> list[dict]:
    """A racket contact is an impulse: the horizontal velocity changes by more than `impulse_mps` between one
    sample interval and the next, near either end, away from a bounce. Covers serves (speed jump) and returns
    (reversal) alike."""
    if len(track3d) < 3:
        return []
    t = np.array([r["t_s"] for r in track3d])
    P = np.array([r["xyz_m"] for r in track3d])
    dt = np.diff(t)
    v = np.diff(P[:, :2], axis=0) / dt[:, None]  # horizontal velocity per interval
    bounce_ts = np.array([b["t_s"] for b in bounces]) if bounces else np.array([])
    out = []
    last = -1.0
    for i in range(1, len(v)):
        if dt[i - 1] > 0.2 or dt[i] > 0.2:
            continue
        jump = np.linalg.norm(v[i] - v[i - 1])
        if jump < impulse_mps or abs(P[i, 0]) < min_x_m or t[i] - last < 0.15:
            continue
        if len(bounce_ts) and np.min(np.abs(bounce_ts - t[i])) < 0.08:
            continue
        out.append({"type": "contact", "t_s": float(t[i]), "xyz_m": P[i].tolist(), "side": side_of(P[i, 0])})
        last = t[i]
    return out


def detect_dead(track3d: list[dict], gap_s: float = 1.5, floor_z_m: float = -0.3) -> list[dict]:
    out = []
    for a, b in zip(track3d[:-1], track3d[1:], strict=True):
        if b["t_s"] - a["t_s"] > gap_s:
            out.append({"type": "ball_dead", "t_s": a["t_s"], "reason": "lost", "last_side": side_of(a["xyz_m"][0])})
    for r in track3d:
        if r["xyz_m"][2] < floor_z_m:
            out.append({"type": "ball_dead", "t_s": r["t_s"], "reason": "floor", "last_side": side_of(r["xyz_m"][0])})
            break
    return out


def serve_toss(track3d: list[dict], hits: list[dict], g: float = 9.81) -> dict | None:
    """Toss height and angle from vertical, from the free-flight parabola between release and the first contact.

    release = the ball starts rising from rest (z of the rest samples is the release height; if no rest was
    observed, the first rising sample is used and `release_observed` is false). apex = the fitted parabola's
    vertex. contact = the first racket contact. Height is apex z minus release z.
    """
    if len(track3d) < 4:
        return None
    t_all = np.array([r["t_s"] for r in track3d])
    z_all = np.array([r["xyz_m"][2] for r in track3d])
    rising_all = np.where(np.gradient(z_all, t_all) > 0.25)[0]
    if len(rising_all) == 0:
        return None
    t_rise = t_all[int(rising_all[0])]
    # the contact is the first racket impulse after the toss starts; without one, the toss can't be closed
    later = [h for h in hits if h["t_s"] > t_rise + 0.05]
    if not later:
        return None
    t_hit = later[0]["t_s"]
    pre = [r for r in track3d if r["t_s"] <= t_hit + 1e-9]
    if len(pre) < 4:
        return None
    t = np.array([r["t_s"] for r in pre])
    P = np.array([r["xyz_m"] for r in pre])
    i_rel = int(np.argmin(np.abs(t - t_rise)))
    rest = P[: max(0, i_rel - 1)]
    release_observed = len(rest) >= 2
    z_rel = float(np.median(rest[:, 2])) if release_observed else float(P[i_rel, 2])
    xy_rel = np.median(rest[:, :2], axis=0) if release_observed else P[i_rel, :2]
    # free flight: from the first rising sample to the sample before the contact
    fl = slice(i_rel, max(i_rel + 3, len(pre) - 1))
    tf, zf = t[fl], P[fl, 2]
    if len(tf) >= 3:
        a, b, c = np.polyfit(tf - tf[0], zf, 2)
        if a < 0:
            t_apex = -b / (2 * a)
            z_apex = float(c - b * b / (4 * a))
            t_apex_abs = float(tf[0] + t_apex)
        else:
            t_apex_abs, z_apex = float(tf[int(np.argmax(zf))]), float(zf.max())
    else:
        t_apex_abs, z_apex = float(tf[int(np.argmax(zf))]), float(zf.max())
    xy_apex = np.array([np.interp(t_apex_abs, t, P[:, 0]), np.interp(t_apex_abs, t, P[:, 1])])
    rel = np.array([xy_rel[0], xy_rel[1], z_rel])
    apex = np.array([xy_apex[0], xy_apex[1], z_apex])
    con = P[-1]
    height = float(z_apex - z_rel)

    def angle(a_, b_):
        d = b_ - a_
        return float(np.degrees(np.arctan2(np.hypot(d[0], d[1]), abs(d[2])))) if np.linalg.norm(d) > 1e-6 else 0.0

    rise, fall = angle(rel, apex), angle(apex, con)
    sig = float(np.sqrt(pre[i_rel].get("sigma_m", 0.03) ** 2 + np.mean([r.get("sigma_m", 0.03) for r in pre[fl]]) ** 2))
    return {
        "type": "serve_toss",
        "release": {"t_s": float(t[i_rel]), "xyz_m": rel.tolist()},
        "apex": {"t_s": t_apex_abs, "xyz_m": apex.tolist()},
        "contact": {"t_s": float(t[-1]), "xyz_m": con.tolist()},
        "height_m": height,
        "sigma_height_m": sig,
        "release_observed": bool(release_observed),
        "rise_angle_deg": rise,
        "fall_angle_deg": fall,
        "angle_from_vertical_deg": max(rise, fall),
    }
