"""`python -m flight.live`: BlurBall on every live camera stream, in real time.

    uv run --directory services/flight --frozen python -m flight.live [--stride 3] [--fp32] [--device auto]

For each camera that is streaming (`frames:{cam}` on Redis, written by the gateway for phones and for recorded clips
streamed as phones alike), it decodes the JPEGs as they arrive, runs BlurBall on windows of three consecutive frames
and publishes one `BallTrackSample` per processed frame to `trk:ball:{cam}` (field `json`; interfaces-v1 §8; `px` null
when no ball was found). With the camera's calibration (`calib:{cam}`, set by the phone or the clip streamer) it also
mirrors the ball's table position into Spacetime `track_sample` at 10 Hz for the dashboard's world view.

It never processes a backlog: a camera that falls more than `--max-lag` frames behind skips to its newest frames
(counted as `skipped`). Every 5 s it logs, per camera, the processed fps, detection rate, skipped frames, model time
and the real-time lag (now minus the frame's capture time on the game clock). The engine side
(`trophy-live`, services/engine) turns the samples into bounces/contacts/dead balls with the golden sport module.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import redis
from trophy.framebus import FrameReader
from trophy.streams import calib_key, cam_key, game_key, trk_ball_key

from .blurball import BlurBall, load

ROOT = Path(__file__).resolve().parents[3]
TRK_MAXLEN = 20_000
log = logging.getLogger("flight.live")


def dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip()
    return out


def apply_h(h: list[float], u: float, v: float) -> tuple[float, float] | None:
    w = h[6] * u + h[7] * v + h[8]
    if abs(w) < 1e-9:
        return None
    return ((h[0] * u + h[1] * v + h[2]) / w, (h[3] * u + h[4] * v + h[5]) / w)


@dataclass
class Cam:
    cam_id: str
    game_id: str
    reader: FrameReader
    t0_ms: float
    buf: list = field(default_factory=list)  # (seq, t_game_s, t_srv_ms, Future[prepared]) not yet in a window
    calib_h: list[float] | None = None
    calib_size: tuple[int, int] | None = None
    last_frame_wall: float = field(default_factory=time.time)
    # stats for the current reporting interval
    n: int = 0
    det: int = 0
    lags: list = field(default_factory=list)
    skipped0: int = 0
    total: int = 0
    total_det: int = 0


class Live:
    def __init__(self, r: redis.Redis, bb: BlurBall, stride: int, max_lag: int, world) -> None:
        self.r = r
        self.bb = bb
        self.stride = stride
        self.max_lag = max_lag
        self.world = world  # TrackSampleWriter or None
        self.cams: dict[str, Cam] = {}
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="decode")
        self.last_scan = 0.0
        self.last_report = time.time()
        self.model_ms0 = 0.0
        self.calls0 = 0

    def scan(self) -> None:
        """Pick up new camera streams; drop ones silent for 10 s."""
        now = time.time()
        if now - self.last_scan < 1.0:
            return
        self.last_scan = now
        for raw in self.r.scan_iter(match="frames:*", count=200):
            key = raw.decode()
            cam_id = key.split(":", 1)[1]
            if cam_id in self.cams:
                continue
            gid = self.r.hget(cam_key(cam_id), "game_id")
            if not gid:
                continue
            newest = self.r.xrevrange(key, count=1)
            if not newest or now * 1000 - float(newest[0][0].decode().split("-")[0]) > 3000:
                continue  # an old stream: nothing live there
            gid = gid.decode()
            t0 = self.r.hget(game_key(gid), "t0_ms")
            cam = Cam(
                cam_id,
                gid,
                FrameReader(self.r, cam_id, mode="all", max_lag=self.max_lag),
                float(t0) if t0 else now * 1000,
            )
            self.load_calib(cam)
            self.cams[cam_id] = cam
            log.info(
                json.dumps(
                    {
                        "svc": "flight",
                        "msg": "camera live",
                        "cam_id": cam_id,
                        "game_id": gid,
                        "calibrated": cam.calib_h is not None,
                    }
                )
            )
        for cam_id, cam in list(self.cams.items()):
            if now - cam.last_frame_wall > 10:
                log.info(
                    json.dumps(
                        {
                            "svc": "flight",
                            "msg": "camera idle",
                            "cam_id": cam_id,
                            "frames": cam.total,
                            "detected": cam.total_det,
                        }
                    )
                )
                del self.cams[cam_id]
            elif cam.calib_h is None:
                self.load_calib(cam)

    def load_calib(self, cam: Cam) -> None:
        raw = self.r.get(calib_key(cam.cam_id))
        if not raw:
            return
        doc = json.loads(raw)
        h = doc.get("H_img_to_field")
        size = doc.get("image_size") or {}
        if h and len(h) == 9:
            cam.calib_h, cam.calib_size = [float(v) for v in h], (int(size.get("w", 0)), int(size.get("h", 0)))

    def _prepare(self, data: bytes):
        """JPEG -> RGB -> the model's normalised CHW input. Runs on the thread pool, overlapping the GPU (OpenCV
        releases the GIL)."""
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        h, w = bgr.shape[:2]
        chw, inverse = self.bb.preprocess(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        return chw, inverse, w, h

    def pump(self) -> bool:
        """Read what each camera has (decoding on the pool); run every window whose frames are ready."""
        worked = False
        for cam in list(self.cams.values()):
            while True:
                f = cam.reader.read(block_ms=0)
                if f is None:
                    break
                cam.buf.append((f.seq, f.t_game_s, f.t_srv_ms, self.pool.submit(self._prepare, f.data)))
                cam.last_frame_wall = time.time()
                if len(cam.buf) > self.max_lag + 3:  # behind real time: keep the newest
                    cam.buf = cam.buf[-3:]
            while len(cam.buf) >= 3 and all(w[3].done() for w in cam.buf[:3]):
                window = cam.buf[:3]
                prepared = [w[3].result() for w in window]
                if any(p is None for p in prepared):
                    cam.buf = cam.buf[3:]
                    continue
                hm = self.bb.heatmaps([p[0] for p in prepared])
                heads = range(3) if self.stride >= 3 else range(self.stride)
                for i in heads:
                    _, inverse, w, h = prepared[i]
                    self.publish(cam, window[i], self.bb.decode(hm[i], inverse, w, h), (w, h))
                cam.buf = cam.buf[min(3, self.stride) :]
                worked = True
        return worked

    def publish(self, cam: Cam, frame, det, size: tuple[int, int]) -> None:
        seq, t_game_s, t_srv_ms, _ = frame
        w, h = size
        sample: dict = {"t_game_s": round(t_game_s, 4), "seq": int(seq), "px": None, "conf": 0.0}
        pos = None
        if det is not None:
            sample.update(
                px=[round(det.x, 2), round(det.y, 2)],
                conf=round(min(1.0, det.score), 3),
                blur_len_px=round(det.blur_len_px, 2),
                blur_angle_deg=round(det.blur_angle_deg, 1),
            )
            if cam.calib_h is not None:
                sx = (cam.calib_size[0] / w) if cam.calib_size and cam.calib_size[0] else 1.0
                sy = (cam.calib_size[1] / h) if cam.calib_size and cam.calib_size[1] else 1.0
                pos = apply_h(cam.calib_h, det.x * sx, det.y * sy)
            cam.det += 1
            cam.total_det += 1
        sample["detector"] = "blurball"
        self.r.xadd(trk_ball_key(cam.cam_id), {"json": json.dumps(sample)}, maxlen=TRK_MAXLEN, approximate=True)
        cam.n += 1
        cam.total += 1
        cam.lags.append(time.time() * 1000 - t_srv_ms)
        if self.world is not None and det is not None:
            self.world.post(
                cam.game_id,
                cam.cam_id,
                sample["t_game_s"],
                pos_m=[round(pos[0], 4), round(pos[1], 4)] if pos else None,
                px=sample["px"],
                conf=sample["conf"],
            )

    def report(self) -> None:
        now = time.time()
        dt = now - self.last_report
        if dt < 5:
            return
        calls = self.bb.calls - self.calls0
        model = (self.bb.model_ms - self.model_ms0) / max(1, calls)
        for cam in self.cams.values():
            if not cam.n:
                continue
            lag = np.array(cam.lags)
            log.info(
                json.dumps(
                    {
                        "svc": "flight",
                        "msg": "live",
                        "cam_id": cam.cam_id,
                        "game_id": cam.game_id,
                        "fps": round(cam.n / dt, 1),
                        "detected": round(cam.det / cam.n, 3),
                        "lag_ms_p50": round(float(np.median(lag)), 1),
                        "lag_ms_p95": round(float(np.percentile(lag, 95)), 1),
                        "skipped": cam.reader.skipped - cam.skipped0,
                        "model_ms": round(model, 1),
                        "device": self.bb.device,
                        "half": self.bb.half,
                        "stride": self.stride,
                    }
                )
            )
            cam.n = cam.det = 0
            cam.lags = []
            cam.skipped0 = cam.reader.skipped
        self.last_report, self.calls0, self.model_ms0 = now, self.bb.calls, self.bb.model_ms


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flight.live", description=__doc__.split("\n\n")[0])
    ap.add_argument("--stride", type=int, default=3, choices=[1, 2, 3], help="frames between windows (3 = each once)")
    ap.add_argument("--max-lag", type=int, default=9, help="frames a camera may fall behind before it skips ahead")
    ap.add_argument("--device", default=None, help="auto | mps | cpu (default: BLURBALL_DEVICE or auto)")
    ap.add_argument(
        "--fp32", action="store_true", help="Mu's validated fp32 path (fp16 is the MPS default; see blurball.load)"
    )
    ap.add_argument("--no-world", action="store_true", help="don't mirror the ball into Spacetime track_sample")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    env = {**dotenv(), **os.environ}
    r = redis.Redis.from_url(env.get("REDIS_URL") or "redis://127.0.0.1:6379/0")
    bb = load(device=a.device, half=False if a.fp32 else None)
    warm = bb.warmup(np.zeros((720, 1280, 3), np.uint8))
    world = None
    if not a.no_world and env.get("SPACETIME_VISION_TOKEN"):
        from trophy.world import SpacetimeClient, TrackSampleWriter

        world = TrackSampleWriter(SpacetimeClient(token=env["SPACETIME_VISION_TOKEN"]))
    log.info(
        json.dumps(
            {
                "svc": "flight",
                "msg": "started",
                "detector": "blurball",
                "device": bb.device,
                "half": bb.half,
                "stride": a.stride,
                "warmup_ms": round(warm, 1),
                "weights_sha256": bb.pred.weight_sha256[:12],
                "world": world is not None,
            }
        )
    )
    live = Live(r, bb, a.stride, a.max_lag, world)
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while not stop:
        live.scan()
        if not live.pump():
            time.sleep(0.005)
        live.report()
    if world is not None:
        world.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
