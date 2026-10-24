"""Validated-input, timestamp-aware stereo geometry; never a referee ruling.

OpenCV convention: X_camera = R @ X_world + t. World units are metres.
Clock convention: source_time_s = game_time_s * drift + offset_s.

DLT and robust reprojection refinement are adapted from the user's earlier
`calhacks/trophy/replay/multiview.py` implementation (2026-10-23 local snapshot).
No reference 3D trajectory is accepted. This module does not make the moving
phone recordings calibrated: their metric reconstruction remains unavailable.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from scipy.optimize import least_squares


@dataclass(frozen=True)
class ClockMap:
    """Maps a camera's source PTS to a shared game timeline, with explicit sign."""

    offset_s: float = 0.0
    drift: float = 1.0

    def __post_init__(self):
        if not np.isfinite([self.offset_s, self.drift]).all() or self.drift <= 0:
            raise ValueError("Clock offset must be finite and drift must be positive")

    def source_time(self, game_time_s: float) -> float:
        return game_time_s * self.drift + self.offset_s

    def game_time(self, source_time_s: float) -> float:
        return (source_time_s - self.offset_s) / self.drift


IDENTITY_CLOCK = ClockMap()


def _missing(reason: str) -> dict[str, Any]:
    return {"status": "missing", "reason": reason, "px": None, "source_frames": []}


def sample_at(
    rows: Sequence[Mapping[str, Any]],
    t_game_s: float,
    clock: ClockMap = IDENTITY_CLOCK,
    *,
    mode: str = "nearest",
    max_gap_s: float = 0.05,
    max_time_delta_s: float = 0.01,
) -> dict[str, Any]:
    """Select real PTS observations or explicitly interpolate consecutive pairs.

    Each input row has `seq`, `t_source_s`, and `px:[x,y] | None`. Optional
    `sigma_px` is localization standard deviation, not detector confidence.
    Explicitly missing rows, long gaps, and timeline boundaries are never filled.
    Linear interpolation is a geometry hypothesis, not an observed exposure.
    """
    if mode not in ("nearest", "linear"):
        raise ValueError("mode must be nearest or linear")
    if not np.isfinite([t_game_s, max_gap_s, max_time_delta_s]).all() or min(max_gap_s, max_time_delta_s) < 0:
        raise ValueError("Time and nonnegative sampling tolerances must be finite")
    if not rows:
        return _missing("no_source_frames")
    stamps = [float(row["t_source_s"]) for row in rows]
    seqs = [row["seq"] for row in rows]
    if not np.isfinite(stamps).all() or any(b <= a for a, b in zip(stamps, stamps[1:], strict=False)):
        raise ValueError("Source PTS must be finite and strictly increasing")
    if any(not isinstance(seq, int) or seq < 0 for seq in seqs) or len(set(seqs)) != len(seqs):
        raise ValueError("Source sequence identifiers must be unique nonnegative integers")
    target = clock.source_time(t_game_s)
    if target < stamps[0] - 1e-10 or target > stamps[-1] + 1e-10:
        return _missing("outside_source_coverage")
    index = bisect_left(stamps, target)
    exact = next((i for i in (index, index - 1) if 0 <= i < len(rows) and abs(stamps[i] - target) <= 1e-10), None)
    if exact is not None:
        ids = [exact]
        weight = 0.0
    elif mode == "nearest":
        ids = [min((index - 1, index), key=lambda i: abs(stamps[i] - target))]
        if abs(clock.game_time(stamps[ids[0]]) - t_game_s) > max_time_delta_s:
            return _missing("nearest_frame_too_far")
        weight = 0.0
    else:
        ids = [index - 1, index]
        gap = (stamps[index] - stamps[index - 1]) / clock.drift
        if gap > max_gap_s:
            return _missing("source_gap_too_long")
        weight = (target - stamps[index - 1]) / (stamps[index] - stamps[index - 1])
    selected = [rows[i] for i in ids]
    identities = {row["cam_id"] for row in selected if row.get("cam_id") is not None}
    if len(identities) > 1:
        return _missing("mixed_source_camera_identity")
    if any(row.get("px") is None or row.get("status") == "missing" for row in selected):
        return _missing("source_observation_missing")
    pixels = np.asarray([row["px"] for row in selected], dtype=float)
    if pixels.shape != (len(ids), 2) or not np.isfinite(pixels).all():
        return _missing("invalid_source_pixels")
    px = pixels[0] if len(ids) == 1 else pixels[0] * (1 - weight) + pixels[1] * weight
    source_frames = [
        {"seq": rows[i]["seq"], "t_source_s": stamps[i], "t_game_s": clock.game_time(stamps[i])} for i in ids
    ]
    if len(ids) == 1:
        timing_bound = abs(source_frames[0]["t_game_s"] - t_game_s)
    else:
        # With only a speed bound, arbitrary acceleration/contact can deviate
        # from the chord. This conservative displacement equivalent peaks at
        # half the endpoint interval; it does not assert smooth flight/contact.
        a, b = t_game_s - source_frames[0]["t_game_s"], source_frames[1]["t_game_s"] - t_game_s
        timing_bound = 2 * a * b / (a + b)
    sigma = max(float(row["sigma_px"]) for row in selected) if all("sigma_px" in row for row in selected) else None
    return {
        "status": "observed" if len(ids) == 1 else "interpolated",
        "cam_id": next(iter(identities), None),
        "px": px.tolist(),
        "sigma_px": sigma,
        "source_frames": source_frames,
        "t_game_s": t_game_s,
        "target_source_s": target,
        "interpolation_weight": weight if len(ids) == 2 else None,
        "temporal_error_bound_s": timing_bound,
    }


