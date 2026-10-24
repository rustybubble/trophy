#!/usr/bin/env python3
"""Offline real pose observations for a fixed two-player side-view arrangement.

Run in the separate MediaPipe environment. Source pixels/PTS remain available;
ROI labels are positional identity assumptions, not reidentification results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

POSE_SHA256 = "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1"
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "weights/pose_landmarker_full.task"
DEFAULT_ROIS = [[0, 180, 640, 720], [640, 180, 1280, 720]]


def extract(
    video: Path,
    output: Path,
    model: Path = DEFAULT_MODEL,
    stride: int = 4,
    crop_width: int = 640,
    max_frames: int | None = None,
) -> dict:
    if hashlib.sha256(model.read_bytes()).hexdigest() != POSE_SHA256:
        raise ValueError("Pose checkpoint checksum differs from the pinned official Full task")
    if stride < 1 or crop_width < 128:
        raise ValueError("stride must be >=1 and crop-width >=128")
    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model), delegate=python.BaseOptions.Delegate.CPU),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.4,
        min_pose_presence_confidence=0.4,
        min_tracking_confidence=0.4,
    )
    trackers = [vision.PoseLandmarker.create_from_options(options) for _ in range(2)]
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    if not cap.isOpened():
        raise ValueError(f"Cannot open {video}")
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frames, latencies = [], []
    start = time.perf_counter()
    index = 0
    previous_stamp = -math.inf
    rois = [
        [round(x0 * width / 1280), round(y0 * height / 720), round(x1 * width / 1280), round(y1 * height / 720)]
        for x0, y0, x1, y1 in DEFAULT_ROIS
    ]
    try:
        while cap.grab():
            if index % stride:
                index += 1
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                raise RuntimeError(f"Frame {index} could not be retrieved")
            stamp = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not math.isfinite(stamp) or stamp <= previous_stamp:
                raise ValueError(f"Non-increasing source PTS at frame {index}; no fps clock substituted")
            previous_stamp = stamp
            people = []
            for pid, (x0, y0, x1, y1) in enumerate(rois):
                source_crop = bgr[y0:y1, x0:x1]
                scale = min(1.0, crop_width / source_crop.shape[1])
                crop = cv2.resize(
                    source_crop,
                    (round(source_crop.shape[1] * scale), round(source_crop.shape[0] * scale)),
                    interpolation=cv2.INTER_AREA,
                )
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
                t = time.perf_counter()
                result = trackers[pid].detect_for_video(image, round(stamp * 1000))
                latencies.append((time.perf_counter() - t) * 1000)
                if result.pose_landmarks:
                    lm, world = result.pose_landmarks[0], result.pose_world_landmarks[0]
                    landmarks = [[v.x * (x1 - x0) + x0, v.y * (y1 - y0) + y0, v.visibility] for v in lm]
                    confidence = float(np.mean([lm[j].visibility for j in [11, 12, 23, 24, 25, 26, 27, 28]]))
                    people.append(
                        {
                            "id": pid,
                            "image_landmarks": landmarks,
                            "world_landmarks": [[v.x, v.y, v.z] for v in world],
                            "confidence": confidence,
                            "roi_source_px": [x0, y0, x1, y1],
                        }
                    )
            frames.append({"frame_index": index, "timestamp_seconds": stamp, "players": people})
            if len(frames) % 150 == 0:
                print(f"Pose {stamp:.1f}s: {len(people)}/2 detected", flush=True)
            index += 1
            if max_frames is not None and len(frames) >= max_frames:
                break
    finally:
        cap.release()
        for tracker in trackers:
            tracker.close()
    report = {
        "model": "MediaPipe Pose Landmarker Full float16 v1",
        "checkpoint_sha256": POSE_SHA256,
        "model_asset_url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
        "package_version": mp.__version__,
        "execution_provider": "native CPU / XNNPACK",
        "source": str(video.resolve()),
        "source_width": width,
        "source_height": height,
        "source_fps": fps,
        "sample_stride": stride,
        "sample_fps_nominal": fps / stride,
        "sampled_frames": len(frames),
        "detected_person_frames": [sum(any(p["id"] == pid for p in f["players"]) for f in frames) for pid in range(2)],
        "mean_person_inference_ms": float(np.mean(latencies)) if latencies else None,
        "total_seconds": time.perf_counter() - start,
        "source_pts_preserved": True,
        "roi_identity": "Green/left=0, Blue/right=1; positional prior, not reidentification",
        "notes": [
            "Coverage is not pose accuracy.",
            "Hip-relative model world coordinates are inferred, not measured table coordinates.",
            "No open-palm, paddle orientation, release or contact evidence is inferred from this body model.",
            "Only observed sampled poses are exported. Missing people remain missing.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"frames": frames, "report": report}, allow_nan=False))
    print(json.dumps(report, indent=2), flush=True)
    return report


HAND_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
HAND_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)


def probe_hands(
    video: Path,
    output: Path,
    hand_model: Path,
    *,
    camera: str,
    start_s: float = 6.0,
    end_s: float = 8.0,
    pose_path: Path | None = None,
    pose_model: Path = DEFAULT_MODEL,
) -> dict:
    """Original-resolution wrist crops; landmarks are pixel observations only.

    Side wrist hints reuse 15Hz raw body observations. Diagonal hints run the
    same official body bundle every fourth decoded frame. A padded native crop
    preserves detail, and every crop-to-source transform is retained.
    """
    if hashlib.sha256(hand_model.read_bytes()).hexdigest() != HAND_SHA256:
        raise ValueError("Hand checkpoint differs from pinned official Full float16 v1 bundle")
    if hashlib.sha256(pose_model.read_bytes()).hexdigest() != POSE_SHA256:
        raise ValueError("Pose checkpoint checksum mismatch")
    if camera not in ("side", "diagonal") or not 0 <= start_s < end_s:
        raise ValueError("Configure side/diagonal camera and valid source interval")
    hand_options = vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(hand_model), delegate=python.BaseOptions.Delegate.CPU),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=0.4,
        min_hand_presence_confidence=0.4,
    )
    hand = vision.HandLandmarker.create_from_options(hand_options)
    pose_trackers = []
    cached = json.loads(pose_path.read_text())["frames"] if pose_path else None
    if cached is None:
        opts = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(pose_model), delegate=python.BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.4,
            min_pose_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        )
        pose_trackers = [vision.PoseLandmarker.create_from_options(opts) for _ in range(2)]
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
    if not cap.isOpened():
        raise ValueError("Cannot decode hand probe input")
    frames, latencies = [], []
    attempts = successful = 0
    last_pose = None
    started = time.perf_counter()
    try:
        while True:
            ok, image = cap.read()
            if not ok:
                break
            stamp = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            seq = round(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            if stamp < start_s:
                continue
            if stamp >= end_s:
                break
            height, width = image.shape[:2]
            if cached is not None:
                row = min(cached, key=lambda f: abs(f["timestamp_seconds"] - stamp))
            else:
                if last_pose is None or len(frames) % 4 == 0:
                    people = []
                    for roi_id, (x0, y0, x1, y1) in enumerate(DEFAULT_ROIS):
                        x0, x1 = round(x0 * width / 1280), round(x1 * width / 1280)
                        y0, y1 = round(y0 * height / 720), round(y1 * height / 720)
                        crop = image[y0:y1, x0:x1]
                        reduced = cv2.resize(crop, (640, round(crop.shape[0] * 640 / crop.shape[1])))
                        rgb = cv2.cvtColor(reduced, cv2.COLOR_BGR2RGB)
                        result = pose_trackers[roi_id].detect_for_video(
                            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)),
                            round(stamp * 1000) + 1,
                        )
                        if result.pose_landmarks:
                            people.append(
                                {
                                    "id": 1 - roi_id if camera == "diagonal" else roi_id,
                                    "image_landmarks": [
                                        [p.x * (x1 - x0) + x0, p.y * (y1 - y0) + y0, p.visibility]
                                        for p in result.pose_landmarks[0]
                                    ],
                                }
                            )
                    last_pose = {"timestamp_seconds": stamp, "players": people}
                row = last_pose
            crop_rows = []
            for player in row["players"]:
                for wrist in (15, 16):
                    x, y, visibility = player["image_landmarks"][wrist]
                    if visibility < 0.3:
                        continue
                    radius = round(width / 1280 * 55)
                    x0, y0 = max(0, round(x) - radius), max(0, round(y) - radius)
                    x1, y1 = min(width, round(x) + radius), min(height, round(y) + radius)
                    if x1 <= x0 or y1 <= y0:
                        continue
                    rgb = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
                    began = time.perf_counter()
                    result = hand.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
                    latencies.append((time.perf_counter() - began) * 1000)
                    attempts += 1
                    hands = []
                    for lm, labels in zip(result.hand_landmarks, result.handedness, strict=True):
                        hands.append(
                            {
                                "landmarks_source_px": [[p.x * (x1 - x0) + x0, p.y * (y1 - y0) + y0] for p in lm],
                                "handedness_label": labels[0].category_name,
                                "handedness_score": labels[0].score,
                            }
                        )
                    successful += bool(hands)
                    crop_rows.append(
                        {
                            "crop_player_id": player["id"],
                            "pose_wrist_index": wrist,
                            "pose_hint_delta_s": row["timestamp_seconds"] - stamp,
                            "crop_source_px": [x0, y0, x1, y1],
                            "hands": hands,
                            "status": "detected" if hands else "missing",
                        }
                    )
            frames.append({"source_seq": seq, "t_source_s": stamp, "camera": camera, "crops": crop_rows})
    finally:
        cap.release()
        hand.close()
        for tracker in pose_trackers:
            tracker.close()
    report = {
        "model": "MediaPipe Hand Landmarker Full float16 v1",
        "checkpoint_sha256": HAND_SHA256,
        "model_url": HAND_URL,
        "docs_url": "https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker",
        "package_version": mp.__version__,
        "execution_provider": "native CPU / XNNPACK",
        "source": str(video.resolve()),
        "camera": camera,
        "interval_source_s": [start_s, end_s],
        "source_frames": len(frames),
        "crop_attempts": attempts,
        "crops_with_hands": successful,
        "mean_crop_inference_ms": float(np.mean(latencies)) if latencies else None,
        "elapsed_s": time.perf_counter() - started,
        "notes": [
            "Coverage is not hand/palm or release accuracy; overlapping wrist crops may detect the same hand.",
            "Native-pixel crops preserve the crop-to-source transform; pose hints are sampled and may be stale.",
            "Hand skeletons and handedness do not prove open stationary palm, ball release, or metric height.",
            "No hand/paddle data is fed into automatic real-footage serve decisions without validation.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"frames": frames, "report": report}, allow_nan=False))
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/local/tt-demo/poses.json"))
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--crop-width", type=int, default=640)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--hand-model", type=Path)
    parser.add_argument("--hand-camera", choices=["side", "diagonal"], default="side")
    parser.add_argument("--hand-start", type=float, default=6.0)
    parser.add_argument("--hand-end", type=float, default=8.0)
    parser.add_argument("--pose-hints", type=Path)
    args = parser.parse_args()
    if args.hand_model:
        probe_hands(
            args.video,
            args.output,
            args.hand_model,
            camera=args.hand_camera,
            start_s=args.hand_start,
            end_s=args.hand_end,
            pose_path=args.pose_hints,
            pose_model=args.model,
        )
    else:
        extract(args.video, args.output, args.model, args.stride, args.crop_width, args.max_frames)
