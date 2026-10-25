"""`trophy-live`: the golden sport module over live ball tracks, for every camera of every live game.

    uv run --directory services/engine --frozen trophy-live [--lag 0.35] [--period 0.25]

Input: `trk:ball:{cam}` (BallTrackSample per processed frame; flight.live writes them from BlurBall) and each camera's
calibration (`calib:{cam}`, image -> table homography). Output: bounce / contact / net / ball_dead events on Redis
`ev:flight` (the engine's hot path) and Spacetime `observation`, exactly as perception would publish them.

The module (`sports/<sport>/events.py`, the code the Droid's gate replays) is a batch function over one rally's log,
so it is run on a sliding window: every `--period` seconds over the game's samples since the last dead ball (all
cameras together, so its multi-camera merge fuses angles of the same bounce), and only the events that are settled,
with `t` in (previous cut, stream time - `--lag`], are published. Each event goes out once; a dead ball starts the next
rally's window. Stream time is the newest sample's game time, so a stalled camera never invents silence.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import redis
from trophy.events import parse_event
from trophy.streams import calib_key, cam_key, publish_event

from .sportmod.api import BallSample, Camera
from .sportmod.completion import fill_short_gaps
from .sportmod.loader import SportModule, load_module

ROOT = Path(__file__).resolve().parents[3]
log = logging.getLogger("trophy.live")


def _dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip()
    return out


def camera_from_calib(cam_id: str, doc: dict[str, Any]) -> Camera | None:
    h = doc.get("H_img_to_field")
    size = doc.get("image_size") or {}
    if not h or len(h) != 9:
        return None
    return Camera(
        cam_id=cam_id,
        image_w=int(size.get("w", 0)),
        image_h=int(size.get("h", 0)),
        H_img_to_field=tuple(float(v) for v in h),
        trusted=bool(doc.get("trusted", False)),
        reproj_err_px=float(doc.get("reproj_err_px", 0.0)),
        fps=30.0,
    )


@dataclass
class GameWindow:
    """One game's live window: the cameras, their samples since the last dead ball, what was already published."""

    game_id: str
    module: SportModule
    cams: dict[str, Camera] = field(default_factory=dict)
    samples: list[BallSample] = field(default_factory=list)
    cut: float = float("-inf")  # events with t <= cut are published
    stream_t: float = float("-inf")
    published: list[tuple[str, float, str]] = field(default_factory=list)  # (type, t, side) recently sent
    n_events: int = 0
    fill_gaps_s: float = 0.0  # > 0: complete short per-camera dropouts first (sportmod.completion, D-39)
    n_filled: int = 0

    def add(self, s: BallSample) -> None:
        self.samples.append(s)
        self.stream_t = max(self.stream_t, s.t_s)

    def settle(self, lag: float, max_window_s: float) -> list[dict[str, Any]]:
        """Run the module over the window; return the newly settled events (each once)."""
        if not self.cams or not self.samples:
            return []
        horizon = self.stream_t - lag
        if horizon <= self.cut:
            return []
        lo = max(self.cut - max_window_s, self.stream_t - max_window_s)
        self.samples = [s for s in self.samples if s.t_s >= lo]
        samples = sorted(self.samples, key=lambda s: (s.t_s, s.cam_id))
        if self.fill_gaps_s > 0:
            done: list[BallSample] = []
            for cam_id in self.cams:
                filled, n = fill_short_gaps([s for s in samples if s.cam_id == cam_id], max_gap_s=self.fill_gaps_s)
                done += filled
                self.n_filled = n  # in the current window
            samples = sorted(done, key=lambda s: (s.t_s, s.cam_id))
        obs = [*self.cams.values(), *samples]
        state = self.module.state(self.game_id, calib_trusted=all(c.trusted for c in self.cams.values()))
        out = []
        for ev in self.module.events(iter(obs), state):
            t = float(ev["t_game_s"])
            if not (self.cut < t <= horizon):
                continue
            side = str((ev.get("payload") or {}).get("side") or (ev.get("payload") or {}).get("last_side") or "")
            if any(k == ev["type"] and abs(tt - t) < 0.15 and sd == side for k, tt, sd in self.published):
                continue  # the same event re-timed by a few ms across a cut
            out.append(ev)
            self.published.append((ev["type"], t, side))
        self.published = [p for p in self.published if p[1] > horizon - 5.0]
        self.cut = horizon
        dead = [float(e["t_game_s"]) for e in out if e["type"] == "ball_dead"]
        if dead:  # the next rally starts a fresh window, as the module's one-rally logs do
            self.samples = [s for s in self.samples if s.t_s > max(dead)]
        self.n_events += len(out)
        return out


