"""2D tracks from two or more fixed cameras -> field-frame 3D samples with a covariance (track3d records).

Time alignment first: each camera's track is linearly interpolated to the reference camera's sample times (the
cameras share the gateway clock; a residual skew σ is carried into the covariance as |v|·σ_t). Then DLT
triangulation, a reprojection check that rejects inconsistent correspondences, and a numeric Jacobian for σ.
"""

from __future__ import annotations

import numpy as np

from .calib import Camera, interpolate_px

MAX_REPROJ_PX = 25.0


def triangulate(views: list[tuple[Camera, np.ndarray]]) -> np.ndarray:
    """Linear (DLT) triangulation from >= 2 (camera, pixel) pairs."""
    A = []
    for cam, px in views:
        P = cam.P
        A.append(px[0] * P[2] - P[0])
        A.append(px[1] * P[2] - P[1])
    A = np.array(A)
    _, _, vt = np.linalg.svd(A)
    X = vt[-1]
    return X[:3] / X[3]


def _reproj_errors(xyz: np.ndarray, views: list[tuple[Camera, np.ndarray]]) -> np.ndarray:
    return np.array([np.linalg.norm(cam.project(xyz)[0] - px) for cam, px in views])


def _pixel_jacobian(views: list[tuple[Camera, np.ndarray]], eps: float = 0.5) -> np.ndarray:
    """d(xyz)/d(pixels), 3 x 2n, by central differences."""
    cols = []
    for i in range(len(views)):
        for k in range(2):
            plus = [(c, p.copy()) for c, p in views]
            minus = [(c, p.copy()) for c, p in views]
            plus[i][1][k] += eps
            minus[i][1][k] -= eps
            cols.append((triangulate(plus) - triangulate(minus)) / (2 * eps))
    return np.array(cols).T


def fuse(
    tracks: dict[str, list[dict]],
    cams: dict[str, Camera],
    px_sigma: float = 2.0,
    skew_sigma_s: float = 0.008,
    fps: float = 30.0,
) -> list[dict]:
    """Return track3d records (brief shape) at the reference camera's sample times, n_views >= 2 only."""
    if len(tracks) < 2:
        return []
    ref = max(tracks, key=lambda c: len(tracks[c]))
    others = [c for c in tracks if c != ref]
    max_gap = 2.5 / fps
    out = []
    for s in tracks[ref]:
        t = s["t_s"]
        views = [(cams[ref], np.array(s["xy_px"], float))]
        prov = [{"cam_id": ref, "frame": s["frame"], "xy_px": s["xy_px"], "vis": 1}]
        confs = [s["conf"]]
        for c in others:
            # Interpolate the other camera to this instant. Across a kink (bounce, hit) a linear interpolation
            # is wrong, so if it fails the reprojection gate, fall back to that camera's nearest sample.
            options = []
            px = interpolate_px(tracks[c], t, max_gap)
            if px is not None:
                options.append((px, True))
            near = min(tracks[c], key=lambda r: abs(r["t_s"] - t), default=None)
            if near is not None and abs(near["t_s"] - t) <= 0.6 / fps:
                options.append((np.array(near["xy_px"], float), False))
            chosen = None
            for px, interp in options:
                trial = views + [(cams[c], px)]
                xyz = triangulate(trial)
                if np.all(np.isfinite(xyz)) and _reproj_errors(xyz, trial).max() <= MAX_REPROJ_PX:
                    chosen = (px, interp)
                    break
            if chosen is None:
                continue
            px, interp = chosen
            views.append((cams[c], px))
            prov.append({"cam_id": c, "frame": None, "xy_px": px.tolist(), "vis": 1, "interpolated": interp})
            confs.append(0.9)
        if len(views) < 2:
            continue
        xyz = triangulate(views)
        errs = _reproj_errors(xyz, views)
        if errs.max() > MAX_REPROJ_PX or not np.all(np.isfinite(xyz)):
            continue  # the two cameras are not looking at the same object
        J = _pixel_jacobian(views)
        cov = (px_sigma**2) * (J @ J.T)
        out.append(
            {
                "t_s": t,
                "xyz_m": xyz.tolist(),
                "cov_m2": cov,
                "conf": float(np.mean(confs)),
                "n_views": len(views),
                "views": prov,
                "reproj_err_px": float(errs.max()),
            }
        )
    # second pass: add the clock-skew term |v| σ_t along the motion, then finalise the covariance
    for i, r in enumerate(out):
        j = i + 1 if i + 1 < len(out) else i - 1
        if 0 <= j < len(out) and out[j]["t_s"] != r["t_s"]:
            v = (np.array(out[j]["xyz_m"]) - np.array(r["xyz_m"])) / (out[j]["t_s"] - r["t_s"])
            r["cov_m2"] = r["cov_m2"] + skew_sigma_s**2 * np.outer(v, v)
        r["sigma_m"] = float(np.sqrt(np.trace(r["cov_m2"]) / 3))
        r["cov_m2"] = r["cov_m2"].tolist()
    return out


