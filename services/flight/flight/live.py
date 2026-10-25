"""Live flight: Redis `frames:{cam}` -> ball track -> measurements on `ev:flight` + Spacetime (one or more phones).

    uv run --extra blurball python -m flight.live --game <g_id | next> [--detector blurball|classical]
                                                  [--corners cam=x,y,x,y,x,y,x,y]

Per camera (role "cam"), a worker reads every frame (`trophy.framebus.FrameReader`, never a backlog; frames zoomed to
the table by the phone, D-29, are mapped back to the full view through their `crop`), runs the ball detector (BlurBall
on MPS by default, D-30; or the classical MOG2 + colour floor) and #19's gated tracker, and writes `trk:ball:{cam}`
every frame plus Spacetime `track_sample` at 10 Hz.

The seam with the engine (agreed in docs/status/a2.md): flight runs the golden sport module
`sports/table_tennis/events.py` (the same code the Droid's gate replays) on its layer-1 ball samples, live, and
publishes the events on `ev:flight`; the engine consumes them unchanged. The module is batch, so it is re-run every
`--every` seconds over the current rally segment (activity bounded by `dead.gap_s` of no moving ball): events are
published once they are `--settle` seconds old, deduplicated by their deterministic id, and the "ball lost"
`ball_dead` only when the segment closes. A `serve_toss` (D-31, `flight.serve`) is measured from the segment's first
rise and published when its strike is seen (or when the segment closes).

Calibration comes from `calib:{cam}` (the PWA's four taps; reloaded on `ctl:calib`) or `--corners`. Without a trusted
calibration every event carries `calib_untrusted` and the engine caps tiers at BETA. A camera without any calibration
is tracked but produces no events (no field geometry, no measurement).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import redis
from trophy.events import parse_event
from trophy.framebus import Crop, FrameReader
from trophy.streams import CTL_CALIB, EV_FLIGHT, EVENT_STREAM_MAXLEN, calib_key, cam_key, game_key
from trophy.tracks import BallTrackWriter
from trophy.world import ObservationWriter, SpacetimeClient, TrackSampleWriter

from . import field as F
from .calib import Camera as PoseCamera
from .calib import solve_pose
from .serve import TossParams
from .serve import estimate as estimate_toss
from .track import Tracker

log = logging.getLogger("trophy.flight")
REPO = Path(__file__).resolve().parents[3]
REF_W, REF_H = 1280, 720  # the reference view: calibration taps and every output pixel live here
SPORT = "table_tennis"
# field.json corner order (A-right, B-right, B-left, A-left) <-> the PWA's tap names
TAP_ORDER = ("A_right", "B_right", "B_left", "A_left")


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = REPO / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip()
    return {**out, **os.environ}


def jlog(msg: str, **kw: Any) -> None:
    log.info(json.dumps({"svc": "flight", "msg": msg, **kw}, default=str))


# ---------------------------------------------------------------- calibration


@dataclass
class CamCalib:
    """One camera's geometry: the module's homography view and, when solvable, the pose for the serve toss."""

    cam_id: str
    H: tuple[float, ...]
    trusted: bool
    reproj_err_px: float
    image_w: int
    image_h: int
    pose: PoseCamera | None
    source: str

    def module_camera(self, fps: float):
        from trophy_engine.sportmod.api import Camera

        return Camera(self.cam_id, self.image_w, self.image_h, self.H, self.trusted, self.reproj_err_px, fps)


def corners_from_h(H: np.ndarray) -> np.ndarray:
    """Field corners (A-right, B-right, B-left, A-left) projected to pixels through inv(H_img_to_field)."""
    Hi = np.linalg.inv(H)
    pts = np.c_[F.CORNERS_M[:, :2], np.ones(4)] @ Hi.T
    return pts[:, :2] / pts[:, 2:3]


def calib_from_json(cam_id: str, cal: dict) -> CamCalib:
    H = np.array(cal["H_img_to_field"], float).reshape(3, 3)
    size = cal.get("image_size") or {"w": REF_W, "h": REF_H}
    w, h = int(size["w"]), int(size["h"])
    try:
        pose = solve_pose(cam_id, corners_from_h(H), w, h)
    except ValueError as e:
        jlog("pose unavailable", cam_id=cam_id, why=str(e))
        pose = None
    return CamCalib(
        cam_id,
        tuple(float(v) for v in H.ravel()),
        bool(cal.get("trusted", False)),
        float(cal.get("reproj_err_px", 0.0)),
        w,
        h,
        pose,
        str(cal.get("solver", "?")),
    )


def calib_from_corners(cam_id: str, corners: list[float]) -> CamCalib:
    """--corners in the PWA's tap order (A_left, A_right, B_right, B_left), reference pixels; always untrusted."""
    taps = np.asarray(corners, float).reshape(4, 2)
    px = taps[[1, 2, 3, 0]]  # -> A-right, B-right, B-left, A-left
    H, _ = cv2.findHomography(px, F.CORNERS_M[:, :2])
    if H is None:
        raise SystemExit(f"--corners {cam_id}: degenerate")
    return calib_from_json(
        cam_id,
        {
            "H_img_to_field": (H / H[2, 2]).ravel().tolist(),
            "image_size": {"w": REF_W, "h": REF_H},
            "trusted": False,
            "solver": "flight --corners",
        },
    )


