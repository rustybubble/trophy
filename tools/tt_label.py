"""Candidate-assisted labelling sheets for the ball tracker eval (local footage only).

    uv run --project services/flight python tools/tt_label.py data/local/ttClips/side_IMG_4342.mp4 \
        --from 50 --to 107 --every 0.5 --out data/local/tt-label/heldout

For each sampled frame (on even source frames, i.e. the 30 fps phone phase), every plausible ball candidate from a
permissive union of detectors (luma three-frame motion blobs + loose orange blobs, 1280x720) is numbered on a crop of
the table region. A reviewer then writes, per frame, the candidate number that is the ball in play, or "held" (the
ball is visible but at rest / in a hand), "none" (no ball visible), or "miss x,y" (the ball is visible but not
marked; position in working px read off the grid). `--build` turns those answers into evals/labels JSON with the
candidate centroids scaled to source pixels. Labels made this way are assisted by the candidates; say so when
reporting them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from flight.balltrack import LumaDetector
from flight.table import TableTracker
from flight.video import frames, probe

W, H = 1280, 720


def orange_blobs(cur: np.ndarray, roi: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = roi
    hsv = cv2.cvtColor(cur[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] <= 25) & (hsv[..., 1] >= 40) & (hsv[..., 2] >= 200)
    n, _, st, cen = cv2.connectedComponentsWithStats(cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)), 8)
    return [
        (float(cen[k][0] + x0), float(cen[k][1] + y0))
        for k in range(1, n)
        if 4 <= st[k][4] <= 400 and max(st[k][2], st[k][3]) <= 48
    ]


def sheets(a: argparse.Namespace) -> None:
    info = probe(a.clip)
    a.out.mkdir(parents=True, exist_ok=True)
    want = {int(round(t * info.fps)) // 2 * 2 for t in np.arange(a.t0, a.t1, a.every)}
    det = LumaDetector(diff_t=10)  # permissive: every moving bright blob (shake-aligned three-frame difference)
    tables = TableTracker(every=5)
    items, tiles = [], []
    for seq, _t, bgr in frames(a.clip, W, H, max(0.0, a.t0 - 0.5), a.t1 - a.t0 + 0.6):
        if seq % 2:
            continue  # the 30 fps phone phase
        tb = tables.update(bgr)
        x0, y0, x1, y1 = tb.roi(W, H) if tb else (0, 0, W, H)
        det.roi = (x0, y0, x1, y1)
        moving, _ = det.detect(bgr)
        if seq not in want:
            continue
        cands: list[tuple[float, float]] = []
        for c in [(m.x, m.y) for m in moving] + orange_blobs(bgr, (x0, y0, x1, y1)):
            if all(np.hypot(c[0] - o[0], c[1] - o[1]) > 6 for o in cands):
                cands.append(c)
        crop = bgr[y0:y1, x0:x1].copy()
        for gx in range((x0 // 100 + 1) * 100, x1, 100):
            cv2.line(crop, (gx - x0, 0), (gx - x0, 8), (255, 255, 255), 1)
            cv2.putText(crop, str(gx), (gx - x0 + 2, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        for gy in range((y0 // 100 + 1) * 100, y1, 100):
            cv2.line(crop, (0, gy - y0), (8, gy - y0), (255, 255, 255), 1)
            cv2.putText(crop, str(gy), (10, gy - y0 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        shown = [(i, c) for i, c in enumerate(cands) if x0 <= c[0] < x1 and y0 <= c[1] < y1]
        for i, (cx, cy) in shown:
            p = (int(cx - x0), int(cy - y0))
            cv2.circle(crop, p, 9, (255, 0, 255), 1)
            cv2.putText(crop, str(i), (p[0] + 9, p[1] - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1)
        cv2.putText(crop, f"seq {seq}  t {seq / info.fps:.2f}s", (10, crop.shape[0] - 10), 0, 0.6, (0, 255, 255), 2)
        tiles.append(crop)
        items.append({"seq": seq, "t_source_s": round(seq / info.fps, 3), "cands": [[round(v, 1) for v in c] for c in cands]})
    for k in range(0, len(tiles), 2):
        pair = tiles[k : k + 2]
        wmax = max(t.shape[1] for t in pair)
        pair = [cv2.copyMakeBorder(t, 0, 6, 0, wmax - t.shape[1], cv2.BORDER_CONSTANT, value=(40, 40, 40)) for t in pair]
        cv2.imwrite(str(a.out / f"sheet_{k // 2:03d}.png"), np.vstack(pair))
    (a.out / "candidates.json").write_text(json.dumps({"clip": a.clip.name, "fps": info.fps, "frames": items}), "utf8")
    print(f"{len(items)} frames, {len(tiles) // 2 + len(tiles) % 2} sheets in {a.out}")


def build(a: argparse.Namespace) -> None:
    info = probe(a.clip)
    sx, sy = info.w / W, info.h / H
    cand = {f["seq"]: f for f in json.loads((a.out / "candidates.json").read_text("utf8"))["frames"]}
    answers = json.loads((a.out / "answers.json").read_text("utf8"))
    labels = []
    for seq_s, ans in answers["answers"].items():
        f = cand[int(seq_s)]
        lab = {"cam_id": a.cam, "seq": f["seq"], "t_source_s": f["t_source_s"], "source_size": [info.w, info.h]}
        if ans in ("held", "none", "unsure"):
            lab["status"] = ans
        else:
            if str(ans).startswith("miss"):  # visible but not among the candidates: position read off the grid
                x, y = (float(v) for v in str(ans).split()[1].split(","))
            else:
                x, y = f["cands"][int(ans)]
            lab.update(status="visible", x=round(x * sx), y=round(y * sy))
        labels.append(lab)
    doc = {
        "schema": "trophy.ball_labels.v1",
        "reviewed_by": answers["reviewed_by"],
        "split": answers["split"],
        "method": "candidate-assisted: reviewer chose the ball among numbered candidates on 720p crops, or marked held / "
        "none / an unmarked position read off a 100 px grid (position error up to ~10 working px for those)",
        "tolerance_source_px": 32,
        "labels": sorted(labels, key=lambda lab: lab["seq"]),
    }
    a.labels.write_text(json.dumps(doc, indent=1) + "\n", "utf8")
    print(f"{len(labels)} labels -> {a.labels}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=30.0)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--build", action="store_true", help="answers.json -> labels JSON")
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--cam", default="side")
    a = ap.parse_args()
    build(a) if a.build else sheets(a)


if __name__ == "__main__":
    main()
