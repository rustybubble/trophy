"""Integrity and measured-output checks for the optional real HMR2 experiment."""
import json
from pathlib import Path

import numpy as np
import pytest

OUT = Path(__file__).resolve().parents[1] / 'artifacts/user-two-camera/reconstruction'


def result():
    if not (OUT / 'fitted-bodies.npz').exists():
        pytest.skip('Run the real HMR2 user-footage reconstruction first')
    return np.load(OUT / 'fitted-bodies.npz'), json.loads((OUT / 'scene.json').read_text())


def test_exported_mesh_dimensions_and_faces_match_the_viewer():
    body, scene = result()
    count = len(body['times'])
    assert body['vertices'].shape == (count, 2, 6890, 3)
    assert np.isfinite(body['vertices']).all()
    assert body['faces'].shape[1] == 3
    assert body['faces'].min() >= 0 and body['faces'].max() < 6890
    assert (OUT / 'vertices.f32').stat().st_size == count * 2 * 6890 * 3 * 4
    assert (OUT / 'faces.u32').stat().st_size == body['faces'].size * 4
    assert scene['frame_count'] == len(scene['frames']) == count
    from trophy.replay.multiview import viewer_coordinates
    assert np.allclose([f['player_roots'] for f in scene['frames']],
                       viewer_coordinates(body['roots']))


def test_body_rotations_and_shape_are_finite_and_anatomically_parameterized():
    body, _ = result()
    rotation = body['rotations']
    assert np.isfinite(rotation).all() and np.isfinite(body['betas']).all()
    assert np.allclose(rotation @ rotation.swapaxes(-1, -2), np.eye(3), atol=1e-5)
    assert np.allclose(np.linalg.det(rotation), 1, atol=1e-5)
    assert body['betas'].shape == (2, 10)


def test_real_body_fit_improves_image_agreement_without_claiming_metric_truth():
    _, scene = result()
    report = scene['report']
    assert report['reprojection_after']['median_px'] < report['reprojection_before']['median_px']
    assert report['reprojection_after']['median_px'] < 10
    assert not report['human_3d_ground_truth_available']
    assert not report['independent_3d_accuracy_measured']
    assert not scene['geometry_report']['metric_ground_truth_available']


def test_ball_positions_are_preserved_from_the_independent_triangulation():
    _, scene = result()
    source = json.loads((OUT.parent / 'hmr2/geometry.json').read_text())
    for frame in scene['frames']:
        assert frame['ball'] == source['ball'][frame['frame_index']]
    assert any(f['ball']['position'] is None for f in scene['frames'])
    assert not source['ball_report']['missing_positions_fabricated']
