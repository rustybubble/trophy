"""Evaluate a tracker output against the manual labels and the continuity audit from Mu Du's failure report.

    uv run --project services/flight python tools/tt_eval.py data/local/tt-track/side.jsonl --cam side \
        --labels evals/labels/ttclips-manual.json evals/labels/ttclips-heldout.json

Localization: a visible label counts as found if an OBSERVED position is within the labels' tolerance (32 source
px); "wrong" = observed but farther; "missing" = no observation. Predicted (bridged) positions are reported
separately and never count as found. Continuity: consecutive observed frames (Δt <= 20 ms) whose displacement
exceeds 384 / 960 source px (10% / 25% of 3840), the same thresholds as the report; across a track change too.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(p: Path) -> dict[int, dict]:
    return {r["seq"]: r for r in map(json.loads, p.read_text("utf8").splitlines())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("track", type=Path)
    ap.add_argument("--cam", required=True)
    ap.add_argument("--labels", type=Path, nargs="+", required=True)
    a = ap.parse_args()
    rows = load(a.track)

    for lp in a.labels:
        doc = json.loads(lp.read_text("utf8"))
        tol = doc.get("tolerance_source_px", 32)
        labels = [lab for lab in doc["labels"] if lab["cam_id"] == a.cam and lab["seq"] in rows]
        vis = [lab for lab in labels if lab["status"] == "visible"]
        found = wrong = missing = bridged = 0
        errs = []
        for lab in vis:
            r = rows[lab["seq"]]
            if r["state"] == "observed":
                e = ((r["x"] - lab["x"]) ** 2 + (r["y"] - lab["y"]) ** 2) ** 0.5
                errs.append(e)
                if e <= tol:
                    found += 1
                else:
                    wrong += 1
            else:
                missing += 1
                bridged += r["state"] == "predicted"
        med = sorted(errs)[len(errs) // 2] if errs else float("nan")
        print(
            f"{lp.name} [{a.cam}]: visible labels {len(vis)} in range -> found {found}, wrong {wrong}, missing "
            f"{missing} (of which bridged by prediction {bridged}); median error of observed {med:.1f} px"
        )

    seqs = sorted(rows)
    stride = min((b - a for a, b in zip(seqs, seqs[1:], strict=False)), default=1)  # 2 for a --live 30 fps track
    pairs = j384 = j960 = switches = 0
    biggest = 0.0
    for s0, s1 in zip(seqs, seqs[1:], strict=False):
        r0, r1 = rows[s0], rows[s1]
        if r0["state"] != "observed" or r1["state"] != "observed" or s1 - s0 != stride:
            continue
        pairs += 1
        d = ((r1["x"] - r0["x"]) ** 2 + (r1["y"] - r0["y"]) ** 2) ** 0.5
        biggest = max(biggest, d)
        j384 += d > 384
        j960 += d > 960
        switches += r0["track_id"] != r1["track_id"]
    n = len(rows)
    obs = sum(r["state"] == "observed" for r in rows.values())
    print(
        f"continuity [{a.cam}]: {n} frames, observed {obs} ({obs / n:.0%}); adjacent observed pairs {pairs}: "
        f">384 px {j384}, >960 px {j960}, largest {biggest:.0f} px, adjacent pairs across a track change {switches}"
    )


if __name__ == "__main__":
    main()
