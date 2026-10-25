import csv
import json
import subprocess

import cv2
import numpy as np
import pytest

from trophy.model import geometry, preprocess, decode_heatmap, load_source, ROOT
from trophy.pipeline import Encoder, analyze, capture, verify_video, window_indices


def test_temporal_boundaries():
    assert window_indices(0) == []
    assert window_indices(1) == []
    assert window_indices(2) == []
    assert window_indices(3) == [(0, 1, 2)]
    windows = window_indices(8)
    assert windows[0] == (0, 1, 2) and windows[-1] == (5, 6, 7)
    assert set(sum((list(w) for w in windows), [])) == set(range(8))


@pytest.mark.parametrize('size', [(1280, 720), (720, 1280), (640, 480)])
def test_coordinate_roundtrip_and_full_frame(size):
    w, h = size
    mat = geometry(w, h)
    inv = cv2.invertAffineTransform(mat)
    for point in [(0, 0), (w / 2, h / 2), (w - 1, h - 1)]:
        transformed = mat @ np.r_[point, 1]
        assert np.all(transformed >= 0) and transformed[0] < 512 and transformed[1] < 288
        np.testing.assert_allclose(inv @ np.r_[transformed, 1], point, atol=.001)


def test_geometry_matches_upstream_for_landscape():
    upstream = load_source('test_upstream_image', ROOT / 'vendor/blurball/src/utils/image.py')
    expected = upstream.get_affine_transform(np.array([640, 360], np.float32), 1280, 0, [512, 288])
    np.testing.assert_allclose(geometry(1280, 720), expected, atol=.00001)


def test_rgb_normalization_and_chronological_channel_order():
    rgb = np.zeros((288, 512, 3), np.uint8)
    rgb[:, :, 0] = 255
    first, _ = preprocess(rgb)
    second, _ = preprocess(np.zeros_like(rgb))
    np.testing.assert_allclose(first[:, 100, 100], [(1 - .485) / .229, -.456 / .224, -.406 / .225], atol=1e-6)
    temporal = np.concatenate([first, second, first])
    assert temporal.shape == (9, 288, 512)
    np.testing.assert_array_equal(temporal[:3], first)
    np.testing.assert_array_equal(temporal[3:6], second)


def test_missing_threshold_mass_center_and_padding():
    hm = np.zeros((288, 512), np.float32)
    inv = cv2.invertAffineTransform(geometry(1280, 720))
    assert decode_heatmap(hm, inv, 1280, 720, .7) == ([], 0.)
    hm[100, 200] = .8
    hm[100, 201] = 1.
    candidates, peak = decode_heatmap(hm, inv, 1280, 720, .7)
    assert peak == 1 and len(candidates) == 1
    c = candidates[0]
    assert c['x'] == pytest.approx((200 * .8 + 201) / 1.8 * 2.5, abs=.001)
    assert c['y'] == pytest.approx(250)
    assert c['blur_length_px'] == pytest.approx(2.5)
    portrait_inv = cv2.invertAffineTransform(geometry(720, 1280))
    hm[:] = 0
    hm[100, 10] = 1
    assert decode_heatmap(hm, portrait_inv, 720, 1280, .7)[0] == []
    hm[:] = .7
    assert decode_heatmap(hm, inv, 1280, 720, .7)[0] == []


class FakePredictor:
    """Unit fixture only. End-to-end evidence uses the official checkpoint separately."""
    device = 'cpu'
    weight_sha256 = 'unit-test-fixture'
    warmup_ms = None
    calls = []
    def __init__(self, *a, **kw):
        type(self).calls = []
    def warmup(self, frames):
        self.warmup_ms = .01
    def predict(self, frames):
        self.calls.append([float(f[0, 100, 100]) for f in frames])
        hm = np.zeros((3, 288, 512), np.float32)
        # Heads have distinct locations; validates first/middle/last alignment.
        for head in range(3):
            hm[head, 140, 240 + head] = .9
        return hm, .01, .001


def make_video(path, values=(10, 30, 50, 70), width=64, height=36, fps=29.97):
    enc = Encoder(path, width, height, fps)
    for value in values:
        enc.write(np.full((height, width, 3), value, np.uint8))
    enc.close()


