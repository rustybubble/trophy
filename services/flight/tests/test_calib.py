import numpy as np
import pytest

from flight.calib import camera_looking_at, focal_from_homography, refine_corners, solve_pose
from flight.field import CORNERS_M

SIDE = dict(pos=(0.0, -3.2, 1.9), look_at=(0.0, 0.0, 0.3), f_px=1000.0)
DIAG = dict(pos=(3.0, 2.6, 2.1), look_at=(0.0, 0.0, 0.2), f_px=1050.0)


@pytest.mark.parametrize("spec", [SIDE, DIAG])
def test_pose_recovered_from_exact_corners(spec):
    truth = camera_looking_at("c", **spec)
    px = truth.project(CORNERS_M)
    cam = solve_pose("c", px, truth.width, truth.height)
    assert cam.f_source == "homography"
    assert abs(cam.K[0, 0] - spec["f_px"]) / spec["f_px"] < 0.02
    assert np.linalg.norm(cam.centre_m - np.asarray(spec["pos"])) < 0.05
    assert cam.reproj_err_px < 0.1
    pts = np.array([[0.5, 0.2, 0.3], [-1.0, -0.6, 0.05], [1.2, 0.7, 0.5]])
    assert np.abs(cam.project(pts) - truth.project(pts)).max() < 1.0


def test_pose_with_noisy_corners_reports_error():
    truth = camera_looking_at("c", **SIDE)
    rng = np.random.default_rng(0)
    px = truth.project(CORNERS_M) + rng.normal(0, 1.5, (4, 2))
    cam = solve_pose("c", px, truth.width, truth.height)
    assert 0.2 < cam.reproj_err_px < 4.0
    assert np.linalg.norm(cam.centre_m - np.asarray(SIDE["pos"])) < 0.3


def test_focal_from_homography_matches_truth():
    import cv2

    truth = camera_looking_at("c", **DIAG)
    H, _ = cv2.findHomography(CORNERS_M[:, :2], truth.project(CORNERS_M))
    f = focal_from_homography(H, truth.width / 2, truth.height / 2)
    assert abs(f - DIAG["f_px"]) / DIAG["f_px"] < 0.02


def test_lift_to_plane_inverts_projection():
    truth = camera_looking_at("c", **SIDE)
    p = np.array([0.4, -0.3, 0.02])
    px = truth.project(p)[0]
    back = truth.lift_to_plane(px, 0.02)
    assert np.linalg.norm(back - p) < 1e-6


def test_refine_corners_snaps_to_drawn_table():
    import cv2

    truth = camera_looking_at("c", **SIDE)
    px = truth.project(CORNERS_M)
    img = np.full((720, 1280), 60, np.uint8)
    cv2.fillPoly(img, [np.round(px).astype(np.int32)], 140)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    tapped = px + np.array([[4, -3], [-5, 2], [3, 4], [-2, -4]], float)
    refined = refine_corners(img, tapped)
    before = np.linalg.norm(tapped - px, axis=1).mean()
    after = np.linalg.norm(refined - px, axis=1).mean()
    assert after < before / 2
    assert after < 1.5
