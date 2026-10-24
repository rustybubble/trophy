#!/usr/bin/env python3
"""Localization recall on separately reviewed source pixels; coverage is separate."""

import argparse
import json
import math
from pathlib import Path


def evaluate(labels, predictions, tolerance):
    tp = miss = wrong = 0
    distances = []
    unknown = 0
    for label in labels:
        if label["status"] != "visible":
            unknown += 1
            continue
        p = predictions.get(label["seq"])
        if not p or p.get("x") is None:
            miss += 1
            continue
        d = math.hypot(p["x"] - label["x"], p["y"] - label["y"])
        distances.append(d)
        if d <= tolerance:
            tp += 1
        else:
            wrong += 1
    n = tp + miss + wrong
    return dict(
        labeled_visible=n,
        unassessable=unknown,
        correct_within_tolerance=tp,
        missed=miss,
        localized_elsewhere=wrong,
        recall=tp / n if n else None,
        tolerance_source_px=tolerance,
        false_localizations_on_visible_frames=wrong,
        false_positives_on_absent_frames=None,
        note="No absent-frame annotations; false-positive rate on absent frames is not established.",
    )


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=root / "data/local/tt-demo/evaluation.json")
    p.add_argument("--detector", default="tracking")
    a = p.parse_args()
    labels = json.loads((root / "evals/labels/ttclips-manual.json").read_text())
    report = dict(method=labels["method"], split=labels["split"], views={})
    for cam in ("side", "diagonal"):
        d = json.loads((root / f"data/local/tt-demo/{cam}-{a.detector}.json").read_text())
        report["views"][cam] = evaluate(
            [label for label in labels["labels"] if label["cam_id"] == cam],
            {r["seq"]: r for r in d["frames"]},
            labels["tolerance_source_px"],
        )
    a.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
