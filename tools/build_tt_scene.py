#!/usr/bin/env python3
"""Build an illustrative pose replay from actual sampled body observations.

This is not measured 3D reconstruction: a monocular pose model and approximate
single-plane camera place avatars. The decisive evidence remains source video.
Ball positions are deliberately unavailable without validated dynamic geometry.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/flight"))
from flight.geometry import calibrate, reconstruct_players  # noqa: E402
from flight.motion import smooth_player_motion  # noqa: E402
from scipy.ndimage import median_filter  # noqa: E402

CORNER_PIXELS_1920 = np.array([[566, 624], [386, 701], [1527, 729], [1378, 646]], np.float64)
WORLD_CORNERS = [[-1.37, 0.7625, 0.76], [-1.37, -0.7625, 0.76], [1.37, -0.7625, 0.76], [1.37, 0.7625, 0.76]]


def _image_at(video: Path, stamp: float) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, stamp * 1000)
        ok, image = cap.read()
        if not ok:
            raise ValueError("Could not decode reference calibration frame")
        return cv2.resize(image, (1280, 720), interpolation=cv2.INTER_AREA)
    finally:
        cap.release()


def table_transforms(video: Path, raw_frames: list[dict], reference_s: float = 6.0):
    """Independent ORB/RANSAC table-region matches to a real reference frame.

    This stabilizes avatar root placement only. Accepted image homographies do
    not turn single-plane camera assumptions into metric motion calibration.
    Missing/rejected transforms remain explicitly unavailable, never extrapolated.
    """
    reference = _image_at(video, reference_s)
    corners = CORNER_PIXELS_1920 * (2 / 3)
    mask = np.zeros((720, 1280), np.uint8)
    cv2.fillConvexPoly(mask, np.rint(corners).astype(np.int32), 255)
    mask = cv2.dilate(mask, np.ones((45, 45), np.uint8))
    orb = cv2.ORB_create(nfeatures=1800, fastThreshold=8, edgeThreshold=15)
    key_ref, desc_ref = orb.detectAndCompute(cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), mask)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    output, inliers, shifts = [], [], []
    cap = cv2.VideoCapture(str(video))
    current_index = 0
    try:
        for row in raw_frames:
            index = row["frame_index"]
            while current_index <= index:
                if not cap.grab():
                    raise RuntimeError("Video ended before pose source frame")
                current_index += 1
            ok, image = cap.retrieve()
            if not ok:
                raise RuntimeError("Cannot retrieve source pose frame")
            small = cv2.resize(image, (1280, 720), interpolation=cv2.INTER_AREA)
            # The actual table can shift outside its reference mask. Search a
            # padded band, while matching only reference table-region features.
            search_mask = np.zeros((720, 1280), np.uint8)
            search_mask[260:650, :] = 255
            key_cur, desc_cur = orb.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), search_mask)
            accepted = None
            count = 0
            if desc_ref is not None and desc_cur is not None and len(desc_cur) >= 2:
                matches = matcher.knnMatch(desc_ref, desc_cur, k=2)
                good = [a for pair in matches if len(pair) == 2 for a, b in [pair] if a.distance < 0.72 * b.distance]
                if len(good) >= 10:
                    ref_pts = np.array([key_ref[m.queryIdx].pt for m in good])
                    cur_pts = np.array([key_cur[m.trainIdx].pt for m in good])
                    transform, flags = cv2.findHomography(cur_pts, ref_pts, cv2.RANSAC, 3.0)
                    count = int(flags.sum()) if flags is not None else 0
                    if transform is not None and count >= 10 and count / len(good) >= 0.45:
                        inverse = np.linalg.inv(transform)
                        projected = cv2.perspectiveTransform(corners[None].astype(np.float32), inverse)[0]
                        area_ref = abs(cv2.contourArea(corners.astype(np.float32)))
                        area_now = abs(cv2.contourArea(projected))
                        shift = float(np.median(np.linalg.norm(projected - corners, axis=1)))
                        if (
                            np.isfinite(projected).all()
                            and cv2.isContourConvex(projected)
                            and 0.45 < area_now / area_ref < 2.0
                            and shift < 280
                        ):
                            accepted = transform
                            shifts.append(shift)
                            inliers.append(count)
            output.append(
                {
                    "source_seq": index,
                    "t_source_s": row["timestamp_seconds"],
                    "current_to_reference_H": accepted.tolist() if accepted is not None else None,
                    "inliers": count,
                    "status": "table_region_image_fit" if accepted is not None else "unavailable",
                }
            )
    finally:
        cap.release()
    return output, {
        "method": "ORB table-region descriptors + independent current-to-reference RANSAC",
        "reference_source_s": reference_s,
        "reference_corners_px_1920": CORNER_PIXELS_1920.tolist(),
        "accepted_frames": sum(x["current_to_reference_H"] is not None for x in output),
        "total_frames": len(output),
        "median_inliers": float(np.median(inliers)) if inliers else None,
        "median_corner_motion_px_1280": float(np.median(shifts)) if shifts else None,
        "scope": "illustrative avatar image stabilization only; not validated metric calibration",
    }


def build(video: Path, poses_path: Path, output: Path, stabilize: bool = True) -> dict:
    started = time.perf_counter()
    pose_document = json.loads(poses_path.read_text())
    frames = copy.deepcopy(pose_document["frames"])
    metadata = pose_document["report"]
    width, height = metadata["source_width"], metadata["source_height"]
    config = {
        "width": 1280,
        "height": 720,
        "table_corners_world_m": WORLD_CORNERS,
        "table_corners_px": (CORNER_PIXELS_1920 * (2 / 3)).tolist(),
    }
    camera = calibrate(config)
    transforms, motion_report = table_transforms(video, frames) if stabilize else ([], {"method": "disabled"})
    accepted = 0
    for index, row in enumerate(frames):
        for person in row["players"]:
            points = np.array(person["image_landmarks"], np.float64)
            points[:, 0] *= 1280 / width
            points[:, 1] *= 720 / height
            transform = transforms[index]["current_to_reference_H"] if stabilize else None
            if transform is not None:
                points[:, :2] = cv2.perspectiveTransform(points[None, :, :2], np.asarray(transform))[0]
            person["image_landmarks"] = points.tolist()
        if stabilize and transforms[index]["current_to_reference_H"] is not None:
            accepted += 1
    reconstructed = reconstruct_players(frames, camera, smooth=False)
    scene_frames = []
    for index, (row, people) in enumerate(zip(frames, reconstructed, strict=True)):
        scene_frames.append(
            {
                "t": row["timestamp_seconds"],
                "source_seq": row["frame_index"],
                "players": people,
                "camera_stabilization": transforms[index]["status"] if stabilize else "disabled",
                "ball": {"position": None, "status": "unavailable_dynamic_metric_calibration"},
            }
        )
    # A stable presentation uses explicit playing-lane/depth priors. Raw joints
    # above retain the unfiltered approximate reconstruction for audit. The
    # renderer never feeds this prior back to ball geometry or the referee.
    presentation = copy.deepcopy(scene_frames)
    for pid in (0, 1):
        valid = np.array([f["players"][pid]["joints"] is not None for f in presentation])
        ids = np.flatnonzero(valid)
        for run in np.split(ids, np.flatnonzero(np.diff(ids) > 1) + 1):
            if not len(run):
                continue
            roots = np.array([presentation[i]["players"][pid]["root"] for i in run])
            roots[:, 0] = np.clip(roots[:, 0], -3.5 if pid == 0 else 1.35, -1.35 if pid == 0 else 3.5)
            roots[:, 1] = 0.0  # lateral depth is unobserved in this presentation
            roots[:, 2] = np.clip(roots[:, 2], 0.60, 0.95)
            roots = median_filter(roots, size=(5, 1), mode="nearest")
            for i, root in zip(run, roots, strict=True):
                person = presentation[i]["players"][pid]
                q = np.asarray(person["joints"])
                q += root - np.asarray(person["root"])
                person["joints"] = q.tolist()
                person["root"] = root.tolist()
    smoothing_report = smooth_player_motion(presentation, metadata["sample_fps_nominal"])
    for frame, display in zip(scene_frames, presentation, strict=True):
        for person, rendered in zip(frame["players"], display["players"], strict=True):
            if person["joints"] is not None:
                person["render_joints"] = rendered.get("render_joints", rendered["joints"])
                person["render_root"] = rendered.get("render_root", rendered["root"])
                person["presentation_root_prior"] = (
                    "bounded end-position lane, unobserved lateral depth at zero, median-filtered approximate root"
                )
    smoothing_report["root_prior"] = (
        "Display only: end-position lane x +/-[1.35,3.5]m, unobserved y=0, 5-sample median root filter"
    )
    smoothing_report["accuracy"] = "Smoothing diagnostics are not motion-capture accuracy or metric evidence"
    report = {
        "status": "illustrative pose, not metric evidence",
        "source": str(video.resolve()),
        "source_pose_report": metadata,
        "sampled_frames": len(scene_frames),
        "visible_person_frames": [
            sum(f["players"][pid]["joints"] is not None for f in scene_frames) for pid in range(2)
        ],
        "calibration": {
            "status": camera["calibration_status"],
            "trusted": False,
            "corner_fit_rmse_px_1280": camera["corner_rmse_px"],
            "camera_position_m_estimate": camera["center"].tolist(),
            "focal_px_estimate_1280": camera["focal_length_px"],
            "validation": (
                "Four manually selected coplanar corners at source 6s; no independent height/intrinsics ground truth"
            ),
        },
        "camera_stabilization": motion_report,
        "presentation_smoothing": smoothing_report,
        "hands": "Hand Landmarker not run; hand/palm visibility and release remain unavailable",
        "paddle": "Wrist-attached illustration only; face orientation and contact not measured",
        "ball_3d": "Unavailable: moving cameras lack validated time-varying metric calibration and sync",
        "total_build_seconds": time.perf_counter() - started,
        "notes": [
            "Source 2D landmark coordinates and model world outputs are retained unchanged in poses.json.",
            "Scene root placement, occluded-leg prior, body shape and paddle are illustrative estimates.",
            "Image stabilization is for presentation, and may fail under occlusion or large camera motion.",
            "render_joints are separately smoothed; raw joints and source time are unchanged by smoothing.",
            "No avatar quantity is used as referee measurement evidence.",
        ],
    }
    scene = {
        "frames": scene_frames,
        "status": report["status"],
        "cameras": [],
        "table": {"length_m": 2.74, "width_m": 1.525, "top_height_m": 0.76, "net_height_m": 0.1525},
        "report": report,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scene, allow_nan=False))
    output.with_name("scene-report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    output.with_name("camera-stabilization.json").write_text(json.dumps(transforms, allow_nan=False))
    print(json.dumps(report, indent=2), flush=True)
    return report


def attach_hand_reports(scene_path: Path) -> dict:
    """Attach cached pixel-probe provenance without rerunning body inference."""
    scene = json.loads(scene_path.read_text())
    reports = []
    for camera in ("side", "diagonal"):
        path = scene_path.parent / f"hands-{camera}.json"
        if path.exists():
            reports.append(json.loads(path.read_text())["report"])
    scene["report"]["hands"] = {
        "status": "pixel wrist-crop observations only; metric release/open-palm evidence unvalidated",
        "probes": reports,
    }
    scene_path.write_text(json.dumps(scene, allow_nan=False))
    scene_path.with_name("scene-report.json").write_text(json.dumps(scene["report"], indent=2, allow_nan=False))
    return scene["report"]["hands"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--poses", type=Path, default=Path("data/local/tt-demo/poses.json"))
    parser.add_argument("--output", type=Path, default=Path("data/local/tt-demo/scene.json"))
    parser.add_argument("--no-stabilization", action="store_true")
    parser.add_argument("--refresh-hands", action="store_true", help="Attach cached hand probe reports only")
    args = parser.parse_args()
    if args.refresh_hands:
        print(json.dumps(attach_hand_reports(args.output), indent=2))
    else:
        build(args.video, args.poses, args.output, not args.no_stabilization)
        attach_hand_reports(args.output)
