"""Observed hip anchors for initializing the subsequent image-based body fit.

Interpolated or nearest anchors are optimizer starting values, not measured
positions. They never replace the independently reconstructed ball observations.
"""
import numpy as np

from .multiview import triangulate


def initialize_body_roots(times, aligned_poses, cameras, max_error=35):
    times = np.asarray(times, float)
    if times.ndim != 1 or not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('Body initialization needs finite, increasing frame times')
    poses = np.asarray(aligned_poses, float)
    if poses.shape != (2, len(times), 2, 33, 3):
        raise ValueError('Body initialization requires two aligned views and two player tracks')
    anchors = np.full((len(times), 2, 3), np.nan)
    for frame in range(len(times)):
        for player in range(2):
            hips = poses[:, frame, player, 23:25]
            if not np.isfinite(hips).all() or np.any(hips[..., 2] < .45):
                continue
            result = triangulate(hips[..., :2].mean(axis=1), cameras, max_error=max_error)
            if result is not None:
                anchors[frame, player] = result['position']
    observed = np.isfinite(anchors).all(axis=-1)
    sources = np.empty(observed.shape, dtype=object)
    roots = np.empty_like(anchors, dtype=np.float32)
    for player in range(2):
        good = np.flatnonzero(observed[:, player])
        if not len(good):
            raise ValueError(f'Player {player+1} has no usable two-camera hip anchors anywhere in the shared interval. '
                             'Check player regions, identity matching, calibration and camera sync.')
        for axis in range(3):
            roots[:, player, axis] = np.interp(times, times[good], anchors[good, player, axis])
        for frame in range(len(times)):
            if observed[frame, player]:
                sources[frame, player] = 'two-view hip triangulation'
            elif frame < good[0] or frame > good[-1]:
                sources[frame, player] = 'nearest observed hip initialization; fitted to current images'
            else:
                sources[frame, player] = 'interpolated hip initialization; fitted to current images'
    return roots, sources, observed
