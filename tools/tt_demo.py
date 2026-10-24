#!/usr/bin/env python3
"""Local-only evidence demo server. No footage or credentials leave this host."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import mimetypes
import os
import re
import sys
import tempfile
import threading
import uuid
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


referee = load("tt_referee", ROOT / "services/flight/referee.py")


def synthetic_session():
    """Fixture truth never becomes real-video detector output."""
    cases = [
        ("Low toss", 0.12, 10, 0.005, 1),
        ("16 cm boundary", 0.16, 0, 0, 0),
        ("Angle above 30°", 0.23, 40, 0.005, 1),
        ("30° boundary", 0.23, 30, 0, 0),
        ("Height uncertain", 0.16, 10, 0.02, 1),
        ("Missing release", None, None, None, None),
        ("Angle uncertain", 0.23, 30, 0.005, 2),
    ]
    points = []
    frames = []
    for i, (label, height, angle, dh, da) in enumerate(cases):
        start = i * 4
        measurement = dict(
            height_interval_m=[height - dh, height + dh] if height else None,
            angle_interval_deg=[angle - da, angle + da] if angle is not None else None,
            calibrated=True,
            release_observed=height is not None,
            timing_validated=True,
            measurement_validated=True,
        )
        assessment = referee.assess_serve(**measurement)
        points.append(
            dict(
                id=f"synthetic-{i + 1}",
                label=label,
                start_s=start,
                end_s=start + 3.5,
                evidence_s=start + 1,
                status=assessment["status"],
                reason=label + " — synthetic known geometry",
                kind="serve_toss",
                server="A",
                assessment=assessment,
                measurement=measurement,
                evidence_origin="synthetic_fixture",
                rule_ref="2.6.2 / TTR 30° review criterion",
                height_m=height,
                rise_angle_deg=angle,
                winner="B" if assessment["status"] == "toss_fault_supported" else None,
            )
        )
        for j in range(120):
            t = j / 30
            pos = None
            if height is not None and 0.5 <= t <= 1.5:
                u = t - 0.5
                z = height * 4 * u * (1 - u)
                # Upward chord matches configured angle. Descent is separate.
                x = math.tan(math.radians(angle)) * height * min(1, u * 2)
                pos = [-1.7 + x, 0, 1.05 + z]
            frames.append(dict(t=start + t, players=[], ball=dict(position=pos, status="synthetic_truth")))
    return dict(
        id="g_syntt001",
        label="Synthetic threshold laboratory",
        synthetic=True,
        recorded=False,
        duration_s=len(cases) * 4,
        cameras=[],
        points=points,
        sync=dict(method="Synthetic truth clock", offset_s=0, uncertainty_s=0, verified=True),
        calibration=dict(trusted=True, status="Known synthetic geometry — not real-world calibration"),
        scene=dict(frames=frames, status="Synthetic known geometry; no video/model inference"),
        limitations=[
            "Synthetic demonstrations test geometry and deterministic rule behavior; "
            "they establish no accuracy on real footage.",
            "Passing height and angle does not establish full service legality.",
            "Release-to-apex chord angle is an implementation convention, "
            "not a verified official technical definition.",
        ],
        provenance=dict(footage="Generated mathematical fixtures; no original video", profile=referee.PROFILE),
        benchmark={},
    )


class Demo:
    def __init__(self, directory):
        self.directory = directory
        self.lock = threading.RLock()
        self.states = {k: referee.Referee() for k in ("recorded", "synthetic")}
        self.audit = directory / "review-audit.jsonl"
        self.reviews = {}
        self.requests = {}
        self.sync_override = None
        if self.audit.exists():
            for i, line in enumerate(self.audit.read_text().splitlines()):
                row = json.loads(line)
                row.setdefault("event_id", f"legacy-audit-{i}")
                self.apply(row, persist=False)

    def session(self, dataset):
        if dataset == "synthetic":
            return synthetic_session()
        p = self.directory / "session.json"
        if not p.exists():
            raise ValueError("Build recordings first: python tools/build_tt_demo.py")
        d = json.loads(p.read_text())
        if self.sync_override is not None:
            d["sync"]["offset_s"] = self.sync_override
            d["sync"]["method"] = "Manual playback offset; capture timing unverified"
            d["sync"]["verified"] = False
            d["cameras"][1]["offset_s"] = self.sync_override
            for r in d["cameras"][1]["frames"]:
                r["t_game_s"] = (r["t_source_s"] - self.sync_override) / d["cameras"][1].get("drift", 1)
        scene = self.directory / "scene.json"
        if scene.exists():
            d["scene"] = json.loads(scene.read_text())
        for p in d["points"]:
            if p["id"] in self.reviews:
                p.update(self.reviews[p["id"]])
        return d

    def apply(self, row, persist=True):
        """Apply one audited action. A retry must reuse its explicit event_id.

        New calls without an ID get a random ID, persisted in the audit. This
        allows A -> B -> A corrections with the same reason. IDs are scoped by
        dataset; reuse with a conflicting payload is rejected before mutation.
        """
        if not isinstance(row, dict):
            raise ValueError("Request must be an object")
        row = deepcopy(row)
        dataset = row.get("dataset", "recorded")
        if dataset not in self.states:
            raise ValueError("Unknown dataset")
        row["dataset"] = dataset
        action = row.get("action")
        if action not in ("sync", "resolve", "challenge"):
            raise ValueError("Unknown action")
        rally = row.get("rally_id")
        if action != "sync" and (not isinstance(rally, str) or not rally or len(rally) > 200):
            raise ValueError("Need a nonempty rally_id of at most 200 characters")
        event_id = row.setdefault("event_id", "request-" + uuid.uuid4().hex)
        if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
            raise ValueError("Need a nonempty event_id of at most 200 characters")
        if action == "resolve":
            row.setdefault("kind", "point")
            row["reason"] = str(row.get("reason") or "Player resolution after source-video review")[:500]
        # Encoding also rejects NaN before state or audit can change.
        encoded = json.dumps(row, allow_nan=False, sort_keys=True)
        request_key = (dataset, event_id)
        if request_key in self.requests:
            if self.requests[request_key] != encoded:
                raise ValueError("event_id was already used for a different action")
            return self.states[dataset].snapshot()
        if any(c["event_id"] == event_id for c in self.states[dataset].snapshot()["history"]):
            raise ValueError("event_id conflicts with an existing referee event")
        before = deepcopy((self.states, self.reviews, self.sync_override, self.requests))
        try:
            result = self._apply_action(row)
            if persist:
                # Replace the small local audit atomically, so an interrupted
                # append cannot leave a partial JSON line that breaks restart.
                previous = self.audit.read_bytes() if self.audit.exists() else b""
                pending = None
                try:
                    with tempfile.NamedTemporaryFile(dir=self.directory, prefix=".review-audit-", delete=False) as f:
                        pending = Path(f.name)
                        f.write(previous + encoded.encode() + b"\n")
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(pending, self.audit)
                finally:
                    if pending and pending.exists():
                        pending.unlink()
            self.requests[request_key] = encoded
            return result
        except Exception:
            self.states, self.reviews, self.sync_override, self.requests = before
            raise

    def _apply_action(self, row):
        dataset = row["dataset"]
        state = self.states[dataset]
        action = row["action"]
        rally = row.get("rally_id")
        if action == "sync":
            value = row["offset_s"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or abs(value) > 20
            ):
                raise ValueError("Offset must be finite and within ±20 seconds")
            self.sync_override = value
        elif action == "resolve":
            if row.get("kind", "point") not in ("point", "let"):
                raise ValueError("Unknown resolution kind")
            winner = None if row.get("kind") == "let" else row.get("winner")
            if row.get("kind", "point") == "point" and winner not in ("A", "B"):
                raise ValueError("Choose A or B")
            reason = str(row.get("reason") or "Player resolution after source-video review")[:500]
            event_id = row["event_id"]
            existing = next((c for c in state.snapshot()["calls"] if c["rally_id"] == rally), None)
            if existing and existing["status"] in ("point", "let"):
                state.correct(rally, winner, event_id, reason)
            else:
                state.resolve(rally, winner, event_id, reason)
            if dataset == "recorded":
                self.reviews[rally] = dict(
                    status="manually_resolved",
                    winner=winner,
                    reason=reason,
                    evidence_origin="player_resolution",
                    review_status="resolved",
                )
        elif action == "challenge":
            state.submit(
                dict(
                    event_id=row["event_id"],
                    rally_id=rally,
                    type="ambiguous",
                    reason="Challenge opened. Source views need review.",
                )
            )
            if dataset == "recorded":
                self.reviews.setdefault(rally, {}).update(
                    review_status="requested",
                    review_reason="Challenge opened. Source views need review; any prior decision stands.",
                )
        else:
            raise ValueError("Unknown action")
        return state.snapshot()

    def advance(self, dataset, t):
        if dataset not in self.states:
            raise ValueError("Unknown dataset")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
            raise ValueError("Need finite playback time")
        state = self.states[dataset]
        calls = []
        if dataset == "synthetic":
            for p in synthetic_session()["points"]:
                if p["end_s"] <= t and p["assessment"]["status"] == "toss_fault_supported":
                    before = len(state.snapshot()["history"])
                    call = state.submit(
                        dict(
                            event_id="fixture-" + p["id"],
                            rally_id=p["id"],
                            type="serve_toss",
                            evidence=dict(
                                verified=True,
                                trigger="incorrect_service",
                                offender="A",
                                refs=["synthetic_truth:" + p["id"]],
                            ),
                        )
                    )
                    if len(state.snapshot()["history"]) > before:
                        calls.append(call)
        return dict(state=state.snapshot(), newly_calls=calls)


def handler(demo):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TrophyLocal/1.0"

        def log_message(self, *args):
            pass

        def json(self, data, status=200):
            raw = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            try:
                host = urlparse("//" + self.headers.get("Host", ""))
                return (
                    host.hostname in ("127.0.0.1", "localhost", "::1") and (host.port or 80) == self.server.server_port
                )
            except ValueError:
                return False

        def do_GET(self):
            try:
                if not self.valid_host():
                    return self.json({"error": "Local host required"}, 403)
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)
                dataset = query.get("dataset", ["recorded"])[0]
                if dataset not in demo.states:
                    return self.json({"error": "Unknown dataset"}, 400)
                with demo.lock:
                    if path == "/api/session":
                        return self.json(demo.session(dataset))
                    if path == "/api/synthetic":
                        return self.json(demo.session("synthetic"))
                    if path == "/api/state":
                        return self.json(demo.states[dataset].snapshot())
                    if path == "/healthz":
                        return self.json(
                            dict(
                                ok=True,
                                recordings=(demo.directory / "session.json").exists(),
                                shared_state="local durable audit; Spacetime not connected",
                            )
                        )
                if path.startswith("/media/"):
                    name = path[len("/media/") :]
                    if name not in ("side.mp4", "diagonal.mp4"):
                        return self.send_error(404)
                    return self.file(demo.directory / name)
                if path.startswith("/original/"):
                    files = {"side": "Adobe Express - IMG_4342.mp4", "diagonal": "IMG_2865 (1).mov"}
                    name = path[len("/original/") :]
                    if name not in files:
                        return self.send_error(404)
                    return self.file(ROOT / "data/ttClips" / files[name])
                file = (ROOT / "apps/tt-demo" / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
                if not file.is_relative_to(ROOT / "apps/tt-demo"):
                    return self.send_error(403)
                return self.file(file)
            except (ValueError, KeyError) as e:
                self.json({"error": str(e)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except FileNotFoundError:
                self.json({"error": "File not ready. Run tools/build_tt_demo.py first."}, 404)

        def file(self, path):
            if not path.is_file():
                return self.send_error(404)
            size = path.stat().st_size
            start, end = 0, size - 1
            status = 200
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                if not match or len(requested) > 128:
                    return self.range_error(size)
                a, b = match.groups()
                if a:
                    start = int(a)
                    end = min(size - 1, int(b)) if b else size - 1
                elif b:
                    start = max(0, size - int(b))
                else:
                    return self.range_error(size)
                if start >= size or start > end:
                    return self.range_error(size)
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def range_error(self, size):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            try:
                if not self.valid_host():
                    return self.json({"error": "Local host required"}, 403)
                # Local page may mutate only from this origin. No wildcard CORS.
                origin = self.headers.get("Origin")
                if origin and (
                    urlparse(origin).scheme not in ("http", "https")
                    or urlparse(origin).netloc != self.headers.get("Host")
                ):
                    return self.json({"error": "Cross-origin writes refused"}, 403)
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 65536:
                    return self.json({"error": "Invalid request length"}, 400)
                row = json.loads(self.rfile.read(length))
                if not isinstance(row, dict):
                    raise ValueError("Request must be an object")
                action = urlparse(self.path).path.removeprefix("/api/")
                with demo.lock:
                    if action == "calibrate":
                        cal = load("tt_calibration", ROOT / "services/courtcam-adapter/calibration.py")
                        return self.json(cal.calibrate(row))
                    if action == "advance":
                        return self.json(demo.advance(row.get("dataset", "recorded"), row.get("t_game_s")))
                    if action not in ("resolve", "challenge", "sync"):
                        return self.json({"error": "Unknown route"}, 404)
                    if action in ("resolve", "challenge") and not any(
                        p["id"] == row.get("rally_id") for p in demo.session(row.get("dataset", "recorded"))["points"]
                    ):
                        raise ValueError("Unknown rally")
                    return self.json(demo.apply({**row, "action": action}))
            except (ValueError, KeyError, TypeError) as e:
                self.json({"error": str(e)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except OSError:
                self.json({"error": "Could not persist the action; state was not changed."}, 500)

    return Handler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--directory", type=Path, default=ROOT / "data/local/tt-demo")
    a = p.parse_args()
    a.directory.mkdir(parents=True, exist_ok=True)
    demo = Demo(a.directory)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler(demo))
    print(f"Trophy two-camera demo: http://127.0.0.1:{a.port}/ (local recordings only)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
