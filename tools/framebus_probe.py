#!/usr/bin/env python3
"""Bounded frame-bus diagnostic: dimensions/sequence/timing only, no image logs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/py-trophy"))


def main():
    import redis
    from trophy.framebus import FrameReader

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cam")
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--mode", choices=["latest", "all"], default="all")
    args = parser.parse_args()
    if not 0 < args.duration <= 60:
        parser.error("duration must be in (0,60] seconds")
    reader = FrameReader(redis.Redis.from_url(args.redis_url, decode_responses=False), args.cam, mode=args.mode)
    start = time.monotonic()
    count = 0
    previous = None
    gaps = 0
    first = last = None
    while time.monotonic() - start < args.duration:
        frame = reader.read(block_ms=50)
        if frame is None:
            continue
        if previous is not None and frame.seq > previous + 1:
            gaps += frame.seq - previous - 1
        previous = frame.seq
        first = frame.t_game_s if first is None else first
        last = frame.t_game_s
        count += 1
        print(
            json.dumps(
                {
                    "seq": frame.seq,
                    "t_game_s": frame.t_game_s,
                    "source": frame.source,
                    "w": frame.w,
                    "h": frame.h,
                    "sync_err_ms": frame.sync_err_ms,
                }
            )
        )
    print(
        json.dumps(
            {
                "frames": count,
                "read_fps": count / (time.monotonic() - start),
                "sequence_gaps": gaps,
                "reader_skipped": reader.skipped,
                "first_game_s": first,
                "last_game_s": last,
            }
        )
    )


if __name__ == "__main__":
    main()
