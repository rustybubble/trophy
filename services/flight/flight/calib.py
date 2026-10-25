"""Camera pose from the four table corners, once per fixed camera.

The corners (pixels, in the brief's order) and the known table rectangle give a planar homography. With the
principal point at the image centre and square pixels, that homography also fixes the focal length (Zhang's
constraints on one plane). solvePnP then refines the pose, and the reprojection error is reported, never assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .field import CORNERS_M

DEFAULT_F_OVER_W = 0.78  # a phone's main lens (about 26 mm equivalent) when the homography can't fix f


@dataclass
class Camera:
    cam_id: str
    width: int
    height: int
    K: np.ndarray  # 3x3
    R: np.ndarray  # 3x3, field -> camera
    t: np.ndarray  # 3, field -> camera
    reproj_err_px: float
    f_source: str  # "homography" | "given" | "default"

    @property
    def P(self) -> np.ndarray:
        return self.K @ np.hstack([self.R, self.t.reshape(3, 1)])

    @property
    def centre_m(self) -> np.ndarray:
        return -self.R.T @ self.t

    def project(self, xyz: np.ndarray) -> np.ndarray:
        """Field points (N,3) -> pixels (N,2)."""
        xyz = np.atleast_2d(xyz)
        cam = (self.R @ xyz.T).T + self.t
        f = np.array([self.K[0, 0], self.K[1, 1]])
        c = np.array([self.K[0, 2], self.K[1, 2]])
        return (cam[:, :2] / cam[:, 2:3]) * f + c

    def ray(self, px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pixel -> (origin, unit direction) in the field frame."""
        x = (px[0] - self.K[0, 2]) / self.K[0, 0]
        y = (px[1] - self.K[1, 2]) / self.K[1, 1]
        d = self.R.T @ np.array([x, y, 1.0])
        return self.centre_m, d / np.linalg.norm(d)

    def lift_to_plane(self, px: np.ndarray, z_m: float) -> np.ndarray | None:
        """Pixel -> the field point on the horizontal plane z = z_m (the bounce case). None if the ray misses."""
        o, d = self.ray(np.asarray(px, float))
        if abs(d[2]) < 1e-9:
            return None
        s = (z_m - o[2]) / d[2]
        if s <= 0:
            return None
        return o + s * d

    def to_json(self) -> dict:
        return {
            "cam_id": self.cam_id,
            "width": self.width,
            "height": self.height,
            "K": self.K.tolist(),
            "R": self.R.tolist(),
            "t": self.t.tolist(),
            "P": self.P.tolist(),
            "reproj_err_px": self.reproj_err_px,
            "f_source": self.f_source,
        }

    @classmethod
    def from_json(cls, d: dict) -> Camera:
        return cls(
            d["cam_id"],
            d["width"],
            d["height"],
            np.array(d["K"], float),
            np.array(d["R"], float),
            np.array(d["t"], float),
            d.get("reproj_err_px", float("nan")),
            d.get("f_source", "given"),
        )


def focal_from_homography(H: np.ndarray, cx: float, cy: float) -> float | None:
    """Focal length (px) from one plane homography, principal point known, square pixels.

    With K = [[f,0,cx],[0,f,cy],[0,0,1]], H ~ K [r1 r2 t], and r1 ⟂ r2, |r1| = |r2|:
    h1' . h2' = 0 and |h1'|^2 = |h2'|^2 where h' = K^-1 h. Both are linear in 1/f^2.
    """
    T = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]], float)
    G = T @ H  # principal point removed; now K' = diag(f, f, 1)
    h1, h2 = G[:, 0], G[:, 1]
    # (h1x h2x + h1y h2y)/f^2 + h1z h2z = 0
    a1, b1 = h1[0] * h2[0] + h1[1] * h2[1], h1[2] * h2[2]
    # (h1x^2 + h1y^2 - h2x^2 - h2y^2)/f^2 + (h1z^2 - h2z^2) = 0
    a2, b2 = (h1[0] ** 2 + h1[1] ** 2) - (h2[0] ** 2 + h2[1] ** 2), h1[2] ** 2 - h2[2] ** 2
    # least squares on [a1, a2] * u + [b1, b2] = 0, u = 1/f^2
    a, b = np.array([a1, a2]), np.array([b1, b2])
    if np.dot(a, a) < 1e-12:
        return None
    u = -np.dot(a, b) / np.dot(a, a)
    if u <= 0:
        return None
    return float(1.0 / np.sqrt(u))


