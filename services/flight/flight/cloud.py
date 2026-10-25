"""trophy-cloud: clips -> field.json + track3d.jsonl + events.json + viewer.html.

  python -m flight.cloud synth      --out DIR [--seed N]                     # synthetic two-camera rally + truth
  python -m flight.cloud frame0     --video V --out PNG                        # first frame, to read corner pixels
  python -m flight.cloud calibrate  --cam ID --video V --corners x,y,x,y,x,y,x,y [--refine] --field field.json
  python -m flight.cloud run        --field field.json --cam ID=SOURCE ... [--offset ID=s] [--ball white] --out DIR
  python -m flight.cloud eval       --out DIR --truth truth.json

SOURCE is a video (classical detector), a tracker-branch BlurBall JSON cache, or a BlurBall CSV (needs --fps).
Corner order: A-right, B-right, B-left, A-left (counter-clockwise from above; see flight.field.CORNERS_M).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from . import field as F
from .calib import Camera, refine_corners, solve_pose
from .detect import (
    ClassicalDetector,
    blurball_csv_candidates,
    blurball_json_candidates,
    first_frame,
    video_candidates,
    video_info,
)
from .events import detect_bounces, detect_dead, detect_hits, serve_toss
from .lift import fuse
from .track import Tracker

VIEWER = Path(__file__).with_name("viewer.html")


def _load_field(path: Path) -> tuple[dict, dict[str, Camera]]:
    fj = json.loads(Path(path).read_text(encoding="utf8"))
    cams = {c["cam_id"]: Camera.from_json(c) for c in fj.get("cameras", [])}
    return fj, cams


def cmd_synth(a):
    from .synth import make_dataset

    truth = make_dataset(Path(a.out), seed=a.seed, shots=a.shots)
    # a field.json calibrated from the TRUE corner pixels, as taps would give
    cams = [solve_pose(cid, c["corners_px"], c["width"], c["height"]).to_json() for cid, c in truth["cameras"].items()]
    fj = F.field_json(cams, {"sync_method": "synthetic", "skew_sigma_s": 0.012})
    fj["synthetic"] = True
    (Path(a.out) / "field.json").write_text(json.dumps(fj, indent=1), encoding="utf8")
    print(f"wrote {a.out}/side.mp4, diag.mp4, *-blurball-like.json, truth.json, field.json (SYNTHETIC)")


def cmd_frame0(a):
    cv2.imwrite(a.out, first_frame(a.video))
    info = video_info(a.video)
    print(f"wrote {a.out} ({info['width']}x{info['height']} @ {info['fps']:.2f} fps, {info['frames']} frames)")


def cmd_calibrate(a):
    px = np.array([float(v) for v in a.corners.split(",")]).reshape(4, 2)
    info = video_info(a.video)
    if a.refine:
        gray = cv2.cvtColor(first_frame(a.video), cv2.COLOR_BGR2GRAY)
        refined = refine_corners(gray, px)
        print("refine moved corners by px:", np.round(np.linalg.norm(refined - px, axis=1), 1).tolist())
        px = refined
    cam = solve_pose(a.cam, px, info["width"], info["height"], f_px=a.f_px)
    fj, _ = _load_field(a.field) if Path(a.field).exists() else (F.field_json(), {})
    fj["cameras"] = [c for c in fj.get("cameras", []) if c["cam_id"] != a.cam] + [cam.to_json()]
    fj.setdefault("time", {"sync_method": "manual_offset", "skew_sigma_s": 0.008})
    Path(a.field).write_text(json.dumps(fj, indent=1), encoding="utf8")
    print(
        f"{a.cam}: f={cam.K[0, 0]:.0f}px ({cam.f_source}), centre={np.round(cam.centre_m, 2).tolist()} m, "
        f"reproj={cam.reproj_err_px:.2f}px -> {a.field}"
    )


def _candidates(source: str, cam: Camera, a, offset: float):
    p = Path(source)
    if p.suffix.lower() == ".json":
        return blurball_json_candidates(p, offset), "blurball_json"
    if p.suffix.lower() == ".csv":
        if not a.fps:
            sys.exit("--fps is required for a BlurBall CSV")
        return blurball_csv_candidates(p, a.fps, offset), "blurball_csv"
    info = video_info(p)
    r_px = None
    if a.ball_radius_px:
        r_px = a.ball_radius_px
    else:
        # expected ball radius at the table centre's depth
        depth = float((cam.R @ np.zeros(3) + cam.t)[2])
        r_px = max(1.5, cam.K[0, 0] * F.BALL_RADIUS_M / depth)
    det = ClassicalDetector(colour=a.ball, expected_radius_px=r_px)
    return video_candidates(p, det, offset, limit=a.limit), f"classical({a.ball}, r~{r_px:.1f}px, {info['fps']:.0f}fps)"


def cmd_run(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fj, cams = _load_field(a.field)
    offsets = dict(kv.split("=") for kv in (a.offset or []))
    tracks, sources = {}, {}
    for kv in a.cam:
        cid, src = kv.split("=", 1)
        if cid not in cams:
            sys.exit(f"camera {cid} is not in {a.field}; run calibrate first")
        cands, how = _candidates(src, cams[cid], a, float(offsets.get(cid, 0.0)))
        tracks[cid] = Tracker().run(cands)
        sources[cid] = how
        print(f"{cid}: {len(tracks[cid])} tracked samples from {how}")
        (out / f"track2d-{cid}.json").write_text(json.dumps(tracks[cid]), encoding="utf8")
    skew = float(fj.get("time", {}).get("skew_sigma_s", 0.008))
    fps = a.fps or 30.0
    t3 = fuse(tracks, cams, px_sigma=a.px_sigma, skew_sigma_s=skew, fps=fps)
    with open(out / "track3d.jsonl", "w", encoding="utf8") as f:
        for r in t3:
            f.write(json.dumps(r) + "\n")
    bounces = detect_bounces(t3, cams=cams, tracks2d=tracks)
    hits = detect_hits(t3, bounces)
    dead = detect_dead(t3)
    serve = serve_toss(t3, hits)
    events = {"bounces": bounces, "hits": hits, "dead": dead, "serve_toss": serve, "sources": sources}
    (out / "events.json").write_text(json.dumps(events, indent=1), encoding="utf8")
    (out / "field.json").write_text(json.dumps(fj, indent=1), encoding="utf8")
    html = VIEWER.read_text(encoding="utf8").replace(
        "/*__DATA__*/",
        "const DATA = " + json.dumps({"field": fj, "track3d": t3, "events": events, "tracks2d": tracks}) + ";",
    )
    (out / "viewer.html").write_text(html, encoding="utf8")
    n2 = sum(r["n_views"] >= 2 for r in t3)
    sig = np.median([r["sigma_m"] for r in t3]) if t3 else float("nan")
    print(
        f"track3d: {len(t3)} samples ({n2} triangulated), median sigma {sig:.3f} m; "
        f"{len(bounces)} bounces, {len(hits)} contacts, {len(dead)} dead, serve {'yes' if serve else 'no'}"
    )
    print(f"open {out / 'viewer.html'}")


def cmd_eval(a):
    out = Path(a.out)
    truth = json.loads(Path(a.truth).read_text(encoding="utf8"))
    t3 = [json.loads(line) for line in (out / "track3d.jsonl").read_text(encoding="utf8").splitlines() if line.strip()]
    ev = json.loads((out / "events.json").read_text(encoding="utf8"))
    tt = np.array([r["t_s"] for r in truth["track"]])
    tp = np.array([r["xyz_m"] for r in truth["track"]])
    errs, sig = [], []
    for r in t3:
        i = int(np.argmin(np.abs(tt - r["t_s"])))
        if abs(tt[i] - r["t_s"]) < 0.01:
            errs.append(np.linalg.norm(np.array(r["xyz_m"]) - tp[i]))
            sig.append(r["sigma_m"])
    errs, sig = np.array(errs), np.array(sig)
    rep = {"synthetic": truth.get("synthetic", False), "n_samples": len(t3)}
    if len(errs):
        rep["track3d_err_m"] = {
            "median": float(np.median(errs)),
            "p90": float(np.percentile(errs, 90)),
            "p95": float(np.percentile(errs, 95)),
            "max": float(errs.max()),
            "within_3sigma": float(np.mean(errs < 3 * sig)),
        }
    b_err, matched = [], 0
    for tb in truth["bounces"]:
        near = [b for b in ev["bounces"] if abs(b["t_s"] - tb["t_s"]) < 0.08]
        if near:
            b = near[0]
            matched += 1
            b_err.append(float(np.hypot(b["xyz_m"][0] - tb["xyz_m"][0], b["xyz_m"][1] - tb["xyz_m"][1])))
    rep["bounces"] = {
        "truth": len(truth["bounces"]),
        "detected": len(ev["bounces"]),
        "matched_within_80ms": matched,
        "xy_err_m": {"median": float(np.median(b_err)), "max": float(max(b_err))} if b_err else None,
    }
    hm = sum(any(abs(h["t_s"] - th["t_s"]) < 0.1 for h in ev["hits"]) for th in truth["hits"])
    rep["contacts"] = {"truth": len(truth["hits"]), "detected": len(ev["hits"]), "matched_within_100ms": hm}
    if ev.get("serve_toss") and truth.get("serve", {}).get("apex"):
        th = truth["serve"]["apex"]["xyz_m"][2] - truth["serve"]["release"]["xyz_m"][2]
        rep["serve_toss"] = {"truth_height_m": th, "measured_height_m": ev["serve_toss"]["height_m"]}
    (out / "eval.json").write_text(json.dumps(rep, indent=1), encoding="utf8")
    print(json.dumps(rep, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="trophy-cloud", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synth")
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--shots", type=int, default=6)
    s.set_defaults(fn=cmd_synth)
    s = sub.add_parser("frame0")
    s.add_argument("--video", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_frame0)
    s = sub.add_parser("calibrate")
    s.add_argument("--cam", required=True)
    s.add_argument("--video", required=True)
    s.add_argument("--corners", required=True, help="8 numbers: x,y for A-right, B-right, B-left, A-left")
    s.add_argument("--refine", action="store_true", help="snap the corners to the table's edge lines")
    s.add_argument("--f-px", type=float, default=None, help="focal length in px if known (else from the homography)")
    s.add_argument("--field", default="field.json")
    s.set_defaults(fn=cmd_calibrate)
    s = sub.add_parser("run")
    s.add_argument("--field", required=True)
    s.add_argument("--cam", action="append", required=True, help="ID=SOURCE (video, BlurBall JSON or CSV)")
    s.add_argument("--offset", action="append", help="ID=seconds added to that camera's clock")
    s.add_argument("--ball", default="white", choices=["white", "orange"])
    s.add_argument("--ball-radius-px", type=float, default=None)
    s.add_argument("--fps", type=float, default=None)
    s.add_argument("--px-sigma", type=float, default=2.0)
    s.add_argument("--limit", type=int, default=None, help="frames per video (for a quick look)")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("eval")
    s.add_argument("--out", required=True)
    s.add_argument("--truth", required=True)
    s.set_defaults(fn=cmd_eval)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