def _camera(camera: Mapping[str, Any]):
    K = np.asarray(camera["K"], dtype=float).reshape(3, 3)
    if "R" in camera:
        R = np.asarray(camera["R"], dtype=float).reshape(3, 3)
    else:
        R = cv2.Rodrigues(np.asarray(camera["rvec"], dtype=float).reshape(3))[0]
    t = np.asarray(camera.get("t", camera.get("tvec")), dtype=float).reshape(3)
    if not np.isfinite(K).all() or not np.isfinite(R).all() or not np.isfinite(t).all():
        raise ValueError("Camera matrices must be finite")
    if not np.allclose(K[2], [0, 0, 1]) or min(K[0, 0], K[1, 1]) <= 0:
        raise ValueError("K must have positive focal lengths and pinhole bottom row")
    if not np.allclose(R @ R.T, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(R), 1, atol=1e-6):
        raise ValueError("R must be a proper orthonormal rotation")
    return {"K": K, "R": R, "t": t, "P": K @ np.c_[R, t], "center": -R.T @ t}


def _project(position: np.ndarray, camera: Mapping[str, np.ndarray]) -> np.ndarray:
    point = camera["P"] @ np.r_[position, 1.0]
    return point[:2] / point[2]


def _rejected(reason: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason, "pos_m": None, "sources": [dict(row) for row in observations]}


