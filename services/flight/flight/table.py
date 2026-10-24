"""Find the table-tennis table top in a side-view frame (handheld cameras move, so this runs per frame).

The top surface is the largest wide, flat region of pale grey-blue (H ~104-111, S ~25-30 in OpenCV units). From it
we take the two ends (left = end A, right = end B as filmed), the top edge as a line y = a·x + b (the playing
surface seen edge-on from the side), and the net x. Everything is in working-image pixels. A frame where no
plausible table is found returns None (calls then can't use table geometry for that frame).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Table:
    x_left: float
    x_right: float
    a: float  # top edge: y = a*x + b
    b: float
    net_x: float
    thickness: float  # apparent height of the visible top surface band, px

    def top_y(self, x: float) -> float:
        return self.a * x + self.b

    def side(self, x: float) -> str:
        return "A" if x < self.net_x else "B"

    def over(self, x: float, margin: float = 0.0) -> bool:
        return self.x_left - margin <= x <= self.x_right + margin


def find_table(bgr: np.ndarray) -> Table | None:
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # top surface measured on the side clip: H 104-111, S 24-31, V 190-208 (pale grey-blue); bins S~170, wall H~26
    mask = ((H >= 99) & (H <= 116) & (S >= 14) & (S <= 55) & (V >= 150) & (V <= 235)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 15), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    best, best_score = None, 0.0
    for k in range(1, n):
        x, y, bw, bh, area = st[k]
        if bw < w * 0.25 or bh > bw * 0.5 or area < w * 4:
            continue
        score = bw * min(1.0, area / (bw * max(bh, 1)) * 2)
        if score > best_score:
            best, best_score = k, score
    if best is None:
        return None
    x, y, bw, bh, _ = st[best]
    comp = lab[y : y + bh, x : x + bw] == best
    cols = np.arange(bw)
    has = comp.any(axis=0)
    if has.sum() < bw * 0.6:
        return None
    top = np.argmax(comp, axis=0).astype(float) + y
    bottom = (bh - 1 - np.argmax(comp[::-1], axis=0)).astype(float) + y
    xs = cols[has] + x
    # robust top-edge line: fit, drop the worst 20%, refit (the net and players' hands break the edge)
    a, b = np.polyfit(xs, top[has], 1)
    resid = np.abs(top[has] - (a * xs + b))
    keep = resid <= np.percentile(resid, 80)
    a, b = np.polyfit(xs[keep], top[has][keep], 1)
    thickness = float(np.median((bottom - top)[has]))
    x_left, x_right = float(xs.min()), float(xs.max())
    net_x = _net_x(bgr, x_left, x_right, a, b)
    return Table(x_left, x_right, float(a), float(b), net_x, thickness)


def _net_x(bgr: np.ndarray, x_left: float, x_right: float, a: float, b: float) -> float:
    """The net post/mesh: the darkest narrow column just above the top edge, within the middle third."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mid0 = int(x_left + (x_right - x_left) * 0.33)
    mid1 = int(x_left + (x_right - x_left) * 0.67)
    scores = []
    for xx in range(mid0, mid1):
        yt = int(a * xx + b)
        band = gray[max(0, yt - 28) : max(1, yt - 4), xx]
        scores.append(float(band.mean()) if band.size else 255.0)
    if not scores:
        return (x_left + x_right) / 2
    sm = np.convolve(np.asarray(scores), np.ones(5) / 5, mode="same")
    return float(mid0 + int(np.argmin(sm)))


class TableTracker:
    """Per-frame table detection, smoothed (the camera drifts slowly; detections jitter frame to frame)."""

    def __init__(self, every: int = 10, alpha: float = 0.5) -> None:
        self.every = every
        self.alpha = alpha
        self.n = 0
        self.cur: Table | None = None

    def update(self, bgr: np.ndarray) -> Table | None:
        self.n += 1
        if self.cur is not None and self.n % self.every:
            return self.cur
        t = find_table(bgr)
        if t is None:
            return self.cur
        if self.cur is None:
            self.cur = t
        else:
            c, k = self.cur, self.alpha
            self.cur = Table(*(getattr(c, f) * (1 - k) + getattr(t, f) * k for f in Table.__dataclass_fields__))
        return self.cur
