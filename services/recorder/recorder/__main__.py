from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

import redis
from trophy.recordings import ffmpeg_binary, select_encoder

from .service import Recorder
from .state import GameEndMonitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Record local camera streams; Ctrl-C finalizes HLS.")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    parser.add_argument("--root", type=Path, default=Path("data/local/recordings"))
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--encoder", default="auto")
    parser.add_argument("--stdb-uri", default=os.environ.get("SPACETIME_URI", "http://127.0.0.1:3000"))
    parser.add_argument("--stdb-module", default=os.environ.get("SPACETIME_MODULE", "trophy"))
    parser.add_argument(
        "--idle-exit", type=float, default=0, help="finalize after this many idle seconds (smoke tests)"
    )
    args = parser.parse_args()
    if not 1 <= args.fps <= 60:
        parser.error("fps must be 1..60")
    encoder = select_encoder(ffmpeg_binary(), args.encoder)
    r = redis.Redis.from_url(args.redis_url)
    monitor = GameEndMonitor(args.stdb_uri, args.stdb_module)
    recorder = Recorder(r, args.root, args.fps, encoder, monitor)
    stopping = False

    def stop(_sig: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({"service": "recorder", "encoder": encoder, "fps": args.fps}), flush=True)
    last = time.monotonic()
    last_monitor_error = None
    try:
        while not stopping:
            if recorder.poll():
                last = time.monotonic()
            if monitor.error != last_monitor_error:
                print(json.dumps({"service": "recorder", "game_end_monitor_error": monitor.error}), flush=True)
                last_monitor_error = monitor.error
            if args.idle_exit and recorder.frames and time.monotonic() - last > args.idle_exit:
                break
            time.sleep(0.01)
    except Exception as exc:
        for session in recorder.sessions.values():
            session.meta["error"] = type(exc).__name__
        raise
    finally:
        recorder.close()
        r.close()
    print(json.dumps({"service": "recorder", "frames": recorder.frames, "finalized": True}), flush=True)


if __name__ == "__main__":
    main()
