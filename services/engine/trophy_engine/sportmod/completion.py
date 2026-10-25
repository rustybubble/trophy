"""Short-gap completion of a live 2D ball track, after Mu Du's `complete_ball_track` (D-39,
spikes/serve-analysis/trophy/replay/ball_completion.py), for the one-camera path.

BlurBall misses a frame or two around fast contacts and bounces; the golden module then loses the bounce (it needs
`min_track_len` samples on each side of the lowest point). Within one camera, a run of missed frames no longer than
`max_gap_s` (Mu's `interpolated` limit, 0.25 s) between two measured samples is filled with the shape-preserving
cubic (PCHIP, Fritsch-Carlson: SciPy's PchipInterpolator) through the measured samples around it. PCHIP cannot
overshoot its support, so it never invents a lowest point the measurements don't imply. Measured samples are never
changed; filled ones carry `conf` = the lower neighbour's x `conf_scale` and are counted, so they stay estimates.
No extrapolation past the ends of the track (Mu's bounded end extrapolation is a display device, not evidence).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from .api import BallSample


def pchip_slopes(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    """Fritsch-Carlson derivatives (as scipy.interpolate.PchipInterpolator) at each knot."""
    n = len(xs)
    if n < 2:
        return [0.0] * n
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    if n == 2:
        return [d[0], d[0]]
    m = [0.0] * n
    for k in range(1, n - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])

    def edge(h0: float, h1: float, d0: float, d1: float) -> float:  # SciPy's one-sided three-point end slope
        s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if s * d0 <= 0:
            return 0.0
        if d0 * d1 <= 0 and abs(s) > abs(3 * d0):
            return 3 * d0
        return s

    m[0] = edge(h[0], h[1], d[0], d[1])
    m[-1] = edge(h[-1], h[-2], d[-1], d[-2])
    return m


def pchip_eval(xs: Sequence[float], ys: Sequence[float], m: Sequence[float], x: float) -> float:
    i = max(0, min(len(xs) - 2, max(k for k in range(len(xs) - 1) if xs[k] <= x)))
    h = xs[i + 1] - xs[i]
    t = (x - xs[i]) / h
    h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
    h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]


def fill_short_gaps(
    samples: Sequence[BallSample], *, max_gap_s: float = 0.25, support: int = 3, conf_scale: float = 0.9
) -> tuple[list[BallSample], int]:
    """One camera's samples (time order, misses have px None) -> the same samples with short gaps filled, and how
    many were filled. A gap is filled only with at least two measured samples on each side within the run."""
    out = list(samples)
    meas = [i for i, s in enumerate(out) if s.px is not None]
    filled = 0
    for a, b in zip(meas, meas[1:], strict=False):
        if b - a < 2 or out[b].t_s - out[a].t_s > max_gap_s:
            continue
        left = [i for i in meas if i <= a][-support:]
        right = [i for i in meas if i >= b][:support]
        if len(left) < 2 or len(right) < 2:
            continue
        knots = left + right
        ts = [out[i].t_s for i in knots]
        if any(t1 - t0 > max_gap_s for t0, t1 in zip(ts, ts[1:], strict=False)):
            continue  # the support itself spans a long dropout: not one continuous flight
        us = [out[i].px[0] for i in knots]  # type: ignore[index]
        vs = [out[i].px[1] for i in knots]  # type: ignore[index]
        mu, mv = pchip_slopes(ts, us), pchip_slopes(ts, vs)
        conf = min(out[a].conf, out[b].conf) * conf_scale
        for j in range(a + 1, b):
            t = out[j].t_s
            out[j] = replace(out[j], px=(pchip_eval(ts, us, mu, t), pchip_eval(ts, vs, mv, t)), conf=conf)
            filled += 1
    return out, filled
