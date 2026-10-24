"""Play a recorded game clip into the running gateway as if a phone were filming it, then exercise a challenge
with a high-quality (original-resolution) replay segment. For testing on real footage, locally only.

    uv run python scripts/clip_as_phone.py ../../data/local/ttClips/side_IMG_4342.mp4 --start 5 --seconds 12

1. Creates a game, joins as cam+judge, syncs the clock over /api/ws/ctl.
2. Streams the clip from --start, scaled to 1280x720 JPEG at 30 fps in real time over /api/ws/frames (like the PWA).
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
from trophy.recordings import ffmpeg_binary

ROOT = Path(__file__).resolve().parents[3]
BASE = "http://127.0.0.1:8000"
STDB = "http://127.0.0.1:3000"
MODULE = "trophy"
REDIS_URL = "redis://127.0.0.1:6379/0"
ENV_PATH = ROOT / ".env"


def env() -> dict[str, str]:
    out = {}
    for line in ENV_PATH.read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


def now_ms() -> float:
    return time.time() * 1000


def reducer(name: str, payload: object, token: str) -> None:
    req = urllib.request.Request(
        f"{STDB}/v1/database/{MODULE}/call/{name}",
        data=json.dumps([json.dumps(payload)]).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    urllib.request.urlopen(req, timeout=10).read()


async def jpeg_frames(path: Path, start: float, seconds: float):
    """1280x720 JPEGs at 30 fps from ffmpeg (MJPEG on a pipe), with each frame's clip time."""
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_binary(),
        "-v",
        "error",
        "-ss",
        str(start),
        "-t",
        str(seconds),
        "-i",
        str(path),
        "-vf",
        "fps=30,scale=1280:720",
        "-q:v",
        "5",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-",
        stdout=asyncio.subprocess.PIPE,
    )
    buf = b""
    n = 0
    assert proc.stdout
    while True:
        chunk = await proc.stdout.read(1 << 16)
        if not chunk:
            break
        buf += chunk
        while True:
            s = buf.find(b"\xff\xd8")
            e = buf.find(b"\xff\xd9", s + 2)
            if s < 0 or e < 0:
                break
            yield start + n / 30, buf[s : e + 2]
            n += 1
            buf = buf[e + 2 :]
    await proc.wait()


async def main(
    path: Path, start: float, seconds: float, check_replay: bool = False, report: Path | None = None
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
            async for c, jpeg in jpeg_frames(path, start, seconds):
                t_phone = wall0 + (c - start) * 1000
                await asyncio.sleep(max(0, (t_phone - now_ms()) / 1000))
                await fws.send(pack_header(sent, t_phone) + jpeg)
                sent += 1

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
                    ffmpeg_binary(),
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
                    params={"call_id": call_id, "seg": 0, "t_start_phone_ms": t_seg0, "t_end_phone_ms": t_seg0 + 6000},
                    content=seg.read_bytes(),
                    headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"},
                )
            up_s = time.perf_counter() - t
            meta = r.json()
        await ctl.close()

    replay_check = None
    if check_replay:
        from gateway.tokens import mint

        service_token, _ = mint(e["TROPHY_TOKEN_SECRET"], gid, "engine", "service", 600)
        params = {"cam": cam, "t0": t_call_game - 4, "t1": t_call_game - 2}
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as http:
            auth = {"Authorization": f"Bearer {tok}"}
            clip = await http.get(f"/api/replay/{gid}/clip", params=params, headers=auth)
            clip.raise_for_status()
            overlay = await http.get(f"/api/replay/{gid}/overlay", params={**params, "call_id": call_id}, headers=auth)
            overlay.raise_for_status()
            crops = await http.get(
                f"/api/replay/{gid}/frames",
                params={**params, "n": 4},
                headers={"Authorization": f"Bearer {service_token}"},
            )
            crops.raise_for_status()
            manifest = await http.get(f"/api/watch/{gid}/manifest", headers=auth)
            manifest.raise_for_status()
            playlist = await http.get(manifest.json()["cams"][0]["hls_url"])
            playlist.raise_for_status()
            tracks = await http.get(f"/api/watch/{gid}/tracks", params={"cam": cam}, headers=auth)
            tracks.raise_for_status()
            assert tracks.json()["schema"] == "replay.tracks.v1"
            assert 1 <= len(crops.json()["frames"]) <= 4
            assert all(len(f["jpeg_b64"]) < 1_000_000 for f in crops.json()["frames"])
            replay_check = {
                "clip_bytes": len(clip.content),
                "crop_frames": len(crops.json()["frames"]),
                "max_crop_base64_bytes": max(len(f["jpeg_b64"]) for f in crops.json()["frames"]),
                "hls_playlist": playlist.status_code,
                "track_frames": len(tracks.json()["frames"]),
                "overlay_warnings": overlay.json()["warnings"],
            }
            print("replay check: " + json.dumps(replay_check))
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "game_id": gid,
                    "cam_id": cam,
                    "call_id": call_id,
                    "t_call_game_s": t_call_game,
                    "frames_sent": sent,
                    "source": path.name,
                    "synthetic_call": True,
                    "replay": replay_check,
                },
                indent=2,
            )
            + "\n"
        )

    rows = redis.Redis.from_url(REDIS_URL).xrange(f"frames:{cam}")
    tsrv = [float(f[b"t_srv_ms"]) for _, f in rows]
    span = (tsrv[-1] - tsrv[0]) / 1000 if len(tsrv) > 1 else 0
    print(f"game {gid} cam {cam}: streamed {sent} frames of {path.name} [{start:.1f}-{start + seconds:.1f}s]")
    fps = (len(rows) - 1) / span if span else 0
    size = f"{rows[-1][1][b'w'].decode()}x{rows[-1][1][b'h'].decode()}"
    print(f"gateway kept {len(rows)} frames: {fps:.1f} fps over {span:.1f}s, w,h={size}")
    print(
        f"HQ replay segment: HTTP {r.status_code}, {meta.get('w')}x{meta.get('h')} {meta.get('codec')}, "
        f"{meta.get('bytes', 0) / 1e6:.1f} MB, {meta.get('duration_s')} s, upload {up_s:.2f} s (localhost), "
        f"game {meta.get('t_game_start_s', 0):.2f}-{meta.get('t_game_end_s', 0):.2f}s vs call at {t_call_game:.2f}s"
    )
    print(f"call {call_id}; use the local game session to review it (join credentials are not logged)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("--start", type=float, default=5.0)
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--stdb", default=STDB)
    ap.add_argument("--module", default=MODULE)
    ap.add_argument("--redis-url", default=REDIS_URL)
    ap.add_argument("--env-file", type=Path, default=ENV_PATH)
    ap.add_argument("--check-replay", action="store_true")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    if a.check_replay and a.seconds < 6:
        ap.error("--check-replay requires at least 6 seconds")
    BASE, STDB, MODULE, REDIS_URL, ENV_PATH = a.base, a.stdb, a.module, a.redis_url, a.env_file
    asyncio.run(main(a.clip, a.start, a.seconds, a.check_replay, a.report))
