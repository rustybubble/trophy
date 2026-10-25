"""Explicit display estimates for an incomplete measured 3D ball track.

Raw measurements are never overwritten. Smoothing respects inferred impact
boundaries; shape-preserving interpolation cannot overshoot its support. These
are trajectory estimates, not additional measured positions or contact labels.
"""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.signal import find_peaks


def complete_ball_track(times, positions, *, max_gap_s=1.25, extrapolate_s=.35):
    times = np.asarray(times, float)
    raw = np.asarray(positions, float)
    if raw.shape != (len(times), 3) or len(times) < 2:
        raise ValueError('Expected an N x 3 track with at least two timestamps')
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('Timestamps must be finite and strictly increasing')
    if max_gap_s <= 0 or extrapolate_s < 0:
        raise ValueError('Invalid temporal limits')
    valid = np.isfinite(raw).all(axis=1)
    ids = np.flatnonzero(valid)
    output = np.full_like(raw, np.nan)
    status = np.full(len(times), 'unavailable', dtype=object)
    if len(ids) < 3:
        output[valid] = raw[valid]
        status[valid] = 'triangulated'
        return output, status.tolist(), dict(impact_candidates=[], measured_frames=int(valid.sum()))

    # Split at lengthy missing intervals; never smooth through them.
    breaks = np.flatnonzero(np.diff(times[ids]) > .22) + 1
    groups = np.split(ids, breaks)
    impacts = []
    smoothed = raw.copy()
    for group in groups:
        if len(group) < 4:
            continue
        points = raw[group]
        # Turnarounds near table ends and sharp height minima are fit boundaries,
        # not automatically confirmed racket hits or table contacts.
        turns = np.r_[find_peaks(points[:, 1], prominence=.3, distance=5)[0],
                      find_peaks(-points[:, 1], prominence=.3, distance=5)[0]]
        lows = find_peaks(-points[:, 2], prominence=.07, distance=4)[0]
        lows = lows[points[lows, 2] < .2]
        boundaries = sorted(set([0, len(group)-1, *turns.tolist(), *lows.tolist()]))
        impacts.extend(int(group[j]) for j in sorted(set([*turns.tolist(), *lows.tolist()])))
        for left, right in zip(boundaries[:-1], boundaries[1:]):
            for j in range(left+1, right):
                neighbours = np.arange(max(left, j-2), min(right+1, j+3))
                support = group[neighbours]
                if len(support) < 4:
                    continue
                dt = times[support] - times[group[j]]
                design = np.c_[np.ones(len(dt)), dt, dt**2]
                fit = np.linalg.lstsq(design, raw[support], rcond=None)[0]
                residual = np.linalg.norm(design @ fit - raw[support], axis=1)
                weights = np.minimum(1., .025 / np.maximum(residual, 1e-8))
                fit = np.linalg.lstsq(design * weights[:, None],
                                      raw[support] * weights[:, None], rcond=None)[0]
                # Bound the smoothing displacement; leave major changes visible.
                delta = fit[0] - raw[group[j]]
                norm = np.linalg.norm(delta)
                smoothed[group[j]] = raw[group[j]] + delta * min(1., .045/max(norm, 1e-9))
    output[valid] = smoothed[valid]
    status[valid] = 'triangulated_smoothed'

    # Interpolate each supported component separately to avoid silently bridging
    # a long interval via the interpolator's global spline support.
    for group in np.split(ids, np.flatnonzero(np.diff(times[ids]) > max_gap_s) + 1):
        if len(group) < 2:
            continue
        interpolation = PchipInterpolator(times[group], smoothed[group], axis=0, extrapolate=False)
        for a, b in zip(group[:-1], group[1:]):
            interior = np.arange(a+1, b)
            if len(interior):
                output[interior] = interpolation(times[interior])
                status[interior] = 'interpolated' if times[b]-times[a] <= .25 else 'long_gap_estimate'

    # End extrapolation is deliberately bounded. Velocity is estimated from a
    # local observed run and decays with horizon, limiting runaway predictions.
    for side in ['leading', 'trailing']:
        edge = ids[0] if side == 'leading' else ids[-1]
        support = ids[:5] if side == 'leading' else ids[-5:]
        support = support[np.abs(times[support]-times[edge]) <= .25]
        if len(support) < 3:
            continue
        dt = times[support]-times[edge]
        velocity = np.linalg.lstsq(np.c_[np.ones(len(dt)), dt], smoothed[support], rcond=None)[0][1]
        speed = np.linalg.norm(velocity)
        velocity *= min(1., 12/max(speed, 1e-9))
        candidate = np.flatnonzero((times < times[edge]) if side == 'leading' else (times > times[edge]))
        for j in candidate:
            delta = times[j]-times[edge]
            if abs(delta) <= extrapolate_s+1e-9:
                output[j] = smoothed[edge] + velocity*delta*(1-.3*abs(delta)/max(extrapolate_s, 1e-9))
                status[j] = 'extrapolated'

    # Table geometry is a display constraint, not a claim of a detected bounce.
    finite = np.isfinite(output).all(axis=1)
    over_table = finite & (np.abs(output[:, 0]) <= .7625) & (np.abs(output[:, 1]) <= 1.37)
    output[over_table, 2] = np.maximum(output[over_table, 2], .02)
    impossible = finite & ((np.linalg.norm(output[:, :2], axis=1) > 5) |
                           (output[:, 2] > 2.5) | (output[:, 2] < -.74))
    output[impossible] = np.nan
    status[impossible] = 'unavailable'
    return output, status.tolist(), dict(impact_candidates=impacts, measured_frames=int(valid.sum()),
        smoothing='impact-aware robust local quadratic, displacement capped at 4.5 cm',
        interpolation='shape-preserving cubic; estimates preserve raw evidence separately',
        max_gap_seconds=max_gap_s, extrapolation_limit_seconds=extrapolate_s)
