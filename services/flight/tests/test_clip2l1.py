"""clip2l1: the four-corner homography and the layer-1 log an uploaded clip becomes."""

from __future__ import annotations

import json

import cv2
import numpy as np

from flight import field as F
from flight.calib import camera_looking_at
from flight.clip2l1 import convert, homography_img_to_field


def test_homography_maps_corners_to_the_table():
    cam = camera_looking_at("side", (0.0, -3.0, 2.0), (0.0, 0.0, 0.0), 1000.0)
    px = cam.project(F.CORNERS_M)
    H9, err = homography_img_to_field(px)
    assert err < 1e-3
    H = np.array(H9).reshape(3, 3)
    back = cv2.perspectiveTransform(px.reshape(-1, 1, 2).astype(float), H).reshape(4, 2)
    assert np.allclose(back, F.CORNERS_M[:, :2], atol=1e-3)
    # the projected table centre and net posts map back to where they are on the table
    pts = np.array([[0.0, 0.0, 0.0], [0.0, -F.WIDTH_M / 2, 0.0], [0.6, 0.3, 0.0]])
    back = cv2.perspectiveTransform(cam.project(pts).reshape(-1, 1, 2).astype(float), H).reshape(-1, 2)
    assert np.allclose(back, pts[:, :2], atol=1e-3)


def test_convert_writes_an_untrusted_camera_row_and_ball_samples(tmp_path):
    # a tiny synthetic clip: a white blob moving over a dark background
    video = tmp_path / "clip.mp4"
    w, h = 320, 180
    out = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (w, h))
    for i in range(30):
        frame = np.full((h, w, 3), 40, np.uint8)
        cv2.circle(frame, (40 + i * 7, 90), 4, (255, 255, 255), -1)
        out.write(frame)
    out.release()
    corners = np.array([[40, 150], [280, 150], [240, 60], [80, 60]], float)
    meta = convert(video, corners, tmp_path / "l1", name="t", game_id="g_x", cam_id="c_x")
    assert meta["width"] == w and meta["height"] == h and meta["samples"] > 0
    lines = [json.loads(line) for line in (tmp_path / "l1" / "t.l1.jsonl").read_text().splitlines()]
    assert lines[0]["table"] == "camera" and lines[0]["row"]["calibration"]["trusted"] is False
    assert lines[0]["row"]["calib_trusted"] is False
    assert all(rec["table"] == "ball_sample" for rec in lines[1:])
    assert {"t_game_s", "seq", "px", "conf"} <= set(lines[1]["row"])
    labels = json.loads((tmp_path / "l1" / "t.labels.json").read_text())
    assert labels["synthetic"] is False and labels["bounces"] == []
