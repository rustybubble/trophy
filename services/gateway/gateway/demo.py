"""Recorded clips, refereed as if they were being filmed live (the dashboard's "Clips as live cameras" panel).

    POST /api/demo/uploads?name=<file>         body = the video (mp4 | quicktime | webm); judge/display token
         -> {upload_id, width, height, fps, duration_s, recorded_at_ms, suggested_corners_norm, frame_url, video_url}
    GET  /api/demo/uploads/{game}/{id}/{name}  frame0.jpg (the first streamed frame) or play.mp4 (?token= for media)
    POST /api/demo/live {clips: [{upload_id, corners_norm[4][2], offset_s?}], mode: auto|simultaneous|sequential,
                         speed?}
    GET  /api/demo/live/{live_id}              status, per-camera schedule and progress
    GET  /api/demo/library                     preloaded multi-camera games (data/local/clips/library/<id>/preset.json)
    GET  /api/demo/library/{id}/{label}/frame0.jpg   a preset camera's first streamed frame (?token= for media)
    POST /api/demo/library/{id}/live {speed?, first_server?}   stream a preset's cameras into this game, no upload

Going live starts the game (start_game) and runs `scripts/stream_clips.py`: every clip joins the game as a camera
phone, syncs its clock, saves its calibration (the four corners) and streams 1280x720 JPEG at 30 fps over the same
/api/ws/frames socket a phone uses, paced by the wall clock. Downstream nothing knows these are files: the recorder
archives the frames, flight's live worker runs BlurBall on each frame as it arrives, `trophy-live` runs the golden
sport module over the ball tracks, the engine calls the points and the phones speak them.

mode auto: clips whose recordings overlap in time (from the files' own creation timestamps) are angles of the same
moment and stream together, aligned by those timestamps (plus offset_s); clips that don't overlap are takes from one
camera position and stream back to back as one phone. Tapped corners are never auto-checked, so calibration is
untrusted and every call is BETA at most. Uploads stay in data/local/uploads/<game>/ (gitignored).

A library preset is a folder with the camera files and a preset.json ({preset_id, title, sport, source, license,
notes, mode, cameras: [{label, video, corners_norm[4][2], offset_s}]}, built by scripts/build_library.py). Playing one
streams the same way as uploads do, so BlurBall, the sport module and the engine recompute every call on each run;
nothing is cached but the files themselves.
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from trophy.streams import CTL_ENGINE, CTL_STREAM_MAXLEN, make_ctl

from .config import ROOT, Settings
from .tokens import Claims, TokenError, verify

UPLOAD_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}
UPLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
W, H = 1280, 720  # what stream_clips.py sends; frame0.jpg and play.mp4 use the same scaling, so taps map 1:1
VF = f"fps=30,scale={W}:{H}:force_original_aspect_ratio=decrease:flags=area,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
SERVE_ANALYSIS = ROOT / "spikes" / "serve-analysis"


def _id(n: int = 8) -> str:
    return "".join(secrets.choice(CROCKFORD) for _ in range(n))


class LiveClip(BaseModel):
    upload_id: str = Field(pattern=r"^u_[0-9a-z]{8}$")
    corners_norm: list[list[float]] = Field(min_length=4, max_length=4)
    offset_s: float = 0.0


class LiveBody(BaseModel):
    clips: list[LiveClip] = Field(min_length=1, max_length=6)
    mode: Literal["auto", "simultaneous", "sequential"] = "auto"
    speed: float = Field(1.0, ge=0.25, le=4)
    first_server: str = "A"


class LibraryLiveBody(BaseModel):
    speed: float = Field(1.0, ge=0.25, le=4)
    first_server: str = "A"


LABEL_RE = r"^[a-z0-9_-]{1,24}$"


def load_presets(library: Path) -> list[dict[str, Any]]:
    """Every valid preset.json under the library dir (sorted by id); invalid ones are listed with an `error`."""
    out: list[dict[str, Any]] = []
    if not library.is_dir():
        return out
    for d in sorted(p for p in library.iterdir() if p.is_dir()):
        pj = d / "preset.json"
        if not pj.exists():
            continue
        try:
            m = json.loads(pj.read_text("utf8"))
            cams = m["cameras"]
            if not cams or len(cams) > 6:
                raise ValueError("1-6 cameras")
            for cam in cams:
                if not re.match(LABEL_RE, str(cam.get("label", ""))):
                    raise ValueError(f"bad camera label {cam.get('label')!r}")
                if not (d / cam["video"]).is_file():
                    raise ValueError(f"{cam['video']} is missing")
                corners = cam["corners_norm"]
                if len(corners) != 4 or any(len(xy) != 2 for xy in corners):
                    raise ValueError(f"{cam['label']}: corners_norm needs 4 [x, y] pairs")
            out.append({**m, "preset_id": d.name, "dir": str(d)})
        except (KeyError, ValueError, TypeError) as e:
            out.append({"preset_id": d.name, "title": d.name, "cameras": [], "error": str(e), "dir": str(d)})
    return out


async def run(*cmd: str, timeout: float = 600, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(cwd) if cwd else None, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return 124, "", "timeout"
    return proc.returncode or 0, out.decode("utf8", "replace"), err.decode("utf8", "replace")


async def probe(path: Path) -> dict[str, Any]:
    code, out, _ = await run(
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,codec_name,width,height,avg_frame_rate:stream_side_data=rotation:format=duration:format_tags",
        "-of", "json", str(path), timeout=30,
    )  # fmt: skip
    if code:
        return {}
    d = json.loads(out or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    tags = {k.lower(): v_ for k, v_ in (d.get("format", {}).get("tags") or {}).items()}
    num, _, den = str(v.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    rot = next((sd.get("rotation") for sd in v.get("side_data_list", []) if "rotation" in sd), 0) or 0
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if abs(int(rot)) in (90, 270):
        w, h = h, w
    recorded = None
    for key in ("com.apple.quicktime.creationdate", "creation_time"):
        if tags.get(key):
            try:
                recorded = datetime.fromisoformat(tags[key].replace("Z", "+00:00")).timestamp() * 1000
                break
            except ValueError:
                pass
    return {
        "codec": v.get("codec_name"),
        "width": w,
        "height": h,
        "fps": round(fps, 3),
        "duration_s": float(d.get("format", {}).get("duration") or 0) or None,
        "recorded_at_ms": recorded,
        "device": tags.get("com.apple.quicktime.model"),
    }


def plan(clips: list[dict[str, Any]], mode: str) -> tuple[str, list[dict[str, Any]], str]:
    """Decide simultaneous vs sequential and each clip's start, from the recordings' own timestamps."""
    reason = ""
    if mode == "auto":
        timed = [c for c in clips if c.get("recorded_at_ms") is not None and c.get("duration_s")]
        if len(clips) == 1:
            mode, reason = "simultaneous", "one clip"
        elif len(timed) == len(clips):
            spans = sorted((c["recorded_at_ms"], c["recorded_at_ms"] + c["duration_s"] * 1000) for c in timed)
            overlap = all(spans[i + 1][0] < spans[i][1] for i in range(len(spans) - 1))
            mode = "simultaneous" if overlap else "sequential"
            reason = (
                "the recordings overlap in time: angles of the same moment"
                if overlap
                else "the recordings don't overlap in time: takes from one camera, played back to back"
            )
        else:
            mode, reason = "simultaneous", "no recording timestamps: assumed angles of the same moment"
    if mode == "sequential":
        clips = sorted(clips, key=lambda c: c.get("recorded_at_ms") or 0)
    elif all(c.get("recorded_at_ms") is not None for c in clips):  # align angles by their start times
        t0 = min(c["recorded_at_ms"] for c in clips)
        for c in clips:
            c["auto_offset_s"] = round((c["recorded_at_ms"] - t0) / 1000, 3)
    return mode, clips, reason or f"chosen: {mode}"


def demo_router(st: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/demo")
    lives: dict[str, dict[str, Any]] = {}

    def claims(token: str | None, authorization: str | None) -> Claims:
        raw = token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
        if not raw:
            raise HTTPException(401, "missing token")
        try:
            return verify(st.token_secret, raw)
        except TokenError as e:
            raise HTTPException(401, str(e)) from None

    def judge(authorization: str | None) -> Claims:
        c = claims(None, authorization)
        if not (c.has("judge") or c.has("display")):
            raise HTTPException(403, "only the judge/dashboard can do this")
        return c

    def updir(game_id: str, upload_id: str) -> Path:
        return st.data_dir / "uploads" / game_id / upload_id

    library = st.data_dir / "clips" / "library"

    def meta_of(game_id: str, upload_id: str) -> dict[str, Any]:
        p = updir(game_id, upload_id) / "upload.json"
        if not p.exists():
            raise HTTPException(404, f"no such upload {upload_id}")
        return json.loads(p.read_text("utf8"))

    async def suggest_corners(video: Path) -> dict[str, Any] | None:
        py = SERVE_ANALYSIS / ".venv" / "bin" / "python"
        if not py.exists():
            return None
        code, out, _ = await run(
            str(py), "scripts/suggest_table_corners.py", str(video), "--width", str(W), cwd=SERVE_ANALYSIS, timeout=60
        )
        if code:
            return None
        try:
            d = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return d if d.get("corners_norm") else None

    @router.post("/uploads", status_code=201)
    async def upload(
        request: Request, name: str = "clip.mp4", authorization: str | None = Header(None)
    ) -> dict[str, Any]:
        c = judge(authorization)
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
        info = await probe(video)
        if not info.get("width"):
            raise HTTPException(422, "could not read the clip (no video stream)")
        # the first frame and a browser preview, scaled exactly as the stream will be (so corner taps map 1:1)
        frame_cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            VF,
            str(d / "frame0.jpg"),
        ]
        prev_cmd = [
            "ffmpeg", "-v", "error", "-y", "-hwaccel", "videotoolbox", "-i", str(video), "-an", "-vf", VF,
            "-c:v", "h264_videotoolbox", "-b:v", "6M", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(d / "play.mp4"),
        ]  # fmt: skip
        (code, _, err), (pcode, _, perr), corners = await asyncio.gather(
            run(*frame_cmd, timeout=60), run(*prev_cmd, timeout=900), suggest_corners(video)
        )
        if code:
            raise HTTPException(422, f"could not read the clip: {err.strip()[-300:]}")
        if pcode:  # no VideoToolbox (not a Mac): software H.264
            sw = [*prev_cmd[:5], *prev_cmd[7:]]
            sw[sw.index("h264_videotoolbox")] = "libx264"
            pcode, _, perr = await run(*sw, timeout=900)
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
            "video_url": f"{base}/play.mp4" if not pcode else None,
            "stream_size": {"w": W, "h": H},
            "suggested_corners_norm": (corners or {}).get("corners_norm"),
            "corner_suggestion": {k: v for k, v in (corners or {}).items() if k != "corners_norm"} or None,
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
        if name not in ("frame0.jpg", "play.mp4"):
            raise HTTPException(404, "no such file")
        path = updir(game_id, upload_id) / name
        if not path.exists():
            raise HTTPException(404, "no such file")
        mime = "image/jpeg" if name.endswith(".jpg") else "video/mp4"
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

    async def stream(live: dict[str, Any], args: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ROOT / "services" / "gateway" / "scripts" / "stream_clips.py"),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        live["pid"] = proc.pid
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode("utf8", "replace").strip()
            try:
                ev = json.loads(line)
            except ValueError:
                live["log"].append(line[:300])
                del live["log"][:-20]
                continue
            kind = ev.get("event")
            if kind == "joined":
                live["cameras"][ev["label"]] = {"cam_id": ev["cam_id"], "clips": ev["clips"], "frames": 0}
            elif kind == "calibrated":
                live["cameras"].setdefault(ev["label"], {})["reproj_px"] = ev.get("reproj_px")
            elif kind == "start":
                live["status"], live["wall0_ms"] = "streaming", ev["wall0_ms"]
            elif kind == "streaming":
                cam = live["cameras"].setdefault(ev["label"], {})
                cam.setdefault("schedule", []).append({"clip": ev["clip"], "at_s": ev["at_s"]})
                cam["now_playing"] = ev["clip"]
            elif kind in ("progress", "done"):
                live["cameras"].setdefault(ev["label"], {}).update(
                    {k: ev[k] for k in ("frames", "lag_max_ms", "seconds") if k in ev}
                )
        code = await proc.wait()
        live["status"] = "done" if code == 0 else "failed"
        if code:
            live["error"] = "; ".join(live["log"][-3:]) or f"streamer exited with {code}"
        live["finished_at_ms"] = time.time() * 1000

    async def launch(
        c: Claims,
        r: Any,
        mode: str,
        speed: float,
        first_server: str,
        cams: list[dict[str, Any]],
        **extra: Any,
    ) -> dict[str, Any]:
        """Start the game and stream `cams` ([{video: Path, label, corners_norm, offset_s, name, ...}]) into it."""
        if any(v["status"] in ("starting", "streaming") for v in lives.values() if v["game_id"] == c.game_id):
            raise HTTPException(409, "this game is already streaming clips")
        key = await r.hget(f"game:{c.game_id}", "join_key")
        if not key:
            raise HTTPException(404, "no such game")
        args = ["--game", c.game_id, "--join-key", key.decode(), "--mode", mode, "--speed", str(speed)]
        args += ["--gateway", f"http://127.0.0.1:{st.port}"]  # this gateway, whatever PORT_OFFSET is
        for m in cams:
            corners = ",".join(f"{v:.6f}" for xy in m["corners_norm"] for v in xy[:2])
            args += ["--clip", f"{m['video']}:{m['label']}:{corners}"]
            if mode == "simultaneous" and m.get("offset_s"):
                args += ["--offset", f"{m['label']}={m['offset_s']}"]
            # where the corners came from: the detector's (Mu Du's table_detection suggests them at upload time; the
            # dashboard only asks for taps when it found nothing), the judge's taps, or a library preset
            src = m.get("corners_source")
            if src is None:
                sugg = m.get("suggested_corners_norm") or []
                auto = len(sugg) == 4 and all(
                    abs(float(a[k]) - float(b[k])) < 1e-4
                    for a, b in zip(m["corners_norm"], sugg, strict=True)
                    for k in (0, 1)
                )
                frames = (m.get("corner_suggestion") or {}).get("agreeing_frames")
                src = ("auto" + (f":{frames}" if frames else "")) if auto else "tapped"
            args += ["--corners-source", f"{m['label']}={src}"]
        if mode == "sequential":
            args += ["--label", "camera (recorded takes)"]
        # the game goes live: the engine opens rallies as events arrive
        cmd = make_ctl("start_game", c.game_id, {"first_server": first_server}, by_cam_id=c.cam_id)
        await r.xadd(
            CTL_ENGINE, {"json": cmd.model_dump_json(by_alias=True)}, maxlen=CTL_STREAM_MAXLEN, approximate=True
        )
        live = {
            "live_id": "l_" + _id(),
            "game_id": c.game_id,
            "status": "starting",
            "mode": mode,
            "speed": speed,
            "clips": [
                {k: m.get(k) for k in ("upload_id", "label", "name", "video_url", "duration_s", "offset_s")}
                for m in cams
            ],
            "cameras": {},
            "log": [],
            "started_at_ms": time.time() * 1000,
            **extra,
        }
        lives[live["live_id"]] = live
        asyncio.get_running_loop().create_task(stream(live, args))
        return live

    @router.post("/live", status_code=202)
    async def go_live(request: Request, body: LiveBody, authorization: str | None = Header(None)) -> dict[str, Any]:
        c = judge(authorization)
        metas = []
        for cl in body.clips:
            m = meta_of(c.game_id, cl.upload_id)
            metas.append({**m, "corners_norm": cl.corners_norm, "offset_s": cl.offset_s})
        mode, ordered, reason = plan(metas, body.mode)
        cams = []
        for i, m in enumerate(ordered):
            label = f"cam{i + 1}" if mode == "simultaneous" else f"take{i + 1}"
            cams.append(
                {
                    **m,
                    "label": label,
                    "video": updir(c.game_id, m["upload_id"]) / m["video"],
                    "offset_s": m.get("auto_offset_s", 0.0) + m.get("offset_s", 0.0),
                }
            )
        return await launch(c, request.app.state.r, mode, body.speed, body.first_server, cams, mode_reason=reason)

    def preset_of(preset_id: str) -> dict[str, Any]:
        p = next((p for p in load_presets(library) if p["preset_id"] == preset_id), None)
        if p is None:
            raise HTTPException(404, f"no such preset {preset_id}")
        if p.get("error"):
            raise HTTPException(422, f"preset {preset_id}: {p['error']}")
        return p

    def public(p: dict[str, Any]) -> dict[str, Any]:
        base = f"/api/demo/library/{p['preset_id']}"
        return {
            k: v
            for k, v in {
                **p,
                "cameras": [
                    {**cam, "frame_url": f"{base}/{cam['label']}/frame0.jpg", "video": None} for cam in p["cameras"]
                ],
            }.items()
            if k != "dir"
        }

    @router.get("/library")
    async def library_list(authorization: str | None = Header(None)) -> dict[str, Any]:
        """Preloaded multi-camera games: pick one and play it, no upload. Footage stays local."""
        judge(authorization)
        return {"library_dir": str(library), "presets": [public(p) for p in load_presets(library)]}

    @router.get("/library/{preset_id}/{label}/frame0.jpg")
    async def library_frame(
        preset_id: str, label: str, token: str | None = None, authorization: str | None = Header(None)
    ) -> FileResponse:
        claims(token, authorization)
        p = preset_of(preset_id)
        cam = next((x for x in p["cameras"] if x["label"] == label), None)
        if cam is None:
            raise HTTPException(404, "no such camera")
        d = Path(p["dir"])
        out = d / f"frame0_{label}.jpg"
        if not out.exists():  # the first frame scaled exactly as the stream will be (built once, kept)
            code, _, err = await run(
                "ffmpeg", "-v", "error", "-y", "-i", str(d / cam["video"]), "-frames:v", "1", "-vf", VF, str(out),
                timeout=60,
            )  # fmt: skip
            if code:
                raise HTTPException(500, f"could not read {cam['video']}: {err.strip()[-200:]}")
        return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @router.post("/library/{preset_id}/live", status_code=202)
    async def library_live(
        preset_id: str, request: Request, body: LibraryLiveBody, authorization: str | None = Header(None)
    ) -> dict[str, Any]:
        """Stream a preset's cameras into this game as phones. Nothing is precomputed: the tracker, the sport module
        and the engine run on the frames as they arrive, every time."""
        c = judge(authorization)
        p = preset_of(preset_id)
        d = Path(p["dir"])
        mode = p.get("mode", "simultaneous")
        cams = [
            {
                "label": cam["label"],
                "name": f"{p.get('title', preset_id)} · {cam['label']}",
                "video": d / cam["video"],
                "corners_norm": cam["corners_norm"],
                "offset_s": float(cam.get("offset_s", 0.0)),
                "duration_s": cam.get("duration_s"),
                "corners_source": cam.get("corners_source", "preset"),
            }
            for cam in p["cameras"]
        ]
        return await launch(
            c, request.app.state.r, mode, body.speed, body.first_server, cams,
            mode_reason=f"preloaded game: {p.get('title', preset_id)}", preset_id=preset_id,
            source=p.get("source"), license=p.get("license"),
        )  # fmt: skip

    @router.get("/cams/{cam_id}/live")
    async def cam_live(cam_id: str, request: Request, authorization: str | None = Header(None)) -> Response:
        """The camera's newest streamed frame, with BlurBall's detection for that frame (X-Ball: x,y,score or none).
        The dashboard polls it to show what the referee sees, live."""
        c = claims(None, authorization)
        r = request.app.state.r
        if (await r.hget(f"cam:{cam_id}", "game_id") or b"").decode() != c.game_id:
            raise HTTPException(403, "camera belongs to another game")
        got = await r.xrevrange(f"frames:{cam_id}", count=1)
        if not got:
            raise HTTPException(404, "no frames yet")
        f = {(k.decode() if isinstance(k, bytes) else k): v for k, v in got[0][1].items()}
        seq = int(f["seq"])
        ball, ball_seq, lag = "none", None, None
        for _, tf in await r.xrevrange(f"trk:ball:{cam_id}", count=12):
            d = json.loads(tf[b"json"])
            if d["seq"] <= seq:  # the newest processed frame at or before this one
                ball_seq, lag = d["seq"], seq - d["seq"]
                if d.get("px"):
                    ball = f"{d['px'][0]:.1f},{d['px'][1]:.1f},{d.get('conf', 0):.2f}"
                break
        return Response(
            f["data"],
            media_type="image/jpeg",
            headers={
                "X-Seq": str(seq),
                "X-T-Game": f["t_game_s"].decode() if isinstance(f["t_game_s"], bytes) else str(f["t_game_s"]),
                "X-Ball": ball,
                "X-Ball-Seq": str(ball_seq) if ball_seq is not None else "",
                "X-Ball-Lag-Frames": str(lag) if lag is not None else "",
                "Access-Control-Expose-Headers": "X-Seq, X-T-Game, X-Ball, X-Ball-Seq, X-Ball-Lag-Frames",
                "Cache-Control": "no-store",
            },
        )

    @router.get("/live/{live_id}")
    async def live_status(live_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        c = claims(None, authorization)
        live = lives.get(live_id)
        if live is None or (live["game_id"] != c.game_id and not c.has("service")):
            raise HTTPException(404, "no such live session")
        return live

    return router
