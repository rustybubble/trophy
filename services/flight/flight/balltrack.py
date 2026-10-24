"""Table-tennis ball detection + gated single-target tracking (fixes DET-1: no teleports).

Detection (per 720p frame): bright-orange pixels (the ball is far brighter than skin or the red paddles), grouped
into small blobs, each with a motion measure after cancelling handheld camera shake (phase correlation).

Tracking: one confirmed track at a time.
- A track starts only after 3 detections in consecutive-ish frames that move consistently (no single-frame ghosts).
- A detection joins the track only if it is physically reachable from the last observed position
  (|Δ| <= VMAX px/frame × frames elapsed) and close to the constant-velocity prediction; reversals at bounces and
  hits stay reachable because the gate is anchored on the last observation, not only on the prediction.
- Near the prediction a weaker colour test is allowed (motion blur and the blue table wash the ball out).
- Short gaps are bridged with predictions (flagged "predicted", never presented as observations); after MAX_COAST
  frames the track ends. A new track gets a new id, so trails never connect two tracks.
- A confirmed track that stops moving for STILL_FRAMES (e.g. it locked onto a sticker) is dropped.
All thresholds are in 1280×720 pixels at 60 fps; scores are heuristics, not probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .colour import ColourModel

VMAX = 95.0  # px/frame at 720p/60 fps ≈ 27 m/s at this side-view scale; a hard physical gate
MAX_COAST = 8  # frames bridged by prediction (133 ms)
CONFIRM = 3  # detections needed to start a track
STILL_FRAMES = 45  # a confirmed "ball" that hasn't moved for 0.75 s is dropped
MIN_AREA, MAX_AREA = 3, 420
SHAKE_SCALE = 8  # camera-shake estimate on a 1/8-size frame (subpixel phase correlation)
MIN_START_SPEED = 5.0  # px/frame (~1.4 m/s): a new track must be flying, not a hand at rest or a jittering poster


@dataclass
class Candidate:
    x: float
    y: float
    area: int
    colour: float  # 0..1, how ball-coloured
    motion: float  # 0..1, max frame difference inside the blob after shake compensation
    strong: bool  # passed the strict colour test


@dataclass
class TrackPoint:
    seq: int
    t: float
    state: str  # "observed" | "predicted" | "none"
    x: float | None = None
    y: float | None = None
    track_id: int | None = None
    score: float = 0.0


class Detector:
    def __init__(self, colour: ColourModel | None = None) -> None:
        self.colour = colour or ColourModel()  # per-camera; see flight.colour.learn
        self.prev_gray: np.ndarray | None = None
        self.prev_small: np.ndarray | None = None

    def shake(self, gray: np.ndarray) -> tuple[float, float]:
        f = SHAKE_SCALE
        small = cv2.resize(gray, (gray.shape[1] // f, gray.shape[0] // f), interpolation=cv2.INTER_AREA)
        small = small.astype(np.float32)
        if self.prev_small is None:
            self.prev_small = small
            return 0.0, 0.0
        (dx, dy), _ = cv2.phaseCorrelate(self.prev_small, small)
        self.prev_small = small
        return dx * f, dy * f

    def detect(
        self, bgr: np.ndarray, near: tuple[float, float, float] | None = None
    ) -> tuple[list[Candidate], tuple[float, float]]:
        """Candidates in this frame. `near` = (x, y, r): also accept weak colour inside that circle."""
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        h_lo, h_hi, s_lo, v_lo = self.colour.pixel_mask
        strong = (h >= h_lo) & (h <= h_hi) & (s >= s_lo) & (v >= v_lo)
        mask = strong.copy()
        if near is not None:
            cx, cy, rad = near
            x0, x1 = int(max(0, cx - rad)), int(min(bgr.shape[1], cx + rad + 1))
            y0, y1 = int(max(0, cy - rad)), int(min(bgr.shape[0], cy + rad + 1))
            if x1 > x0 and y1 > y0:  # weak colour only inside the search window (cheap, and that's where it's used)
                roi = bgr[y0:y1, x0:x1].astype(np.int16)
                b, g, r = roi[..., 0], roi[..., 1], roi[..., 2]
                hh0, ss0, vv0 = h[y0:y1, x0:x1], s[y0:y1, x0:x1], v[y0:y1, x0:x1]
                weak = (hh0 <= h_hi + 4) & (ss0 >= 40) & (vv0 >= v_lo - 40) & (r - b >= 35) & (r >= g)
                mask[y0:y1, x0:x1] |= weak
        raw = mask
        mask = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8))

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        dx, dy = self.shake(gray)
        prev = self.prev_gray
        self.prev_gray = gray
        idx, idy = int(round(dx)), int(round(dy))
        gh, gw = gray.shape

        def motion_at(x: int, y: int, w: int, hh: int) -> float:
            # frame difference inside the blob's box against the shake-compensated previous frame
            if prev is None:
                return 0.0
            px0, py0 = x - idx, y - idy
            if px0 < 0 or py0 < 0 or px0 + w > gw or py0 + hh > gh:
                return 0.0
            return float(cv2.absdiff(gray[y : y + hh, x : x + w], prev[py0 : py0 + hh, px0 : px0 + w]).max()) / 255

        n, lab, st, cen = cv2.connectedComponentsWithStats(mask, 8)
        out: list[Candidate] = []
        for k in range(1, n):
            x, y, w, hh, area = st[k]
            if not MIN_AREA <= area <= MAX_AREA or max(w, hh) > 48:
                continue
            sl = (slice(y, y + hh), slice(x, x + w))
            inside = (lab[sl] == k) & raw[sl]  # stats on real mask pixels, not the dilation halo
            if not inside.any():
                continue
            vv, ss, hh_ = v[sl][inside], s[sl][inside], h[sl][inside]
            # blob-level ball test with this camera's colour model: brightness separates the ball from skin/paddles
            is_strong = bool(strong[sl][inside].any()) and self.colour.is_ball(
                float(hh_.mean()), float(ss.mean()), float(vv.mean()), float(vv.max())
            )
            colour = float(s[sl][inside].mean()) / 255 * (1.0 if is_strong else 0.6)
            motion = motion_at(int(x), int(y), int(w), int(hh))
            out.append(Candidate(float(cen[k][0]), float(cen[k][1]), int(area), colour, motion, is_strong))
        return out, (dx, dy)


@dataclass
class _Track:
    id: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    last_obs: tuple[float, float, int] = (0.0, 0.0, 0)  # x, y, frame index
    last_strong: int = 0  # frame of the last strict-colour detection
    misses: int = 0
    hits: int = 0
    moved_at: int = 0  # frame index when it last moved > 3 px from the anchor
    anchor: tuple[float, float] = (0.0, 0.0)


def _speed(ch: list[tuple[int, Candidate]]) -> float:
    (f0, a), (f1, b) = ch[0], ch[-1]
    return float(np.hypot(b.x - a.x, b.y - a.y)) / max(1, f1 - f0)


def _rising(ch: list[tuple[int, Candidate]], k: float) -> bool:
    """A serve toss: the ball leaves the palm slowly, rising frame after frame (image y decreasing)."""
    ys = [c.y for _, c in ch]
    (f0, _), (f1, _) = ch[0], ch[-1]
    return all(b < a - 0.3 for a, b in zip(ys, ys[1:], strict=False)) and (ys[0] - ys[-1]) / max(1, f1 - f0) >= 1.2 * k


WEAK_ONLY = 5  # a track must see a strict-colour detection at least this often (weak ones only bridge)


@dataclass
class Tracker:
    detector: Detector = field(default_factory=Detector)
    track: _Track | None = None
    tentative: list[list[tuple[int, Candidate]]] = field(default_factory=list)
    next_id: int = 1
    frame: int = 0
    last_seq: int | None = None
    fps: float = 60.0  # the constants above are per 1/60 s; live phone streams run ~30 fps

    def __post_init__(self) -> None:
        k = 60.0 / self.fps
        self.vmax = VMAX * k
        self.min_start = MIN_START_SPEED * k
        self.max_coast = max(2, round(MAX_COAST / k))
        self.still = max(4, round(STILL_FRAMES / k))
        self.weak_only = max(2, round(WEAK_ONLY / k))

    def _flying(self, ch: list[tuple[int, Candidate]]) -> bool:
        return _speed(ch) >= self.min_start or _rising(ch, 60.0 / self.fps)

    def _grow_chains(self, cands: list[Candidate], dx: float, dy: float, exclude: Candidate | None) -> None:
        """Candidate new tracks: chains of strict-colour, moving detections with consistent velocity."""
        moving = [c for c in cands if c.strong and c.motion >= 0.08 and c is not exclude]
        chains: list[list[tuple[int, Candidate]]] = []
        for ch in self.tentative:
            f0, last = ch[-1]
            if self.frame - f0 > 2:
                continue  # chain went stale
            lx, ly = last.x + dx, last.y + dy
            if len(ch) >= 2:
                (f1, c1), (f2, c2) = ch[-2], ch[-1]
                vx, vy = (c2.x - c1.x) / (f2 - f1), (c2.y - c1.y) / (f2 - f1)
                ex, ey = lx + vx * (self.frame - f0), ly + vy * (self.frame - f0)
                tol = 18 + 0.6 * float(np.hypot(vx, vy))
            else:
                ex, ey, tol = lx, ly, self.vmax * (self.frame - f0)
            nxt = [c for c in moving if np.hypot(c.x - ex, c.y - ey) <= tol and np.hypot(c.x - lx, c.y - ly) > 1.5]
            if nxt:
                c = min(nxt, key=lambda c: np.hypot(c.x - ex, c.y - ey))
                chains.append(ch + [(self.frame, c)])
            elif self.frame - f0 <= 1:
                chains.append(ch)
        used = {id(c) for ch in chains for _, c in ch}
        chains += [[(self.frame, c)] for c in moving if id(c) not in used]
        self.tentative = sorted(chains, key=len, reverse=True)[:40]

    def _start(self, ch: list[tuple[int, Candidate]]) -> _Track:
        (f1, c1), (f2, c2) = ch[-2], ch[-1]
        tr = _Track(
            id=self.next_id,
            x=c2.x,
            y=c2.y,
            vx=(c2.x - c1.x) / (f2 - f1),
            vy=(c2.y - c1.y) / (f2 - f1),
            last_obs=(c2.x, c2.y, self.frame),
            last_strong=self.frame,
            hits=len(ch),
            moved_at=self.frame,
            anchor=(c2.x, c2.y),
        )
        self.next_id += 1
        self.tentative = []
        return tr

    def step(self, seq: int, t: float, bgr: np.ndarray) -> TrackPoint:
        gap = 1 if self.last_seq is None else seq - self.last_seq
        self.last_seq = seq
        if gap != 1:
            # dropped frames (a live reader that fell behind): gates and velocities are per frame, so don't
            # bridge the gap blind; start over from fresh detections
            self.track, self.tentative = None, []
        self.frame += max(1, gap)
        tr = self.track
        near = None
        gate = 0.0
        if tr:
            gate = min(self.vmax * (tr.misses + 1), 20 + 1.5 * float(np.hypot(tr.vx, tr.vy)) + 10 * tr.misses)
            near = (tr.x + tr.vx, tr.y + tr.vy, gate + 10)
        cands, (dx, dy) = self.detector.detect(bgr, near=near)

        best = None
        if tr:
            px, py = tr.x + tr.vx + dx, tr.y + tr.vy + dy
            lx, ly, lf = tr.last_obs
            lx, ly = lx + dx, ly + dy  # shake moves the scene, including where the ball last was
            reach = self.vmax * (self.frame - lf) + 6
            best_cost = 1e9
            for c in cands:
                if np.hypot(c.x - lx, c.y - ly) > reach:
                    continue  # physically unreachable: never join (no teleports)
                d = float(np.hypot(c.x - px, c.y - py))
                if not c.strong and d > gate:
                    continue  # weak colour is only trusted right where the ball should be
                if c.strong and d > max(gate + 40, 0.75 * reach):
                    continue
                cost = d - 25 * c.colour - (35 if c.strong else 0)
                if cost < best_cost:
                    best, best_cost = c, cost

        self._grow_chains(cands, dx, dy, best)

        if tr and best is not None:
            k = max(1, self.frame - tr.last_obs[2])
            tr.vx, tr.vy = (best.x - (tr.last_obs[0] + dx)) / k, (best.y - (tr.last_obs[1] + dy)) / k
            tr.x, tr.y = best.x, best.y
            tr.last_obs = (best.x, best.y, self.frame)
            tr.misses = 0
            tr.hits += 1
            if best.strong:
                tr.last_strong = self.frame
            if np.hypot(best.x - tr.anchor[0] - dx, best.y - tr.anchor[1] - dy) > 3:
                tr.anchor, tr.moved_at = (best.x, best.y), self.frame
            else:
                tr.anchor = (tr.anchor[0] + dx, tr.anchor[1] + dy)
            if self.frame - tr.moved_at > self.still or self.frame - tr.last_strong > self.weak_only:
                self.track = None  # stuck on a static object, or only skin-like support: drop it
            else:
                return TrackPoint(seq, t, "observed", best.x, best.y, tr.id, round(0.5 + 0.5 * best.colour, 3))
        elif tr:
            tr.misses += 1
            tr.x, tr.y = tr.x + tr.vx + dx, tr.y + tr.vy + dy
            tr.last_obs = (tr.last_obs[0] + dx, tr.last_obs[1] + dy, tr.last_obs[2])
            tr.anchor = (tr.anchor[0] + dx, tr.anchor[1] + dy)
            if tr.misses > self.max_coast or self.frame - tr.last_strong > self.max_coast:
                self.track = None
            else:
                weak_track = self.frame - tr.last_strong > 2
                done = [ch for ch in self.tentative if len(ch) >= CONFIRM and self._flying(ch)]
                if not (weak_track and done):
                    return TrackPoint(seq, t, "predicted", tr.x, tr.y, tr.id, 0.0)
                self.track = None  # a fresh, consistently moving ball beats a track that lost the ball

        done = [ch for ch in self.tentative if len(ch) >= CONFIRM and ch[-1][0] == self.frame and self._flying(ch)]
        if done:
            ch = max(done, key=lambda ch: (len(ch), sum(c.colour for _, c in ch)))
            self.track = self._start(ch)
            c2 = ch[-1][1]
            return TrackPoint(seq, t, "observed", c2.x, c2.y, self.track.id, round(0.5 + 0.5 * c2.colour, 3))
        return TrackPoint(seq, t, "none")