def triangulate(
    observations: Sequence[Mapping[str, Any]],
    cameras: Sequence[Mapping[str, Any]],
    *,
    sync_uncertainty_s: float | None,
    speed_bound_mps: float | None,
    max_metric_error_m: float = 0.03,
    max_reprojection_error_px: float = 3.0,
    min_ray_angle_deg: float = 1.0,
    pixel_sigma_px: float | None = None,
) -> dict[str, Any]:
    """Triangulate two qualified rectified pixel observations with rejection.

    Cameras require `trusted:true`, `rectified:true`, K, R/t (or rvec/tvec),
    and a supplied `calibration_error_bound_m`. Missing error budgets stay
    unavailable. A supplied pixel sigma is an error-model assumption; detector
    scores do not become localization uncertainty or calibrated probabilities.
    """
    if len(cameras) != 2 or len(observations) != 2:
        raise ValueError("Exactly two camera/observation pairs are required")
    if (
        not np.isfinite([max_metric_error_m, max_reprojection_error_px, min_ray_angle_deg]).all()
        or min(max_metric_error_m, max_reprojection_error_px, min_ray_angle_deg) <= 0
    ):
        raise ValueError("Geometry gates must be finite and positive")
    identities = [camera.get("cam_id", camera.get("id")) for camera in cameras]
    if identities[0] is not None and identities[0] == identities[1]:
        return _rejected("duplicate_camera_identity", observations)
    if any(
        row.get("cam_id") is not None and row["cam_id"] != identity
        for row, identity in zip(observations, identities, strict=True)
    ):
        return _rejected("camera_identity_mismatch", observations)
    if any(not camera.get("trusted", False) for camera in cameras):
        return _rejected("calibration_untrusted", observations)
    if any(
        not camera.get("rectified", False) or np.any(np.asarray(camera.get("dist", [0.0])) != 0) for camera in cameras
    ):
        return _rejected("pixels_not_rectified", observations)
    if any(row.get("px") is None for row in observations):
        return _rejected("missing_observation", observations)
    if sync_uncertainty_s is None or not np.isfinite(sync_uncertainty_s) or sync_uncertainty_s < 0:
        return _rejected("timing_uncertainty_unavailable", observations)
    if speed_bound_mps is None or not np.isfinite(speed_bound_mps) or speed_bound_mps < 0:
        return _rejected("speed_bound_unavailable", observations)
    calibration_bounds = [camera.get("calibration_error_bound_m") for camera in cameras]
    if any(value is None or not np.isfinite(value) or value < 0 for value in calibration_bounds):
        return _rejected("calibration_uncertainty_unavailable", observations)
    sampling_bounds = [row.get("temporal_error_bound_s", 0.0) for row in observations]
    if any(not np.isfinite(value) or value < 0 for value in sampling_bounds):
        return _rejected("invalid_sampling_uncertainty", observations)
    temporal_bound_m = speed_bound_mps * (sync_uncertainty_s + sum(sampling_bounds))
    if temporal_bound_m + sum(calibration_bounds) > max_metric_error_m:
        return _rejected("timing_or_calibration_error_budget_exceeded", observations)
    sigmas = [row.get("sigma_px") if row.get("sigma_px") is not None else pixel_sigma_px for row in observations]
    if any(sigma is None or not np.isfinite(sigma) or sigma <= 0 for sigma in sigmas):
        return _rejected("pixel_uncertainty_unavailable", observations)
    pixels = np.asarray([row["px"] for row in observations], dtype=float)
    if pixels.shape != (2, 2) or not np.isfinite(pixels).all():
        return _rejected("invalid_pixels", observations)
    geometry = [_camera(camera) for camera in cameras]
    rays = [
        camera["R"].T @ np.linalg.solve(camera["K"], np.r_[px, 1.0])
        for camera, px in zip(geometry, pixels, strict=True)
    ]
    rays = [ray / np.linalg.norm(ray) for ray in rays]
    angle = float(np.degrees(np.arccos(np.clip(abs(rays[0] @ rays[1]), 0, 1))))
    if angle < min_ray_angle_deg:
        return _rejected("parallel_or_weak_rays", observations)
    rows = []
    for px, camera, sigma in zip(pixels, geometry, sigmas, strict=True):
        rows.extend(
            [(px[0] * camera["P"][2] - camera["P"][0]) / sigma, (px[1] * camera["P"][2] - camera["P"][1]) / sigma]
        )
    _, _, vt = np.linalg.svd(rows)
    if abs(vt[-1, 3]) < 1e-12:
        return _rejected("point_at_infinity", observations)
    initial = vt[-1, :3] / vt[-1, 3]
    fit = least_squares(
        lambda x: np.concatenate(
            [(_project(x, camera) - px) / sigma for camera, px, sigma in zip(geometry, pixels, sigmas, strict=True)]
        ),
        initial,
        loss="huber",
        f_scale=3.0,
        max_nfev=50,
    )
    position = fit.x
    if not fit.success or not np.isfinite(position).all():
        return _rejected("refinement_failed", observations)
    if any((camera["R"] @ position + camera["t"])[2] <= 1e-8 for camera in geometry):
        return _rejected("behind_camera", observations)
    errors = [
        float(np.linalg.norm(_project(position, camera) - px)) for camera, px in zip(geometry, pixels, strict=True)
    ]
    if max(errors) > max_reprojection_error_px:
        return _rejected("reprojection_error_exceeded", observations)
    jacobian = []
    for camera, sigma in zip(geometry, sigmas, strict=True):
        P = camera["P"]
        q = P @ np.r_[position, 1.0]
        jacobian.extend([(P[i, :3] * q[2] - q[i] * P[2, :3]) / q[2] ** 2 / sigma for i in (0, 1)])
    information = np.asarray(jacobian).T @ np.asarray(jacobian)
    if np.linalg.cond(information) > 1e12:
        return _rejected("uncertainty_ill_conditioned", observations)
    covariance = np.linalg.inv(information)
    sigma_m = float(np.sqrt(np.linalg.eigvalsh(covariance).max()))
    estimated_budget = 3 * sigma_m + temporal_bound_m + sum(calibration_bounds)
    if estimated_budget > max_metric_error_m:
        return _rejected("estimated_metric_error_budget_exceeded", observations)
    return {
        "status": "triangulated",
        "pos_m": position.tolist(),
        "covariance_m2": covariance.reshape(-1).tolist(),
        "sigma_m": sigma_m,
        "temporal_displacement_bound_m": temporal_bound_m,
        "calibration_error_bound_m": sum(calibration_bounds),
        "estimated_error_budget_m": estimated_budget,
        "reprojection_errors_px": errors,
        "ray_angle_deg": angle,
        "sources": [dict(row) for row in observations],
        "cam_ids": [camera.get("cam_id", camera.get("id")) for camera in cameras],
        "used_interpolation": any(row.get("status") == "interpolated" for row in observations),
        "uncertainty_method": (
            "Linearized supplied pixel-noise covariance; 3 sigma plus supplied calibration "
            "and speed/time budgets. Not an accuracy guarantee."
        ),
    }


def reconstruct_pair_at(
    t_game_s: float,
    rows_a: Sequence[Mapping[str, Any]],
    rows_b: Sequence[Mapping[str, Any]],
    camera_a: Mapping[str, Any],
    camera_b: Mapping[str, Any],
    *,
    clock_a: ClockMap = IDENTITY_CLOCK,
    clock_b: ClockMap = IDENTITY_CLOCK,
    mode: str = "nearest",
    max_gap_s: float = 0.05,
    max_time_delta_s: float = 0.01,
    **geometry_options: Any,
) -> dict[str, Any]:
    """Join independent source timelines and triangulate without frame pairing."""
    observations = [
        sample_at(rows, t_game_s, clock, mode=mode, max_gap_s=max_gap_s, max_time_delta_s=max_time_delta_s)
        for rows, clock in ((rows_a, clock_a), (rows_b, clock_b))
    ]
    for observation, camera in zip(observations, [camera_a, camera_b], strict=True):
        if observation.get("cam_id") is None:
            observation["cam_id"] = camera.get("cam_id", camera.get("id"))
    result = triangulate(observations, [camera_a, camera_b], **geometry_options)
    result["t_game_s"] = t_game_s
    return result
