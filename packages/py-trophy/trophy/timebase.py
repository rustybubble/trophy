"""Time (interfaces-v1 §2): server clock, game time, and the per-camera phone->server clock fit.

The phone sends ``ping {t0}``; the gateway answers ``pong {t0, t1, t2}``; the phone stamps ``t3`` on receipt
and reports the completed sample in its next ping (``prev``). :class:`ClockFit` keeps the lowest-RTT
samples (NTP-style) and fits ``t_srv = t_phone + a + b·(t_phone − t_ref)``.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field


def now_ms() -> float:
    """Server clock ``t_srv_ms``: epoch milliseconds (float)."""
    return time.time() * 1000.0


def t_game_s(t_srv_ms: float, t0_ms: float) -> float:
    return (t_srv_ms - t0_ms) / 1000.0


def t_srv_ms_from_game(t_game: float, t0_ms: float) -> float:
    return t0_ms + t_game * 1000.0


@dataclass(frozen=True)
class ClockSample:
    t0: float  # phone send (phone clock, ms)
    t1: float  # server receive (server clock, ms)
    t2: float  # server send (server clock, ms)
    t3: float  # phone receive (phone clock, ms)

    @property
    def offset_ms(self) -> float:
        """Server minus phone."""
        return ((self.t1 - self.t0) + (self.t2 - self.t3)) / 2.0

    @property
    def rtt_ms(self) -> float:
        return (self.t3 - self.t0) - (self.t2 - self.t1)

    @property
    def t_phone_mid(self) -> float:
        return (self.t0 + self.t3) / 2.0


@dataclass
class ClockFit:
    """Min-RTT clock fit for one camera.

    ``window`` samples are kept; the best ``keep_frac`` by RTT (at least ``min_keep``) are fitted. Drift
    ``b`` is only estimated once the kept samples span ``min_span_ms`` of phone time, and is clamped to
    ``max_drift_ppm``.
    """

    window: int = 64
    keep_frac: float = 0.25
    min_keep: int = 3
    min_span_ms: float = 10_000.0
    max_drift_ppm: float = 200.0
    pipeline_offset_ms: float = 0.0
    samples: deque[ClockSample] = field(default_factory=deque)
    a: float = 0.0
    b: float = 0.0
    t_ref: float = 0.0
    sync_err_ms: float = float("inf")

    def add(self, t0: float, t1: float, t2: float, t3: float) -> ClockSample | None:
        s = ClockSample(t0, t1, t2, t3)
        if s.rtt_ms < 0 or t3 < t0 or t2 < t1:
            return None  # garbage sample
        self.samples.append(s)
        while len(self.samples) > self.window:
            self.samples.popleft()
        self._fit()
        return s

    @property
    def ready(self) -> bool:
        return bool(self.samples)

    @property
    def offset_ms(self) -> float:
        return self.a

    @property
    def drift_ppm(self) -> float:
        return self.b * 1e6

    def _fit(self) -> None:
        ranked = sorted(self.samples, key=lambda s: s.rtt_ms)
        k = max(self.min_keep, int(len(ranked) * self.keep_frac))
        best = ranked[:k]
        min_rtt = best[0].rtt_ms
        xs = [s.t_phone_mid for s in best]
        ys = [s.offset_ms for s in best]
        self.t_ref = max(xs)
        span = max(xs) - min(xs)
        if len(best) >= 3 and span >= self.min_span_ms:
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx if sxx else 0.0
            lim = self.max_drift_ppm * 1e-6
            b = max(-lim, min(lim, b))
            self.b = b
            self.a = my + b * (self.t_ref - mx)
            resid = [y - (self.a + b * (x - self.t_ref)) for x, y in zip(xs, ys, strict=True)]
            spread = statistics.pstdev(resid) if len(resid) > 1 else 0.0
        else:
            self.b = 0.0
            self.a = best[0].offset_ms
            spread = statistics.pstdev(ys) if len(ys) > 1 else 0.0
        # The offset error of one exchange is bounded by RTT/2; add the residual spread.
        self.sync_err_ms = min_rtt / 2.0 + spread

    def to_srv(self, t_phone_ms: float, extra_offset_ms: float = 0.0) -> float:
        """Map a phone timestamp to server ms. ``extra_offset_ms`` is e.g. ``audio_offset_ms``."""
        return t_phone_ms + self.a + self.b * (t_phone_ms - self.t_ref) + self.pipeline_offset_ms + extra_offset_ms
