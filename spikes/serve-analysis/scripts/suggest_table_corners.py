"""Suggest the four table corners of a clip for the Trophy dashboard (uses trophy/table_detection.py).

    .venv/bin/python scripts/suggest_table_corners.py VIDEO [--times 0,2,4,8,12] [--width 1280]

Samples a few frames, runs the tabletop detector on each, puts the corners in Trophy's order (near-left, near-right,
far-right, far-left: the two lowest on screen are the near edge) and prints the per-corner median in source pixels
plus how many frames agreed. A suggestion only: the judge confirms or drags the corners. Prints {"corners": null} when
no frame shows the table.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import imageio_ffmpeg  # noqa: E402
import numpy as np  # noqa: E402

from trophy.table_detection import detect_table  # noqa: E402


def canonical(q):
    q = np.asarray(q, float).reshape(4, 2)
    order = np.argsort(q[:, 1])
    far, near = q[order[:2]], q[order[2:]]
    near = near[np.argsort(near[:, 0])]
    far = far[np.argsort(far[:, 0])]
    return np.array([near[0], near[1], far[1], far[0]])


def frame_at(video, t, width):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-ss', str(t), '-i', str(video), '-frames:v', '1',
           '-vf', f'scale={width}:-2:flags=area', '-f', 'image2pipe', '-vcodec', 'png', '-']
    out = subprocess.run(cmd, capture_output=True).stdout
    if not out:
        return None
    return cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('--times', default='0,1,2,4,8,12')
    ap.add_argument('--width', type=int, default=1280)
    a = ap.parse_args()
    quads, size = [], None
    for t in (float(v) for v in a.times.split(',')):
        img = frame_at(a.video, t, a.width)
        if img is None:
            continue
        size = img.shape[1], img.shape[0]
        d = detect_table(img)
        if d is not None:
            quads.append(canonical(d['corners']))
    if not quads:
        print(json.dumps({'corners': None, 'frames_tried': len(a.times.split(','))}))
        return
    med = np.median(np.stack(quads), axis=0)
    spread = float(np.max(np.linalg.norm(np.stack(quads) - med, axis=2))) if len(quads) > 1 else 0.0
    print(json.dumps({'corners_norm': [[float(x / size[0]), float(y / size[1])] for x, y in med],
                      'agreeing_frames': len(quads), 'max_spread_px': round(spread, 1), 'detector': 'table_detection'}))


if __name__ == '__main__':
    main()
