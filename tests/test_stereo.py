"""Synthetic calibrated geometry validates math, not accuracy on phone clips."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/flight"))
from flight.stereo import ClockMap, reconstruct_pair_at, sample_at, triangulate  # noqa: E402


def cameras():
    K = np.array([[800.0, 0, 640], [0, 800, 360], [0, 0, 1]])
    return [
        {
            "cam_id": name,
            "K": K.tolist(),
            "R": np.eye(3).tolist(),
            "t": [-x, 0.0, 0.0],
            "trusted": True,
            "rectified": True,
            "calibration_error_bound_m": 0.0,
        }
        for name, x in [("a", -0.5), ("b", 0.5)]
    ]


def project(point, camera):
    q = np.array(camera["K"]) @ (np.array(camera["R"]) @ point + np.array(camera["t"]))
    return (q[:2] / q[2]).tolist()


def observations(point, pair=None, sigma=0.1):
    pair = pair or cameras()
    return [
        {
            "px": project(point, camera),
            "sigma_px": sigma,
            "source_frames": [{"seq": i + 100, "t_source_s": 2.0, "t_game_s": 2.0}],
            "status": "observed",
            "temporal_error_bound_s": 0.0,
        }
        for i, camera in enumerate(pair)
    ]


def options():
    return {"sync_uncertainty_s": 0.0001, "speed_bound_mps": 1.0}


def test_known_metric_point_and_source_references_survive_reconstruction():
    point = np.array([0.15, 0.2, 4.0])
    rows = observations(point)
    result = triangulate(rows, cameras(), **options())
    assert result["status"] == "triangulated"
    np.testing.assert_allclose(result["pos_m"], point, atol=1e-9)
    assert max(result["reprojection_errors_px"]) < 1e-8
    assert result["sources"] == rows
    assert result["sigma_m"] > 0
    assert np.linalg.eigvalsh(np.array(result["covariance_m2"]).reshape(3, 3)).min() > 0
    assert not result["used_interpolation"]
    assert "normal" not in result
    json.dumps(result, allow_nan=False)


def test_covariance_responds_to_supplied_localization_error():
    point = np.array([0.15, 0.2, 4.0])
    a = triangulate(observations(point, sigma=0.1), cameras(), **options(), max_metric_error_m=1.0)
    b = triangulate(observations(point, sigma=0.2), cameras(), **options(), max_metric_error_m=1.0)
    np.testing.assert_allclose(np.array(b["covariance_m2"]), np.array(a["covariance_m2"]) * 4, rtol=1e-6)


@pytest.mark.parametrize("offset,drift", [(0.037, 1.001), (-0.021, 0.998)])
def test_different_source_rates_offset_and_drift_use_pts_with_explicit_interpolation(offset, drift):
    pair = cameras()
    clock_b = ClockMap(offset_s=offset, drift=drift)

    def row(seq, game_time, camera, clock):
        return {
            "seq": seq,
            "t_source_s": clock.source_time(game_time),
            "px": project(np.array([0.1 * game_time, 0.2, 4.0]), camera),
            "sigma_px": 0.1,
        }

    a = [row(100 + i, t, pair[0], ClockMap()) for i, t in enumerate(np.arange(7) / 20)]
    b = [row(200 + i, t, pair[1], clock_b) for i, t in enumerate(np.arange(10) / 30)]
    result = reconstruct_pair_at(0.05, a, b, *pair, clock_b=clock_b, mode="linear", **options())
    assert result["status"] == "triangulated"
    np.testing.assert_allclose(result["pos_m"], [0.005, 0.2, 4.0], atol=1e-8)
    assert result["used_interpolation"]
    assert [f["seq"] for f in result["sources"][0]["source_frames"]] == [101]
    assert [f["seq"] for f in result["sources"][1]["source_frames"]] == [201, 202]
    assert result["sources"][1]["target_source_s"] == pytest.approx(0.05 * drift + offset)
    assert result["sources"][1]["source_frames"][0]["t_source_s"] == b[1]["t_source_s"]
    assert clock_b.game_time(clock_b.source_time(0.17)) == pytest.approx(0.17)


def test_missing_samples_and_long_gaps_are_not_interpolated_or_extrapolated():
    rows = [
        {"seq": 10, "t_source_s": 0, "px": [1, 2]},
        {"seq": 11, "t_source_s": 0.1, "px": None},
        {"seq": 12, "t_source_s": 0.2, "px": [3, 4]},
    ]
    assert sample_at(rows, 0.05, mode="linear", max_gap_s=0.2)["reason"] == "source_observation_missing"
    assert sample_at(rows, 0.1)["reason"] == "source_observation_missing"
    assert sample_at([rows[0], rows[2]], 0.1, mode="linear")["reason"] == "source_gap_too_long"
    assert sample_at(rows, -0.01)["reason"] == "outside_source_coverage"
    assert sample_at(rows, 0.21, mode="linear")["reason"] == "outside_source_coverage"


def test_nearest_frame_provenance_preserves_actual_exposure_and_timing_error():
    rows = [{"seq": 91, "t_source_s": 0.1, "px": [1, 2]}, {"seq": 93, "t_source_s": 0.14, "px": [3, 4]}]
    result = sample_at(rows, 0.103, max_time_delta_s=0.005)
    assert result["status"] == "observed"
    assert result["source_frames"] == [{"seq": 91, "t_source_s": 0.1, "t_game_s": 0.1}]
    assert result["temporal_error_bound_s"] == pytest.approx(0.003)
    assert result["px"] == [1.0, 2.0]
    assert sample_at(rows, 0.12, max_time_delta_s=0.005)["reason"] == "nearest_frame_too_far"


def test_untrusted_calibration_rejects_even_perfect_reprojection():
    pair = cameras()
    rows = observations(np.array([0.0, 0.0, 4.0]), pair)
    pair[0]["trusted"] = False
    result = triangulate(rows, pair, **options())
    assert result["status"] == "rejected"
    assert result["reason"] == "calibration_untrusted"
    assert result["pos_m"] is None


def test_time_uncertainty_rejects_fast_ball_before_claiming_metric_position():
    result = triangulate(
        observations(np.array([0.0, 0.0, 4.0])),
        cameras(),
        sync_uncertainty_s=0.01,
        speed_bound_mps=20.0,
        max_metric_error_m=0.03,
    )
    assert result["reason"] == "timing_or_calibration_error_budget_exceeded"
    assert result["pos_m"] is None


def test_interpolation_uncertainty_is_budgeted_at_possible_contacts():
    pair = cameras()
    a = [
        {"seq": i, "t_source_s": t, "px": project(np.array([0.0, 0.0, 4.0]), pair[0]), "sigma_px": 0.1}
        for i, t in enumerate([0.0, 0.02])
    ]
    b = [{**r, "px": project(np.array([0.0, 0.0, 4.0]), pair[1])} for r in a]
    result = reconstruct_pair_at(
        0.01, a, b, *pair, mode="linear", sync_uncertainty_s=0, speed_bound_mps=20, max_metric_error_m=0.03
    )
    assert result["reason"] == "timing_or_calibration_error_budget_exceeded"
    assert all(r["status"] == "interpolated" for r in result["sources"])


def test_parallel_rays_and_behind_camera_solutions_are_rejected():
    pair = cameras()
    pair[1]["t"] = pair[0]["t"]
    assert (
        triangulate(observations(np.array([0.0, 0.0, 4.0]), pair), pair, **options())["reason"]
        == "parallel_or_weak_rays"
    )
    pair = cameras()
    assert triangulate(observations(np.array([0.0, 0.0, -4.0]), pair), pair, **options())["reason"] == "behind_camera"


def test_bad_epipolar_correspondence_is_rejected_by_reprojection():
    rows = observations(np.array([0.0, 0.0, 4.0]))
    rows[1]["px"][1] += 25
    assert triangulate(rows, cameras(), **options())["reason"] == "reprojection_error_exceeded"


@pytest.mark.parametrize(
    "field,expected",
    [("calibration_error_bound_m", "calibration_uncertainty_unavailable"), ("rectified", "pixels_not_rectified")],
)
def test_missing_calibration_prerequisites_remain_unavailable(field, expected):
    pair = cameras()
    pair[0].pop(field)
    assert triangulate(observations(np.array([0.0, 0.0, 4.0])), pair, **options())["reason"] == expected


def test_missing_pixel_or_timing_uncertainty_is_not_replaced_with_detector_confidence():
    rows = observations(np.array([0.0, 0.0, 4.0]))
    rows[0].pop("sigma_px")
    rows[0]["score"] = 0.999
    assert triangulate(rows, cameras(), **options())["reason"] == "pixel_uncertainty_unavailable"
    assert (
        triangulate(rows, cameras(), sync_uncertainty_s=None, speed_bound_mps=1)["reason"]
        == "timing_uncertainty_unavailable"
    )


def test_duplicate_source_pts_and_invalid_drift_are_configuration_errors():
    rows = [{"seq": 1, "t_source_s": 0.1, "px": [1, 2]}, {"seq": 2, "t_source_s": 0.1, "px": [2, 3]}]
    with pytest.raises(ValueError, match="strictly increasing"):
        sample_at(rows, 0.1)
    with pytest.raises(ValueError, match="drift"):
        ClockMap(drift=-1)


def test_flat_contract_camera_arrays_and_rodrigues_pose_are_supported():
    pair = cameras()
    rows = observations(np.array([0.1, 0.2, 4.0]), pair)
    for camera in pair:
        camera["K"] = np.array(camera["K"]).reshape(-1).tolist()
        camera.pop("R")
        camera["rvec"] = [0.0, 0.0, 0.0]
        camera["tvec"] = camera.pop("t")
    result = triangulate(rows, pair, **options())
    assert result["status"] == "triangulated"
    np.testing.assert_allclose(result["pos_m"], [0.1, 0.2, 4.0], atol=1e-9)


def test_geometry_error_budget_rejects_perfect_pixel_fit_with_large_localization_uncertainty():
    rows = observations(np.array([0.0, 0.0, 4.0]), sigma=5.0)
    assert triangulate(rows, cameras(), **options())["reason"] == "estimated_metric_error_budget_exceeded"


def test_source_camera_identity_mismatch_is_not_silently_reassigned():
    rows = observations(np.array([0.0, 0.0, 4.0]))
    rows[0]["cam_id"] = "b"
    assert triangulate(rows, cameras(), **options())["reason"] == "camera_identity_mismatch"


def test_nonzero_distortion_is_not_silently_treated_as_rectified_pixels():
    pair = cameras()
    pair[0]["dist"] = [0.01]
    assert triangulate(observations(np.array([0.0, 0.0, 4.0])), pair, **options())["reason"] == "pixels_not_rectified"
