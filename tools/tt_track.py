"""Run the gated ball tracker over a recorded clip; write one JSON line per source frame.

    uv run --project services/flight python tools/tt_track.py data/local/ttClips/side_IMG_4342.mp4 \
        --out data/local/tt-track/side.jsonl [--start 0 --seconds 20]

Ball coordinates are written in SOURCE pixels (x, y; e.g. 3840x2160, comparable with the manual labels) and in
working 1280x720 pixels (wx, wy). `tb` is the smoothed table (x_left, x_right, a, b, net_x, thickness) in working px.

`--live` simulates what flight.live sees from a phone: ~30 fps (every 2nd frame of a 60 fps clip), each frame
round-tripped through a 4:2:0 JPEG at quality 70 (the PWA's canvas encoder), and the colour model learnt online
(flight.colour.LiveLearner, defaults until then). Rows keep source frame numbers so the labels still apply.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
from flight.balltrack import Detector, Tracker
from flight.colour import LiveLearner, learn
from flight.table import TableTracker
from flight.video import frames, probe

W, H = 1280, 720


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--live", action="store_true", help="simulate the live phone path (30 fps, JPEG, online colour)")
    a = ap.parse_args()
    info = probe(a.clip)
    sx, sy = info.w / W, info.h / H
    a.out.parent.mkdir(parents=True, exist_ok=True)
    # learn this camera's ball colour from the first 30 s (cameras differ in white balance and exposure)
    stride = max(1, round(info.fps / 30)) if a.live else 1
    live_learner: LiveLearner | None = None
    if a.live:
        live_learner = LiveLearner()
        tr = Tracker(fps=info.fps / stride)
    else:
        colour = learn(frames(a.clip, W, H, a.start, 30.0))
        print(f"colour model: {colour}")
        tr = Tracker(detector=Detector(colour), fps=info.fps)
    tables = TableTracker()
    n = obs = 0
    t_proc = 0.0
    t0 = time.perf_counter()
    with a.out.open("w", encoding="utf8") as f:
        for seq, t, bgr in frames(a.clip, W, H, a.start, a.seconds):
            if seq % stride:
                continue
            if a.live:
                ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
                bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            p0 = time.perf_counter()
            if live_learner is not None:
                model = live_learner.add(bgr)
                if model is not None:
                    print(f"colour model after {n} frames: {model}")
                    tr.detector, live_learner = Detector(model), None
            p = tr.step(seq // stride, t, bgr)
            tb = tables.update(bgr)
            t_proc += time.perf_counter() - p0
            row = {"seq": seq, "t": round(t, 4), "state": p.state, "track_id": p.track_id, "score": p.score}
            if p.x is not None and p.y is not None:
                row["x"], row["y"] = round(p.x * sx, 1), round(p.y * sy, 1)  # source pixels
                row["wx"], row["wy"] = round(p.x, 2), round(p.y, 2)  # working pixels (rally analysis)
            if tb is not None:
                row["tb"] = [round(v, 4) for v in (tb.x_left, tb.x_right, tb.a, tb.b, tb.net_x, tb.thickness)]
            f.write(json.dumps(row) + "\n")
            n += 1
            obs += p.state == "observed"
    wall = time.perf_counter() - t0
    print(
        f"{a.clip.name}: {n} frames, observed {obs} ({obs / max(n, 1):.0%}), tracks {tr.next_id - 1}; "
        f"tracker {n / t_proc:.0f} fps (CPU, {W}x{H}), end-to-end incl. 4K decode {n / wall:.0f} fps"
    )


if __name__ == "__main__":
    main()
