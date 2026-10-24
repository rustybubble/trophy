"""Fallback for POST /api/calibrate when Agent 2's courtcam-adapter is down (interfaces-v1 §6).

A plain 4-point DLT homography for table tennis only. It is never ``trusted`` (no degeneracy or pose checks),
so the engine caps calls at BETA while it is in use.
"""

from __future__ import annotations

import time

import numpy as np

# Table tennis field frame (§3): origin at the table centre, +x toward end B, +y left facing A->B, metres.
_L, _W = 2.74 / 2, 1.525 / 2
LANDMARKS = {
    "table_tennis": {
        "A_left": (-_L, _W),
        "A_right": (-_L, -_W),
        "B_right": (_L, -_W),
        "B_left": (_L, _W),
    }
}


def homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """DLT for N >= 4 point pairs (Hartley-normalised); src image px -> dst field metres."""

    def norm(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        c = p.mean(axis=0)
        d = np.sqrt(((p - c) ** 2).sum(axis=1)).mean() or 1.0
        s = np.sqrt(2) / d
        t = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
        ph = np.c_[p, np.ones(len(p))] @ t.T
        return ph, t

    sh, ts = norm(src)
    dh, td = norm(dst)
    rows = []
    for (x, y, _), (u, v, _) in zip(sh, dh, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    hn = vt[-1].reshape(3, 3)
    h = np.linalg.inv(td) @ hn @ ts
    return h / h[2, 2]


def calibrate(req: dict) -> dict:
    sport = req["sport"]
    if sport not in LANDMARKS:
        raise ValueError(f"no stub template for {sport}")
    lm = LANDMARKS[sport]
    pts = [p for p in req["points"] if p["name"] in lm]
    if len(pts) < 4:
        raise ValueError(f"need the 4 table corners {list(lm)}")
    src = np.array([p["px"] for p in pts], dtype=float)
    dst = np.array([lm[p["name"]] for p in pts], dtype=float)
    h = homography(src, dst)
    proj = np.c_[dst, np.ones(len(dst))] @ np.linalg.inv(h).T
    proj = proj[:, :2] / proj[:, 2:3]
    err = float(np.sqrt(((proj - src) ** 2).sum(axis=1)).max())
    return {
        "schema": "trophy.calibration.v1",
        "game_id": req["game_id"],
        "cam_id": req["cam_id"],
        "sport": sport,
        "created_at_ms": time.time() * 1000,
        "image_size": req["image_size"],
        "method": "stub-homography",
        "H_img_to_field": [float(x) for x in h.ravel()],
        "reproj_err_px": err,
        "trusted": False,
        "warnings": ["courtcam-adapter unavailable: gateway stub homography, untrusted (calls capped at BETA)"],
        "solver": "gateway-stub",
    }
