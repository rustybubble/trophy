#!/usr/bin/env python3
# ruff: noqa: E402
"""Offline BlurBall block-three inference, real native temporal windows only.

Each head maps to its own observed source frame. Step-three scheduling is a
separate measured variant from sliding-window inference, not a hidden speedup.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/flight"))
import av
import cv2
import numpy as np
from flight.blurball import Predictor, decode_heatmap, preprocess
from flight.recording import sha256


def track(path, out, predictor, gray=False, limit=None, start_s=0):
    rows = []
    buffer = []
    model_ms = []
    score_ms = []
    start = time.perf_counter()
    with av.open(str(path)) as c:
        stream = c.streams.video[0]
        stream.thread_type = "AUTO"
        for seq, f in enumerate(c.decode(video=0)):
            stamp = float(f.pts * f.time_base)
            if stamp < start_s:
                continue
            bgr = f.reformat(width=1280, height=720, format="bgr24").to_ndarray()
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if gray:
                rgb = np.repeat(rgb.max(axis=2)[..., None], 3, axis=2)
            processed, inverse = preprocess(rgb)
            row = dict(
                seq=seq,
                pts=int(f.pts),
                time_base=str(f.time_base),
                t_source_s=stamp,
                t_game_s=stamp,
                source_size=[f.width, f.height],
                x=None,
                y=None,
                score=None,
                status="missing",
            )
            rows.append(row)
            buffer.append((processed, row))
            if len(buffer) == 3:
                if predictor.warmup_ms is None:
                    predictor.warmup([x[0] for x in buffer])
                    start = time.perf_counter()
                hm, ms, transfer_ms = predictor.predict([x[0] for x in buffer])
                model_ms.append(ms)
                tick = time.perf_counter()
                for head, (_, r) in enumerate(buffer):
                    candidates, peak = decode_heatmap(hm[head], inverse, 1280, 720, 0.65)
                    if candidates:
                        best = max(candidates, key=lambda x: x["component_mass"])
                        r.update(
                            x=best["x"] * 3,
                            y=best["y"] * 3,
                            score=best["score"],
                            status="observed_2d",
                            heatmap_peak=peak,
                        )
                score_ms.append((time.perf_counter() - tick) * 1000)
                buffer = []
            if len(rows) % 900 == 0:
                print(path.name, len(rows), flush=True)
            if limit and len(rows) >= limit:
                break
    for _, r in buffer:
        r["status"] = "insufficient_temporal_context"
    elapsed = time.perf_counter() - start
    report = dict(
        detector="BlurBall max-channel-gray" if gray else "BlurBall RGB",
        source_sha256=sha256(path),
        device=predictor.device,
        weights_sha256=predictor.weight_sha256,
        upstream_commit="2f0f5496f7ba4b5b1a36790749935121b2ce972d",
        temporal_stride=3,
        temporal_window=3,
        input_size=[512, 288],
        source_processing_size=[1280, 720],
        photometric="max-channel-gray" if gray else "rgb",
        threshold=0.65,
        source_frames=len(rows),
        observed_frames=sum(r["x"] is not None for r in rows),
        elapsed_s=elapsed,
        end_to_end_fps=len(rows) / elapsed,
        model_mean_ms=float(np.mean(model_ms)),
        model_p95_ms=float(np.percentile(model_ms, 95)),
        postprocess_mean_ms=float(np.mean(score_ms)),
        recall=None,
        false_positives=None,
        score_note="Heatmap scores are uncalibrated; not a probability of correct call.",
        private_evaluation_only=True,
        public_weights_permission="Not granted. No weights redistributed.",
    )
    out.write_text(json.dumps(dict(frames=rows, report=report), allow_nan=False))
    print(report, flush=True)
    return rows, report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gray", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--start", type=float, default=0)
    p.add_argument("--suffix", default="blurball")
    a = p.parse_args()
    predictor = Predictor(device="mps")
    for cam, file in [("side", "Adobe Express - IMG_4342.mp4"), ("diagonal", "IMG_2865 (1).mov")]:
        track(
            ROOT / "data/ttClips" / file,
            ROOT / f"data/local/tt-demo/{cam}-{a.suffix}.json",
            predictor,
            a.gray,
            a.limit,
            a.start,
        )


if __name__ == "__main__":
    main()
