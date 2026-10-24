#!/usr/bin/env python3
"""Publish original decoded clip frames to Trophy's Redis bus, preserving PTS.

Video is never written to Spacetime. This tool emits frames only, not inferred
measurements or outcomes. `--index-only` can audit timing without Redis.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import av
import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/py-trophy"))


def iter_frames(path: str | Path, start_s: float = 0.0, end_s: float | None = None):
    """Yield source seq, exact PTS seconds, and decoded BGR. No fps clock fallback.

    The iterator decodes from the start to retain original source-frame identity.
    Missing/non-increasing PTS is rejected rather than guessed from average FPS.
    """
    if not math.isfinite(start_s) or start_s < 0:
        raise ValueError("start_s must be nonnegative and finite")
    if end_s is not None and (not math.isfinite(end_s) or end_s <= start_s):
        raise ValueError("end_s must be finite and greater than start_s")
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError("Clip has no video stream")
        stream = container.streams.video[0]
        rotation = str(stream.metadata.get("rotate", "0"))
        if rotation not in ("0", "0.0", "360"):
            raise ValueError("Bake display rotation into a local copy and retain its source transform before ingest")
        previous = None
        for seq, frame in enumerate(container.decode(stream)):
            if frame.pts is None or frame.time_base is None:
                raise ValueError(f"Frame {seq} has no source PTS")
            stamp = float(frame.pts * frame.time_base)
            if not math.isfinite(stamp) or (previous is not None and stamp <= previous):
                raise ValueError(f"Frame {seq} has non-increasing source PTS")
            previous = stamp
            if stamp < start_s:
                continue
            if end_s is not None and stamp >= end_s:
                break
            yield seq, stamp, frame.to_ndarray(format="bgr24")


def play(
    path: str | Path,
    *,
    game_id: str,
    cam_id: str,
    clip_offset_s: float = 0.0,
    sync_err_ms: float = 0.0,
    start_s: float = 0.0,
    end_s: float | None = None,
    redis_url: str = "redis://127.0.0.1:6379/0",
    realtime: bool = True,
    speed: float = 1.0,
    width: int = 1280,
    jpeg_quality: int = 85,
    calibration: str | Path | None = None,
    index_path: str | Path | None = None,
    index_only: bool = False,
    max_frames: int | None = None,
    game_epoch_ms: float | None = None,
) -> dict[str, Any]:
    if not math.isfinite(clip_offset_s) or not math.isfinite(sync_err_ms) or sync_err_ms < 0:
        raise ValueError("Offset and nonnegative uncertainty must be finite")
    if not math.isfinite(speed) or speed <= 0 or width < 1 or not 1 <= jpeg_quality <= 100:
        raise ValueError("Invalid playback speed, width, or JPEG quality")
    if max_frames is not None and max_frames < 1:
        raise ValueError("max_frames must be positive")
    if game_epoch_ms is not None and not math.isfinite(game_epoch_ms):
        raise ValueError("game_epoch_ms must be finite")
    writer = None
    calibration_size = None
    if not index_only:
        import redis
        from trophy.framebus import FrameWriter

        client = redis.Redis.from_url(redis_url, decode_responses=False)
        client.ping()
        writer = FrameWriter(client)
        if calibration:
            from trophy.contracts import Calibration

            document = json.loads(Path(calibration).read_text())
            parsed = Calibration.model_validate(document)
            if parsed.cam_id != cam_id or parsed.game_id != game_id:
                raise ValueError("Calibration game/camera identity does not match the clip")
            calibration_size = (parsed.image_size.w, parsed.image_size.h)
            encoded = json.dumps(document, allow_nan=False)
            client.set(f"calib:{cam_id}", encoded)
            client.publish("ctl:calib", json.dumps({"cam_id": cam_id}))
    output = None
    if index_path:
        target = Path(index_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        output = target.open("w")
    wall_start = time.monotonic()
    first_time = None
    count = 0
    last_time = None
    epoch_assumed = game_epoch_ms is None
    if game_epoch_ms is None:
        game_epoch_ms = time.time() * 1000 - (start_s + clip_offset_s) * 1000
    try:
        for seq, stamp, image in iter_frames(path, start_s, end_s):
            if first_time is None:
                first_time = stamp
            if realtime:
                delay = (stamp - first_time) / speed - (time.monotonic() - wall_start)
                if delay > 0:
                    time.sleep(delay)
            height, original_width = image.shape[:2]
            if original_width > width:
                image = cv2.resize(
                    image, (width, max(1, round(height * width / original_width))), interpolation=cv2.INTER_AREA
                )
            height, image_width = image.shape[:2]
            if calibration_size and calibration_size != (image_width, height):
                raise ValueError("Calibration image_size must match the resized bus frame dimensions")
            game_time = stamp + clip_offset_s
            if writer:
                encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                if not encoded:
                    raise RuntimeError("Cannot encode decoded source frame")
                writer.write(
                    game_id=game_id,
                    cam_id=cam_id,
                    seq=seq,
                    t_phone_ms=stamp * 1000,
                    t_srv_ms=game_epoch_ms + game_time * 1000,
                    t_game_s=game_time,
                    sync_err_ms=sync_err_ms,
                    jpeg=jpeg.tobytes(),
                    source="file",
                    flags=2 if count == 0 else 0,
                    size=(image_width, height),
                )
            if output:
                output.write(
                    json.dumps(
                        {
                            "seq": seq,
                            "t_source_s": stamp,
                            "t_game_s": game_time,
                            "source": "file",
                            "w": image_width,
                            "h": height,
                        }
                    )
                    + "\n"
                )
            count += 1
            last_time = stamp
            if max_frames is not None and count >= max_frames:
                break
    finally:
        if output:
            output.close()
    return {
        "frames": count,
        "first_source_s": first_time,
        "last_source_s": last_time,
        "clip_offset_s": clip_offset_s,
        "source": "file",
        "index_only": index_only,
        "elapsed_s": time.monotonic() - wall_start,
        "game_epoch_ms": game_epoch_ms,
        "epoch_assumed": epoch_assumed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--game", default="g_ttdemo01")
    parser.add_argument("--cam", default="c_side01")
    parser.add_argument("--offset", type=float, default=0.0, help="t_game_s = source PTS seconds + offset")
    parser.add_argument("--sync-err-ms", type=float, default=0.0)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    parser.add_argument("--fast", action="store_true", help="No wall-clock pacing; readers may skip this backlog")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--quality", type=int, default=85)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--index-only", action="store_true")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--game-epoch-ms", type=float, help="Shared t0_ms from the existing gateway game")
    args = parser.parse_args()
    result = play(
        args.video,
        game_id=args.game,
        cam_id=args.cam,
        clip_offset_s=args.offset,
        sync_err_ms=args.sync_err_ms,
        start_s=args.start,
        end_s=args.end,
        redis_url=args.redis_url,
        realtime=not args.fast,
        speed=args.speed,
        width=args.width,
        jpeg_quality=args.quality,
        calibration=args.calibration,
        index_path=args.index,
        index_only=args.index_only,
        max_frames=args.max_frames,
        game_epoch_ms=args.game_epoch_ms,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
