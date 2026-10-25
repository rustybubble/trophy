"""Replayed-feed scenarios for the judging demo (D-42, docs/plan/judging-demo.md).

A scenario (data/scenarios/<id>/scenario.yaml) is one or more recorded angles of the same moment, plus hand-annotated
events for sports with no perception (D-44). Going live:

1. every angle is trimmed once to a phone-playable 1280x720 30 fps H.264 + AAC file (cached under data/local);
2. the engine gets ctl `feed_schedule` (sport, teams, feeds): it resets the game to the scenario's sport and writes one
   Spacetime `feed` row per angle, so every phone can play its angle at the scheduled server time;
3. stream_clips.py streams the same files into frames:{cam} as camera phones, so the referee sees exactly what a
   phone would send; annotated events are published on the same clock by the annotation feeder.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from trophy.streams import CTL_ENGINE, CTL_STREAM_MAXLEN, make_ctl

from .config import ROOT, Settings
from .tokens import Claims, TokenError, verify

SCENARIOS_DIR = ROOT / "data" / "scenarios"
W, H, FPS = 1280, 720, 30
START_IN_S = 4.0  # countdown on the phones before the first frame
VF = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease:flags=area,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"


class ScenarioBody(BaseModel):
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    speed: float = Field(1.0, gt=0.1, le=4.0)


def load_scenarios(root: Path = SCENARIOS_DIR) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(root.glob("*/scenario.yaml")):
        try:
            s = yaml.safe_load(p.read_text("utf8")) or {}
        except yaml.YAMLError:
            continue
        if s.get("id") and s.get("angles"):
            s["_dir"] = p.parent
            out[s["id"]] = s
    return out


def media_path(st: Settings, sid: str, label: str) -> Path:
    return st.data_dir / "scenarios" / sid / "play" / f"{label}.mp4"


def source_path(angle: dict[str, Any]) -> Path:
    f = Path(angle["file"])
    return f if f.is_absolute() else ROOT / f


def summary(s: dict[str, Any], st: Settings) -> dict[str, Any]:
    angles = [
        {"label": a["label"], "ready": source_path(a).exists() or media_path(st, s["id"], a["label"]).exists()}
        for a in s["angles"]
    ]
    return {
        "id": s["id"],
        "title": s.get("title", s["id"]),
        "sport": s.get("sport", "table_tennis"),
        "source": s.get("source", "team_recording"),
        "credit": s.get("credit"),
        "annotated": bool(s.get("annotated")),
        "teams": s.get("teams") or [],
        "angles": angles,
        "ready": all(a["ready"] for a in angles),
    }


async def run(*cmd: str, timeout: float = 600) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        return 124, "timeout"
    return proc.returncode or 0, out.decode("utf8", "replace")


async def prepare(st: Settings, s: dict[str, Any], angle: dict[str, Any]) -> Path:
    """Trim one angle to [start_s, start_s + duration_s] as the file both the phones and the streamer play."""
    out = media_path(st, s["id"], angle["label"])
    src = source_path(angle)
    if out.exists() and (not src.exists() or out.stat().st_mtime >= src.stat().st_mtime):
        return out
    if not src.exists():
        raise HTTPException(409, f"scenario {s['id']}: media for angle {angle['label']} is missing ({angle['file']})")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.mp4")
    trim = ["-ss", str(float(angle.get("start_s", 0)))]
    if angle.get("duration_s"):
        trim += ["-t", str(float(angle["duration_s"]))]
    tail = ["-vf", VF, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)]
    hw = ["ffmpeg", "-v", "error", "-y", *trim, "-i", str(src), "-c:v", "h264_videotoolbox", "-b:v", "5M", *tail]
    code, err = await run(*hw)
    if code:  # no VideoToolbox (not a Mac): software H.264
        sw = ["ffmpeg", "-v", "error", "-y", *trim, "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", *tail]
        code, err = await run(*sw)
    if code:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"could not prepare {angle['label']}: {err.strip()[-300:]}")
    tmp.replace(out)
    return out


def scenario_router(st: Settings) -> APIRouter:
    router = APIRouter(prefix="/api")
    runs: dict[str, dict[str, Any]] = {}  # game_id -> the current replay run

    def claims(token: str | None, authorization: str | None) -> Claims:
        raw = token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
        if not raw:
            raise HTTPException(401, "missing token")
        try:
            return verify(st.token_secret, raw)
        except TokenError as e:
            raise HTTPException(401, str(e)) from None

    def judge(c: Claims, game_id: str) -> None:
        if c.game_id != game_id:
            raise HTTPException(403, "token for another game")
        if not (c.has("judge") or c.has("display")):
            raise HTTPException(403, "only a judge or display can start a scenario")

    async def ctl(r: Any, cmd: str, game_id: str, args: dict[str, Any], by: str | None = None) -> None:
        c = make_ctl(cmd, game_id, args, by_cam_id=by)
        await r.xadd(CTL_ENGINE, {"json": c.model_dump_json(by_alias=True)}, maxlen=CTL_STREAM_MAXLEN, approximate=True)

    def feeds_of(live: dict[str, Any], status: str) -> list[dict[str, Any]]:
        s = live["scenario"]
        out = []
        for a in s["angles"]:
            cam = live["cameras"].get(a["label"])
            if not cam:
                continue
            out.append(
                {
                    "cam_id": cam["cam_id"],
                    "label": a["label"],
                    "status": status,
                    "scenario_id": s["id"],
                    "video_url": f"/api/scenarios/{s['id']}/media/{a['label']}.mp4",
                    "offset_s": -float(a.get("offset_s", 0.0)),  # clip time shown at wall0 (stream_clips delays by it)
                    "duration_s": live["durations"].get(a["label"], float(a.get("duration_s") or 0)),
                    "wall0_ms": live["wall0_ms"],
                    "t_game0_s": (live["wall0_ms"] - live["t0_ms"]) / 1000.0,
                    "source": s.get("source", "team_recording"),
                    "credit": s.get("credit"),
                    "annotated": bool(s.get("annotated")),
                    "calibrated": bool(a.get("corners_norm")),
                }
            )
        return out

    async def schedule(r: Any, live: dict[str, Any], status: str) -> None:
        s = live["scenario"]
        await ctl(
            r,
            "feed_schedule",
            live["game_id"],
            {
                "scenario_id": s["id"],
                "sport": s.get("sport", "table_tennis"),
                "teams": s.get("teams") or [],
                "params": {"replayed": True, "scenario": s.get("title", s["id"])},
                "feeds": feeds_of(live, status),
            },
        )

    async def feeder(r: Any, live: dict[str, Any]) -> None:
        s = live["scenario"]
        events = s.get("events")
        if not (s.get("annotated") and events):
            return
        from .annotations import run_feeder  # the annotation feeder (D-44)

        label = s.get("events_angle") or s["angles"][0]["label"]
        angle = next((a for a in s["angles"] if a["label"] == label), s["angles"][0])
        path = Path(events) if Path(events).is_absolute() else ROOT / events
        kw: dict[str, Any] = {
            "game_id": live["game_id"],
            "sport": s.get("sport", ""),
            "events_path": path,
            "wall0_ms": live["wall0_ms"] + float(angle.get("offset_s", 0.0)) * 1000 / live["speed"],
            "t_game0_s": (live["wall0_ms"] - live["t0_ms"]) / 1000.0 + float(angle.get("offset_s", 0.0)),
            "speed": live["speed"],
        }
        cam = live["cameras"].get(angle["label"])
        if cam:
            kw["cam_id"] = cam["cam_id"]
        try:
            live["annotated_events"] = await run_feeder(r, **kw)
        except TypeError:  # an older feeder without cam_id
            kw.pop("cam_id", None)
            live["annotated_events"] = await run_feeder(r, **kw)

    async def stream(r: Any, live: dict[str, Any], args: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ROOT / "services" / "gateway" / "scripts" / "stream_clips.py"),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        live["proc"] = proc
        assert proc.stdout
        tasks: list[asyncio.Task] = []
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
                live["cameras"][ev["label"]] = {"cam_id": ev["cam_id"], "frames": 0}
            elif kind == "start":
                live["status"], live["wall0_ms"] = "playing", ev["wall0_ms"]
                await schedule(r, live, "playing")
                tasks.append(asyncio.create_task(feeder(r, live)))
            elif kind in ("progress", "done"):
                live["cameras"].setdefault(ev["label"], {}).update(
                    {k: ev[k] for k in ("frames", "lag_max_ms", "seconds") if k in ev}
                )
        code = await proc.wait()
        for t in tasks:
            if not t.done():
                t.cancel()
        stopped = live.get("stopped")
        live["status"] = "ended" if code == 0 or stopped else "failed"
        if code and not stopped:
            live["error"] = "; ".join(live["log"][-3:]) or f"streamer exited with {code}"
        if live.get("wall0_ms"):
            await schedule(r, live, "ended" if live["status"] == "ended" else "failed")
        live["finished_at_ms"] = time.time() * 1000

    def public(live: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in live.items() if k not in ("proc", "scenario")}
        return out | {"scenario_id": live["scenario"]["id"]}

    @router.get("/time")
    async def server_time() -> dict[str, float]:
        """The server clock, for viewers that align replayed feeds without a ctl socket (NTP-style)."""
        return {"t_ms": time.time() * 1000}

    @router.get("/scenarios")
    async def list_scenarios(token: str | None = None, authorization: str | None = Header(None)) -> list[dict]:
        claims(token, authorization)
        return [summary(s, st) for s in load_scenarios().values()]

    @router.get("/scenarios/{sid}/media/{name}")
    async def media(sid: str, name: str, token: str | None = None, authorization: str | None = Header(None)):
        claims(token, authorization)
        s = load_scenarios().get(sid)
        label = name.removesuffix(".mp4")
        if s is None or not name.endswith(".mp4") or label not in {a["label"] for a in s["angles"]}:
            raise HTTPException(404, "no such media")
        p = media_path(st, sid, label)
        if not p.exists():
            raise HTTPException(404, "not prepared yet")
        return FileResponse(p, media_type="video/mp4", headers={"Cache-Control": "private, max-age=3600"})

    @router.post("/scenarios/{sid}/prepare")
    async def prepare_all(sid: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        claims(None, authorization)
        s = load_scenarios().get(sid)
        if s is None:
            raise HTTPException(404, "no such scenario")
        await asyncio.gather(*(prepare(st, s, a) for a in s["angles"]))
        return summary(s, st)

    @router.get("/games/{game_id}/scenario")
    async def status(game_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        c = claims(None, authorization)
        if c.game_id != game_id:
            raise HTTPException(403, "token for another game")
        live = runs.get(game_id)
        if live is None:
            raise HTTPException(404, "no scenario running")
        return public(live)

    @router.post("/games/{game_id}/scenario", status_code=202)
    async def go_live(game_id: str, body: ScenarioBody, request: Request, authorization: str | None = Header(None)):
        c = claims(None, authorization)
        judge(c, game_id)
        cur = runs.get(game_id)
        if cur and cur["status"] in ("preparing", "starting", "playing"):
            raise HTTPException(409, "a scenario is already playing in this game; stop it first")
        s = load_scenarios().get(body.scenario_id)
        if s is None:
            raise HTTPException(404, "no such scenario")
        r = request.app.state.r
        g = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in (await r.hgetall(f"game:{game_id}")).items()
        }
        if not g.get("join_key"):
            raise HTTPException(404, "no such game")
        live: dict[str, Any] = {
            "live_id": "s_" + secrets.token_hex(6),
            "game_id": game_id,
            "scenario": s,
            "status": "preparing",
            "speed": body.speed,
            "t0_ms": float(g["t0_ms"]),
            "cameras": {},
            "durations": {},
            "log": [],
            "started_at_ms": time.time() * 1000,
        }
        runs[game_id] = live
        try:
            files = await asyncio.gather(*(prepare(st, s, a) for a in s["angles"]))
        except HTTPException:
            live["status"] = "failed"
            raise
        for a, f in zip(s["angles"], files, strict=True):
            probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]
            code, out = await run(*probe)
            live["durations"][a["label"]] = float(out.strip() or 0) if code == 0 else float(a.get("duration_s") or 0)
        args = [
            "--game", game_id, "--join-key", g["join_key"], "--mode", "simultaneous",
            "--speed", str(body.speed), "--start-in", str(START_IN_S), "--sport", s.get("sport", "table_tennis"),
            "--gateway", f"http://127.0.0.1:{st.port}",
        ]  # fmt: skip
        for a, f in zip(s["angles"], files, strict=True):
            corners = ",".join(f"{v:.6f}" for xy in a.get("corners_norm") or [] for v in xy[:2])
            args += ["--clip", f"{f}:{a['label']}:{corners}"]
            if a.get("offset_s"):
                args += ["--offset", f"{a['label']}={float(a['offset_s'])}"]
        # reset the game to the scenario's sport and teams before the cameras join, so their calibration lands on the
        # new game state; the feed rows follow once the streamer has fixed wall0
        await ctl(
            r,
            "feed_schedule",
            game_id,
            {
                "scenario_id": s["id"],
                "sport": s.get("sport", "table_tennis"),
                "teams": s.get("teams") or [],
                "params": {"replayed": True, "scenario": s.get("title", s["id"])},
                "feeds": [],
                "reset": True,
            },
        )
        live["status"] = "starting"
        asyncio.get_running_loop().create_task(stream(r, live, args))
        return public(live)

    @router.post("/games/{game_id}/scenario/stop")
    async def stop(game_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        c = claims(None, authorization)
        judge(c, game_id)
        live = runs.get(game_id)
        if live is None:
            raise HTTPException(404, "no scenario running")
        live["stopped"] = True
        proc = live.get("proc")
        if proc is not None and proc.returncode is None:
            proc.terminate()
        return public(live)

    return router
