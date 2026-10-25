"""Measure a ball detector + the gated tracker on frames that went through the phone path.

    python -m flight.bench --video side.mp4 --detector blurball [--photometric maxgray] [--start 1 --end 44]
                           [--labels evals/labels/ttclips-side-tune.json --cam side] [--out report.json]

Frames are taken at `--fps` (30, as phones send; a 60 fps clip keeps every other frame), resized to 1280x720 and
round-tripped through JPEG q70 4:2:0 like the PWA (CLAUDE.md Gotchas: tune on the phone path, not the original). The
timed loop is what flight.live does per frame: JPEG decode, detect, track. Reported: device actually used, per-frame
ms (p50/p95), end-to-end fps, model ms. With `--labels` (trophy.ball_labels.v1, source pixels): for `visible` labels,
whether the track (and, separately, the raw top candidate) is within the label's tolerance at that frame; for `none`
labels, whether the track reports a ball there (a false positive). `held`/`unsure`/`unassessable` are counted but not
scored. These are detector-tuning numbers on whatever clip is given, never call accuracy.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from .detect import ClassicalDetector
from .track import Tracker

W, H = 1280, 720


def phone_path(bgr: np.ndarray, quality: int = 70) -> bytes:
    if bgr.shape[1] != W or bgr.shape[0] != H:
        bgr = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(
        ".jpg",
        bgr,
        [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420],
    )
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return buf.tobytes()


def frames(video: Path, start_s: float, end_s: float | None, fps: float):
    """Yields (source_frame_index, t_source_s, jpeg) at about `fps`, from start_s to end_s."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))
    i0 = int(round(start_s * src_fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i0)
    i = i0
    while True:
        ok, bgr = cap.read()
        if not ok or (end_s is not None and i / src_fps > end_s):
            break
        if (i - i0) % step == 0:
            yield i, i / src_fps, phone_path(bgr)
        i += 1
    cap.release()


def make_detector(args):
    if args.detector == "classical":
        det = ClassicalDetector(colour=args.ball, expected_radius_px=args.radius_px)
        return det, {"name": "classical", "device": "cpu", "colour": args.ball}
    from .blurball import BlurBallDetector, Predictor

    pred = Predictor(device=args.device)
    det = BlurBallDetector(pred, threshold=args.threshold, stride=args.stride, photometric=args.photometric)
    info = {
        "name": "blurball",
        "device": pred.device,
        "torch": pred.torch_version,
        "threshold": args.threshold,
        "stride": args.stride,
        "photometric": args.photometric,
        "weights_sha256": pred.weights_sha256[:12],
    }
    return det, info


def run(args) -> dict:
    det, info = make_detector(args)
    tracker = Tracker()
    per_frame_ms: list[float] = []
    raw: dict[int, list[dict]] = {}  # source frame -> candidates
    t_of: dict[int, float] = {}
    src_of: dict[int, int] = {}  # bench seq (consecutive, as a phone sends) -> source frame index
    n = 0
    t_wall = time.perf_counter()
    for src_i, t_s, jpeg in frames(args.video, args.start, args.end, args.fps):
        t0 = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        src_of[n] = src_i
        if info["name"] == "classical":
            resolved = [{"frame": n, "t_s": t_s, "candidates": det(img)}]
        else:
            resolved = det.push(n, t_s, img)
        for r in resolved:
            r["frame"] = src_of[r["frame"]]
            tracker.step(r["frame"], r["t_s"], r["candidates"])
            raw[r["frame"]] = r["candidates"]
        per_frame_ms.append((time.perf_counter() - t0) * 1000)
        t_of[src_i] = t_s
        n += 1
        if args.max_frames and n >= args.max_frames:
            break
    wall = time.perf_counter() - t_wall
    ms = np.array(per_frame_ms) if per_frame_ms else np.zeros(1)
    rep = {
        "video": Path(args.video).name,
        "window_s": [args.start, args.end],
        "fps_sampled": args.fps,
        "frame_size": [W, H],
        "phone_path": "JPEG q70 4:2:0",
        "machine": f"{platform.machine()} {platform.mac_ver()[0] or platform.platform()}",
        "detector": info,
        "frames": n,
        "per_frame_ms_p50": round(float(np.percentile(ms, 50)), 2),
        "per_frame_ms_p95": round(float(np.percentile(ms, 95)), 2),
        "processing_fps": round(1000.0 / float(ms.mean()), 1),
        "wall_fps_incl_video_decode": round(n / wall, 1) if wall else None,
        "model_ms_ewma": round(getattr(det, "model_ms", 0.0), 2) or None,
        "track_samples": len(tracker.out),
        "track_coverage": round(len(tracker.out) / max(1, n), 3),
    }
    if args.labels:
        rep["labels"] = score_labels(args, tracker.out, raw)
    return rep


def score_labels(args, track: list[dict], raw: dict[int, list[dict]]) -> dict:
    data = json.loads(Path(args.labels).read_text())
    tol_src = float(data.get("tolerance_source_px", 32))
    by_frame = {s["frame"]: s for s in track}
    out = {
        "file": Path(args.labels).name,
        "split": data.get("split"),
        "tolerance_source_px": tol_src,
        "visible": 0,
        "track_hit": 0,
        "track_miss": 0,
        "track_wrong": 0,
        "raw_top1_hit": 0,
        "none": 0,
        "none_false_pos": 0,
        "not_scored": {},
    }
    lo, hi = min(raw) if raw else 0, max(raw) if raw else -1
    for lab in data["labels"]:
        if args.cam and lab.get("cam_id") != args.cam:
            continue
        f = int(lab["seq"])
        if not (lo <= f <= hi):
            continue
        sw, sh = lab.get("source_size") or [W, H]
        sx = W / sw
        tol = tol_src * sx
        # the processed frame nearest the label (a 60 fps clip sampled at 30 fps keeps every other frame)
        g = min(raw, key=lambda k: abs(k - f))
        if abs(g - f) > 1:
            continue
        st = lab["status"]
        s = by_frame.get(g)
        if st == "visible":
            out["visible"] += 1
            truth = np.array([lab["x"] * sx, lab["y"] * sx])
            if s is None:
                out["track_miss"] += 1
            elif np.linalg.norm(np.array(s["xy_px"]) - truth) <= tol:
                out["track_hit"] += 1
            else:
                out["track_wrong"] += 1
            c = raw.get(g) or []
            if c and np.linalg.norm(np.array(c[0]["xy_px"]) - truth) <= tol:
                out["raw_top1_hit"] += 1
        elif st == "none":
            out["none"] += 1
            if s is not None:
                out["none_false_pos"] += 1
        else:
            out["not_scored"][st] = out["not_scored"].get(st, 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--detector", choices=["classical", "blurball"], default="classical")
    ap.add_argument("--ball", default="white", help="classical colour model: white | orange")
    ap.add_argument("--radius-px", type=float, default=None)
    ap.add_argument("--device", default="auto", help="blurball: auto | mps | cpu")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--photometric", choices=["rgb", "maxgray"], default="rgb")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--cam", default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    rep = run(args)
    text = json.dumps(rep, indent=1)
    print(text)
    if args.out:
        args.out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
