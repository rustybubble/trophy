"""Live check of the running gateway through the public origin, acting like a phone.

    uv run python scripts/live_check.py [--base https://trophy.photo] [--seconds 10] [--fps 30]

Creates a game, joins as cam+judge, mints a Cartesia token, syncs the clock over /api/ws/ctl, streams a real
720p JPEG (an ffmpeg test pattern: synthetic, no people) over /api/ws/frames, then reads Redis to report what
landed: frames, achieved fps, gateway-arrival-to-Redis lag and the clock fit. Run it on the demo machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import time
from pathlib import Path

import httpx
import redis
import websockets
from trophy.framebus import pack_header

ROOT = Path(__file__).resolve().parents[3]


def test_jpeg() -> bytes:
    p = ROOT / "data" / "local" / "spikes" / "testsrc_720p.jpg"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=1280x720",
                "-frames:v",
                "1",
                "-q:v",
                "5",
                str(p),
            ],
            check=True,
        )
    return p.read_bytes()


def now_ms() -> float:
    return time.time() * 1000


async def main(base: str, seconds: float, fps: float) -> None:
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    async with httpx.AsyncClient(base_url=base, timeout=10) as http:
        health = (await http.get("/api/healthz")).json()
        print("healthz:", health)
        g = (await http.post("/api/games", json={"sport": "table_tennis"})).json()
        j = (
            await http.post(
                f"/api/games/{g['game_id']}/join",
                json={
                    "join_key": g["join_key"],
                    "label": "live-check",
                    "role": "cam,judge",
                    "device": {"ua": "live_check"},
                },
            )
        ).json()
        tok = j["cam_token"]
        t = time.perf_counter()
        v = await http.get("/api/voice/token", headers={"Authorization": f"Bearer {tok}"})
        print(
            f"voice token: HTTP {v.status_code} in {(time.perf_counter() - t) * 1000:.0f} ms, "
            f"key fields {sorted(v.json())}"
        )

    jpeg = test_jpeg()
    async with websockets.connect(f"{ws_base}/api/ws/ctl?token={tok}") as ctl:
        prev, sync = None, None
        for _ in range(12):
            t0 = now_ms()
            await ctl.send(json.dumps({"type": "ping", "t0": t0, **({"prev": prev} if prev else {})}))
            pong = json.loads(await ctl.recv())
            t3 = now_ms()
            if prev:
                sync = json.loads(await ctl.recv())
            prev = {"t0": t0, "t1": pong["t1"], "t2": pong["t2"], "t3": t3}
            await asyncio.sleep(0.05)
        print(
            f"clock fit: offset {sync['offset_ms']:.2f} ms, sync_err {sync['sync_err_ms']:.2f} ms "
            "(same machine: expect ~0)"
        )

        async with websockets.connect(f"{ws_base}/api/ws/frames?token={tok}", max_size=None) as fws:
            n, dropped, t_end = 0, 0, time.perf_counter() + seconds
            period = 1 / fps
            nxt = time.perf_counter()
            while time.perf_counter() < t_end:
                # latest-frame-wins, like the PWA: skip a frame if the socket still has data buffered
                if fws.transport.get_write_buffer_size() == 0:
                    await fws.send(pack_header(n, now_ms()) + jpeg)
                    n += 1
                else:
                    dropped += 1
                nxt += period
                await asyncio.sleep(max(0, nxt - time.perf_counter()))
        await asyncio.sleep(0.5)

    r = redis.Redis.from_url("redis://127.0.0.1:6379/0")
    rows = r.xrange(f"frames:{j['cam_id']}")
    lags = [float(f[b"t_srv_ms"]) - float(f[b"t_phone_ms"]) for _, f in rows]
    ids = [int(eid.decode().split("-")[0]) for eid, _ in rows]
    span_s = (ids[-1] - ids[0]) / 1000 if len(ids) > 1 else 0
    cam = {k.decode(): v.decode() for k, v in r.hgetall(f"cam:{j['cam_id']}").items()}
    print(
        f"frames: sent {n} ({len(jpeg) / 1024:.0f} KB each), skipped {dropped}, on Redis {len(rows)} "
        f"(stream keeps ~300), achieved {len(rows) / span_s if span_s else 0:.1f} fps over the kept span"
    )
    print(
        f"t_srv - t_phone (clock-mapped; same machine, so ~0 means the fit is right): "
        f"median {statistics.median(lags):.2f} ms, max {max(lags):.2f} ms"
    )
    print(
        f"cam hash: fps_in={cam.get('fps_in')} w={cam.get('w')} h={cam.get('h')} sync_err_ms={cam.get('sync_err_ms')}"
    )
    print(
        f"game {g['game_id']} cam {j['cam_id']} "
        f"(synthetic test pattern; delete with: redis-cli DEL frames:{j['cam_id']})"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://trophy.photo")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--fps", type=float, default=30)
    a = ap.parse_args()
    asyncio.run(main(a.base, a.seconds, a.fps))
