"""Automatic demo outlines must cover the full table, not just one net half."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from trophy.table_detection import detect_table, tabletop_quad
from trophy.session import calibrate_camera


def test_blank_frame_does_not_become_a_table():
    assert detect_table(np.full((540, 960, 3), 230, np.uint8)) is None


def test_visible_table_boundary_is_found_from_pixels_without_entered_corners():
    image = np.full((540, 960, 3), 230, np.uint8)
    polygon = np.array([[175, 378], [533, 436], [676, 295], [460, 277]], np.int32)
    cv2.fillConvexPoly(image, polygon, (175, 163, 162))
    cv2.polylines(image, [polygon], True, (250, 250, 250), 3)
    cv2.line(image, (340, 315), (626, 343), (30, 30, 30), 7)
    result = tabletop_quad(image)
    assert result is not None
    points, _ = result
    assert points[:, 1].min() < 295
    assert points[:, 1].max() > 420
    assert cv2.contourArea(points.astype(np.float32)) > 35000


@pytest.mark.parametrize('index', [1, 2])
def test_uploaded_demo_views_segment_and_initialize_usable_calibration(index):
    # Local real-footage regression, not a claim of independent metric accuracy.
    path = Path(f'artifacts/table-segmentation-check/camera{index}.jpg')
    if not path.exists():
        pytest.skip('Demo first-frame snapshots are not present')
    image = cv2.imread(str(path))
    result = detect_table(image)
    assert result is not None
    points = np.asarray(result['corners'])
    assert cv2.isContourConvex(points.astype(np.float32))
    if index == 1:
        assert points[:, 0].min() < 230 and points[:, 0].max() > 700
    else:
        assert points[:, 1].min() < 300 and points[:, 1].max() > 420
    _, report = calibrate_camera(dict(table_corners_px=result['corners'], focal_px=result['focal_px'],
        calibration_mode=result['calibration_mode'], player_rois_px=[[0, 0, 480, 540], [480, 0, 960, 540]]),
        dict(width=960, height=540))
    assert report['table_corner_rmse_px'] < 8
