#!/usr/bin/env python3
# ruff: noqa: E402
"""Rebuild local recorded demo from originals, preserving source-frame PTS."""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/flight"))
from flight.recording import audio_signal, estimate_sync, inspect, rally_candidates, track_clip

FILES = [("side", "Side view", "Adobe Express - IMG_4342.mp4"), ("diagonal", "Diagonal view", "IMG_2865 (1).mov")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "data/ttClips")
    parser.add_argument("--output", type=Path, default=ROOT / "data/local/tt-demo")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--detector", choices=["classical", "blurball-gray", "hybrid"], default="classical")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--skip-preview", action="store_true")
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    cameras = []
    signals = []
    for cid, label, file in FILES:
        path = a.input / file
        meta = inspect(path)
        print(json.dumps(meta), flush=True)
        target = (
            a.output / f"{cid}-tracking.json" if a.detector == "classical" else a.output / f"{cid}-{a.detector}.json"
        )
        if a.detector != "classical" and not target.exists():
            raise ValueError("Precompute the requested model tracker with tools/track_tt_blurball.py first")
        if target.exists() and (not a.force or a.detector != "classical"):
            cached = json.loads(target.read_text())
            rows, report = cached["frames"], cached["report"]
            if report.get("source_sha256") != meta["sha256"]:
                raise ValueError(
                    f"Cached tracking source mismatch for {cid}; rebuild that detector for these original bytes"
                )
        else:
            rows, report = track_clip(path, target, max_frames=a.max_frames)
        cameras.append(
            dict(
                id=cid,
                label=label,
                url=f"/media/{cid}.mp4",
                original_url=f"/original/{cid}",
                width=meta["width"],
                height=meta["height"],
                fps=meta["fps"],
                duration_s=meta["duration_s"],
                offset_s=0,
                drift=1,
                frames=rows,
                report=report,
                source=meta,
            )
        )
        signals.append(audio_signal(path))
    sync = (
        estimate_sync(*signals)
        if all(s is not None for s in signals)
        else dict(
            offset_s=0, drift=1, verified=False, uncertainty_s=None, method="No shared audio; manual offset required"
        )
    )
    cameras[1]["offset_s"] = sync["offset_s"]
    cameras[1]["drift"] = sync["drift"]
    for r in cameras[1]["frames"]:
        r["t_game_s"] = (r["t_source_s"] - sync["offset_s"]) / sync["drift"]
    boundary_rows = cameras[0]["frames"]
    if a.detector == "hybrid":
        boundary_rows = json.loads((a.output / "side-blurball-gray.json").read_text())["frames"]
    points = rally_candidates(boundary_rows)
    duration = min(cameras[0]["duration_s"], (cameras[1]["duration_s"] - sync["offset_s"]) / sync["drift"])
    session = dict(
        id="g_ttcmps01",
        label="Our table. Two phones.",
        recorded=True,
        preprocessed=True,
        duration_s=duration,
        cameras=cameras,
        sync=sync,
        teams=[dict(id="A", name="Green"), dict(id="B", name="Blue")],
        calibration=dict(trusted=False, status="Moving cameras; metric calibration not verified"),
        points=points,
        benchmark={c["id"]: c["report"] for c in cameras},
        limitations=[
            "Candidate intervals are not verified point boundaries. Ball disappearance never awards a point.",
            "Ball tracking is uncalibrated; amber fallback markers are observed color candidates, not ruling evidence.",
            "Both cameras move; fixed-camera geometry cannot establish metric toss height or edge/side contact.",
            "Audio alignment is approximate. Exposure timing, rolling shutter and acoustic travel remain unverified.",
            "Real-footage serve and edge rulings require review; synthetic threshold examples are separate.",
            (
                "Score starts at 0–0 for this local review session; actual "
                "initial match score and first server are unknown."
            ),
        ],
        provenance=dict(
            footage="User-supplied original phone recordings; local processing only; no redistribution",
            labels=(
                "Approximate development ball labels: see evals/reports; no validated real point/serve/edge accuracy"
            ),
            profile="ITTF 2026; TTR angle review profile",
            ball=report["detector"],
            model_weights_public_use="Not approved; current model-derived demo is local/private only",
            detector=a.detector,
        ),
    )
    (a.output / "session.json").write_text(json.dumps(session, allow_nan=False))
    (a.output / "footage-manifest.json").write_text(
        json.dumps(
            dict(
                acquired="2026-10-24",
                source="user-provided data/ttClips",
                usage="local development and evaluation; publication not authorized",
                split="demo/development; no held-out accuracy claim",
                files=[c["source"] for c in cameras],
                sync=sync,
            ),
            indent=2,
        )
    )
    if not a.skip_preview:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = []
            for cid, _, file in FILES:
                out = a.output / f"{cid}.mp4"
                if out.exists() and not a.force:
                    continue
                futures.append(
                    pool.submit(
                        subprocess.run,
                        [
                            ffmpeg,
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            "-i",
                            str(a.input / file),
                            "-vf",
                            "scale=1280:-2",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "veryfast",
                            "-crf",
                            "21",
                            "-pix_fmt",
                            "yuv420p",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "128k",
                            "-movflags",
                            "+faststart",
                            str(out),
                        ],
                        check=True,
                    )
                )
            for f in futures:
                f.result()
    print("Session ready:", a.output / "session.json", "sync", sync, flush=True)


if __name__ == "__main__":
    main()
