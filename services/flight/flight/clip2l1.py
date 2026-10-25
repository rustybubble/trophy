"""One uploaded phone clip + four tapped table corners -> a layer-1 log for the golden 2D sport module.

    python -m flight.clip2l1 --video clip.mp4 --corners x,y,x,y,x,y,x,y --out DIR [--name clip] [--ball white|orange]

This is the one-phone path of the weekend demo (CLAUDE.md: "live ping pong on one phone"): the classical detector
and the gated tracker give a 2D ball track, the corners give the image -> table homography, and the engine's golden
`sports/table_tennis/events.py` (the same code the Droid's gate replays) turns the log into bounce / contact /
ball_dead events. Flight's 3D fusion needs two cameras (`fuse` keeps n_views >= 2 only), so a single clip goes this
way. Corner order: A-right, B-right, B-left, A-left (counter-clockwise seen from above), as everywhere in flight.

Writes `<out>/<name>.l1.jsonl` (one `camera` row + `ball_sample` rows), `<name>.labels.json` (an unlabelled, honest
labels file: no truth, nothing to score), `<name>.track2d.json` (the 2D track for overlays) and `<name>.meta.json`.
Nothing here is a measurement of accuracy; the clip is whatever the user uploaded.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from . import field as F
from .calib import solve_pose
from .detect import ClassicalDetector, video_candidates, video_info
from .track import Tracker


def homography_img_to_field(corners_px: np.ndarray) -> tuple[list[float], float]:
    """Image pixels -> table metres (z = 0). Returns the row-major 3x3 and its RMS reprojection error in px."""
    corners_px = np.asarray(corners_px, float).reshape(4, 2)
    H, _ = cv2.findHomography(corners_px, F.CORNERS_M[:, :2])
    if H is None:
        raise ValueError("degenerate corners: no homography")
    H = H / H[2, 2]
    back, _ = cv2.findHomography(F.CORNERS_M[:, :2], corners_px)
    proj = cv2.perspectiveTransform(F.CORNERS_M[:, :2].reshape(-1, 1, 2), back).reshape(4, 2)
    err = float(np.sqrt(np.mean(np.sum((proj - corners_px) ** 2, axis=1))))
    return [float(v) for v in H.ravel()], err


def convert(
    video: Path,
    corners_px: np.ndarray,
    out: Path,
    *,
    name: str = "clip",
    cam_id: str = "c_clip001",
    game_id: str = "g_clip",
    ball: str = "white",
    limit: int | None = None,
    ball_radius_px: float | None = None,
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    info = video_info(video)
    w, h, fps = int(info["width"]), int(info["height"]), float(info["fps"]) or 30.0
    H9, reproj = homography_img_to_field(corners_px)
    r_px = ball_radius_px
    pose_note = ""
    if r_px is None:
        try:
            cam = solve_pose(cam_id, corners_px, w, h)
            depth = float((cam.R @ np.zeros(3) + cam.t)[2])
            r_px = max(1.5, cam.K[0, 0] * F.BALL_RADIUS_M / depth)
            pose_note = f"f={cam.K[0, 0]:.0f}px ({cam.f_source}), reproj {cam.reproj_err_px:.2f}px"
        except ValueError as e:  # a poor view still gets a track; the radius is a guess
            r_px, pose_note = 4.0, f"pose failed ({e}); default ball radius"
    det = ClassicalDetector(colour=ball, expected_radius_px=float(r_px))
    t0 = time.perf_counter()
    track = Tracker().run(video_candidates(video, det, 0.0, limit=limit))
    track_s = time.perf_counter() - t0
    now_ms = int(time.time() * 1000)
    calibration = {
        "schema": "trophy.calibration.v1",
        "game_id": game_id,
        "cam_id": cam_id,
        "sport": "table_tennis",
        "created_at_ms": now_ms,
        "image_size": {"w": w, "h": h},
        "method": "four-corner homography (tapped on the first frame of an uploaded clip)",
        "H_img_to_field": H9,
        "reproj_err_px": reproj,
        "trusted": False,
        "warnings": ["uploaded clip: four tapped corners, one camera, no clock sync; untrusted, so calls cap at BETA"],
        "solver": "flight.clip2l1",
    }
    camera_row = {
        "cam_id": cam_id,
        "game_id": game_id,
        "label": f"uploaded clip {video.name}",
        "role": "cam",
        "device": {"source": "upload", "file": video.name, "fps": fps},
        "calibration": calibration,
        "calib_trusted": False,
        "connected": True,
        "fps_in": fps,
        "sync_err_ms": 0.0,
        "last_seen_ms": now_ms,
    }
    log = out / f"{name}.l1.jsonl"
    with log.open("w", encoding="utf8") as f:
        f.write(json.dumps({"table": "camera", "cam_id": cam_id, "row": camera_row}) + "\n")
        for s in track:
            row = {
                "cam_id": cam_id,
                "t_game_s": round(float(s["t_s"]), 4),
                "seq": int(s["frame"]),
                "px": [round(s["xy_px"][0], 2), round(s["xy_px"][1], 2)],
                "conf": round(float(s["conf"]), 3),
            }
            f.write(json.dumps({"table": "ball_sample", "cam_id": cam_id, "row": row}) + "\n")
    labels = {
        "synthetic": False,
        "label": "uploaded clip: UNLABELLED, no ground truth; nothing here measures accuracy",
        "sport": "table_tennis",
        "labeller": "none",
        "bounces": [],
        "tol_count": 0,
        "tol_t_s": 0.1,
        "alternate_sides": False,
        "min_recall": 0.0,
    }
    (out / f"{name}.labels.json").write_text(json.dumps(labels, indent=1), encoding="utf8")
    (out / f"{name}.track2d.json").write_text(json.dumps(track), encoding="utf8")
    meta = {
        "video": str(video),
        "name": name,
        "cam_id": cam_id,
        "game_id": game_id,
        "width": w,
        "height": h,
        "fps": fps,
        "frames": int(info.get("frames") or 0),
        "duration_s": (int(info.get("frames") or 0) / fps) if fps else None,
        "corners_px": np.asarray(corners_px, float).reshape(4, 2).tolist(),
        "H_img_to_field": H9,
        "homography_reproj_px": reproj,
        "ball": ball,
        "ball_radius_px": float(r_px),
        "pose": pose_note,
        "samples": len(track),
        "tracked_fraction": (len(track) / max(1, int(info.get("frames") or len(track)))) if limit is None else None,
        "tracking_s": round(track_s, 2),
        "l1": str(log),
    }
    (out / f"{name}.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flight.clip2l1", description=__doc__.split("\n\n")[0])
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--corners", required=True, help="8 numbers: x,y for A-right, B-right, B-left, A-left")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--name", default="clip")
    ap.add_argument("--cam-id", default="c_clip001")
    ap.add_argument("--game-id", default="g_clip")
    ap.add_argument("--ball", default="white", choices=["white", "orange"])
    ap.add_argument("--ball-radius-px", type=float, default=None)
    ap.add_argument("--limit", type=int, default=None, help="frames to process (a quick look)")
    a = ap.parse_args(argv)
    corners = np.array([float(v) for v in a.corners.split(",")])
    if corners.size != 8:
        sys.exit("--corners needs 8 numbers")
    meta = convert(
        a.video,
        corners,
        a.out,
        name=a.name,
        cam_id=a.cam_id,
        game_id=a.game_id,
        ball=a.ball,
        limit=a.limit,
        ball_radius_px=a.ball_radius_px,
    )
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
