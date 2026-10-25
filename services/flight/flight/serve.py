"""Serve toss from one fixed camera (D-31, ITTF Law 2.6.2): release, apex, contact, height, angle, with sigma.

One camera cannot measure depth, so each ball pixel is lifted onto a vertical plane: the plane through the server's
end of the table (x = +-(L/2 + behind_m), y = 0) whose normal is the camera's horizontal viewing direction. A side-on
camera at the net line looks along y, so the plane is y = 0 and it measures x and z well (`observable_plane: "xz"`).
The plane's offset is uncertain by `sigma_plane_m` (where across the table the server tosses); that error scales the
lifted positions, and it is propagated into sigma_height_m and sigma_angle_rad together with the pixel noise.

What it reports, all measurements (D-18; the rule pack decides):
- release: the ball leaving a still palm. Observed when the ball sat still (palm) for >= `palm_min_s` just before the
  rise; then release.z is the median still height and t lies between the last still and the first rising sample.
  Otherwise release is the first rising sample seen, `release` and `palm` go in evidence_missing, and height_m is a
  lower bound.
- apex: the vertex of a parabola fitted to the free flight between release and contact (or the highest sample when
  the fit is degenerate).
- contact: the racket strike, found as the first sample after the apex whose in-plane horizontal velocity jumps by
  more than `strike_speed_mps` relative to the toss's own drift (a serve strike sends the ball toward the net while it
  is still falling, so it is not a local minimum of height and the sport module's `contact` does not see it).
- angle_from_vertical_rad: the launch direction at release (the rise's tangent, from the flight fit), in the measured
  plane. The out-of-plane component is not observed, so this is a lower bound on the true angle and `depth` is in
  evidence_missing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import field as F
from .calib import Camera

ESTIMATOR = {"name": "flight-serve-toss-1cam", "version": "0.1.0"}


@dataclass
class TossParams:
    behind_m: float = 0.3  # the server tosses about this far behind the end line
    sigma_plane_m: float = 0.4  # 1 sigma of the toss plane's offset (where across the table the toss happens)
    sigma_px: float = 2.0  # detector pixel noise, 1 sigma
    still_px: float = 4.0  # max movement of a ball resting on the palm between samples
    palm_min_s: float = 0.15  # still at least this long before the rise to count as "on the open palm"
    min_rise_samples: int = 3
    min_rise_m: float = 0.03  # less than this is not a toss
    strike_speed_mps: float = 1.5  # in-plane horizontal velocity change that marks the strike
    lookback_s: float = 3.0


def _ray(cam: Camera, u: float, v: float) -> tuple[np.ndarray, np.ndarray]:
    d = cam.R.T @ np.linalg.solve(cam.K, np.array([u, v, 1.0]))
    return cam.centre_m, d / np.linalg.norm(d)


def toss_plane(cam: Camera, server_side: str, p: TossParams) -> tuple[np.ndarray, np.ndarray]:
    """(point, unit normal) of the vertical toss plane for this camera and server."""
    axis = cam.R.T @ np.array([0.0, 0.0, 1.0])  # optical axis in the field frame
    n = np.array([axis[0], axis[1], 0.0])
    if np.linalg.norm(n) < 1e-6:
        n = np.array([0.0, 1.0, 0.0])  # looking straight down: any vertical plane; take y = const
    n /= np.linalg.norm(n)
    x0 = (-1 if server_side == "A" else 1) * (F.LENGTH_M / 2 + p.behind_m)
    return np.array([x0, 0.0, 0.0]), n


def lift(cam: Camera, u: float, v: float, plane: tuple[np.ndarray, np.ndarray], offset_m: float = 0.0) -> np.ndarray:
    """Pixel -> field point on the plane (shifted along its normal by offset_m). NaN when the ray is parallel."""
    p0, n = plane
    c, d = _ray(cam, u, v)
    den = float(d @ n)
    if abs(den) < 1e-6:
        return np.full(3, np.nan)
    s = float((p0 + offset_m * n - c) @ n) / den
    return c + s * d


def _horiz(n: np.ndarray) -> np.ndarray:
    """The in-plane horizontal unit vector (perpendicular to the normal and to z)."""
    h = np.cross(np.array([0.0, 0.0, 1.0]), n)
    return h / np.linalg.norm(h)


def _mark(t: float, t0: float, t1: float, pos: np.ndarray, sigma_m: float) -> dict:
    return {
        "t_s": round(t, 4),
        "t0_s": round(t0, 4),
        "t1_s": round(t1, 4),
        "sigma_t_s": round(max(1e-3, (t1 - t0) / math.sqrt(12)), 4),
        "pos_m": {"x": round(float(pos[0]), 4), "y": round(float(pos[1]), 4), "z": round(float(pos[2]), 4)},
        "sigma_m": round(sigma_m, 4),
    }


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def estimate(
    samples: list[tuple[float, float, float]],
    cam: Camera,
    p: TossParams | None = None,
    *,
    server_side: str | None = None,
    calib_trusted: bool = False,
) -> dict | None:
    """samples: (t_s, u, v) of one camera's tracked ball, time-ordered, covering the serve. Returns a
    ServeTossPayload dict, or None when there is no toss-shaped rise in the samples."""
    p = p or TossParams()
    if len(samples) < p.min_rise_samples + 1:
        return None
    t = np.array([s[0] for s in samples])
    uv = np.array([[s[1], s[2]] for s in samples])
    if server_side is None:
        # which end the ball is over at the start (the plane choice depends on it; try A, then refine)
        x_a = lift(cam, *uv[0], toss_plane(cam, "A", p))[0]
        server_side = "A" if (np.isnan(x_a) or x_a < 0) else "B"
    plane = toss_plane(cam, server_side, p)
    P = np.array([lift(cam, u, v, plane) for u, v in uv])
    if np.isnan(P).any():
        return None
    h_axis = _horiz(plane[1])
    z, x = P[:, 2], P @ h_axis

    # apex candidate: the highest sample before any strike; strike: first fast in-plane horizontal move after it
    dt = np.diff(t)
    vx = np.diff(x) / np.where(dt > 0, dt, np.inf)
    i_top = int(np.argmax(z))
    i_strike = None
    v_flight = float(np.median(vx[max(0, i_top - 4) : i_top])) if i_top > 0 else 0.0  # horizontal drift of the toss
    for i in range(i_top, len(vx)):
        if abs(vx[i] - v_flight) >= p.strike_speed_mps:
            i_strike = i  # strike between sample i and i+1: a horizontal impulse
            break
    flight_end = i_strike if i_strike is not None else len(t) - 1
    i_top = int(np.argmax(z[: flight_end + 1]))

    # the rise: walk back from the apex while height keeps decreasing
    i_rise = i_top
    while i_rise > 0 and z[i_rise - 1] < z[i_rise]:
        i_rise -= 1
    if i_top - i_rise + 1 < p.min_rise_samples or z[i_top] - z[i_rise] < p.min_rise_m:
        return None

    # palm: still samples just before the rise
    j = i_rise
    while j > 0 and np.linalg.norm(uv[j] - uv[j - 1]) <= p.still_px:
        j -= 1
    palm_still_s = float(t[i_rise] - t[j]) if j < i_rise else 0.0
    missing: list[str] = ["depth", "spin"]
    if not calib_trusted:
        missing.append("calibration")
    m_px = float(np.median(np.linalg.norm(np.diff(uv[: i_top + 1], axis=0), axis=1))) if i_top else 0.0
    dist = float(np.linalg.norm(P[i_top] - cam.centre_m))
    f = float(cam.K[0, 0])
    sig_pt = dist * p.sigma_px / f  # metres per point from pixel noise
    if palm_still_s >= p.palm_min_s:
        palm = P[j : i_rise + 1]
        rel_pos = np.median(palm, axis=0)
        t_rel0, t_rel1 = float(t[i_rise]), float(t[i_rise + 1])
        release = _mark((t_rel0 + t_rel1) / 2, t_rel0, t_rel1, rel_pos, sig_pt / math.sqrt(max(1, len(palm))))
        i_fit0 = i_rise + 1
    else:
        missing += ["release", "palm"]
        rel_pos = P[i_rise]
        t_lo = float(t[i_rise - 1]) if i_rise > 0 else float(t[i_rise]) - 1 / 30
        release = _mark(float(t[i_rise]), t_lo, float(t[i_rise]), rel_pos, sig_pt)
        i_fit0 = i_rise

    # apex: parabola through the free flight
    fit = slice(i_fit0, flight_end + 1)
    tf, zf = t[fit], z[fit]
    apex_t, apex_z, sig_apex = float(t[i_top]), float(z[i_top]), sig_pt
    if len(tf) >= 3:
        a, b, c = np.polyfit(tf - tf[0], zf, 2)
        if a < 0:
            tv = -b / (2 * a)
            if 0 <= tv <= tf[-1] - tf[0] + 0.05:
                apex_t, apex_z = float(tf[0] + tv), float(c - b * b / (4 * a))
                res = zf - np.polyval([a, b, c], tf - tf[0])
                sig_apex = float(max(sig_pt / math.sqrt(len(tf)), np.sqrt(np.mean(res**2))))
    apex_pos = P[i_top].copy()
    apex_pos[2] = apex_z
    frame_s = float(np.median(dt)) if len(dt) else 1 / 30
    apex = _mark(apex_t, apex_t - frame_s / 2, apex_t + frame_s / 2, apex_pos, sig_apex)

    # plane-offset error: re-lift release and apex with the plane shifted by one sigma
    def at(offset: float) -> tuple[np.ndarray, np.ndarray]:
        return lift(cam, *uv[i_rise], plane, offset), lift(cam, *uv[i_top], plane, offset)

    pr1, pa1 = at(p.sigma_plane_m)
    pr0, pa0 = at(0.0)
    height = float(apex_z - rel_pos[2])
    scale = 1.0 + float(((pa1 - pr1)[2] - (pa0 - pr0)[2]) / max(1e-6, (pa0 - pr0)[2]))
    sig_height = math.hypot(math.hypot(release["sigma_m"], sig_apex), abs(scale - 1.0) * height)

    # angle: the launch direction at release from the flight fit (x linear, z quadratic in t). The chord release ->
    # apex of a parabola leans atan(2 tan(theta)) from vertical, so it would overstate the projection angle the law
    # is about; the chord is the fallback when the fit has too few samples.
    xf = x[fit]
    angle = sig_angle = None
    if len(tf) >= 5:
        tau = float(release["t_s"]) - float(tf[0])
        (a, b, _c), cz = np.polyfit(tf - tf[0], zf, 2, cov=True)
        (k, _x0), cx = np.polyfit(tf - tf[0], xf, 1, cov=True)
        vz = 2 * a * tau + b
        var_vz = 4 * tau * tau * cz[0, 0] + cz[1, 1] + 4 * tau * cz[0, 1]
        if vz > 0:
            angle = math.atan2(abs(k), vz)
            sig_angle = math.sqrt((vz**2) * cx[0, 0] + (k**2) * max(var_vz, 0.0)) / (k * k + vz * vz)
    if angle is None:
        seg = apex_pos - rel_pos
        horiz, vert = abs(float(seg @ h_axis)), float(seg[2])
        angle = math.atan(0.5 * horiz / max(vert, 1e-6))  # tan(theta) = chord_tan / 2 for a parabola
        sig_angle = math.hypot(release["sigma_m"], sig_apex) / max(1e-3, math.hypot(horiz, vert))
    sig_angle = max(0.02, float(sig_angle))

    out: dict = {
        "server_side": server_side,
        "release": release,
        "apex": apex,
        "height_m": round(height, 4),
        "sigma_height_m": round(max(sig_height, 0.003), 4),
        "angle_from_vertical_rad": round(angle, 4),
        "sigma_angle_rad": round(sig_angle, 4),
        "angle_segment": "rise",
        "observable_plane": "xz",
        "palm_still_s": round(palm_still_s, 3),
        "estimator": ESTIMATOR,
    }
    if i_strike is not None:
        tc0, tc1 = float(t[i_strike]), float(t[i_strike + 1])
        tc = (tc0 + tc1) / 2
        out["contact"] = _mark(tc, tc0, tc1, (P[i_strike] + P[i_strike + 1]) / 2, sig_pt)
        sig_t = math.hypot(apex["sigma_t_s"], out["contact"]["sigma_t_s"])
        p_desc = _phi((tc - apex_t) / max(sig_t, 1e-3))
        out["struck_on_descent"] = bool(p_desc >= 0.5)
        out["struck_on_descent_p"] = round(p_desc, 4)
        hit_angles = [
            math.atan2(abs(float((P[k] - rel_pos) @ h_axis)), max(float(P[k][2] - rel_pos[2]), 1e-6))
            for k in range(i_rise + 1, i_strike + 1)
            if P[k][2] > rel_pos[2]
        ]
        if hit_angles:
            out["house_hand_to_hit_angle_rad"] = round(max(hit_angles), 4)
    else:
        missing += ["contact", "descent"]
        out["struck_on_descent"] = None
        out["struck_on_descent_p"] = 0.5
    if not calib_trusted:
        out["calib_untrusted"] = True
    out["evidence_missing"] = sorted(set(missing))
    out["_debug"] = {
        "plane_scale_per_sigma": round(scale - 1.0, 4),
        "median_step_px": round(m_px, 2),
        "n_flight": int(len(tf)),
    }
    return out