# ---------------------------------------------------------------- per-camera worker


@dataclass(frozen=True)
class View:
    """Maps a frame's pixels to reference pixels (the full view at REF_W x REF_H). A frame zoomed to the table
    (`crop`, D-29) keeps its own resolution; uncropped frames of another size are scaled."""

    crop: Crop | None
    w: int
    h: int

    def pt(self, x: float, y: float) -> tuple[float, float]:
        if self.crop is None:
            return x * REF_W / self.w, y * REF_H / self.h
        cx, cy, cw, ch = self.crop
        return (cx + x / self.w * cw) * REF_W, (cy + y / self.h * ch) * REF_H


def make_detector(kind: str, args):
    if kind == "classical":
        from .detect import ClassicalDetector

        det = ClassicalDetector(colour=args.ball)
        return det, {"model": "classical-mog2", "device": "cpu", "ep": "opencv"}
    from .blurball import BlurBallDetector, Predictor

    pred = Predictor(device=args.device)
    det = BlurBallDetector(pred, threshold=args.threshold, stride=args.stride, photometric=args.photometric)
    info = {"model": f"blurball@{pred.weights_sha256[:8]}", "device": pred.device, "ep": f"torch {pred.torch_version}"}
    return det, info


class CamWorker(threading.Thread):
    def __init__(
        self, r: redis.Redis, game_id: str, cam_id: str, sink: Analyzer, trk: TrackSampleWriter | None, args
    ) -> None:
        super().__init__(name=f"flight-{cam_id}", daemon=True)
        self.r, self.game_id, self.cam_id, self.sink, self.trk, self.args = r, game_id, cam_id, sink, trk, args
        self.stop = threading.Event()
        self.stats: dict[str, float] = {"frames": 0, "samples": 0, "fps": 0.0, "ms": 0.0, "skipped": 0, "lag_ms": 0.0}
        self.detector_info: dict[str, str] = {}
        self.t_last = 0.0  # game time of the newest frame

    def run(self) -> None:
        reader = FrameReader(self.r, self.cam_id, mode="all", max_lag=45)
        balls = BallTrackWriter(self.r, self.cam_id)
        det, self.detector_info = make_detector(self.args.detector, self.args)
        jlog("detector", cam_id=self.cam_id, **self.detector_info)
        tracker = Tracker()
        view: View | None = None
        t_win, n_win = time.monotonic(), 0
        last_seq: int | None = None
        while not self.stop.is_set():
            f = reader.read(block_ms=200)
            if f is None:
                continue
            t0 = time.perf_counter()
            img = cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            v = View(f.crop, img.shape[1], img.shape[0])
            gap = last_seq is not None and f.seq != last_seq + 1
            if v != view or gap:  # new geometry, or dropped frames: the track (and BlurBall's window) restart
                tracker, view = Tracker(), v
                if hasattr(det, "reset"):
                    det.reset()
            last_seq = f.seq
            self.t_last = f.t_game_s
            if self.args.detector == "classical":
                resolved = [{"frame": f.seq, "t_s": f.t_game_s, "candidates": det(img)}]
            else:
                resolved = det.push(f.seq, f.t_game_s, img)
            for fr in resolved:
                for c in fr["candidates"]:  # the tracker works in reference pixels
                    c["xy_px"] = list(v.pt(*c["xy_px"]))
                tracker.step(fr["frame"], fr["t_s"], fr["candidates"])
            got = {s["frame"]: s for s in tracker.drain()}
            tracker.out.clear()  # the live loop keeps its own buffer
            for fr in resolved:
                s = got.pop(fr["frame"], None)
                self._write(balls, fr["frame"], fr["t_s"], s)
            for s in got.values():  # a promotion back-filled earlier frames
                self._write(balls, s["frame"], s["t_s"], s)
            self.stats["frames"] += 1
            n_win += 1
            self.stats["ms"] = 0.9 * self.stats["ms"] + 0.1 * (time.perf_counter() - t0) * 1000
            self.stats["skipped"] = reader.skipped
            self.stats["lag_ms"] = time.time() * 1000 - f.t_srv_ms
            now = time.monotonic()
            if now - t_win >= 2:
                self.stats["fps"] = n_win / (now - t_win)
                t_win, n_win = now, 0

    def _write(self, balls: BallTrackWriter, seq: int, t_s: float, s: dict | None) -> None:
        if s is None:
            balls.write({"t_game_s": t_s, "seq": seq, "px": None, "conf": 0.0})
            self.sink.tick(self.cam_id, t_s)
            return
        xy = [round(s["xy_px"][0], 1), round(s["xy_px"][1], 1)]
        rec: dict[str, Any] = {"t_game_s": t_s, "seq": seq, "px": xy, "conf": round(s["conf"], 3)}
        if s.get("L_px") is not None:
            rec["blur_len_px"] = round(float(s["L_px"]), 1)
            rec["blur_angle_rad"] = round(math.radians(float(s.get("theta_deg") or 0.0)), 3)
        balls.write(rec)
        if self.trk is not None:
            self.trk.post(self.game_id, self.cam_id, t_s, px=xy, conf=rec["conf"])
        self.stats["samples"] += 1
        self.sink.add(self.cam_id, t_s, seq, xy[0], xy[1], s["conf"])


