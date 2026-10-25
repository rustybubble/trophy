"""Combined-session clock, calibration and model-boundary regression tests."""
import json

import numpy as np
import pytest

from trophy import session
from trophy.replay.multiview import load_camera, project


def sample_view(name='side'):
    camera = load_camera(f'samples/tt3d/game_00/{name}.yaml')
    info = dict(width=1920, height=1080, duration=10)
    view = dict(video=f'{name}.mp4', table_corners_px=project(session.TABLE_CORNERS, camera).tolist(),
                player_rois_px=[[0, 0, 960, 1080], [960, 0, 1920, 1080]])
    return camera, view, info


@pytest.mark.parametrize('name', ['side', 'oblique'])
def test_table_calibration_recovers_known_camera_without_reference_ball(name):
    actual, view, info = sample_view(name)
    found, report = session.calibrate_camera(view, info)
    assert np.allclose(found['K'], actual['K'], atol=.01)
    assert np.allclose(found['center'], actual['center'], atol=1e-5)
    assert report['table_corner_rmse_px'] < .001


@pytest.mark.parametrize('points', [None, [[0, 0]]*4, [[10, 10], [100, 100], [10, 100], [100, 10]],
                                   [[10, 10], [2000, 10], [100, 100], [10, 100]]])
def test_invalid_calibration_is_rejected(points):
    _, view, info = sample_view()
    view['table_corners_px'] = points
    with pytest.raises(ValueError):
        session.calibrate_camera(view, info)


@pytest.mark.parametrize('offset,expected', [(2, [1, 3]), (-2, [2, 0])])
def test_shared_segment_clock_sign_and_overlap(offset, expected):
    starts, count = session.shared_segment([{'duration': 10}, {'duration': 5}], 1, 6, offset)
    assert starts == expected
    assert count == min(6, 10-expected[0], 5-expected[1])*30


def test_nonoverlapping_or_short_sources_fail_before_inference():
    with pytest.raises(ValueError, match='overlapping'):
        session.shared_segment([{'duration': 2}, {'duration': 2}], 0, 2, 3)
    with pytest.raises(ValueError, match='finite'):
        session.shared_segment([{'duration': 2}]*2, 0, 2, float('nan'))


def test_reversed_image_sides_preserve_player_identity_and_share_replay_clock():
    _, view, info = sample_view()
    reversed_view = dict(view, player_rois_px=view['player_rois_px'][::-1])
    config = session.serve_config([view, reversed_view], ['a.mp4', 'b.mp4'], [info]*2, -.04, 'test')
    assert config['views'][0]['player_map'] == {'left': 'p0', 'right': 'p1'}
    assert config['views'][1]['player_map'] == {'left': 'p1', 'right': 'p0'}
    assert config['views'][1]['source_offset_seconds'] == -.04
    assert config['views'][1]['player_regions_norm']['left'] == [0, 0, .5, 1]


def test_packaging_preserves_meshes_and_ball_missingness_and_uses_portable_review(tmp_path):
    out = tmp_path
    replay = out / 'replay'
    replay.mkdir()
    for name in ['vertices.f32', 'faces.u32']:
        (replay / name).write_bytes(b'existing-model-data')
    scene = dict(frame_count=2, duration=1, start_time=.1, frames=[
        dict(frame_index=1, time=.1, ball={'position': None, 'status': 'missing_or_rejected'}),
        dict(frame_index=2, time=1, ball={'position': [1, 2, 3], 'status': 'triangulated'})])
    session.write_json(replay / 'scene.json', scene)
    (out / 'serves').mkdir()
    events = [dict(time_seconds=t) for t in [0, .5, 1.1]]
    session.write_json(out / 'serves/serves.json', dict(events=events, views=[{'video': 'a'}, {'video': 'b'}]))
    videos = []
    for i in [1, 2]:
        folder = out / f'ball-camera{i}'
        folder.mkdir()
        session.write_json(folder / 'detections.json', [])
        (folder / 'annotated.mp4').write_bytes(b'annotated')
        source = out / f'camera{i}.mp4'
        source.write_bytes(b'source-video')
        videos.append(source)
    result = session.package_replay(out, videos, [{'width': 640, 'height': 480}]*2, [8, 8.4], {'offset': .4})
    assert result['serve_events'] == [events[1]]
    assert result['frames'] == scene['frames']
    assert (replay / 'vertices.f32').read_bytes() == b'existing-model-data'
    review = json.loads((replay / 'review/serves.json').read_text())
    assert review['views'][1]['review_url'] == '../source2.mp4'
    assert (replay / 'source1.mp4').read_bytes() == b'source-video'
    assert ',,,,missing_or_rejected' in (replay / 'ball-3d.csv').read_text()


def test_model_stage_failure_stops_pipeline_and_preserves_failure_report(tmp_path, monkeypatch):
    _, view, info = sample_view()
    monkeypatch.setattr(session, 'preflight', lambda: None)
    monkeypatch.setattr(session, 'video_info', lambda p: info)
    calls = []
    def failing_stage(*args):
        calls.append(args)
        raise RuntimeError('explicit model failure')
    monkeypatch.setattr(session, 'run_stage', failing_stage)
    with pytest.raises(RuntimeError, match='explicit model failure'):
        session.analyze_two_camera(dict(views=[view, view], sync_mode='manual'), tmp_path/'session')
    assert len(calls) == 1
    report = json.loads((tmp_path / 'session/session-report.json').read_text())
    assert report['status'] == 'failed'
    assert not (tmp_path / 'session/replay/scene.json').exists()


def test_combined_page_and_existing_tools_load_without_errors():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(session.ROOT / 'app.py')).run(timeout=20)
    assert not app.exception
    assert any('Two-camera analysis' in title.value for title in app.title)
    assert any(button.label == 'Analyze clip' for button in app.button)
    assert any(button.label == 'Find serves' for button in app.button)


def test_source_preview_and_calibration_controls_work_in_pinned_numpy_environment():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(session.ROOT / 'app.py')).run(timeout=20)
    for index, name in enumerate(['side', 'oblique']):
        app.text_input(key=f'combined-path{index}').set_value(str(session.ROOT / f'samples/tt3d/game_00/{name}-010.mp4'))
    app.run(timeout=20)
    assert not app.exception
    assert not app.error
    assert len(app.subheader) == 2
    assert not next(b.disabled for b in app.button if b.label == 'Analyze both cameras')
    assert len(app.get('component_instance')) == 2
    assert not any(field.label in ['A · x, y', 'B · x, y', 'C · x, y', 'D · x, y'] for field in app.text_input)


def test_click_selection_preserves_source_pixels_and_incomplete_or_reset_state():
    from trophy.corner_picker import selected_corners
    points = [[356, 725], [1503, 753], [1348, 671], [538, 649]]
    assert selected_corners(points, 1920, 1080) == points
    assert selected_corners(points[:1], 1920, 1080) == [points[0], [None, None], [None, None], [None, None]]
    assert selected_corners([], 1920, 1080) == [[None, None]]*4
    for invalid in [[[1920, 0]], [[0, -1]], [[float('nan'), 3]], [[1, 2]]*5, [1, 2]]:
        with pytest.raises(ValueError):
            selected_corners(invalid, 1920, 1080)
