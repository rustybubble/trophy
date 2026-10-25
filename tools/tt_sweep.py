"""Compare ball-detector settings on the live phone path, against labels (local footage only).

    uv run --project services/flight python tools/tt_sweep.py data/local/ttClips/side_IMG_4342.mp4 \
        --tune evals/labels/ttclips-manual.json evals/labels/ttclips-side-tune.json \
        --heldout evals/labels/ttclips-side-heldout.json --tune-until 45

Every config sees the same frames: every 2nd frame of the 60 fps clip (the phone's 30 fps), round-tripped through a
4:2:0 JPEG (`--quality`, default 70, the PWA's 0.7), with the table region and the guarded online colour learner as in
flight.live. Settings are chosen on the tuning segment (t < --tune-until) and only reported on the held-out one.

`--zoom-capture 1080|2160` streams only the table region (the PWA's table crop, D-29) from a phone capture of that
height, at most 1280 px wide (never upscaled); positions are mapped back to source pixels for scoring.

Per segment: visible labels found (observed within the labels' tolerance), wrong (observed farther away) and missing;
false positives = observed on frames labelled "none" (no ball visible) or "held" (ball in a hand, not in play);
within-track jumps = adjacent frames of the same track more than --jump source px apart; and track count.
"""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import cv2
import numpy as np
from flight.balltrack import Detector, LumaDetector, Tracker
from flight.colour import ColourModel, LiveLearner
from flight.table import TableTracker, find_table
from flight.video import frames, probe

W, H = 1280, 720


def table_crop(clip: Path) -> tuple[float, float, float, float]:
    for _seq, _t, bgr in frames(clip, W, H, 0.0, 3.0):
        tb = find_table(bgr)
        if tb is not None and (c := tb.stream_crop(W, H)) is not None:
            return c
    raise SystemExit("no table found to crop to")


