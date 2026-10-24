"""Tabletop homography and explicitly qualified OpenCV pinhole calibration.

No courtcam source is vendored. The default four-click fit is a rendering aid,
not independently validated metric calibration above the table.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any

import cv2
import numpy as np

HALF_LENGTH = 1.37
HALF_WIDTH = 0.7625
LANDMARKS = {
    "A_left": (-HALF_LENGTH, HALF_WIDTH, 0.0),
    "A_right": (-HALF_LENGTH, -HALF_WIDTH, 0.0),
    "B_right": (HALF_LENGTH, -HALF_WIDTH, 0.0),
    "B_left": (HALF_LENGTH, HALF_WIDTH, 0.0),
}
LINES = {
    "end_A": [LANDMARKS["A_left"], LANDMARKS["A_right"]],
    "end_B": [LANDMARKS["B_left"], LANDMARKS["B_right"]],
    "side_left": [LANDMARKS["A_left"], LANDMARKS["B_left"]],
    "side_right": [LANDMARKS["A_right"], LANDMARKS["B_right"]],
    "net": [(0.0, HALF_WIDTH, 0.0), (0.0, -HALF_WIDTH, 0.0)],
    "centre": [(-HALF_LENGTH, 0.0, 0.0), (HALF_LENGTH, 0.0, 0.0)],
}


def _array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.size == math.prod(shape):
        result = result.reshape(shape)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain {math.prod(shape)} finite values")
    return result


def _project_plane(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.c_[points[:, :2], np.ones(len(points))] @ matrix.T
    if np.any(np.abs(homogeneous[:, 2]) < 1e-10):
        raise ValueError("Homography sends a required table line to infinity")
    return homogeneous[:, :2] / homogeneous[:, 2, None]


def calibrate(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return `trophy.calibration.v1`, or raise ValueError on invalid taps.

    Optional extensions preserve the v1 schema: `intrinsics: {K: [...9]}`,
    `validation_points: [{pos_m: [x,y,z], px:[u,v]}]`. Independent validation
    must contain >=4 off-plane points and span >=0.16 m in z for metric trust.
    Intrinsics use a rectified image with zero distortion only. Distorted lens
    calibration is intentionally unsupported rather than mixing distortion models.
    """
    if request.get("schema") != "trophy.calibration_request.v1":
        raise ValueError("Expected trophy.calibration_request.v1")
    if request.get("sport") != "table_tennis":
        raise ValueError("Only table_tennis is implemented")
    size = request.get("image_size", {})
    width, height = size.get("w"), size.get("h")
    if not isinstance(width, int) or not isinstance(height, int) or min(width, height) <= 0:
        raise ValueError("image_size must contain positive integer w/h")
    taps = request.get("points", [])
    if len(taps) != 4 or {tap.get("name") for tap in taps} != set(LANDMARKS):
        raise ValueError("Tap exactly A_left, A_right, B_right, B_left once each")
    by_name = {tap["name"]: tap["px"] for tap in taps}
    pixels = _array([by_name[name] for name in LANDMARKS], (4, 2), "table pixels")
    if np.any(pixels < 0) or np.any(pixels[:, 0] >= width) or np.any(pixels[:, 1] >= height):
        raise ValueError("Table taps must be inside the source image")
    contour = pixels.astype(np.float32)
    area = abs(float(cv2.contourArea(contour)))
    if not cv2.isContourConvex(contour) or area < max(64.0, width * height * 0.001):
        raise ValueError("Table taps must form a convex, nondegenerate quadrilateral with sufficient area")
    distances = np.linalg.norm(pixels[:, None] - pixels[None, :], axis=-1)
    if np.min(distances[np.triu_indices(4, 1)]) < 8:
        raise ValueError("Table corners are too close together")
    world = np.asarray(list(LANDMARKS.values()), dtype=np.float64)
    homography, _ = cv2.findHomography(pixels, world[:, :2], method=0)
    if homography is None or not np.isfinite(homography).all():
        raise ValueError("No finite tabletop homography")
    inverse = np.linalg.inv(homography)
    # Normalize by coordinate scales before testing conditioning; raw pixel/metre
    # matrix condition numbers vary merely because source resolution changes.
    normalized = np.diag([1 / HALF_LENGTH, 1 / HALF_WIDTH, 1]) @ homography @ np.diag([width, height, 1])
    if np.linalg.cond(normalized) > 1e6:
        raise ValueError("Table geometry is ill-conditioned")
    errors = np.linalg.norm(_project_plane(world, inverse) - pixels, axis=1)
    span = float(np.max(distances))
    gate = max(5.0, span * 0.01)
    overlays = [_project_plane(np.asarray(line), inverse).reshape(-1).tolist() for line in LINES.values()]
    warnings = [
        "Homography is valid only on the tabletop z=0; it does not measure airborne ball height.",
        "Four-corner reprojection residual is a fit residual, not held-out calibration accuracy.",
        "Moving or zooming cameras require recalibration at the relevant source time.",
    ]
    response: dict[str, Any] = {
        "schema": "trophy.calibration.v1",
        "game_id": request.get("game_id", ""),
        "cam_id": request.get("cam_id", ""),
        "sport": "table_tennis",
        "created_at_ms": time.time() * 1000,
        "image_size": {"w": width, "h": height},
        "method": "homography",
        "H_img_to_field": homography.reshape(-1).tolist(),
        "reproj_err_px": float(np.sqrt(np.mean(errors**2))),
        "trusted": False,
        "warnings": warnings,
        "overlay_px": overlays,
        "solver": "opencv-planar-v1",
    }
    intrinsics = request.get("intrinsics")
    if intrinsics:
        K = _array(intrinsics.get("K"), (3, 3), "intrinsics K")
        if not np.allclose(K[2], [0, 0, 1]) or min(K[0, 0], K[1, 1]) <= 0:
            raise ValueError("K must be a positive-focal pinhole camera matrix")
        if not (0.15 * width < K[0, 0] < 10 * width and 0.15 * height < K[1, 1] < 10 * width):
            raise ValueError("Implausible focal lengths")
        if intrinsics.get("dist") and np.any(np.asarray(intrinsics["dist"]) != 0):
            raise ValueError("Rectify the image first; nonzero lens distortion is not supported")
        assumed_intrinsics = False
    else:
        focal = max(width, height)
        K = np.array([[focal, 0.0, width / 2], [0.0, focal, height / 2], [0.0, 0.0, 1.0]])
        assumed_intrinsics = True
        warnings.append("Pinhole intrinsics are assumed (f=max(w,h), centred principal point, zero distortion).")
    try:
        ok, rvec, tvec = cv2.solvePnP(world, pixels, K, None, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            raise ValueError("Pinhole pose solver failed")
        rotation = cv2.Rodrigues(rvec)[0]
        camera = -rotation.T @ tvec.reshape(3)
        depths = (world @ rotation.T + tvec.reshape(3))[:, 2]
        pnp_pixels = cv2.projectPoints(world, rvec, tvec, K, None)[0].reshape(-1, 2)
        pnp_error = float(np.sqrt(np.mean(np.sum((pnp_pixels - pixels) ** 2, axis=1))))
        if camera[2] <= 0 or np.any(depths <= 0) or pnp_error > gate:
            warnings.append("Pinhole pose rejected: below-table/behind-camera geometry or excessive residual.")
            return response
        response.update(
            {
                "method": "homography+pnp_approximate" if assumed_intrinsics else "homography+pnp",
                "K": K.reshape(-1).tolist(),
                "dist": [0.0],
                "rvec": rvec.reshape(3).tolist(),
                "tvec": tvec.reshape(3).tolist(),
                "camera_position_m": camera.tolist(),
            }
        )
        validation = request.get("validation_points", [])
        if not assumed_intrinsics and len(validation) >= 4:
            check_world = _array([p["pos_m"] for p in validation], (len(validation), 3), "validation positions")
            check_pixels = _array([p["px"] for p in validation], (len(validation), 2), "validation pixels")
            projected = cv2.projectPoints(check_world, rvec, tvec, K, None)[0].reshape(-1, 2)
            validation_error = float(np.max(np.linalg.norm(projected - check_pixels, axis=1)))
            elevated = np.count_nonzero(np.abs(check_world[:, 2]) >= 0.08) >= 4
            spread = float(np.ptp(np.r_[check_world[:, 2], 0.0])) >= 0.16
            if elevated and spread and validation_error <= gate:
                response["trusted"] = True
                warnings.append(f"Independent nonplanar validation max residual {validation_error:.3f} px.")
            else:
                warnings.append("Independent validation failed residual/elevated-point/span gate.")
        if not response["trusted"]:
            warnings.append(
                "Metric camera pose is untrusted until known intrinsics and independent elevated checks pass."
            )
    except cv2.error:
        warnings.append("Pinhole pose unavailable; tabletop homography remains available.")
    return response
