"""Play a recorded game clip into the running gateway as if a phone were filming it, then exercise a challenge
with a high-quality (original-resolution) replay segment. For testing on real footage, locally only.

    uv run --with opencv-python-headless==4.10.0.84 python scripts/clip_as_phone.py \
        ../../data/local/ttClips/side_IMG_4342.mp4 --start 5 --seconds 12

1. Creates a game, joins as cam+judge, syncs the clock over /api/ws/ctl.
2. Streams the clip from --start, scaled to 1280x720 JPEG at 30 fps in real time over /api/ws/frames (like the PWA).
   Frames are encoded with libjpeg (OpenCV) at quality 70, 4:2:0, like the PWA's canvas encoder at 0.7; ffmpeg's
   MJPEG encoder loses noticeably more of a small ball's colour at a similar size, so it isn't used.
3. Posts a BETA test call (as the engine, SPACETIME_ENGINE_TOKEN) at the end, opens a challenge on it, and uploads a
   6 s segment cut from the ORIGINAL file around the call (`ffmpeg -c copy`, no re-encode) to /api/clips (as D-27's
   phone recorder would).
Footage stays in data/local (gitignored); nothing is published.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import httpx
import redis
import websockets
from trophy.framebus import pack_header

ROOT = Path(__file__).resolve().parents[3]
BASE = "http://127.0.0.1:8000"
STDB = "http://127.0.0.1:3000"


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


def now_ms() -> float:
    return time.time() * 1000


def reducer(name: str, payload: object, token: str) -> None:
    req = urllib.request.Request(
        f"{STDB}/v1/database/trophy/call/{name}",
        data=json.dumps([json.dumps(payload)]).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    urllib.request.urlopen(req, timeout=10).read()


async def jpeg_frames(path: Path, start: float, seconds: float, crop: tuple[float, float, float, float] | None = None):
    """1280x720 JPEGs at 30 fps (ffmpeg decodes and scales, libjpeg encodes), with each frame's clip time. With
    `crop` (normalised x, y, w, h), only that region, as the PWA streams once the table is set (D-29)."""
    import cv2  # dev tool only: `uv run --with opencv-python-headless==4.10.0.84`
    import numpy as np

    w, h = 1280, 720
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        str(start),
        "-t",
        str(seconds),
        "-i",
        str(path),
        "-vf",
        "fps=30,"
        + (f"crop=iw*{crop[2]}:ih*{crop[3]}:iw*{crop[0]}:ih*{crop[1]}," if crop else "")
        + f"scale={w}:{h}:flags=area",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-",
        stdout=asyncio.subprocess.PIPE,
    )
    n = 0
    assert proc.stdout
    while True:
        try:
            raw = await proc.stdout.readexactly(w * h * 3)
        except asyncio.IncompleteReadError:
            break
        img = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
        _, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        yield start + n / 30, jpeg.tobytes()
        n += 1
    await proc.wait()


async def main(
    path: Path,
    start: float,
    seconds: float,
    no_challenge: bool = False,
    crop: tuple[float, float, float, float] | None = None,
) -> None:
    e = env()
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as http:
        g = (await http.post("/api/games", json={"sport": "table_tennis"})).json()
        j = (
            await http.post(
                f"/api/games/{g['game_id']}/join",
                json={"join_key": g["join_key"], "label": f"clip:{path.name}", "role": "cam,judge"},
            )
        ).json()
    tok, gid, cam = j["cam_token"], g["game_id"], j["cam_id"]
    t0_game_ms = g["t0_ms"]
    reducer(
        "upsert_game",
        {
            "game_id": gid,
            "sport": "table_tennis",
            "pack_version": "table_tennis@1",
            "status": "live",
            "t0_ms": t0_game_ms,
            "period_no": 1,
            "rally_no": 0,
            "teams": [{"team_id": "A", "name": "A"}, {"team_id": "B", "name": "B"}],
            "params": {
                "synthetic": True,
                "label": f"TEST: recorded clip {path.name} played as a phone; hand-posted call",
            },
            "created_at_ms": t0_game_ms,
        },
        e["SPACETIME_ENGINE_TOKEN"],
    )
    ws_base = BASE.replace("http", "ws")
    async with websockets.connect(f"{ws_base}/api/ws/ctl?token={tok}") as ctl:
        prev = None
        for _ in range(10):
            t0 = now_ms()
            await ctl.send(json.dumps({"type": "ping", "t0": t0, **({"prev": prev} if prev else {})}))
            pong = json.loads(await ctl.recv())
            if prev:
                await ctl.recv()
            prev = {"t0": t0, "t1": pong["t1"], "t2": pong["t2"], "t3": now_ms()}

        # stream in real time; the phone clock of clip time c is wall0 + (c - start) * 1000
        wall0 = now_ms() + 300
        sent = 0
        async with websockets.connect(f"{ws_base}/api/ws/frames?token={tok}", max_size=None) as fws:
            async for c, jpeg in jpeg_frames(path, start, seconds, crop):
                t_phone = wall0 + (c - start) * 1000
                await asyncio.sleep(max(0, (t_phone - now_ms()) / 1000))
                await fws.send(pack_header(sent, t_phone, 0, crop) + jpeg)
                sent += 1

        if not no_challenge:
            # a challenged call at the end of the streamed window; the replay segment is cut from the original file
            call_clip_t = start + seconds - 1.0
            t_call_game = (wall0 + (call_clip_t - start) * 1000 - t0_game_ms) / 1000
            call_id = "01JCLP" + secrets.token_hex(10).upper()[:20]
            reducer(
                "post_call",
                {
                    "schema": "trophy.call.v1",
                    "id": call_id,
                    "game_id": gid,
                    "t_game_s": t_call_game,
                    "rule_id": "edge_ball",
                    "rule_version": "table_tennis@1",
                    "kind": "edge_call",
                    "outcome": "edge_good",
                    "team_id": "A",
                    "p": 0.66,
                    "p_source": "manual",
                    "tier": "BETA",
                    "shown": "challengeable",
                    "text": "TEST call on recorded footage (hand-posted)",
                    "speech": "Test call.",
                    "cue": {"beep": "none", "flash": "none"},
                    "event_ids": [],
                    "evidence": [{"cam_id": cam, "t0_s": t_call_game - 2, "t1_s": t_call_game}],
                    "status": "final",
                    "created_at_ms": now_ms(),
                },
                e["SPACETIME_ENGINE_TOKEN"],
            )
            reducer(
                "open_challenge",
                {
                    "challenge_id": "01JCHL" + secrets.token_hex(10).upper()[:20],
                    "game_id": gid,
                    "call_id": call_id,
                    "by_cam_id": cam,
                    "status": "open",
                    "result": None,
                    "created_at_ms": now_ms(),
                },
                e["SPACETIME_ENGINE_TOKEN"],
            )
            seg_start = max(start, start + seconds - 6.0)
            with tempfile.TemporaryDirectory() as td:
                seg = Path(td) / "seg.mp4"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-ss",
                        str(seg_start),
                        "-t",
                        "6",
                        "-i",
                        str(path),
                        "-c",
                        "copy",
                        "-an",
                        "-movflags",
                        "+faststart",
                        str(seg),
                    ],
                    check=True,
                )
                t_seg0 = wall0 + (seg_start - start) * 1000
                t = time.perf_counter()
                async with httpx.AsyncClient(base_url=BASE, timeout=120) as http:
                    r = await http.post(
                        "/api/clips",
                        params={
                            "call_id": call_id,
                            "seg": 0,
                            "t_start_phone_ms": t_seg0,
                            "t_end_phone_ms": t_seg0 + 6000,
                        },
                        content=seg.read_bytes(),
                        headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"},
                    )
                up_s = time.perf_counter() - t
                meta = r.json()
        await ctl.close()

    rows = redis.Redis().xrange(f"frames:{cam}")
    tsrv = [float(f[b"t_srv_ms"]) for _, f in rows]
    span = (tsrv[-1] - tsrv[0]) / 1000 if len(tsrv) > 1 else 0
    print(f"game {gid} cam {cam}: streamed {sent} frames of {path.name} [{start:.1f}-{start + seconds:.1f}s]")
    fps = (len(rows) - 1) / span if span else 0
    size = f"{rows[-1][1][b'w'].decode()}x{rows[-1][1][b'h'].decode()}"
    print(f"gateway kept {len(rows)} frames: {fps:.1f} fps over {span:.1f}s, w,h={size}")
    if no_challenge:
        print(f"game {gid} join key {g['join_key']}")
        return
    print(
        f"HQ replay segment: HTTP {r.status_code}, {meta.get('w')}x{meta.get('h')} {meta.get('codec')}, "
        f"{meta.get('bytes', 0) / 1e6:.1f} MB, {meta.get('duration_s')} s, upload {up_s:.2f} s (localhost), "
        f"game {meta.get('t_game_start_s', 0):.2f}-{meta.get('t_game_end_s', 0):.2f}s vs call at {t_call_game:.2f}s"
    )
    print(f"call {call_id}; view as judge: join game {gid} with key {g['join_key']} and tap Watch replay")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("--start", type=float, default=5.0)
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--no-challenge", action="store_true", help="only stream (e.g. to test flight.live)")
    ap.add_argument("--crop", help="x,y,w,h (normalised): stream only this region, like the PWA's table zoom")
    a = ap.parse_args()
    crop = tuple(float(v) for v in a.crop.split(",")) if a.crop else None
    asyncio.run(main(a.clip, a.start, a.seconds, a.no_challenge, crop))  # type: ignore[arg-type]
