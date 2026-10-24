"""Contact sheet for eyeballing a tracker run: every Nth frame, track (red = observed, yellow = predicted, with the
track id) and manual label (green circle). Writes a PNG under data/local (footage stays local).

    uv run --project services/flight python tools/tt_sheet.py data/local/ttClips/side_IMG_4342.mp4 \
        data/local/tt-track/side_dev.jsonl --start 7.4 --seconds 2.4 --every 6 --out data/local/tt-track/sheet.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from flight.video import frames, probe


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("track", type=Path)
    ap.add_argument("--labels", type=Path, nargs="*", default=[Path("evals/labels/ttclips-manual.json")])
    ap.add_argument("--cam", default="side")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    info = probe(a.clip)
    W, H = 640, 360
    sx, sy = W / info.w, H / info.h
    rows = {r["seq"]: r for r in map(json.loads, a.track.read_text("utf8").splitlines())}
    labels = {}
    for lp in a.labels:
        for lab in json.loads(lp.read_text("utf8"))["labels"]:
            if lab["cam_id"] == a.cam and lab["status"] == "visible":
                labels[lab["seq"]] = lab
    tiles = []
    for i, (seq, _t, f) in enumerate(frames(a.clip, W, H, a.start, a.seconds)):
        if i % a.every:
            continue
        img = f.copy()
        if seq in labels:
            lab = labels[seq]
            cv2.circle(img, (int(lab["x"] * sx), int(lab["y"] * sy)), 9, (0, 255, 0), 2)
        r = rows.get(seq)
        if r and r.get("x") is not None:
            col = (0, 0, 255) if r["state"] == "observed" else (0, 255, 255)
            p = (int(r["x"] * sx), int(r["y"] * sy))
            cv2.drawMarker(img, p, col, cv2.MARKER_CROSS, 16, 2)
            cv2.putText(img, f"#{r['track_id']}", (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        cv2.putText(img, f"{seq}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        tiles.append(img)
    while len(tiles) % a.cols:
        tiles.append(np.zeros_like(tiles[0]))
    grid = np.vstack([np.hstack(tiles[i : i + a.cols]) for i in range(0, len(tiles), a.cols)])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(a.out), grid)
    print(a.out, grid.shape)


if __name__ == "__main__":
    main()
