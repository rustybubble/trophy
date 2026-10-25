"""Upload a clip and referee it end to end (the dashboard's "Upload a clip" panel).

    POST /api/demo/uploads?name=<file>         body = the video (mp4 | quicktime | webm); judge/display token
    GET  /api/demo/uploads/{game}/{id}/{name}  frame0.jpg or the video (?token= for <img>/<video>)
    POST /api/demo/runs {upload_id, corners[4][2], ball, speed}
    GET  /api/demo/runs/{run_id}

A run is two subprocesses in the background: flight's `clip2l1` (classical 2D ball track + the four-corner
homography -> a layer-1 log; `services/flight/.venv`) and the engine's `trophy-play --samples` (the golden sport
module turns the log into bounce/contact/ball_dead events, published on Redis `ev:flight`, paced by the clip's
clock; `services/engine/.venv`). The live `trophy-engine` consumes them like perception's events, so the calls and
score land in Spacetime for the game and show on the dashboard and phones. Uploads live in
`data/local/uploads/<game>/` (gitignored). One camera, tapped corners, no clock sync: every call is BETA at most and
nothing here measures accuracy.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import Settings
from .tokens import Claims, TokenError, verify

UPLOAD_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}
UPLOAD_MAX_BYTES = 1024 * 1024 * 1024
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


def _id(n: int = 8) -> str:
    return "".join(secrets.choice(CROCKFORD) for _ in range(n))


class RunBody(BaseModel):
    upload_id: str = Field(pattern=r"^u_[0-9a-z]{8}$")
    corners: list[list[float]] = Field(min_length=4, max_length=4)
    ball: str = Field("white", pattern=r"^(white|orange)$")
    speed: float = Field(1.0, ge=0.25, le=8)


def demo_router(st: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/demo")
    runs: dict[str, dict[str, Any]] = {}

    def claims(token: str | None, authorization: str | None) -> Claims:
        raw = token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
        if not raw:
            raise HTTPException(401, "missing token")
        try:
            return verify(st.token_secret, raw)
        except TokenError as e:
            raise HTTPException(401, str(e)) from None

    def updir(game_id: str, upload_id: str) -> Path:
        return st.data_dir / "uploads" / game_id / upload_id

    def meta_of(game_id: str, upload_id: str) -> dict[str, Any]:
        p = updir(game_id, upload_id) / "upload.json"
        if not p.exists():
            raise HTTPException(404, "no such upload")
        return json.loads(p.read_text("utf8"))

    async def flight(*args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            str(st.flight_python),
            "-m",
            *args,
            cwd=str(st.flight_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out.decode("utf8", "replace"), err.decode("utf8", "replace")

    async def codec_of(path: Path) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            return out.decode().strip().split(",")[0]
        except (TimeoutError, OSError):
            return ""

    async def browser_copy(src: Path, dst: Path) -> bool:
        """Chromium plays H.264/VP9/AV1 only: MPEG-4 part 2 (OpenCV's mp4v) and HEVC (.mov from an iPhone) get an H.264
        copy next to the original, which stays the file flight tracks."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(src),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(dst),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await asyncio.wait_for(proc.communicate(), timeout=600)
            return proc.returncode == 0 and dst.exists()
        except (TimeoutError, OSError):
            return False

    @router.post("/uploads", status_code=201)
    async def upload(
        request: Request, name: str = "clip.mp4", authorization: str | None = Header(None)
    ) -> dict[str, Any]:
        c = claims(None, authorization)
        if not (c.has("judge") or c.has("display")):
            raise HTTPException(403, "only the judge/dashboard uploads clips")
        ctype = (request.headers.get("content-type") or "").split(";")[0].strip()
        if ctype not in UPLOAD_TYPES:
            raise HTTPException(415, f"clip type must be one of {sorted(UPLOAD_TYPES)}")
        upload_id = "u_" + _id()
        d = updir(c.game_id, upload_id)
        d.mkdir(parents=True, exist_ok=True)
        video = d / f"clip.{UPLOAD_TYPES[ctype]}"
        size = 0
        with video.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > UPLOAD_MAX_BYTES:
                    f.close()
                    video.unlink(missing_ok=True)
                    raise HTTPException(413, "clip too large")
                f.write(chunk)
        if size == 0:
            video.unlink(missing_ok=True)
            raise HTTPException(422, "empty clip")
        code, out, err = await flight("flight.cloud", "frame0", "--video", str(video), "--out", str(d / "frame0.jpg"))
        if code != 0:
            raise HTTPException(422, f"could not read the clip: {err.strip()[-300:] or out.strip()[-300:]}")
        info: dict[str, Any] = {}
        try:  # "wrote X (1280x720 @ 29.97 fps, 900 frames)"
            dims, rest = out.split("(", 1)[1].split("@")
            w, h = (int(v) for v in dims.strip().split("x"))
            fps = float(rest.split("fps")[0])
            frames = int(rest.split(",")[1].split("frames")[0])
            info = {"width": w, "height": h, "fps": fps, "frames": frames, "duration_s": frames / fps if fps else None}
        except (ValueError, IndexError):
            pass
        codec = await codec_of(video)
        playable = video.name
        if codec and codec not in ("h264", "vp9", "av1", "vp8") and await browser_copy(video, d / "play.mp4"):
            playable = "play.mp4"
        base = f"/api/demo/uploads/{c.game_id}/{upload_id}"
        meta = {
            "upload_id": upload_id,
            "game_id": c.game_id,
            "name": name[:120],
            "bytes": size,
            "mime": ctype,
            "video": video.name,
            "uploaded_at_ms": time.time() * 1000,
            "frame_url": f"{base}/frame0.jpg",
            "video_url": f"{base}/{playable}",
            "codec": codec,
            "transcoded": playable != video.name,
            **info,
        }
        (d / "upload.json").write_text(json.dumps(meta), encoding="utf8")
        return meta

    @router.get("/uploads/{game_id}/{upload_id}/{name}")
    async def file(
        game_id: str, upload_id: str, name: str, token: str | None = None, authorization: str | None = Header(None)
    ) -> FileResponse:
        c = claims(token, authorization)
        if game_id != c.game_id and not c.has("service"):
            raise HTTPException(403, "uploads of another game")
        if name not in ("frame0.jpg", "clip.mp4", "clip.mov", "clip.webm", "play.mp4"):
            raise HTTPException(404, "no such file")
        path = updir(game_id, upload_id) / name
        if not path.exists():
            raise HTTPException(404, "no such file")
        by_ext = {v: k for k, v in UPLOAD_TYPES.items()}
        mime = "image/jpeg" if name.endswith(".jpg") else by_ext[name.rsplit(".", 1)[1]]
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

    async def execute(
        run: dict[str, Any], meta: dict[str, Any], body: RunBody, t_offset_s: float, t0_ms: float
    ) -> None:
        d = updir(run["game_id"], body.upload_id)
        log: list[str] = run["log"]
        try:
            run["status"], run["stage"] = "tracking", "tracking the ball (flight, classical detector)"
            corners = ",".join(f"{v:.1f}" for xy in body.corners for v in xy[:2])
            code, out, err = await flight(
                "flight.clip2l1",
                "--video",
                str(d / meta["video"]),
                "--corners",
                corners,
                "--out",
                str(d / "l1"),
                "--name",
                "clip",
                "--game-id",
                run["game_id"],
                "--ball",
                body.ball,
            )
            log.extend(line for line in err.strip().splitlines()[-8:] if line)
            if code != 0:
                raise RuntimeError(f"tracking failed: {err.strip()[-400:] or out.strip()[-400:]}")
            run["meta"] = json.loads(out.strip().splitlines()[-1])
            run["stage"] = f"tracked {run['meta']['samples']} samples; replaying into the engine"
            run["status"], run["play_started_at_ms"] = "playing", time.time() * 1000
            proc = await asyncio.create_subprocess_exec(
                str(st.engine_python),
                "-m",
                "trophy_engine.play",
                "--game",
                run["game_id"],
                "--samples",
                str(d / "l1"),
                "--speed",
                str(body.speed),
                "--first-server",
                "A",
                "--t-offset",
                f"{t_offset_s:.3f}",
                "--t0-ms",
                f"{t0_ms:.3f}",
                cwd=str(st.engine_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout
            n_events = 0
            async for raw in proc.stdout:
                line = raw.decode("utf8", "replace").rstrip()
                if " trophy.play " in line:
                    line = line.split(" trophy.play ", 1)[1]
                if line.startswith("clip "):
                    n_events += 1
                    run["events"] = n_events
                log.append(line[:200])
                del log[:-40]
            code = await proc.wait()
            if code != 0:
                raise RuntimeError(f"replay exited with {code}")
            run["status"], run["stage"] = "done", f"done: {n_events} events fed to the engine"
        except Exception as e:  # noqa: BLE001 - reported on the run, the dashboard shows it
            run["status"], run["stage"], run["error"] = "failed", "failed", str(e)[:400]
        finally:
            run["finished_at_ms"] = time.time() * 1000
            (d / f"{run['run_id']}.json").write_text(json.dumps(run), encoding="utf8")

    @router.post("/runs", status_code=202)
    async def start(request: Request, body: RunBody, authorization: str | None = Header(None)) -> dict[str, Any]:
        c = claims(None, authorization)
        t0_raw = await request.app.state.r.hget(f"game:{c.game_id}", "t0_ms")
        t0_ms = float(t0_raw) if t0_raw else time.time() * 1000
        t_offset_s = max(0.0, (time.time() * 1000 - t0_ms) / 1000.0)  # the game clock keeps running between runs
        if not (c.has("judge") or c.has("display")):
            raise HTTPException(403, "only the judge/dashboard runs clips")
        meta = meta_of(c.game_id, body.upload_id)
        if any(r["status"] in ("queued", "tracking", "playing") for r in runs.values() if r["game_id"] == c.game_id):
            raise HTTPException(409, "a clip is already running in this game")
        run: dict[str, Any] = {
            "run_id": "r_" + _id(),
            "upload_id": body.upload_id,
            "game_id": c.game_id,
            "status": "queued",
            "stage": "queued",
            "speed": body.speed,
            "corners": body.corners,
            "ball": body.ball,
            "started_at_ms": time.time() * 1000,
            "log": [],
        }
        runs[run["run_id"]] = run
        asyncio.get_running_loop().create_task(execute(run, meta, body, t_offset_s, t0_ms))
        return run

    @router.get("/runs/{run_id}")
    async def status(run_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        c = claims(None, authorization)
        run = runs.get(run_id)
        if run is None or (run["game_id"] != c.game_id and not c.has("service")):
            raise HTTPException(404, "no such run")
        return run

    return router
