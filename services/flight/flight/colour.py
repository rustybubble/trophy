"""Per-camera ball colour model, learned from the footage itself.

Cameras differ (white balance, exposure): on the side clip the ball blob is H~8-9, V~240; on the diagonal clip
H~15, V~215. Hand-tuned thresholds for one camera fail on the other. `learn()` runs a quick first pass: small,
bright-cored blobs that fly fast on a smooth parabola (>= 6 frames, >= 8 px/frame, quadratic fit within 3 px RMS)
are taken as the ball; other moving orange-ish blobs (skin, paddles, boxes) as distractors. Thresholds are set from
those two populations. If too few ball samples are found, the (looser) defaults are kept.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

MIN_BALL_SAMPLES = 40  # ball blobs (from ballistic chains) needed before the learned thresholds are used


@dataclass(frozen=True)
class ColourModel:
    # defaults: loose enough for both test cameras as the phone sends them (4:2:0 JPEG at quality 70 costs a small
    # ball a few units of S and V, and white balance moves its hue from ~8 to ~15); the learner tightens them per camera
    h_min: float = 2.0
    h_max: float = 22.0
    v_min: float = 210.0  # blob mean V for a flying (blur-desaturated) ball
    s_min: float = 50.0  # blob mean S for that case
    peak_min: float = 225.0  # brightest pixel in the blob
    learned_from: int = 0  # ball blob samples behind the thresholds (0 = defaults)

    def is_ball(self, mean_h: float, mean_s: float, mean_v: float, peak_v: float) -> bool:
        if not self.h_min <= mean_h <= self.h_max or peak_v < self.peak_min:
            return False
        # a flying ball: blur desaturates it but it stays bright; a sharp ball: very saturated, a bit darker
        return (mean_v >= self.v_min and mean_s >= self.s_min) or (
            mean_v >= self.v_min - 18 and mean_s >= self.s_min + 55
        )

    @property
    def pixel_mask(self) -> tuple[int, int, int, int]:
        """Loose per-pixel prefilter (h_lo, h_hi, s_lo, v_lo) that every candidate blob must come from."""
        return int(max(0, self.h_min - 2)), int(self.h_max + 3), int(max(35, self.s_min - 15)), int(self.v_min - 45)


def _blobs(
    bgr: np.ndarray, prev: np.ndarray | None
) -> list[tuple[float, float, int, float, float, float, float, float]]:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    raw = (H <= 24) & (S >= 40) & (V >= 140)
    n, lab, st, cen = cv2.connectedComponentsWithStats(raw.astype(np.uint8), 8)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray, prev) if prev is not None else np.zeros_like(gray)
    out = []
    for k in range(1, n):
        x, y, w, h, area = st[k]
        if not 4 <= area <= 400 or max(w, h) > 48:
            continue
        sl = (slice(y, y + h), slice(x, x + w))
        ins = lab[sl] == k
        out.append(
            (
                float(cen[k][0]),
                float(cen[k][1]),
                int(area),
                float(H[sl][ins].mean()),
                float(S[sl][ins].mean()),
                float(V[sl][ins].mean()),
                float(V[sl][ins].max()),
                float(diff[sl].max()) / 255,
            )
        )
    return out


def _ballistic(ch: list[tuple[int, tuple]]) -> bool:
    """A ball in flight: >= 6 frames on a smooth parabola (quadratic fit residual <= 3 px RMS)."""
    if len(ch) < 6:
        return False
    f = np.array([fi for fi, _ in ch], float)
    for k in (0, 1):
        v = np.array([b[k] for _, b in ch], float)
        resid = v - np.polyval(np.polyfit(f, v, 2), f)
        if float(np.sqrt(np.mean(resid**2))) > 3.0:
            return False
    return True


class ColourLearner:
    """Incremental version for live streams: add() frames (only blob summaries are kept), then fit()."""

    def __init__(self) -> None:
        self.prev: np.ndarray | None = None
        self.per_frame: list[list[tuple]] = []

    def add(self, bgr: np.ndarray) -> None:
        self.per_frame.append(_blobs(bgr, self.prev))
        self.prev = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    def fit(self) -> ColourModel:
        return _fit(self.per_frame)


class LiveLearner:
    """Learns the model from a live stream: tries a fit every `fit_every` frames and keeps the first one backed by
    enough ball samples, so a camera adapts within seconds of play; after `max_frames` it settles for the defaults."""

    def __init__(self, fit_every: int = 150, max_frames: int = 900) -> None:
        self.lr = ColourLearner()
        self.fit_every, self.max_frames = fit_every, max_frames

    def add(self, bgr: np.ndarray) -> ColourModel | None:
        """Feed one frame; returns the model once it is decided (then stop feeding)."""
        self.lr.add(bgr)
        n = len(self.lr.per_frame)
        if n % self.fit_every:
            return None
        m = self.lr.fit()
        return m if m.learned_from or n >= self.max_frames else None


def learn(frames_iter, max_frames: int = 1800) -> ColourModel:
    """Learn a ColourModel from (seq, t, bgr) frames (the first ~30 s is plenty)."""
    lr = ColourLearner()
    for i, (_seq, _t, bgr) in enumerate(frames_iter):
        if i >= max_frames:
            break
        lr.add(bgr)
    return lr.fit()


def _fit(per_frame: list[list[tuple]]) -> ColourModel:
    # chains of fast, consistent motion
    chains: list[list[tuple]] = []
    active: list[list[tuple[int, tuple]]] = []
    for f, blobs in enumerate(per_frame):
        nxt_active = []
        used = set()
        for ch in active:
            lf, last = ch[-1]
            if f - lf > 1:
                if _ballistic(ch):
                    chains.append([b for _, b in ch])
                continue
            if len(ch) >= 2:
                vx, vy = last[0] - ch[-2][1][0], last[1] - ch[-2][1][1]
                ex, ey, tol = last[0] + vx, last[1] + vy, 10 + 0.5 * np.hypot(vx, vy)
            else:
                ex, ey, tol = last[0], last[1], 60.0
            best = None
            for j, b in enumerate(blobs):
                if j in used:
                    continue
                d = np.hypot(b[0] - ex, b[1] - ey)
                step = np.hypot(b[0] - last[0], b[1] - last[1])
                if d <= tol and step >= 8 and b[2] <= 150 and b[6] >= 220 and (best is None or d < best[0]):
                    best = (d, j, b)
            if best:
                used.add(best[1])
                nxt_active.append(ch + [(f, best[2])])
            else:
                nxt_active.append(ch)
        for j, b in enumerate(blobs):
            if j not in used and b[7] >= 0.08:
                nxt_active.append([(f, b)])
        active = [ch for ch in nxt_active if f - ch[-1][0] <= 1][-200:]
    chains += [[b for _, b in ch] for ch in active if _ballistic(ch)]
    ball = [b for ch in chains for b in ch]
    ball_ids = {id(b) for b in ball}
    other = [b for blobs in per_frame for b in blobs if id(b) not in ball_ids and b[7] >= 0.08]
    if len(ball) < MIN_BALL_SAMPLES:
        return ColourModel()
    bh, bs, bv, bp = (np.array([b[i] for b in ball]) for i in (3, 4, 5, 6))
    med_h = float(np.median(bh))
    mad_h = max(1.0, float(np.median(np.abs(bh - med_h))))
    v_min = float(np.percentile(bv, 5)) - 3
    if other:
        ov = np.array([o[5] for o in other])
        oh = np.array([o[3] for o in other])
        in_hue = (oh >= np.percentile(bh, 5) - 1) & (oh <= np.percentile(bh, 95) + 1)
        if in_hue.any():
            # stay above the bright end of the distractors when the populations separate
            d90 = float(np.percentile(ov[in_hue], 90))  # p90: unchained ball frames leak into the distractor sample
            v_min = max(v_min, d90 + 1) if d90 < np.percentile(bv, 40) else v_min
    return ColourModel(
        h_min=med_h - 3 * mad_h - 1,
        h_max=med_h + 3 * mad_h + 1,
        v_min=v_min,
        s_min=max(40.0, float(np.percentile(bs, 10)) - 5),
        peak_min=max(200.0, float(np.percentile(bp, 5)) - 3),
        learned_from=len(ball),
    )
