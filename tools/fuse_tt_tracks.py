#!/usr/bin/env python3
"""Experimental observed-color fallback for gaps in offline neural tracks.

This variant was selected after reviewing component evaluations. All existing
label sets are development data for this variant: it has NO held-out result.
It does not extrapolate, interpolate, or turn ranking scores into probabilities.
"""

import copy
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fuse(neural, classical, min_score=0.6):
    if len(neural) != len(classical):
        raise ValueError("Different source frame counts")
    rows = []
    fallbacks = 0
    for a, b in zip(neural, classical, strict=True):
        if (a["seq"], a["pts"], a["time_base"]) != (b["seq"], b["pts"], b["time_base"]):
            raise ValueError("Source frame identity mismatch")
        r = copy.deepcopy(a)
        r["detector"] = "BlurBall max-channel-gray"
        if a["x"] is None and b["x"] is not None and b["score"] >= min_score:
            r = copy.deepcopy(b)
            r["status"] = "color_candidate_2d"
            r["detector"] = "conservative orange color/motion fallback"
            fallbacks += 1
        rows.append(r)
    return rows, fallbacks


def main():
    out = ROOT / "data/local/tt-demo"
    for cam in ["side", "diagonal"]:
        start = time.perf_counter()
        n = json.loads((out / f"{cam}-blurball-gray.json").read_text())
        c = json.loads((out / f"{cam}-tracking.json").read_text())
        rows, count = fuse(n["frames"], c["frames"])
        report = dict(
            detector="BlurBall grayscale + observed orange candidate fallback (experimental)",
            device="MPS + CPU",
            source_sha256=n["report"].get("source_sha256"),
            source_frames=len(rows),
            observed_frames=sum(r["x"] is not None for r in rows),
            fallback_frames=count,
            end_to_end_fps=None,
            elapsed_s=None,
            cache_fusion_s=time.perf_counter() - start,
            inference_note="Components were preprocessed separately; no joint end-to-end throughput measured.",
            components={"neural": n["report"], "classical": c["report"]},
            evaluation_note=(
                "Selected after component evaluations. All existing labels are development data "
                "for this variant; held-out accuracy unknown."
            ),
            score_note=(
                "Uncalibrated detector ranking scores; orange fallback is a candidate, never automatic rule evidence."
            ),
            private_evaluation_only=True,
            public_weights_permission="Not granted. No weights redistributed.",
        )
        (out / f"{cam}-hybrid.json").write_text(json.dumps(dict(frames=rows, report=report), allow_nan=False))
        print(cam, count, "observed fallback candidates")


if __name__ == "__main__":
    main()
