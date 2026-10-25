"""Turn per-frame candidates into one continuous ball track per camera.

Constant-velocity prediction, a displacement gate, birth after `birth_frames` consistent candidates, death after
`max_miss` misses. Nothing outside a track is ever emitted, so a wrong blob can't teleport the ball.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class TrackerParams:
    base_gate_px: float = 40.0  # accepted displacement around the prediction at zero speed
    speed_gate_frac: float = 0.6  # plus this fraction of the predicted displacement
    birth_gate_px: float = 160.0  # consecutive-frame displacement allowed while a track is still tentative
    kink_gate_px: float = 160.0  # reach from the last position when the prediction fails (bounce, racket hit)
    birth_frames: int = 3
    max_miss: int = 6
    velocity_alpha: float = 0.4  # weight of the previous velocity estimate
    max_speed_px_s: float = 9000.0  # anything faster is not a ball on a phone camera


@dataclass
class _Track:
    track_id: int
    xy: np.ndarray
    v: np.ndarray
    t: float
    hits: int = 1
    misses: int = 0
    chain: list = field(default_factory=list)


class Tracker:
    def __init__(self, params: TrackerParams | None = None):
        self.p = params or TrackerParams()
        self.active: _Track | None = None
        self.tentative: list[_Track] = []
        self._next_id = 1
        self.out: list[dict] = []

    def _new(self, xy, t, cand, frame) -> _Track:
        tr = _Track(self._next_id, np.asarray(xy, float), np.zeros(2), t)
        tr.chain.append(self._sample(tr, t, cand, frame))
        self._next_id += 1
        return tr

    @staticmethod
    def _sample(tr: _Track, t: float, cand: dict, frame: int) -> dict:
        s = {
            "t_s": t,
            "frame": frame,
            "xy_px": [float(cand["xy_px"][0]), float(cand["xy_px"][1])],
            "conf": float(cand.get("score", 0.5)),
            "track_id": tr.track_id,
            "misses_before": tr.misses,
        }
        for k in ("L_px", "theta_deg", "area_px"):
            if cand.get(k) is not None:
                s[k] = cand[k]
        return s

    def _update(self, tr: _Track, cand: dict, t: float, frame: int) -> dict:
        xy = np.asarray(cand["xy_px"], float)
        dt = t - tr.t
        if dt > 0:
            v_new = (xy - tr.xy) / dt
            tr.v = self.p.velocity_alpha * tr.v + (1 - self.p.velocity_alpha) * v_new if tr.hits > 1 else v_new
        s = self._sample(tr, t, cand, frame)
        tr.xy, tr.t, tr.hits, tr.misses = xy, t, tr.hits + 1, 0
        tr.chain.append(s)
        return s

    def step(self, frame: int, t_s: float, candidates: list[dict]) -> dict | None:
        """Feed one frame. Returns the emitted sample (or None when the ball isn't tracked this frame)."""
        cands = list(candidates)
        emitted = None
        if self.active is not None:
            tr = self.active
            dt = t_s - tr.t
            pred = tr.xy + tr.v * dt
            gate = self.p.base_gate_px + self.p.speed_gate_frac * np.linalg.norm(tr.v) * dt
            best, best_d = None, None
            for c in cands:
                d = np.linalg.norm(np.asarray(c["xy_px"]) - pred)
                if d <= gate and (best_d is None or d < best_d):
                    best, best_d = c, d
            if best is None:
                # A kink (bounce or racket hit) breaks the prediction but not the position: accept the nearest
                # candidate within reach of the LAST position at up to the kink gate.
                reach = max(self.p.kink_gate_px, self.p.base_gate_px + 1.2 * np.linalg.norm(tr.v) * dt)
                for c in cands:
                    d = np.linalg.norm(np.asarray(c["xy_px"]) - tr.xy)
                    if d <= reach and (best_d is None or d < best_d):
                        best, best_d = c, d
            if best is not None:
                emitted = self._update(tr, best, t_s, frame)
                self.out.append(emitted)
                cands.remove(best)
            else:
                tr.misses += 1
                if tr.misses > self.p.max_miss:
                    self.active = None
        # Tentative chains: extend or start. They run even while a track is active so a wrong lock can be replaced.
        still = []
        used = set()
        for tr in self.tentative:
            dt = t_s - tr.t
            if dt <= 0:
                still.append(tr)
                continue
            # First link: anything within the birth gate. Later links: the chain must keep moving like one object,
            # so the candidate has to sit near the constant-velocity extrapolation (random blobs almost never do).
            if tr.hits == 1:
                pred, gate = tr.xy, self.p.birth_gate_px
            else:
                pred = tr.xy + tr.v * dt
                gate = self.p.base_gate_px + self.p.speed_gate_frac * np.linalg.norm(tr.v) * dt
            best, best_d = None, None
            for i, c in enumerate(cands):
                if i in used:
                    continue
                d = np.linalg.norm(np.asarray(c["xy_px"]) - pred)
                step = np.linalg.norm(np.asarray(c["xy_px"]) - tr.xy)
                if d <= gate and step / dt <= self.p.max_speed_px_s and (best_d is None or d < best_d):
                    best, best_d = i, d
            if best is None:
                continue  # a tentative chain dies on its first miss
            used.add(best)
            self._update(tr, cands[best], t_s, frame)
            still.append(tr)
        for i, c in enumerate(cands):
            if i not in used:
                still.append(self._new(c["xy_px"], t_s, c, frame))
        self.tentative = still
        # Promote: a chain of birth_frames when no track is active, or when the active one has gone missing.
        ready = [tr for tr in self.tentative if tr.hits >= self.p.birth_frames]
        if ready and (self.active is None or self.active.misses >= 2):
            tr = max(ready, key=lambda x: x.hits)
            self.active = tr
            self.tentative = [x for x in self.tentative if x is not tr]
            self.out.extend(tr.chain)
            self.out.sort(key=lambda s: s["t_s"])
            emitted = tr.chain[-1]
        return emitted

    def run(self, frames) -> list[dict]:
        for fr in frames:
            self.step(fr["frame"], fr["t_s"], fr["candidates"])
        return self.out