class Live:
    def __init__(
        self,
        r: redis.Redis,
        modules_dir: Path,
        lag: float,
        period: float,
        window_s: float,
        world,
        fill_gaps_s: float = 0.25,
    ) -> None:
        self.r = r
        self.fill_gaps_s = fill_gaps_s
        self.modules_dir = modules_dir
        self.lag = lag
        self.period = period
        self.window_s = window_s
        self.world = world
        self.games: dict[str, GameWindow] = {}
        self.cam_game: dict[str, str] = {}
        self.streams: dict[str, str] = {}  # trk:ball:{cam} -> last entry id
        self.modules: dict[str, SportModule] = {}
        self.last_scan = 0.0
        self.last_settle = 0.0

    def module(self, sport: str) -> SportModule:
        if sport not in self.modules:
            self.modules[sport] = load_module(self.modules_dir / sport)
        return self.modules[sport]

    def scan(self) -> None:
        now = time.time()
        if now - self.last_scan < 1.0:
            return
        self.last_scan = now
        for raw in self.r.scan_iter(match="trk:ball:*", count=200):
            key = raw.decode()
            cam_id = key.rsplit(":", 1)[1]
            if key not in self.streams:
                gid = self.r.hget(cam_key(cam_id), "game_id")
                if not gid:
                    continue
                gid = gid.decode()
                sport = (self.r.hget(f"game:{gid}", "sport") or b"table_tennis").decode()
                tail = self.r.xrevrange(key, count=1)
                self.streams[key] = tail[0][0].decode() if tail else "0-0"  # only what arrives from now on
                self.cam_game[cam_id] = gid
                if gid not in self.games:
                    self.games[gid] = GameWindow(gid, self.module(sport), fill_gaps_s=self.fill_gaps_s)
                    log.info(json.dumps({"svc": "live", "msg": "game", "game_id": gid, "sport": sport}))
                log.info(json.dumps({"svc": "live", "msg": "camera", "cam_id": cam_id, "game_id": gid}))
            g = self.games.get(self.cam_game.get(cam_id, ""))
            if g is not None and cam_id not in g.cams:
                raw_cal = self.r.get(calib_key(cam_id))
                cam = camera_from_calib(cam_id, json.loads(raw_cal)) if raw_cal else None
                if cam is not None:
                    g.cams[cam_id] = cam
                    log.info(
                        json.dumps(
                            {
                                "svc": "live",
                                "msg": "calibration",
                                "cam_id": cam_id,
                                "trusted": cam.trusted,
                                "reproj_px": round(cam.reproj_err_px, 3),
                            }
                        )
                    )

    def read(self) -> int:
        if not self.streams:
            time.sleep(0.05)
            return 0
        got = self.r.xread(dict(self.streams), count=500, block=50)
        n = 0
        for stream, entries in got or []:
            key = stream.decode()
            cam_id = key.rsplit(":", 1)[1]
            g = self.games.get(self.cam_game.get(cam_id, ""))
            for entry_id, fields in entries:
                self.streams[key] = entry_id.decode()
                if g is None:
                    continue
                d = json.loads(fields[b"json"])
                px = d.get("px")
                g.add(
                    BallSample(
                        cam_id,
                        float(d["t_game_s"]),
                        int(d["seq"]),
                        (float(px[0]), float(px[1])) if px else None,
                        float(d.get("conf", 0.0)),
                    )
                )
                n += 1
        return n

    def settle(self) -> None:
        now = time.time()
        if now - self.last_settle < self.period:
            return
        self.last_settle = now
        for g in self.games.values():
            t = time.perf_counter()
            try:
                evs = g.settle(self.lag, self.window_s)
            except Exception:  # noqa: BLE001 - a bad window must not stop live play
                log.exception("module failed on game %s", g.game_id)
                continue
            ms = (time.perf_counter() - t) * 1000
            for ev in evs:
                event = parse_event(ev)
                publish_event(self.r, event)
                if self.world is not None:
                    self.world.post(event)
                payload = ev.get("payload") or {}
                log.info(
                    json.dumps(
                        {
                            "svc": "live",
                            "msg": "event",
                            "game_id": g.game_id,
                            "type": ev["type"],
                            "t_game_s": round(ev["t_game_s"], 3),
                            "cams": ev.get("cams"),
                            "side": payload.get("side") or payload.get("last_side"),
                            "surface": payload.get("surface"),
                            "conf": round(ev.get("conf", 0), 2),
                            "behind_stream_s": round(g.stream_t - ev["t_game_s"], 3),
                            "module_ms": round(ms, 1),
                        }
                    )
                )


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trophy-live", description=__doc__.split("\n\n")[0])
    ap.add_argument("--lag", type=float, default=0.35, help="seconds an event must be old before it is published")
    ap.add_argument("--period", type=float, default=0.25, help="seconds between module runs")
    ap.add_argument("--window", type=float, default=12.0, help="max seconds of samples kept per game")
    ap.add_argument("--modules", type=Path, default=ROOT / "sports")
    ap.add_argument("--no-world", action="store_true", help="don't mirror events into Spacetime observation")
    ap.add_argument(
        "--fill-gaps",
        type=float,
        default=0.25,
        help="complete per-camera dropouts up to this long before the module runs (PCHIP, D-39); 0 disables",
    )
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    env = {**_dotenv(), **os.environ}
    r = redis.Redis.from_url(env.get("REDIS_URL") or "redis://127.0.0.1:6379/0")
    world = None
    if not a.no_world and env.get("SPACETIME_VISION_TOKEN"):
        from trophy.world import ObservationWriter, SpacetimeClient

        world = ObservationWriter(SpacetimeClient(token=env["SPACETIME_VISION_TOKEN"]))
    live = Live(r, a.modules, a.lag, a.period, a.window, world, fill_gaps_s=a.fill_gaps)
    log.info(
        json.dumps({"svc": "live", "msg": "started", "lag_s": a.lag, "period_s": a.period, "fill_gaps_s": a.fill_gaps})
    )
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while not stop:
        live.scan()
        live.read()
        live.settle()
    return 0


def main() -> int:
    return run()
