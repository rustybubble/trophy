"""Dev tool: play a clip onto the frame bus as one phone, in real time, without the gateway (source="file").

    python -m flight.feed --video side.mp4 [--game g_x | --new-game] [--cam c_side] [--start 0 --end 30] [--fps 30]

Frames go through the phone path (1280x720, JPEG q70 4:2:0) and are written to `frames:{cam}` with
t_game_s = t_srv - t0 of the game. With --new-game it creates `game:{id}` and `cam:{cam}` hashes the way the gateway
does (minimal fields), so `flight.live --game next` and the engine can attach. The gateway's
`services/gateway/scripts/clip_as_phone.py` is the end-to-end path through WSS; this one isolates flight.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

import redis
from trophy.framebus import FrameWriter
from trophy.streams import cam_key, game_key, make_ctl, publish_ctl

from .bench import frames


def new_id(prefix: str, n: int) -> str:
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
    return prefix + "".join(secrets.choice(alphabet) for _ in range(n))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--game", default=None)
    ap.add_argument("--new-game", action="store_true")
    ap.add_argument("--cam", default=None)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--redis", default="redis://127.0.0.1:6379/0")
    ap.add_argument("--engine", action="store_true", help="with --new-game: create_game + start_game on ctl:engine")
    ap.add_argument("--first-server", default="A")
    ap.add_argument("--lead-s", type=float, default=1.0, help="wait this long after creating the game")
    a = ap.parse_args(argv)
    r = redis.Redis.from_url(a.redis)
    cam = a.cam or new_id("c_", 6)
    if a.new_game or not a.game:
        a.game = new_id("g_", 8)
        t0 = time.time() * 1000
        r.hset(
            game_key(a.game),
            mapping={
                "sport": "table_tennis",
                "t0_ms": repr(t0),
                "created_at_ms": repr(t0),
                "status": "lobby",
                "pack_version": "1",
            },
        )
        if a.engine:
            publish_ctl(r, make_ctl("create_game", a.game, {"sport": "table_tennis", "t0_ms": t0}))
            publish_ctl(r, make_ctl("start_game", a.game, {"first_server": a.first_server}))
    t0 = float(r.hget(game_key(a.game), "t0_ms"))
    r.hset(
        cam_key(cam),
        mapping={
            "game_id": a.game,
            "label": "feed",
            "role": "cam",
            "fps_in": str(a.fps),
            "w": "1280",
            "h": "720",
            "connected": "1",
        },
    )
    print(json.dumps({"game_id": a.game, "cam_id": cam, "t0_ms": t0}), flush=True)
    time.sleep(a.lead_s)
    fw = FrameWriter(r)
    start = time.perf_counter()
    first_t = None
    n = 0
    for _i, t_src, jpeg in frames(a.video, a.start, a.end, a.fps):
        if first_t is None:
            first_t = t_src
            print(
                json.dumps({"first_frame_t_source_s": t_src, "t_game_s": (time.time() * 1000 - t0) / 1000}), flush=True
            )
        due = start + (t_src - first_t)
        lag = due - time.perf_counter()
        if lag > 0:
            time.sleep(lag)
        t_srv = time.time() * 1000
        fw.write(
            cam_id=cam,
            game_id=a.game,
            seq=n,
            t_phone_ms=t_srv,
            t_srv_ms=t_srv,
            t_game_s=(t_srv - t0) / 1000,
            sync_err_ms=0.0,
            jpeg=jpeg,
            source="file",
        )
        n += 1
    wall = time.perf_counter() - start
    print(json.dumps({"frames": n, "wall_s": round(wall, 2), "fps": round(n / wall, 1) if wall else None}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