# ---------------------------------------------------------------- the module seam


class Analyzer:
    """All cameras' samples -> the sport module, re-run over the open rally segment; new events out, once."""

    def __init__(self, r: redis.Redis, game_id: str, obs: ObservationWriter | None, args) -> None:
        from trophy_engine.sportmod.loader import load_module

        self.r, self.game_id, self.obs, self.args = r, game_id, obs, args
        self.mod = load_module(args.module)
        self.gap_s = float(self.mod.config["dead"]["gap_s"])
        self.min_conf = float(self.mod.config["capture"]["min_conf"])
        self.lock = threading.Lock()
        self.samples: dict[str, list[tuple[float, int, float, float, float]]] = {}  # cam -> (t, seq, u, v, conf)
        self.t_now: dict[str, float] = {}
        self.wall_last = time.monotonic()
        self.calib: dict[str, CamCalib] = {}
        self.seg_start: float | None = None
        self.last_move: float | None = None
        self.sent: set[str] = set()
        self.sent_tt: list[tuple[str, float]] = []  # (type, t) published, to absorb a refined event's new id
        self.toss_done = False
        self.toss_cut: float | None = None
        t0 = r.hget(game_key(game_id), "t0_ms")
        self.t0_ms = float(t0) if t0 else None
        self.latency_ms: list[float] = []
        self.n_events = 0

    # -- input
    def set_calib(self, c: CamCalib) -> None:
        with self.lock:
            self.calib[c.cam_id] = c
        jlog(
            "calibration",
            cam_id=c.cam_id,
            trusted=c.trusted,
            solver=c.source,
            pose=c.pose is not None,
            f_px=round(float(c.pose.K[0, 0])) if c.pose else None,
        )

    def tick(self, cam_id: str, t_s: float) -> None:
        with self.lock:
            self.wall_last = time.monotonic()
            self.t_now[cam_id] = max(t_s, self.t_now.get(cam_id, t_s))

    def add(self, cam_id: str, t_s: float, seq: int, u: float, v: float, conf: float) -> None:
        with self.lock:
            self.wall_last = time.monotonic()
            buf = self.samples.setdefault(cam_id, [])
            prev = buf[-1] if buf else None
            buf.append((t_s, seq, u, v, conf))
            self.t_now[cam_id] = max(t_s, self.t_now.get(cam_id, t_s))
            moving = prev is not None and 0 < t_s - prev[0] < 0.2 and math.hypot(u - prev[2], v - prev[3]) > 4.0
            if moving:
                if self.seg_start is None:
                    self.seg_start = prev[0]
                    self.toss_done = False
                    self.toss_cut = None
                self.last_move = t_s
            horizon = t_s - 60.0
            if buf[0][0] < horizon:
                self.samples[cam_id] = [s for s in buf if s[0] >= horizon]

    # -- analysis
    def step(self) -> None:
        with self.lock:
            if self.seg_start is None or not self.calib or not self.t_now:
                return
            now = min(self.t_now.values()) if len(self.t_now) > 1 else next(iter(self.t_now.values()))
            closing = self.last_move is not None and now - self.last_move >= self.gap_s
            if not closing and self.last_move is not None and time.monotonic() - self.wall_last > self.gap_s + 1.0:
                closing = True  # every camera stopped streaming: close on the wall clock
            t_lo = self.seg_start - 0.1
            t_hi = self.last_move + 0.05 if closing else now
            seg = {c: [s for s in ss if t_lo <= s[0] <= t_hi] for c, ss in self.samples.items() if c in self.calib}
            calib = dict(self.calib)
            seg_start = self.seg_start
            if closing:
                self.seg_start = None
        if not self.toss_done:
            self._serve_toss(calib, seg_start, final=closing)
        # The toss belongs to the serve measurement: the module would read its release (the lowest point before the
        # rise) as a bounce, off the table, i.e. a floor bounce that ends the rally. Hold the module's events while
        # a toss may still resolve (`--toss-hold` s into the segment), then drop the toss's samples.
        if not self.toss_done and not closing and now - seg_start < self.args.toss_hold:
            return
        if self.toss_cut is not None:
            seg = {c: [x for x in ss if x[0] >= self.toss_cut] for c, ss in seg.items()}
        events = self._run_module(seg, calib)
        settle = now - self.args.settle
        for ev in events:
            if ev["type"] == "ball_dead" and (ev.get("payload") or {}).get("reason") == "lost" and not closing:
                continue
            if not closing and ev["t_game_s"] > settle:
                continue
            self._publish(ev)
        if closing:
            self.toss_cut = None
        if closing:
            jlog("segment closed", t0=round(seg_start, 2), t1=round(t_hi, 2))

    def _run_module(self, seg: dict, calib: dict[str, CamCalib]) -> list[dict]:
        from trophy_engine.sportmod.api import BallSample

        obs: list[Any] = []
        for c in calib.values():
            obs.append(c.module_camera(self.args.fps))
        for cam_id, ss in seg.items():
            obs += [BallSample(cam_id, t, seq, (u, v), conf) for t, seq, u, v, conf in ss if conf >= self.min_conf]
        trusted = all(c.trusted for c in calib.values())
        try:
            return list(self.mod.events(obs, self.mod.state(self.game_id, calib_trusted=trusted)))
        except Exception as e:  # a module bug must not stop the tracker
            jlog("module error", error=f"{type(e).__name__}: {e}")
            return []

    def _serve_toss(self, calib: dict[str, CamCalib], seg_start: float, final: bool) -> None:
        # the camera with a pose that saw the most of the toss; the palm phase sits just before the segment start
        best = None
        for cam_id, c in calib.items():
            if c.pose is None:
                continue
            with self.lock:
                ss = [s for s in self.samples.get(cam_id, []) if seg_start - 2.0 <= s[0] <= seg_start + 3.0]
            if len(ss) > (len(best[1]) if best else 0):
                best = (c, ss)
        if best is None:
            return
        c, ss = best
        pay = estimate_toss([(t, u, v) for t, _q, u, v, _c in ss], c.pose, TossParams(), calib_trusted=c.trusted)
        if pay is None or (pay.get("contact") is None and not final):
            return
        self.toss_done = True
        if pay.get("contact") is not None:
            self.toss_cut = float(pay["contact"]["t0_s"])  # the module sees the ball from the strike on
        debug = pay.pop("_debug", {})
        t_ev = (pay.get("contact") or pay["apex"])["t_s"]
        ev = {
            "schema": "trophy.event.v1",
            "id": _ulid(),
            "game_id": self.game_id,
            "t_game_s": round(t_ev, 4),
            "sport": SPORT,
            "type": "serve_toss",
            "source": "flight",
            "cams": [c.cam_id],
            "conf": 0.9 if "release" not in pay["evidence_missing"] else 0.6,
            "side": pay["server_side"],
            "payload": pay,
        }
        jlog(
            "serve_toss",
            height_cm=round(pay["height_m"] * 100, 1),
            sigma_cm=round(pay["sigma_height_m"] * 100, 1),
            angle_deg=round(math.degrees(pay["angle_from_vertical_rad"]), 1),
            missing=pay["evidence_missing"],
            **debug,
        )
        self._publish(ev)

    def _publish(self, ev: dict) -> None:
        if ev["id"] in self.sent:
            return
        t = float(ev["t_game_s"])
        if ev["type"] != "serve_toss" and any(k == ev["type"] and abs(t - tt) < 0.1 for k, tt in self.sent_tt):
            return  # the same event, refined by more samples into a new deterministic id
        self.sent.add(ev["id"])
        self.sent_tt = [x for x in self.sent_tt if t - x[1] < 30] + [(ev["type"], t)]
        try:
            e = parse_event(ev)
        except Exception as err:
            jlog("event rejected by contract", type=ev.get("type"), error=str(err)[:300])
            return
        data = e.model_dump_json(exclude_none=True)
        self.r.xadd(EV_FLIGHT, {"json": data}, maxlen=EVENT_STREAM_MAXLEN, approximate=True)
        if self.obs is not None:
            self.obs.post(json.loads(data))
        self.n_events += 1
        lat = None
        if self.t0_ms is not None:
            lat = time.time() * 1000 - (self.t0_ms + t * 1000)
            self.latency_ms.append(lat)
            self.latency_ms = self.latency_ms[-500:]
        jlog("event", type=ev["type"], t=round(t, 3), side=ev.get("side"), latency_ms=round(lat) if lat else None)


