"""A missing first hip frame must not discard later real body observations."""
import numpy as np
import pytest

from trophy.replay.body_initialization import initialize_body_roots
from trophy.replay.multiview import load_camera, project


def observed_clip():
    cameras = [load_camera(f'samples/tt3d/game_00/{name}.yaml') for name in ['side', 'oblique']]
    times = np.array([0., .1, .3, .6, .8])
    poses = np.full((2, len(times), 2, 33, 3), np.nan)
    roots = np.array([[[.05+t*.1, 1.7, .1], [-.05-t*.1, -1.7, .1]] for t in times])
    for view, camera in enumerate(cameras):
        for frame in range(len(times)):
            for player in range(2):
                pixels = project(roots[frame, player], camera)[0]
                poses[view, frame, player, 23:25] = [*pixels, .99]
    return times, poses, cameras, roots


def test_leading_occlusion_uses_later_anchor_without_calling_it_observed():
    times, poses, cameras, expected = observed_clip()
    poses[:, :2, 1, 23:25] = np.nan
    roots, sources, observed = initialize_body_roots(times, poses, cameras)
    assert np.isfinite(roots).all()
    assert np.allclose(roots[:2, 1], expected[2, 1], atol=1e-5)
    assert not observed[:2, 1].any()
    assert all(s.startswith('nearest observed') for s in sources[:2, 1])
    assert np.allclose(roots[observed], expected[observed], atol=1e-5)


def test_gaps_interpolate_by_actual_time_and_preserve_other_player():
    times, poses, cameras, expected = observed_clip()
    poses[:, 2, 0, 23:25] = np.nan
    roots, sources, observed = initialize_body_roots(times, poses, cameras)
    assert not observed[2, 0]
    assert sources[2, 0].startswith('interpolated')
    assert np.allclose(roots, expected, atol=1e-5)
    assert observed[:, 1].all()


def test_no_real_anchor_fails_explicitly_instead_of_inventing_player_location():
    times, poses, cameras, _ = observed_clip()
    poses[:, :, 1, 23:25] = np.nan
    with pytest.raises(ValueError, match='Player 2 has no usable two-camera hip anchors'):
        initialize_body_roots(times, poses, cameras)


def test_invisible_hip_guesses_are_not_triangulation_anchors():
    times, poses, cameras, _ = observed_clip()
    poses[:, 0, :, 23:25, 2] = .1
    _, _, observed = initialize_body_roots(times, poses, cameras)
    assert not observed[0].any()