def test_exports_temporal_alignment_duplicates_and_fps(tmp_path, monkeypatch):
    monkeypatch.setattr('trophy.pipeline.Predictor', FakePredictor)
    source, out = tmp_path / 'input.mp4', tmp_path / 'output'
    make_video(source, (10, 30, 50, 50, 70))
    report = analyze(source, out, device='cpu')
    rows = json.loads((out / 'detections.json').read_text())
    with (out / 'detections.csv').open() as f:
        csvrows = list(csv.DictReader(f))
    assert len(rows) == len(csvrows) == report['analyzed_frame_count'] == 5
    assert report['inference_windows'] == 2
    assert report['exact_duplicate_frames'] == 1
    assert [r['temporal_contexts'] for r in rows] == [1, 2, 2, 2, 1]
    assert rows[0]['x'] == pytest.approx(240 / 8)
    assert rows[-1]['x'] == pytest.approx(242 / 8)
    assert rows[3]['x'] == rows[2]['x'] and rows[3]['duplicate_of_frame'] == 2
    assert rows[-1]['timestamp_seconds'] == pytest.approx(4 / 29.97, abs=.001)
    assert all(int(c['frame_index']) == r['frame_index'] for c, r in zip(csvrows, rows))
    assert report['output_video']['frames'] == 5
    assert report['output_video']['fps'] == pytest.approx(29.97, abs=.001)
    assert len(FakePredictor.calls) == 2
    assert FakePredictor.calls[0] == sorted(FakePredictor.calls[0])
    assert FakePredictor.calls[1][0] == FakePredictor.calls[0][1]


@pytest.mark.parametrize('values', [(10,), (10, 30), (10, 10, 10, 10)])
def test_short_clip_no_fabricated_positions(tmp_path, monkeypatch, values):
    monkeypatch.setattr('trophy.pipeline.Predictor', FakePredictor)
    source = tmp_path / 'short.mp4'
    make_video(source, values)
    report = analyze(source, tmp_path / 'out')
    rows = json.loads((tmp_path / 'out/detections.json').read_text())
    assert report['inference_windows'] == 0
    assert len(rows) == len(values)
    assert all(not r['detected'] and r['x'] is None and r['y'] is None and r['score'] is None for r in rows)
    assert all(r['status'] == 'insufficient_temporal_context' for r in rows)


def test_maximum_frames_and_duration(tmp_path, monkeypatch):
    monkeypatch.setattr('trophy.pipeline.Predictor', FakePredictor)
    source = tmp_path / 'clip.mp4'
    make_video(source, fps=30)
    assert analyze(source, tmp_path / 'a', max_frames=3)['analyzed_frame_count'] == 3
    assert analyze(source, tmp_path / 'b', max_duration=.05)['analyzed_frame_count'] == 2


def test_rotated_portrait_metadata(tmp_path, monkeypatch):
    import imageio_ffmpeg
    monkeypatch.setattr('trophy.pipeline.Predictor', FakePredictor)
    src, rotated = tmp_path / 'src.mp4', tmp_path / 'rotated.mp4'
    make_video(src)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-display_rotation', '90',
                    '-i', str(src), '-c', 'copy', str(rotated)], check=True)
    report = analyze(rotated, tmp_path / 'out')
    assert (report['source']['width'], report['source']['height']) == (36, 64)
    assert report['source']['rotation_metadata_degrees'] in (90, 270)
    assert (report['output_video']['width'], report['output_video']['height']) == (36, 64)


def test_invalid_inputs_and_encoder_failure(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        analyze(tmp_path / 'missing.mp4', tmp_path / 'a')
    source = tmp_path / 'bad.mp4'
    source.write_bytes(b'not a video')
    with pytest.raises(ValueError, match='threshold'):
        analyze(source, tmp_path / 'b', threshold=1)
    with pytest.raises(ValueError, match='decode'):
        analyze(source, tmp_path / 'c')
    monkeypatch.setattr('trophy.pipeline.imageio_ffmpeg.get_ffmpeg_exe', lambda: '/usr/bin/false')
    encoder = Encoder(tmp_path / 'fail.mp4', 64, 36, 30)
    with pytest.raises(RuntimeError, match='encoding failed'):
        encoder.close()
