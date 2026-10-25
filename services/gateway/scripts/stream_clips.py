"""Stream recorded clips into a running game exactly as live camera phones would, in real time.

    uv run python scripts/stream_clips.py --game g_x --join-key K --clip a.mov:side:x1,y1,...,x4,y4 [--clip ...]
        [--mode simultaneous|sequential] [--offset LABEL=seconds] [--speed 1] [--start-in 2]

Each camera joins the game (POST /api/games/{g}/join, role cam), syncs its clock over /api/ws/ctl the way the PWA does,
saves its calibration (four table corners -> image->table homography, POST /api/cams/{cam}/calibration) and then
streams 1280x720 JPEG (libjpeg q70, 4:2:0, like the PWA) at 30 fps over /api/ws/frames, paced by the wall clock: the
frame shown at clip time c is sent at start + c. Nothing downstream knows these are files: the recorder archives the
frames, flight's live worker runs BlurBall on them as they arrive, the engine calls the points.

--mode simultaneous: every clip is its own camera and they all start together (angles of the same moment; per-clip
  --offset shifts a camera's clock so the angles line up).
--mode sequential: the clips are takes from one camera position, played back to back as one phone's feed.

Prints one JSON line per event (joined, calibrated, streaming, progress, done) on stdout for the gateway's run log.
Footage stays local; nothing is published.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import numpy as np
import websockets
from PIL import Image
from trophy.framebus import pack_header

W, H, FPS = 1280, 720, 30.0
LENGTH_M, WIDTH_M = 2.74, 1.525
# brief order: A-right, B-right, B-left, A-left (counter-clockwise seen from above), table-top centre at the origin
CORNERS_M = np.array(
    [
        [-LENGTH_M / 2, -WIDTH_M / 2],
        [LENGTH_M / 2, -WIDTH_M / 2],
        [LENGTH_M / 2, WIDTH_M / 2],
        [-LENGTH_M / 2, WIDTH_M / 2],
    ],
    float,
)


def say(**kw) -> None:
    print(json.dumps({"t_ms": round(time.time() * 1000), **kw}), flush=True)


def now_ms() -> float:
    return time.time() * 1000


@dataclass
class Clip:
    path: Path
    label: str
    corners_norm: list[tuple[float, float]] | None  # 0..1 of the displayed frame
    offset_s: float = 0.0
    corners_source: str = "tapped"  # auto[:N] (table_detection, N frames agree) | tapped


@dataclass
class Camera:
    label: str
    clips: list[Clip]
    cam_id: str = ""
    token: str = ""
    sent: int = 0
    stats: dict = field(default_factory=dict)


def dlt(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """The 3x3 homography taking src -> dst from four (or more) point pairs (normalised DLT)."""

    def norm(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        c = p.mean(axis=0)
        s = np.sqrt(2) / max(1e-12, np.mean(np.linalg.norm(p - c, axis=1)))
        T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
        return (np.c_[p, np.ones(len(p))] @ T.T)[:, :2], T

    a, Ta = norm(src)
    b, Tb = norm(dst)
    rows = []
    for (x, y), (u, v) in zip(a, b, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, sv, vt = np.linalg.svd(np.array(rows))
    if sv[-2] < 1e-9:
        raise ValueError("degenerate corners: three are on one line")
    Hn = vt[-1].reshape(3, 3)
    Hm = np.linalg.inv(Tb) @ Hn @ Ta
    return Hm / Hm[2, 2]


def apply(Hm: np.ndarray, pts: np.ndarray) -> np.ndarray:
    q = np.c_[pts, np.ones(len(pts))] @ Hm.T
    return q[:, :2] / q[:, 2:3]


def homography(corners_norm: list[tuple[float, float]]) -> tuple[list[float], float]:
    """Image px (the streamed 1280x720) -> table metres, and the RMS corner reprojection error in px."""
    px = np.array([[x * W, y * H] for x, y in corners_norm], float)
    Hm = dlt(px, CORNERS_M)
    err = float(np.sqrt(np.mean(np.sum((apply(np.linalg.inv(Hm), CORNERS_M) - px) ** 2, axis=1))))
    return [float(v) for v in Hm.ravel()], err


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


async def frames(path: Path, speed: float):
    """Decoded, auto-rotated, 30 fps, 1280x720 RGB frames with their clip time. VideoToolbox decodes HEVC/4K when
    available; ffmpeg falls back to software otherwise."""
    vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease:flags=area,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
    proc = await asyncio.create_subprocess_exec(
        ffmpeg(),
        "-v",
        "error",
        "-hwaccel",
        "videotoolbox",
        "-i",
        str(path),
        "-an",
        "-vf",
        vf,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
        stdout=asyncio.subprocess.PIPE,
        limit=W * H * 3 * 4,
    )
    assert proc.stdout
    n = 0
    try:
        while True:
            try:
                raw = await proc.stdout.readexactly(W * H * 3)
            except asyncio.IncompleteReadError:
                break
            yield n / FPS, raw
            n += 1
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()


def jpeg(raw: bytes) -> bytes:
    out = io.BytesIO()
    Image.frombytes("RGB", (W, H), raw).save(out, "JPEG", quality=70, subsampling=2)
    return out.getvalue()


async def clock_sync(base_ws: str, token: str) -> None:
    """The PWA's ping exchange: ten round trips so the gateway's ClockFit is ready before frames arrive."""
    async with websockets.connect(f"{base_ws}/api/ws/ctl?token={token}") as ctl:
        prev = None
        for _ in range(10):
            t0 = now_ms()
            await ctl.send(json.dumps({"type": "ping", "t0": t0, **({"prev": prev} if prev else {})}))
            pong = json.loads(await ctl.recv())
            if prev:
                await ctl.recv()
            prev = {"t0": t0, "t1": pong["t1"], "t2": pong["t2"], "t3": now_ms()}


async def join_and_calibrate(http: httpx.AsyncClient, base_ws: str, game: str, key: str, cam: Camera) -> None:
    j = (
        (
            await http.post(
                f"/api/games/{game}/join",
                json={"join_key": key, "label": cam.label, "role": "cam", "device": {"source": "recorded clip"}},
            )
        )
        .raise_for_status()
        .json()
    )
    cam.cam_id, cam.token = j["cam_id"], j["cam_token"]
    say(event="joined", label=cam.label, cam_id=cam.cam_id, clips=[c.path.name for c in cam.clips])
    await clock_sync(base_ws, cam.token)
    corners = next((c.corners_norm for c in cam.clips if c.corners_norm), None)
    if corners:
        H9, err = homography(corners)
        cal = {
            "schema": "trophy.calibration.v1",
            "game_id": game,
            "cam_id": cam.cam_id,
            "sport": "table_tennis",
            "created_at_ms": now_ms(),
            "image_size": {"w": W, "h": H},
            "method": corner_method(next((c.corners_source for c in cam.clips if c.corners_norm), "tapped")),
            "H_img_to_field": H9,
            "reproj_err_px": err,
            "trusted": False,
            "warnings": [
                "recorded clip streamed as a phone: corners from the clip itself, no live check, so calls cap at BETA"
            ],
            "solver": "stream_clips.homography",
        }
        r = await http.post(
            f"/api/cams/{cam.cam_id}/calibration", json=cal, headers={"Authorization": f"Bearer {cam.token}"}
        )
        r.raise_for_status()
        say(event="calibrated", label=cam.label, cam_id=cam.cam_id, reproj_px=round(err, 3))


async def stream(base_ws: str, cam: Camera, wall0_ms: float, speed: float) -> None:
    """Send each frame at wall0 + clip time (+ the clip's offset, + earlier takes in sequential mode)."""
    lag_max = 0.0
    async with websockets.connect(f"{base_ws}/api/ws/frames?token={cam.token}", max_size=None) as fws:
        t_base = 0.0
        for clip in cam.clips:
            say(event="streaming", label=cam.label, cam_id=cam.cam_id, clip=clip.path.name, at_s=round(t_base, 3))
            last_c = 0.0
            async for c, raw in frames(clip.path, speed):
                t_phone = wall0_ms + ((t_base + c + clip.offset_s) / speed) * 1000
                wait = (t_phone - now_ms()) / 1000
                if wait > 0:
                    await asyncio.sleep(wait)
                else:
                    lag_max = max(lag_max, -wait)
                data = await asyncio.to_thread(jpeg, raw)
                await fws.send(pack_header(cam.sent, t_phone, 0) + data)
                cam.sent += 1
                last_c = c
                if cam.sent % 150 == 0:
                    say(event="progress", label=cam.label, frames=cam.sent, lag_max_ms=round(lag_max * 1000, 1))
            t_base += last_c + 1 / FPS
    cam.stats = {"frames": cam.sent, "seconds": round(t_base, 2), "lag_max_ms": round(lag_max * 1000, 1)}
    say(event="done", label=cam.label, cam_id=cam.cam_id, **cam.stats)


def corner_method(source: str) -> str:
    """The calibration's `method` string: where the four corners came from (shown on the dashboard's camera panel)."""
    if source.startswith("auto"):
        n = source.split(":", 1)[1] if ":" in source else ""
        agree = f", {n} frames agree" if n else ""
        return f"four table corners detected automatically on the clip (table_detection{agree})"
    if source == "preset":
        return "four table corners from the clip library preset (data/local/clips/library)"
    return "four table corners tapped on the clip's first frame"


def parse_clip(s: str) -> Clip:
    parts = s.split(":")
    path = Path(parts[0])
    label = parts[1] if len(parts) > 1 and parts[1] else path.stem
    corners = None
    if len(parts) > 2 and parts[2]:
        v = [float(x) for x in parts[2].split(",")]
        if len(v) != 8:
            raise SystemExit(f"{s}: corners need 8 numbers")
        corners = [(v[i], v[i + 1]) for i in range(0, 8, 2)]
    return Clip(path, label, corners)


async def amain(a: argparse.Namespace) -> int:
    clips = [parse_clip(c) for c in a.clip]
    offsets = dict(kv.split("=", 1) for kv in a.offset or [])
    sources = dict(kv.split("=", 1) for kv in a.corners_source or [])
    for c in clips:
        c.offset_s = float(offsets.get(c.label, 0.0))
        c.corners_source = sources.get(c.label, "tapped")
    if a.mode == "sequential":
        cams = [Camera(a.label or clips[0].label, clips)]
    else:
        cams = [Camera(c.label, [c]) for c in clips]
    base_ws = a.gateway.replace("http", "ws", 1)
    async with httpx.AsyncClient(base_url=a.gateway, timeout=30) as http:
        for cam in cams:
            await join_and_calibrate(http, base_ws, a.game, a.join_key, cam)
    wall0 = now_ms() + a.start_in * 1000
    say(event="start", mode=a.mode, cameras=[c.cam_id for c in cams], wall0_ms=wall0, speed=a.speed)
    await asyncio.gather(*(stream(base_ws, cam, wall0, a.speed) for cam in cams))
    say(event="all_done", cameras={c.cam_id: c.stats for c in cams})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--join-key", required=True)
    ap.add_argument("--clip", action="append", required=True, help="PATH[:LABEL[:x1,y1,...,x4,y4]] corners 0..1")
    ap.add_argument("--mode", choices=["simultaneous", "sequential"], default="simultaneous")
    ap.add_argument("--label", default=None, help="the camera's label in sequential mode")
    ap.add_argument("--offset", action="append", help="LABEL=seconds added to that camera's clock (simultaneous)")
    ap.add_argument(
        "--corners-source",
        action="append",
        help="LABEL=auto[:N] | tapped: where the corners came from (auto = Mu Du's table_detection, N frames agree)",
    )
    ap.add_argument("--speed", type=float, default=1.0, help="1 = real time")
    ap.add_argument("--start-in", type=float, default=2.0, help="seconds before the first frame (all cameras)")
    ap.add_argument("--gateway", default="http://127.0.0.1:8000")
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