def _ulid() -> str:
    from trophy.ids import new_ulid

    return new_ulid()


# ---------------------------------------------------------------- main


def cameras(r: redis.Redis, game_id: str) -> list[str]:
    out = []
    for k in r.scan_iter("cam:*"):
        h = r.hgetall(k)
        if h.get(b"game_id", b"").decode() == game_id and "cam" in h.get(b"role", b"").decode().split(","):
            out.append(k.decode().split(":", 1)[1])
    return sorted(out)


def wait_for_game(r: redis.Redis) -> str:
    started = time.time() * 1000
    while True:
        newest = max(
            (
                (float(r.hget(k, "created_at_ms") or r.hget(k, "t0_ms") or 0), k.decode().split(":", 1)[1])
                for k in r.scan_iter("game:*")
            ),
            default=(0.0, ""),
        )
        if newest[0] > started:
            return newest[1]
        time.sleep(0.5)


def heartbeat(r: redis.Redis, game_id: str, cam_id: str, w: CamWorker) -> None:
    ev = {
        "schema": "trophy.event.v1",
        "id": _ulid(),
        "game_id": game_id,
        "t_game_s": round(w.t_last, 3),
        "sport": SPORT,
        "type": "heartbeat",
        "source": "flight",
        "cams": [cam_id],
        "conf": 1.0,
        "payload": {
            "service": "flight",
            "fps": round(w.stats["fps"], 1),
            "lag_ms": round(w.stats["lag_ms"], 1),
            "model": w.detector_info.get("model", "?"),
            "device": w.detector_info.get("device", "?"),
            "ep": w.detector_info.get("ep", "?"),
        },
    }
    try:
        r.xadd(
            EV_FLIGHT,
            {"json": parse_event(ev).model_dump_json(exclude_none=True)},
            maxlen=EVENT_STREAM_MAXLEN,
            approximate=True,
        )
    except Exception as e:
        jlog("heartbeat rejected", error=str(e)[:200])


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True, help='a game id, or "next" for the next game created')
    ap.add_argument("--detector", choices=["blurball", "classical"], default="blurball")
    ap.add_argument("--ball", default="white", help="classical colour model: white | orange")
    ap.add_argument("--device", default="auto", help="blurball: auto | mps | cpu")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--photometric", choices=["rgb", "maxgray"], default="rgb")
    ap.add_argument("--module", type=Path, default=REPO / "sports" / SPORT)
    ap.add_argument("--corners", action="append", default=[], help="cam_id=x,y,... (A_left, A_right, B_right, B_left)")
    ap.add_argument("--every", type=float, default=0.1, help="seconds between module runs")
    ap.add_argument("--settle", type=float, default=0.2, help="publish events once they are this old (game s)")
    ap.add_argument("--toss-hold", type=float, default=1.5, help="hold module events this long for a serve toss")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--no-spacetime", action="store_true", help="Redis only (tests, or without a vision token)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    a = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    env = _env()
    r = redis.Redis.from_url(env.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    if a.game == "next":
        a.game = wait_for_game(r)
        jlog("attached", game_id=a.game)
    if not r.exists(game_key(a.game)):
        raise SystemExit(f"no game {a.game} in Redis")
    obs = trk = None
    if not a.no_spacetime:
        token = env.get("SPACETIME_VISION_TOKEN", "")
        if not token:
            jlog("no SPACETIME_VISION_TOKEN: Redis only")
        else:
            client = SpacetimeClient(uri=env.get("SPACETIME_URI"), module=env.get("SPACETIME_MODULE"), token=token)
            obs, trk = ObservationWriter(client), TrackSampleWriter(client)
    an = Analyzer(r, a.game, obs, a)
    fixed = {}
    for spec in a.corners:
        cam, _, xs = spec.partition("=")
        fixed[cam] = calib_from_corners(cam, [float(v) for v in xs.split(",")])
        an.set_calib(fixed[cam])

    def load_calib(cam_id: str) -> None:
        if cam_id in fixed:
            return
        raw = r.get(calib_key(cam_id))
        if raw:
            try:
                an.set_calib(calib_from_json(cam_id, json.loads(raw)))
            except (KeyError, ValueError, np.linalg.LinAlgError) as e:
                jlog("bad calibration", cam_id=cam_id, error=str(e))

    def calib_listener() -> None:
        ps = r.pubsub()
        ps.subscribe(CTL_CALIB)
        for m in ps.listen():
            if m.get("type") == "message":
                cam = m["data"].decode() if isinstance(m["data"], bytes) else str(m["data"])
                if cam in workers:
                    load_calib(cam)

    workers: dict[str, CamWorker] = {}
    threading.Thread(target=calib_listener, daemon=True).start()
    last_beat = 0.0
    try:
        while True:
            for cam in cameras(r, a.game) + [c for c in fixed if c not in workers]:
                if cam not in workers:
                    load_calib(cam)
                    w = CamWorker(r, a.game, cam, an, trk, a)
                    w.start()
                    workers[cam] = w
                    jlog("camera", cam_id=cam, fps_in=(r.hget(cam_key(cam), "fps_in") or b"").decode() or None)
            an.step()
            now = time.monotonic()
            if now - last_beat >= 5:
                last_beat = now
                lat = sorted(an.latency_ms)
                for cam, w in workers.items():
                    heartbeat(r, a.game, cam, w)
                    jlog(
                        "stats",
                        cam_id=cam,
                        **{k: round(v, 1) for k, v in w.stats.items()},
                        events=an.n_events,
                        latency_p50_ms=round(lat[len(lat) // 2]) if lat else None,
                        latency_p95_ms=round(lat[int(len(lat) * 0.95)]) if lat else None,
                    )
            time.sleep(a.every)
    except KeyboardInterrupt:
        pass
    finally:
        for w in workers.values():
            w.stop.set()
        if obs is not None:
            obs.close()
        if trk is not None:
            trk.close()


if __name__ == "__main__":
    main()
