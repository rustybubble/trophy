#!/usr/bin/env python3
"""Export metadata-only handoff; optionally mirror via existing Spacetime writers.

No video, image bytes, manual outcome labels or illustrative poses enter this bus.
Uncalibrated detector ranking scores do not become probability-of-call confidence.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/py-trophy"))


def stable_id(value):
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    n = int.from_bytes(hashlib.sha256(value.encode()).digest()[:16], "big")
    result = ""
    for _ in range(26):
        result = alphabet[n & 31] + result
        n >>= 5
    return result


def exports(session):
    events = []
    tracks = []
    for cam in session["cameras"]:
        last_bucket = None
        last_seen = None
        lost = False
        last_heartbeat = None
        for r in cam["frames"]:
            t = r["t_game_s"]
            if t < 0 or t > session["duration_s"]:
                continue
            bucket = int(t * 10 + 1e-7)
            if bucket != last_bucket:
                tracks.append(
                    dict(
                        game_id=session["id"],
                        cam_id=cam["id"],
                        t_game_s=t,
                        object="ball",
                        px=[r["x"], r["y"]] if r["x"] is not None else None,
                        conf=0.0,
                        seq=r["seq"],
                        source_pts=r["pts"],
                        source_time_base=r["time_base"],
                        detector_score=r.get("score"),
                        detector_score_calibrated=False,
                    )
                )
                last_bucket = bucket
            if last_heartbeat is None or t - last_heartbeat >= 5:
                events.append(
                    dict(
                        schema="trophy.event.v1",
                        id=stable_id(f"{session['id']}:{cam['id']}:heartbeat:{r['seq']}"),
                        game_id=session["id"],
                        t_game_s=t,
                        sport="table_tennis",
                        type="heartbeat",
                        source="flight",
                        cams=[cam["id"]],
                        conf=1.0,
                        payload=dict(
                            service="flight-recorded",
                            **(
                                {"fps": cam["report"]["end_to_end_fps"]}
                                if cam["report"].get("end_to_end_fps") is not None
                                else {}
                            ),
                            model=cam["report"]["detector"],
                            device=cam["report"]["device"],
                            calib_untrusted=True,
                            metrics_status="offline processing FPS; not live ingestion latency",
                        ),
                    )
                )
                last_heartbeat = t
            if r["x"] is not None:
                last_seen = r
                lost = False
            elif last_seen is not None and t - last_seen["t_game_s"] > 0.8 and not lost:
                events.append(
                    dict(
                        schema="trophy.event.v1",
                        id=stable_id(f"{session['id']}:{cam['id']}:lost:{last_seen['seq']}"),
                        game_id=session["id"],
                        t_game_s=t,
                        sport="table_tennis",
                        type="ball_dead",
                        source="flight",
                        cams=[cam["id"]],
                        conf=0.0,
                        payload=dict(
                            reason="lost",
                            calib_untrusted=True,
                            interpretation=(
                                "Candidate end only. Missing detection does not establish winner or terminal contact."
                            ),
                        ),
                        evidence=[
                            dict(
                                cam_id=cam["id"],
                                seq0=last_seen["seq"],
                                seq1=r["seq"],
                                t0_s=last_seen["t_game_s"],
                                t1_s=t,
                            )
                        ],
                    )
                )
                lost = True
    return events, tracks


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, default=ROOT / "data/local/tt-demo")
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    session = json.loads((a.directory / "session.json").read_text())
    events, tracks = exports(session)
    for file, rows in [("observations.jsonl", events), ("track-samples.jsonl", tracks)]:
        (a.directory / file).write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in rows))
    if a.publish:
        if not os.environ.get("SPACETIME_VISION_TOKEN"):
            raise ValueError("SPACETIME_VISION_TOKEN required for publication")
        from trophy.events import parse_event
        from trophy.world import ObservationWriter, TrackSampleWriter

        with ObservationWriter() as observations, TrackSampleWriter() as samples:
            for row in events:
                observations.post(parse_event(row))
            for row in tracks:
                samples.post(row["game_id"], row["cam_id"], row["t_game_s"], px=row["px"], conf=row["conf"])
            if not observations.flush(30) or not samples.flush(30) or observations.errors or samples.errors:
                raise RuntimeError("Spacetime mirror incomplete; inspect service configuration, do not claim delivery")
            print(json.dumps(dict(observations_sent=observations.sent, tracks_sent=samples.sent)))
    else:
        print(
            json.dumps(
                dict(
                    observations_exported=len(events),
                    tracks_exported=len(tracks),
                    mirrored=False,
                    note="Offline metadata handoff only. Use --publish with configured Spacetime.",
                )
            )
        )


if __name__ == "__main__":
    main()
