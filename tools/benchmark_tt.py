#!/usr/bin/env python3
# ruff: noqa: E402
"""Bounded native-720p comparison. Accuracy is reported only with separate labels."""

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/flight"))
import av
import cv2
import numpy as np
from flight.recording import OrangeTracker


def benchmark(path, count, model=None):
    if model:
        from flight.blurball import decode_heatmap, preprocess
    rows = []
    buffers = deque(maxlen=3)
    times = []
    model_times = []
    with av.open(str(path)) as c:
        stream = c.streams.video[0]
        stream.thread_type = "AUTO"
        # Representative active interval at six seconds, actual source PTS retained.
        c.seek(int(6 / float(stream.time_base)), stream=stream, backward=True)
        it = c.decode(video=0)
        tracker = OrangeTracker()
        start = time.perf_counter()
        for f in it:
            t = float(f.pts * f.time_base)
            if t < 6:
                continue
            tick = time.perf_counter()
            bgr = f.reformat(width=1280, height=720, format="bgr24").to_ndarray()
            if model:
                processed, inverse = preprocess(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                buffers.append(processed)
                best = None
                if len(buffers) == 3:
                    if not model.warmup_ms:
                        model.warmup(list(buffers))
                        start = time.perf_counter()
                        rows = []
                        times = []
                    hm, ms, _ = model.predict(list(buffers))
                    model_times.append(ms)
                    candidates, _ = decode_heatmap(hm[-1], inverse, 1280, 720, 0.65)
                    best = max(candidates, key=lambda x: x["component_mass"]) if candidates else None
            else:
                best, _ = tracker.update(bgr, t)
            times.append(time.perf_counter() - tick)
            rows.append(dict(t_source_s=t, x=best["x"] if best else None, y=best["y"] if best else None))
            if len(rows) >= count:
                break
    elapsed = time.perf_counter() - start
    return dict(
        frames=len(rows),
        elapsed_s=elapsed,
        end_to_end_fps=len(rows) / elapsed,
        model_mean_ms=float(np.mean(model_times)) if model_times else None,
        per_frame_processing_p50_ms=float(np.median(times) * 1000),
        detected=sum(r["x"] is not None for r in rows),
        recall=None,
        false_positives=None,
        samples=rows,
        decode="original 4K source decoded and resized to 1280×720 CPU",
        note=(
            "Heuristic coverage is not recall. Sequential paired FPS = "
            "reciprocal sum of measured per-view seconds/frame."
        ),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--model", choices=["classical", "blurball"], default="classical")
    p.add_argument("--device", default="mps")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    model = None
    if a.model == "blurball":
        from flight.blurball import Predictor

        model = Predictor(device=a.device)
    report = dict(detector=a.model, device=model.device if model else "CPU", views={})
    for cid, file in [("side", "Adobe Express - IMG_4342.mp4"), ("diagonal", "IMG_2865 (1).mov")]:
        report["views"][cid] = benchmark(ROOT / "data/ttClips" / file, a.frames, model)
        print(cid, report["views"][cid]["end_to_end_fps"], flush=True)
    report["sequential_paired_fps"] = 1 / sum(1 / r["end_to_end_fps"] for r in report["views"].values())
    a.output.write_text(json.dumps(report, indent=2))
    print("paired", report["sequential_paired_fps"])


if __name__ == "__main__":
    main()
