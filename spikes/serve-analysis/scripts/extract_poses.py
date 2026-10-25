"""Pretrained MediaPipe Pose Landmarker, native CPU; no synthetic animation.

Run with .venv-pose/bin/python. Each player uses a separate tracked ROI in the
side-view demo; ROIs are explicit configuration, not generated joint motion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

SHA = '5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1'

def extract(video, output, model, config, limit=None):
    if hashlib.sha256(Path(model).read_bytes()).hexdigest() != SHA:
        raise ValueError('Pose checkpoint checksum mismatch')
    cfg = json.loads(Path(config).read_text())
    rois = cfg.get('player_rois_px')
    if not rois or len(rois) != 2:
        raise ValueError('Configure two player_rois_px boxes covering each player’s movement')
    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model), delegate=python.BaseOptions.Delegate.CPU),
        running_mode=vision.RunningMode.VIDEO, num_poses=1,
        min_pose_detection_confidence=.4, min_pose_presence_confidence=.4, min_tracking_confidence=.4)
    trackers = [vision.PoseLandmarker.create_from_options(options) for _ in rois]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError('Cannot read pose input video')
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    latencies = []
    start = time.perf_counter()
    try:
        while limit is None or len(frames) < limit:
            ok, frame = cap.read()
            if not ok:
                break
            idx = len(frames)
            stamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            people = []
            for pid, (x0, y0, x1, y1) in enumerate(rois):
                rgb = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
                t = time.perf_counter()
                result = trackers[pid].detect_for_video(image, round(idx / fps * 1000))
                latencies.append((time.perf_counter() - t) * 1000)
                if result.pose_landmarks:
                    lm, wl = result.pose_landmarks[0], result.pose_world_landmarks[0]
                    pixels = [[v.x * (x1-x0) + x0, v.y * (y1-y0) + y0, v.visibility] for v in lm]
                    confidence = float(np.mean([lm[j].visibility for j in [11, 12, 23, 24, 25, 26, 27, 28]]))
                    people.append(dict(id=pid, image_landmarks=pixels,
                                       world_landmarks=[[v.x, v.y, v.z] for v in wl], confidence=confidence))
            frames.append(dict(frame_index=idx, timestamp_seconds=stamp, players=people))
            if idx % 30 == 0:
                print(f'Pose inference {idx}: {len(people)}/2 players', flush=True)
    finally:
        cap.release()
        for tracker in trackers:
            tracker.close()
    report = dict(model='MediaPipe Pose Landmarker full float16 v1', package_version=mp.__version__,
                  device='native CPU (XNNPACK)', weights_sha256=SHA, video=str(Path(video).resolve()),
                  analyzed_frames=len(frames), fps=fps, total_seconds=time.perf_counter()-start,
                  mean_person_inference_ms=float(np.mean(latencies)),
                  detected_person_frames=[sum(any(p['id']==pid for p in f['players']) for f in frames) for pid in range(2)],
                  notes=['33 pretrained landmarks per detected person. Hip-relative world coordinates are inferred by the model.',
                         'Fixed side-view player ROIs preserve identity; occluded joints remain model estimates.'])
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(dict(frames=frames, report=report), allow_nan=False))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('video');p.add_argument('--output',required=True);p.add_argument('--config',required=True)
    p.add_argument('--model',default='weights/pose_landmarker_full.task');p.add_argument('--max-frames',type=int)
    a=p.parse_args();extract(a.video,a.output,a.model,a.config,a.max_frames)
