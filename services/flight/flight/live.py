"""Live flight vision module (INT-1): Redis frames -> ball track + table -> measurements -> Redis + Spacetime.

    uv run python -m flight.live --game g_xxxxxxxx [--post-calls]

For every camera of the game (role "cam"), reads `frames:{cam}` (trophy.framebus.FrameReader, every frame, never a
backlog) and runs the gated ball tracker + table finder. The ball colour model starts from defaults and is re-learnt
from this camera's own stream within its first seconds of play (flight.colour.LiveLearner).

Outputs (measurements only, D-18):
- `trk:ball:{cam}` every frame, and Spacetime `track_sample` at 10 Hz (`trophy.world.TrackSampleWriter`);
- `bounce`, `contact` and `ball_dead` events on `ev:flight` and Spacetime `observation` (`ObservationWriter`).
  Image-space measurements: no metric calibration is used, so every payload carries calib_untrusted = true and
  d_lines_m is empty (the engine caps such calls at BETA).

`--post-calls` (INTERIM, until Agent 3's engine runs): applies flight.rally.referee to each finished rally and posts
a point call + score + rally rows to Spacetime with the engine identity (SPACETIME_ENGINE_TOKEN), p_source
"heuristic". Remove the flag once the engine consumes ev:flight.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import redis
from trophy.events import event_json, make_event
from trophy.framebus import FrameReader
from trophy.ids import new_ulid
from trophy.streams import EV_FLIGHT, EVENT_STREAM_MAXLEN, cam_key, game_key
from trophy.tracks import BallTrackWriter
from trophy.world import ObservationWriter, SpacetimeClient, TrackSampleWriter

from .balltrack import Detector, Tracker
from .colour import LiveLearner
from .rally import Rally, build_rallies
from .table import Table, TableTracker

log = logging.getLogger("trophy.flight")
W, H = 1280, 720
WINDOW_S = 40.0  # rally analysis looks back this far
SETTLE_S = 0.4  # events are published once they are this old (smoothing windows have settled)
SPORT = "table_tennis"


def _env(root: Path) -> dict[str, str]:
    out = {}
    p = root / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split("#")[0].strip()
    return {**out, **os.environ}


class CamWorker(threading.Thread):
    def __init__(
        self,
        r: redis.Redis,
        game_id: str,
        cam_id: str,
        obs: ObservationWriter,
        trk: TrackSampleWriter,
        calls: CallPoster | None,
    ) -> None:
        super().__init__(name=f"flight-{cam_id}", daemon=True)
        self.r, self.game_id, self.cam_id = r, game_id, cam_id
        self.obs, self.trk, self.calls = obs, trk, calls
        self.stop = threading.Event()
        self.rows: list[dict] = []
        self.sent: set[tuple] = set()
        self.done_rallies: set[float] = set()  # rally end times already judged
        self.stats = {"frames": 0, "observed": 0, "events": 0, "fps": 0.0, "ms": 0.0, "analyse_ms": 0.0, "skipped": 0}

    def run(self) -> None:
        # max_lag 45 (1.5 s at 30 fps): absorbs short stalls (the colour fits) and catches up, since a frame takes
        # ~22 ms of the 33 ms budget; a longer backlog is skipped, and the tracker restarts across the gap
        reader = FrameReader(self.r, self.cam_id, mode="all", max_lag=45)
        balls = BallTrackWriter(self.r, self.cam_id)
        learner: LiveLearner | None = LiveLearner()
        tracker: Tracker | None = None
        tables = TableTracker()
        last_analysis = 0.0
        t_win, n_win = time.monotonic(), 0
        while not self.stop.is_set():
            f = reader.read(block_ms=200)
            if f is None:
                continue
            t0 = time.perf_counter()
            img = cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            if img.shape[1] != W or img.shape[0] != H:
                img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            if tracker is None:
                fps = float(self.r.hget(cam_key(self.cam_id), "fps_in") or 0)
                tracker = Tracker(fps=fps if 10 <= fps <= 60 else 30.0)  # fps_in is 0 until the gateway measures it
            if learner is not None:
                model = learner.add(img)
                if model is not None:
                    tracker.detector = Detector(model)
                    log.info(
                        json.dumps({"svc": "flight", "cam_id": self.cam_id, "msg": "colour model", "model": str(model)})
                    )
                    learner = None
            p = tracker.step(f.seq, f.t_game_s, img)
            tb = tables.update(img)
            self.stats["frames"] += 1
            n_win += 1
            row = {"seq": f.seq, "t": f.t_game_s, "state": p.state, "track_id": p.track_id}
            if p.x is not None and p.y is not None:
                row["x"], row["y"] = p.x, p.y
            if tb is not None:
                row["tb"] = tb
            self.rows.append(row)
            if p.state == "observed":
                self.stats["observed"] += 1
                balls.write(
                    {"t_game_s": f.t_game_s, "seq": f.seq, "px": [round(p.x, 1), round(p.y, 1)], "conf": p.score}
                )
                self.trk.post(self.game_id, self.cam_id, f.t_game_s, px=(round(p.x, 1), round(p.y, 1)), conf=p.score)
            else:
                balls.write({"t_game_s": f.t_game_s, "seq": f.seq, "px": None, "conf": 0.0})
            self.stats["ms"] = 0.9 * self.stats["ms"] + 0.1 * (time.perf_counter() - t0) * 1000
            self.stats["skipped"] = reader.skipped
            now = time.monotonic()
            if now - t_win >= 2:
                self.stats["fps"] = n_win / (now - t_win)
                t_win, n_win = now, 0
            if now - last_analysis >= 0.25:
                last_analysis = now
                a0 = time.perf_counter()
                self.analyse(f.t_game_s)
                self.stats["analyse_ms"] = (time.perf_counter() - a0) * 1000

    def analyse(self, t_now: float) -> None:
        self.rows = [r for r in self.rows if r["t"] >= t_now - WINDOW_S]
        tables = {r["seq"]: r["tb"] for r in self.rows if "tb" in r}

        def table_at(seq: int) -> Table | None:
            t = tables.get(seq)
            if t is None:
                return None
            half = max(t.net_x - t.x_left, t.x_right - t.net_x)
            return Table(t.net_x - half, t.net_x + half, t.a, t.b, t.net_x, t.thickness)

        for rally in build_rallies(self.rows, table_at):
            for e in rally.events:
                key = (e.kind, round(e.t, 2))
                if key in self.sent or t_now - e.t < SETTLE_S:
                    continue
                self.sent.add(key)
                self.publish(e)
            dead = next((e for e in rally.events if e.kind == "dead"), None)
            finished = dead is not None and (dead.why != "lost from view" or t_now - rally.t_end > 1.5)
            inside = bool(self.rows) and rally.t_start - self.rows[0]["t"] >= 1.0  # not cut by the window's start
            played = any(e.kind == "hit" for e in rally.events) and any(e.kind == "bounce" for e in rally.events)
            key = round(rally.t_end, 1)
            if finished and inside and played and key not in self.done_rallies:
                self.done_rallies.add(key)
                if self.calls:
                    self.calls.post(self.cam_id, rally)

    def publish(self, e) -> None:
        common = dict(game_id=self.game_id, t_game_s=e.t, sport=SPORT, source="flight", cams=[self.cam_id], conf=e.conf)
        if e.kind == "bounce":
            ev = make_event(
                type="bounce",
                side=e.side,
                **common,
                payload={
                    "surface": "table",
                    "side": e.side,
                    "d_lines_m": {},
                    "p_in": e.conf,
                    "edge": None,
                    "timing": "track",
                    "calib_untrusted": True,
                },
            )
        elif e.kind == "hit":
            ev = make_event(
                type="contact",
                side=e.side,
                **common,
                payload={"side": e.side, "kind": "racket", "calib_untrusted": True},
            )
        else:
            ev = make_event(
                type="ball_dead",
                **common,
                payload={"reason": "floor" if "below" in e.why else "lost", "last_side": e.side},
            )
        self.r.xadd(EV_FLIGHT, {"json": event_json(ev)}, maxlen=EVENT_STREAM_MAXLEN, approximate=True)
        self.obs.post(ev)
        self.stats["events"] += 1


class CallPoster:
    """INTERIM stand-in for the engine: rally outcome -> point call + score + rally rows in Spacetime."""

    def __init__(self, stdb: SpacetimeClient, game_id: str) -> None:
        self.stdb, self.game_id = stdb, game_id
        self.score = {"A": 0, "B": 0}
        self.rally_no = 0
        self.lock = threading.Lock()

    def post(self, cam_id: str, rally: Rally) -> None:
        with self.lock:
            self.rally_no += 1
            now = time.time() * 1000
            base = {"game_id": self.game_id, "rally_no": self.rally_no, "t_start_s": rally.t_start}
            if rally.winner is None:
                self.stdb.call(
                    "close_rally",
                    json.dumps(
                        {
                            **base,
                            "status": "voided",
                            "t_end_s": rally.t_end,
                            "winner_team_id": None,
                            "summary": {"why": rally.reason},
                        }
                    ),
                )
                return
            self.score[rally.winner] += 1
            p = max(0.05, min(0.99, rally.confidence))
            tier, shown = ("AUTO", "auto") if p >= 0.9 else ("BETA", "challengeable" if p >= 0.6 else "replay")
            loser = "B" if rally.winner == "A" else "A"
            call = {
                "schema": "trophy.call.v1",
                "id": new_ulid(),
                "game_id": self.game_id,
                "t_game_s": rally.t_end,
                "rule_id": "rally_point",
                "rule_version": "flight-interim",
                "rally_no": self.rally_no,
                "kind": "point",
                "outcome": f"point_{rally.winner}",
                "team_id": rally.winner,
                "points": 1,
                "p": round(p, 3),
                "p_source": "heuristic",
                "tier": tier,
                "shown": shown,
                "text": f"Point {rally.winner} ({round(p * 100)}%)"[:80],
                "speech": f"Point, {rally.winner}. {self.score['A']} {self.score['B']}.",
                "cue": {"beep": "short", "flash": rally.winner},
                "event_ids": [],
                "evidence": [{"cam_id": cam_id, "t0_s": rally.t_start, "t1_s": rally.t_end}],
                "status": "final",
                "why": rally.reason[:200],
                "created_at_ms": now,
            }
            self.stdb.call(
                "close_rally",
                json.dumps(
                    {
                        **base,
                        "status": "closed",
                        "t_end_s": rally.t_end,
                        "winner_team_id": rally.winner,
                        "summary": {"why": rally.reason, "loser": loser},
                    }
                ),
            )
            self.stdb.call("post_call", json.dumps(call))
            disp = f"{self.score['A']}–{self.score['B']}"
            self.stdb.call(
                "set_score",
                json.dumps(
                    [
                        {
                            "game_id": self.game_id,
                            "team_id": t,
                            "points": self.score[t],
                            "display": disp,
                            "updated_at_ms": now,
                        }
                        for t in ("A", "B")
                    ]
                ),
            )
            log.info(json.dumps({"svc": "flight", "msg": "point", "winner": rally.winner, "p": p, "why": rally.reason}))


def cameras(r: redis.Redis, game_id: str) -> list[str]:
    out = []
    for k in r.scan_iter("cam:*"):
        h = r.hgetall(k)
        if h.get(b"game_id", b"").decode() == game_id and "cam" in h.get(b"role", b"").decode():
            out.append(k.decode().split(":", 1)[1])
    return sorted(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, help='a game id, or "next" for the next game created')
    ap.add_argument("--post-calls", action="store_true", help="INTERIM: post point calls (no engine yet)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    env = _env(Path(__file__).resolve().parents[3])
    r = redis.Redis.from_url(env.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    if a.game == "next":  # attach to the next game created after start (handy for tests and demos)
        started = time.time() * 1000
        while True:
            newest = max(
                ((float(r.hget(k, "created_at_ms") or 0), k.decode().split(":", 1)[1]) for k in r.scan_iter("game:*")),
                default=(0.0, ""),
            )
            if newest[0] > started:
                a.game = newest[1]
                break
            time.sleep(0.5)
        log.info(json.dumps({"svc": "flight", "msg": "attached", "game_id": a.game}))
    if not r.exists(game_key(a.game)):
        raise SystemExit(f"no game {a.game} in Redis")
    obs = ObservationWriter(SpacetimeClient(token=env.get("SPACETIME_VISION_TOKEN", "")))
    trk = TrackSampleWriter(SpacetimeClient(token=env.get("SPACETIME_VISION_TOKEN", "")))
    calls = CallPoster(SpacetimeClient(token=env.get("SPACETIME_ENGINE_TOKEN", "")), a.game) if a.post_calls else None
    workers: dict[str, CamWorker] = {}
    try:
        while True:
            for cam in cameras(r, a.game):
                if cam not in workers:
                    w = CamWorker(r, a.game, cam, obs, trk, calls)
                    w.start()
                    workers[cam] = w
                    log.info(json.dumps({"svc": "flight", "msg": "camera", "cam_id": cam}))
            for cam, w in workers.items():
                log.info(
                    json.dumps(
                        {
                            "svc": "flight",
                            "cam_id": cam,
                            **{k: round(v, 1) for k, v in w.stats.items()},
                            "obs_sent": obs.sent,
                            "obs_dropped": obs.dropped,
                        }
                    )
                )
            time.sleep(5)
    except KeyboardInterrupt:
        for w in workers.values():
            w.stop.set()
        obs.close()
        trk.close()


if __name__ == "__main__":
    main()