def phone_frames(
    clip: Path, quality: int, cache: Path, crop=None, size=(W, H)
) -> list[tuple[int, float, bytes]]:
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    out = []
    for seq, t, bgr in frames(clip, size[0], size[1], crop=crop):
        if seq % 2 == 0:
            out.append((seq, t, cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(out))
    return out


CONFIGS = {  # name -> () -> (detector, learn colour online, use the table region)
    "colour strict (original defaults)": lambda: (Detector(ColourModel()), False, False),
    "colour loose (h 2-22, V>=210, S>=50)": lambda: (Detector(ColourModel(2, 22, 210, 50, 225)), False, False),
    "luma t=10": lambda: (LumaDetector(diff_t=10), True, True),
    "luma t=14": lambda: (LumaDetector(diff_t=14), True, True),
    "luma t=20": lambda: (LumaDetector(diff_t=20), True, True),
    "luma t=14 isolated": lambda: (LumaDetector(diff_t=14), True, True),
    "luma t=20 isolated": lambda: (LumaDetector(diff_t=20), True, True),
    "colour strict + guarded learner": lambda: (Detector(ColourModel()), True, False),
    "colour strict + table region": lambda: (Detector(ColourModel()), False, True),
}


def run(fr: list[tuple[int, float, bytes]], make, src: tuple[int, int], crop=None) -> tuple[dict[int, dict], float]:
    det, learn, use_roi = make()
    first = cv2.imdecode(np.frombuffer(fr[0][2], np.uint8), cv2.IMREAD_COLOR)
    fw, fh = first.shape[1], first.shape[0]
    cx, cy, cw, ch = crop or (0.0, 0.0, 1.0, 1.0)
    tr = Tracker(detector=det, fps=30.0, scale=fw / (cw * W))
    tables = TableTracker()
    learner = LiveLearner() if learn else None
    rows: dict[int, dict] = {}
    t0 = time.perf_counter()
    for k, (seq, t, buf) in enumerate(fr):
        bgr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        tb = tables.update(bgr)
        roi = tb.roi(fw, fh) if tb else None
        if learner is not None:
            m = learner.add(bgr, roi)
            if m is not None:
                tr.detector.colour, learner = m, None
        p = tr.step(k, t, bgr, roi if use_roi else None)
        r = {"t": t, "state": p.state, "track_id": p.track_id}
        if p.x is not None and p.y is not None:  # source pixels
            r["x"], r["y"] = (cx + p.x / fw * cw) * src[0], (cy + p.y / fh * ch) * src[1]
        rows[seq] = r
    return rows, (time.perf_counter() - t0) / len(fr) * 1000


def score(rows: dict[int, dict], labels: list[dict], t_range: tuple[float, float], jump: float) -> dict:
    lab = [lab for lab in labels if lab["seq"] in rows and t_range[0] <= rows[lab["seq"]]["t"] < t_range[1]]
    vis = [lab for lab in lab if lab["status"] == "visible"]
    found = wrong = 0
    for v in vis:
        r = rows[v["seq"]]
        if r["state"] == "observed":
            ok = bool(np.hypot(r["x"] - v["x"], r["y"] - v["y"]) <= 32)
            found += ok
            wrong += not ok
    fp = {s: sum(rows[x["seq"]]["state"] == "observed" for x in lab if x["status"] == s) for s in ("none", "held")}
    n = {s: sum(x["status"] == s for x in lab) for s in ("none", "held")}
    seqs = sorted(s for s in rows if t_range[0] <= rows[s]["t"] < t_range[1])
    jumps = tracks = 0
    seen = set()
    for a, b in zip(seqs, seqs[1:], strict=False):
        ra, rb = rows[a], rows[b]
        if ra["state"] == rb["state"] == "observed" and ra["track_id"] == rb["track_id"]:
            jumps += bool(np.hypot(ra["x"] - rb["x"], ra["y"] - rb["y"]) > jump)
    for s in seqs:
        if rows[s]["track_id"] is not None and rows[s]["track_id"] not in seen:
            seen.add(rows[s]["track_id"])
            tracks += 1
    return {
        "visible n": len(vis),
        "found": found,
        "wrong": wrong,
        "missing": len(vis) - found - wrong,
        "fp none": f"{fp['none']}/{n['none']}",
        "fp held": f"{fp['held']}/{n['held']}",
        "within-track jumps": jumps,
        "tracks": tracks,
        "observed %": round(100 * sum(rows[s]["state"] == "observed" for s in seqs) / max(1, len(seqs))),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("--tune", type=Path, nargs="+", required=True)
    ap.add_argument("--heldout", type=Path, nargs="+", required=True)
    ap.add_argument("--tune-until", type=float, default=45.0)
    ap.add_argument("--quality", type=int, default=70)
    ap.add_argument("--zoom-capture", type=int, choices=[1080, 2160], help="stream the table crop of this capture")
    ap.add_argument("--only", nargs="*", help="config names to run (default: all)")
    ap.add_argument("--jump", type=float, default=768.0, help="source px between adjacent 30 fps frames")
    ap.add_argument("--out", type=Path, default=Path("data/local/tt-track/sweep.json"))
    a = ap.parse_args()
    info = probe(a.clip)
    crop, size, tag = None, (W, H), f"q{a.quality}"
    if a.zoom_capture:
        crop = table_crop(a.clip)
        cap_w = a.zoom_capture * 16 // 9
        out_w = min(W, round(crop[2] * cap_w / 2) * 2)
        size, tag = (out_w, round(out_w * 9 / 16 / 2) * 2), f"{tag} zoom{a.zoom_capture}"
        print(f"table crop {[round(v, 3) for v in crop]}, streamed at {size[0]}x{size[1]}: "
              f"zoom {size[0] / (crop[2] * W):.2f}x vs the whole view at 1280x720")
    fr = phone_frames(a.clip, a.quality, Path(f"data/local/tt-track/phone_{tag.replace(' ', '_')}_{a.clip.stem}.pkl"),
                      crop, size)
    load = lambda ps: [lab for p in ps for lab in json.loads(p.read_text("utf8"))["labels"] if lab["cam_id"] == "side"]  # noqa: E731
    tune, held = load(a.tune), load(a.heldout)
    results = json.loads(a.out.read_text("utf8")) if a.out.exists() else {}
    for name, make in CONFIGS.items():
        if a.only and name not in a.only:
            continue
        rows, ms = run(fr, make, (info.w, info.h), crop)
        res = {
            "stream": tag,
            "ms_per_frame": round(ms, 1),
            "tuning": score(rows, tune, (0, a.tune_until), a.jump),
            "heldout": score(rows, held, (a.tune_until, 1e9), a.jump),
        }
        results[f"{name} {tag}"] = res
        print(f"{name} {tag}: {json.dumps(res)}", flush=True)
        a.out.write_text(json.dumps(results, indent=1), "utf8")


if __name__ == "__main__":
    main()