def solve_pose(
    cam_id: str,
    corners_px: np.ndarray,
    width: int,
    height: int,
    f_px: float | None = None,
) -> Camera:
    """Four table corners (pixels, brief order) -> Camera. Raises if the pose is degenerate."""
    corners_px = np.asarray(corners_px, float).reshape(4, 2)
    cx, cy = width / 2.0, height / 2.0
    H, _ = cv2.findHomography(CORNERS_M[:, :2], corners_px)
    if H is None:
        raise ValueError("degenerate corners: no homography")
    source = "given"
    if f_px is None:
        f_px = focal_from_homography(H, cx, cy)
        source = "homography"
        # A near-fronto-parallel or near-square view leaves f poorly constrained; fall back and say so.
        if f_px is None or not (0.4 * width <= f_px <= 2.5 * width):
            f_px = DEFAULT_F_OVER_W * width
            source = "default"
    K = np.array([[f_px, 0, cx], [0, f_px, cy], [0, 0, 1]], float)
    ok, rvec, tvec = cv2.solvePnP(CORNERS_M, corners_px, K, None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        raise ValueError("solvePnP failed")
    rvec, tvec = cv2.solvePnPRefineLM(CORNERS_M, corners_px, K, None, rvec, tvec)
    R, _ = cv2.Rodrigues(rvec)
    t = tvec.ravel()
    cam = Camera(cam_id, width, height, K, R, t, 0.0, source)
    if cam.centre_m[2] <= 0:
        raise ValueError("camera solved below the table surface; check the corner order")
    err = np.linalg.norm(cam.project(CORNERS_M) - corners_px, axis=1)
    cam.reproj_err_px = float(np.sqrt(np.mean(err**2)))
    return cam


def refine_corners(gray: np.ndarray, corners_px: np.ndarray, search_px: int = 12) -> np.ndarray:
    """Snap tapped corners to the table's edge lines: fit each edge from gradient maxima, intersect the lines.

    Returns the input unchanged for any edge where fewer than 8 samples found a clear gradient peak.
    """
    corners_px = np.asarray(corners_px, float).reshape(4, 2)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    h, w = gray.shape
    lines = []
    for i in range(4):
        a, b = corners_px[i], corners_px[(i + 1) % 4]
        d = b - a
        n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
        pts = []
        for s in np.linspace(0.1, 0.9, 40):
            p = a + s * d
            best, best_v = None, 0.0
            for k in range(-search_px, search_px + 1):
                q = p + k * n
                x, y = int(round(q[0])), int(round(q[1]))
                if 0 <= x < w and 0 <= y < h and mag[y, x] > best_v:
                    best, best_v = q, mag[y, x]
            if best is not None and best_v > 0:
                pts.append(best)
        if len(pts) < 8:
            lines.append(None)
            continue
        pts = np.array(pts, np.float32)
        line = cv2.fitLine(pts, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines.append((np.array(line[2:4]), np.array(line[0:2])))  # point, direction
    out = corners_px.copy()
    for i in range(4):
        la, lb = lines[(i - 1) % 4], lines[i]
        if la is None or lb is None:
            continue
        p1, d1 = la
        p2, d2 = lb
        A = np.array([d1, -d2]).T
        if abs(np.linalg.det(A)) < 1e-9:
            continue
        s, _ = np.linalg.solve(A, p2 - p1)
        q = p1 + s * d1
        if np.linalg.norm(q - corners_px[i]) <= 2 * search_px:
            out[i] = q
    return out


def interpolate_px(track: list[dict], t_s: float, max_gap_s: float) -> np.ndarray | None:
    """Linear interpolation of a 2D track ([{t_s, xy_px}] sorted by t) at t_s; None if not bracketed closely."""
    if not track:
        return None
    ts = np.array([r["t_s"] for r in track])
    i = int(np.searchsorted(ts, t_s))
    if i == 0:
        return np.array(track[0]["xy_px"], float) if abs(ts[0] - t_s) <= 1e-6 else None
    if i >= len(ts):
        return np.array(track[-1]["xy_px"], float) if abs(ts[-1] - t_s) <= 1e-6 else None
    t0, t1 = ts[i - 1], ts[i]
    if t1 - t0 > max_gap_s:
        return None
    w = (t_s - t0) / (t1 - t0) if t1 > t0 else 0.0
    p0, p1 = np.array(track[i - 1]["xy_px"], float), np.array(track[i]["xy_px"], float)
    return p0 + w * (p1 - p0)


def camera_looking_at(cam_id: str, pos, look_at, f_px: float, width: int = 1280, height: int = 720) -> Camera:
    """A ground-truth camera at `pos` looking at `look_at` (field frame, z up). Used by the synthetic generator."""
    pos, look_at = np.asarray(pos, float), np.asarray(look_at, float)
    fwd = look_at - pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0, 0, 1.0]))
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    R = np.stack([right, down, fwd])
    K = np.array([[f_px, 0, width / 2], [0, f_px, height / 2], [0, 0, 1]], float)
    return Camera(cam_id, width, height, K, R, -R @ pos, 0.0, "truth")
