"""Synthetic geometry verifies math; it is not phone-footage accuracy evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tt_calibration", ROOT / "services/courtcam-adapter/calibration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def synthetic_request():
    centre = np.array([-3.0, -4.0, 2.4])
    forward = -centre / np.linalg.norm(centre)
    right = np.cross(forward, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward])
    rvec = cv2.Rodrigues(rotation)[0]
    tvec = -rotation @ centre
    K = np.array([[900.0, 0, 640], [0, 900, 360], [0, 0, 1.0]])
    world = np.array(list(module.LANDMARKS.values()))
    pixels = cv2.projectPoints(world, rvec, tvec, K, None)[0].reshape(-1, 2)
    request = {
        "schema": "trophy.calibration_request.v1",
        "game_id": "g_ttdemo01",
        "cam_id": "c_side01",
        "sport": "table_tennis",
        "seq": 0,
        "image_size": {"w": 1280, "h": 720},
        "points": [{"name": name, "px": pixel.tolist()} for name, pixel in zip(module.LANDMARKS, pixels, strict=True)],
    }
    return request, K, rvec, tvec


def test_tabletop_fit_maps_unseen_surface_points_without_claiming_height_accuracy():
    request, K, rvec, tvec = synthetic_request()
    response = module.calibrate(request)
    surface = np.array([[-0.5, 0.23, 0], [0.82, -0.3, 0], [0, 0, 0]], np.float64)
    pixels = cv2.projectPoints(surface, rvec, tvec, K, None)[0].reshape(-1, 2)
    recovered = module._project_plane(pixels, np.array(response["H_img_to_field"]).reshape(3, 3))
    np.testing.assert_allclose(recovered, surface[:, :2], atol=2e-6)
    assert not response["trusted"]
    assert len(response["overlay_px"]) == 6
    assert response["solver"] == "opencv-planar-v1"


def test_known_intrinsics_and_independent_elevated_checks_validate_pose():
    request, K, rvec, tvec = synthetic_request()
    validation = np.array([[-1, 0, 0.16], [1, 0.4, 0.3], [0.3, -0.4, 0.4], [-0.7, -0.2, 0.2]])
    pixels = cv2.projectPoints(validation, rvec, tvec, K, None)[0].reshape(-1, 2)
    request["intrinsics"] = {"K": K.reshape(-1).tolist()}
    request["validation_points"] = [
        {"pos_m": p.tolist(), "px": uv.tolist()} for p, uv in zip(validation, pixels, strict=True)
    ]
    response = module.calibrate(request)
    assert response["trusted"]
    np.testing.assert_allclose(response["camera_position_m"], [-3, -4, 2.4], atol=1e-5)
    request["validation_points"][0]["px"][0] += 50
    assert not module.calibrate(request)["trusted"]


def test_planar_validation_does_not_unlock_airborne_measurements():
    request, K, _, _ = synthetic_request()
    request["intrinsics"] = {"K": K.reshape(-1).tolist()}
    request["validation_points"] = [
        {"pos_m": list(module.LANDMARKS[p["name"]]), "px": p["px"]} for p in request["points"]
    ]
    assert not module.calibrate(request)["trusted"]


@pytest.mark.parametrize(
    "pixels",
    [
        [[200, 200], [210, 210], [220, 220], [230, 230]],
        [[200, 200], [200, 200], [600, 400], [500, 200]],
        [[200, 200], [600, 400], [600, 200], [200, 400]],
        [[-1, 200], [200, 400], [600, 400], [600, 200]],
    ],
)
def test_degenerate_and_out_of_frame_taps_are_rejected(pixels):
    request, _, _, _ = synthetic_request()
    for p, value in zip(request["points"], pixels, strict=True):
        p["px"] = value
    with pytest.raises(ValueError):
        module.calibrate(request)


def test_response_and_table_pack_validate_against_shared_contracts():
    import jsonschema
    import yaml

    request, _, _, _ = synthetic_request()
    jsonschema.validate(
        module.calibrate(request), json.loads((ROOT / "packages/contracts/calibration.schema.json").read_text())
    )
    pack = yaml.safe_load((ROOT / "rulepacks/table_tennis.yaml").read_text())
    jsonschema.validate(pack, json.loads((ROOT / "packages/contracts/rulepack.schema.json").read_text()))
    assert pack["params"]["serve_min_toss_m"] == 0.16


def test_clip_ingest_retains_source_pts_and_identity_when_selecting_interval(tmp_path):
    import av

    clip_spec = importlib.util.spec_from_file_location("tt_play_clip", ROOT / "tools/play_clip.py")
    clip = importlib.util.module_from_spec(clip_spec)
    clip_spec.loader.exec_module(clip)
    path = tmp_path / "vfr.mp4"
    from fractions import Fraction

    with av.open(str(path), "w") as container:
        stream = container.add_stream("libx264", rate=30)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        for i, stamp in enumerate([0, 34, 77, 113, 167]):
            frame = av.VideoFrame.from_ndarray(np.full((64, 64, 3), i * 30, np.uint8), format="bgr24")
            frame.pts = stamp
            frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    all_frames = list(clip.iter_frames(path))
    selected = list(clip.iter_frames(path, start_s=0.06, end_s=0.15))
    assert len(all_frames) == 5
    assert [x[0] for x in selected] == [2, 3]
    assert [x[1] for x in selected] == [all_frames[2][1], all_frames[3][1]]
    index_path = tmp_path / "index.jsonl"
    result = clip.play(
        path,
        game_id="g_ttdemo01",
        cam_id="c_side01",
        clip_offset_s=-0.02,
        realtime=False,
        start_s=0.06,
        end_s=0.15,
        index_path=index_path,
        index_only=True,
    )
    rows = [json.loads(line) for line in index_path.read_text().splitlines()]
    assert result["frames"] == 2
    assert rows[0]["seq"] == 2
    assert rows[0]["t_game_s"] == all_frames[2][1] - 0.02