def _extrapolate_px(track: list[dict], t_s: float, before: bool, n: int = 4, max_span_s: float = 0.2):
    """Quadratic fit of the last/next n samples on one side of t_s, evaluated at t_s (no fit across a kink)."""
    side = [r for r in track if (r["t_s"] < t_s if before else r["t_s"] > t_s)]
    side = side[-n:] if before else side[:n]
    if len(side) < 3 or abs(side[-1 if before else 0]["t_s"] - t_s) > max_span_s / 2:
        return None
    ts = np.array([r["t_s"] for r in side]) - t_s
    if ts.max() - ts.min() > max_span_s:
        return None
    xy = np.array([r["xy_px"] for r in side])
    deg = 2 if len(side) >= 4 else 1
    return np.array([np.polyval(np.polyfit(ts, xy[:, k], deg), 0.0) for k in range(2)])


def kink_time(track: list[dict], t_guess: float, half_window_s: float = 0.06) -> float | None:
    """The instant a 2D track changes direction: where the before-fit and after-fit parabolas meet, in pixels."""
    pb = _fit_side(track, t_guess, before=True)
    pa = _fit_side(track, t_guess, before=False)
    if pb is None or pa is None:
        return None
    ts = np.arange(-half_window_s, half_window_s, 0.0005)
    gap = np.array([np.linalg.norm(pb(tt) - pa(tt)) for tt in ts])
    return float(t_guess + ts[int(np.argmin(gap))])


def _fit_side(track: list[dict], t_s: float, before: bool, n: int = 4, max_span_s: float = 0.2):
    """Quadratic (or linear) fit of up to n samples on one side of t_s; returns f(dt) -> xy_px or None."""
    side = [r for r in track if (r["t_s"] < t_s if before else r["t_s"] > t_s)]
    side = side[-n:] if before else side[:n]
    if len(side) < 3 or abs(side[-1 if before else 0]["t_s"] - t_s) > max_span_s / 2:
        return None
    ts = np.array([r["t_s"] for r in side]) - t_s
    if ts.max() - ts.min() > max_span_s:
        return None
    xy = np.array([r["xy_px"] for r in side])
    deg = 2 if len(side) >= 4 else 1
    coef = [np.polyfit(ts, xy[:, k], deg) for k in range(2)]
    return lambda dt: np.array([np.polyval(coef[0], dt), np.polyval(coef[1], dt)])


def _extrapolate_px(track: list[dict], t_s: float, before: bool):
    f = _fit_side(track, t_s, before)
    return None if f is None else f(0.0)


def surface_point(
    cams: dict[str, Camera],
    tracks: dict[str, list[dict]],
    t_s: float,
    z_m: float,
    px_sigma: float = 2.0,
    t_sigma_s: float = 0.006,
    speed_mps: float = 0.0,
):
    """Where the ball touched the plane z = z_m at t_s, from each camera's own 2D track.

    Each camera's track is extrapolated to t_s from before and from after the contact (never interpolated across
    the kink) and lifted onto the plane. Estimates are combined by inverse variance after dropping any that sit
    far from the others (one bad extrapolation must not drag the answer). The timing term speed·σ_t is added.
    Returns (xyz, cov) or None.
    """
    pts, covs = [], []
    for cid, cam in cams.items():
        for before in (True, False):
            px = _extrapolate_px(tracks.get(cid, []), t_s, before)
            if px is None:
                continue
            p = cam.lift_to_plane(px, z_m)
            if p is None:
                continue
            dx = cam.lift_to_plane(px + np.array([1.0, 0]), z_m) - p
            dy = cam.lift_to_plane(px + np.array([0, 1.0]), z_m) - p
            J = np.array([dx[:2], dy[:2]]).T  # 2x2 footprint of one pixel on the plane
            pts.append(p[:2])
            covs.append((2 * px_sigma) ** 2 * (J @ J.T))  # extrapolation roughly doubles the pixel noise
    if not pts:
        return None

    def combine(idx):
        ws = [np.linalg.inv(covs[i] + 1e-9 * np.eye(2)) for i in idx]
        W = sum(ws)
        xy = np.linalg.solve(W, sum(w @ pts[i] for w, i in zip(ws, idx, strict=True)))
        return xy, np.linalg.inv(W)

    idx = list(range(len(pts)))
    xy, cov2 = combine(idx)
    if len(idx) >= 3:
        med = np.median(np.array(pts), axis=0)
        keep = [i for i in idx if np.linalg.norm(pts[i] - med) < max(0.05, 4 * np.sqrt(np.trace(covs[i]) / 2))]
        if len(keep) >= 2 and len(keep) < len(idx):
            xy, cov2 = combine(keep)
    cov = np.zeros((3, 3))
    cov[:2, :2] = cov2 + (speed_mps * t_sigma_s) ** 2 * np.eye(2)
    cov[2, 2] = 0.005**2
    return np.array([xy[0], xy[1], z_m]), cov
