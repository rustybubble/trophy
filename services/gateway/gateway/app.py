"""The gateway (interfaces-v1 §13): the phone-facing API behind Caddy at /api. It holds no game logic.

Client actions become ``ctl:engine`` commands; frames go to Redis ``frames:{cam}``; audio onsets go to
``ev:audio``; the Cartesia key never leaves this process (phones get short-lived tokens).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import re
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError
from trophy import ids
from trophy.contracts import (
    AdjustScoreArgs,
    BookmarkArgs,
    Calibration,
    CalibrationRequest,
    ChallengeArgs,
    ClipThatArgs,
    CtlCommand,
    EmptyArgs,
    HouseRuleVersionArgs,
    RegenerateInterpreterArgs,
    ResolveChallengeArgs,
    ReviewCallArgs,
    SetServerArgs,
    StartGameArgs,
    SubmitHouseRuleArgs,
    ViewerStatusArgs,
)
from trophy.events import event_json, make_event
from trophy.framebus import FRAMES_MAXLEN, frame_fields, parse_message
from trophy.streams import (
    CTL_CALIB,
    CTL_ENGINE,
    CTL_STREAM_MAXLEN,
    EV_AUDIO,
    EVENT_STREAM_MAXLEN,
    calib_key,
    cam_key,
    frames_key,
    game_key,
    make_ctl,
    role_allows,
)
from trophy.timebase import ClockFit, now_ms

from . import calib_stub
from .config import Settings
from .demo import demo_router
from .replay import replay_router
from .scenarios import scenario_router
from .tokens import Claims, TokenError, mint, normalize_role, verify

log = logging.getLogger("trophy.gateway")

UNSYNCED_ERR_MS = 1000.0  # sync_err_ms for frames stamped by arrival time before the clock fit exists
HEALTH_EVERY_MS = 2000.0
GAME_TTL_S = 2 * 86400
CALL_ID_RE = re.compile(r"^[0-9A-Za-z_-]{6,64}$")
FRAME_DEFAULTS = {"w": 1280, "h": 720, "fps": 30, "quality": 0.7}
CLIP_MAX_BYTES = 250 * 1024 * 1024
CLIP_TYPES = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
CLIP_NAME_RE = re.compile(r"^c_[0-9a-hjkmnp-tv-z]{6}_\d{5}\.(mp4|webm|mov)$")

CLIENT_ARGS = {
    "start_game": StartGameArgs,
    "set_server": SetServerArgs,
    "challenge": ChallengeArgs,
    "resolve_challenge": ResolveChallengeArgs,
    "undo_last_call": EmptyArgs,
    "adjust_score": AdjustScoreArgs,
    "end_period": EmptyArgs,
    "end_game": EmptyArgs,
    "submit_house_rule": SubmitHouseRuleArgs,
    "approve_house_rule": HouseRuleVersionArgs,
    "reject_house_rule": HouseRuleVersionArgs,
    "bookmark": BookmarkArgs,
    "clip_that": ClipThatArgs,
    "review_call": ReviewCallArgs,
    "revert_house_rule": HouseRuleVersionArgs,
    "regenerate_interpreter": RegenerateInterpreterArgs,
    "viewer_status": ViewerStatusArgs,
}


def jlog(msg: str, **kw: Any) -> None:
    """JSON log lines: svc, t_srv_ms, msg, ids. Never frames, tokens or personal data."""
    log.info(json.dumps({"svc": "gateway", "t_srv_ms": round(now_ms(), 1), "msg": msg, **kw}))


def _s(v: bytes | str | None) -> str:
    return v.decode() if isinstance(v, bytes) else (v or "")


# ---------------------------------------------------------------- request bodies
class CreateGame(BaseModel):
    sport: str = Field(pattern=r"^[a-z_]{2,32}$")
    teams: list[dict[str, Any]] | None = None
    params: dict[str, Any] | None = None


class Join(BaseModel):
    join_key: str = Field(min_length=10, max_length=64)
    label: str = Field("", max_length=40)
    role: str = "cam"
    cam_id: str | None = None
    device: dict[str, Any] = Field(default_factory=dict)


class CtlBody(BaseModel):
    cmd: str
    args: dict[str, Any] = Field(default_factory=dict)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    sport: str | None = None
    # The phone's view of the game (scores, teams, the newest calls, rally, server, house rules): the referee resolves
    # "that" to the newest call and answers the score from it, without a Spacetime read (interfaces-v1 §20).
    context: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- per-camera runtime state
class CamRuntime:
    def __init__(self) -> None:
        self.clock = ClockFit()
        self.frames = 0
        self.window_start_ms = now_ms()
        self.fps = 0.0
        self.last_health_ms = 0.0
        self.w = 0
        self.h = 0
        self.ctl_ws: WebSocket | None = None


def create_app(settings: Settings | None = None, r: Any = None, http: httpx.AsyncClient | None = None) -> FastAPI:
    st = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.r = r or aioredis.from_url(st.redis_url)
        app.state.http = http or httpx.AsyncClient(timeout=8.0)
        yield
        if http is None:
            await app.state.http.aclose()
        if r is None:
            await app.state.r.aclose()

    app = FastAPI(title="Trophy gateway", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = st
    app.state.cams = {}  # cam_id -> CamRuntime
    app.state.stdb_read_token = None

    def rt(cam_id: str) -> CamRuntime:
        cams: dict[str, CamRuntime] = app.state.cams
        if cam_id not in cams:
            cams[cam_id] = CamRuntime()
        return cams[cam_id]

    # ------------------------------------------------------------ helpers
    async def game(gid: str) -> dict[str, str]:
        h = await app.state.r.hgetall(game_key(gid))
        if not h:
            raise HTTPException(404, "no such game")
        return {_s(k): _s(v) for k, v in h.items()}

    async def publish(cmd: CtlCommand) -> str:
        await app.state.r.xadd(
            CTL_ENGINE, {"json": cmd.model_dump_json(by_alias=True)}, maxlen=CTL_STREAM_MAXLEN, approximate=True
        )
        return cmd.req_id

    def claims_from(token: str | None) -> Claims:
        if not token:
            raise HTTPException(401, "missing token")
        try:
            return verify(st.token_secret, token)
        except TokenError as e:
            raise HTTPException(401, str(e)) from None

    async def auth(authorization: str | None = Header(None)) -> Claims:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        return claims_from(authorization[7:])

    async def cam_game(cam_id: str) -> str:
        gid = _s(await app.state.r.hget(cam_key(cam_id), "game_id"))
        if not gid:
            raise HTTPException(404, "no such camera")
        return gid

    async def health_ctl(c: Claims, cam: CamRuntime, connected: bool) -> None:
        cam.last_health_ms = now_ms()
        fields = {
            "connected": "1" if connected else "0",
            "fps_in": f"{cam.fps:.1f}",
            "w": str(cam.w),
            "h": str(cam.h),
            "sync_err_ms": f"{cam.clock.sync_err_ms if cam.clock.ready else UNSYNCED_ERR_MS:.1f}",
            "last_seen_ms": f"{cam.last_health_ms:.0f}",
        }
        await app.state.r.hset(cam_key(c.cam_id), mapping=fields)
        args = {
            "cam_id": c.cam_id,
            "connected": connected,
            "fps_in": cam.fps,
            "w": cam.w,
            "h": cam.h,
            "sync_err_ms": float(fields["sync_err_ms"]),
            "last_seen_ms": cam.last_health_ms,
        }
        await publish(make_ctl("camera_health", c.game_id, args))

    # ------------------------------------------------------------ games and joining
    @app.post("/api/games")
    async def create_game(body: CreateGame) -> dict[str, Any]:
        gid, key, t0 = ids.new_game_id(), ids.new_join_key(), now_ms()
        await app.state.r.hset(
            game_key(gid),
            mapping={
                "sport": body.sport,
                "t0_ms": repr(t0),
                "status": "lobby",
                "join_key": key,
                "created_at_ms": repr(t0),
            },
        )
        await app.state.r.expire(game_key(gid), GAME_TTL_S)
        args: dict[str, Any] = {"sport": body.sport, "t0_ms": t0}
        if body.teams:
            args["teams"] = body.teams
        if body.params:
            args["params"] = body.params
        await publish(make_ctl("create_game", gid, args))
        jlog("game created", game_id=gid, sport=body.sport)
        return {"game_id": gid, "join_key": key, "join_url": f"{st.public_origin()}/cam/?g={gid}&k={key}", "t0_ms": t0}

    @app.get("/api/games/{gid}/public")
    async def game_public(gid: str) -> dict[str, Any]:
        g = await game(gid)
        return {
            "game_id": gid,
            "sport": g["sport"],
            "status": g.get("status", "lobby"),
            "t0_ms": float(g["t0_ms"]),
            "stdb": {"uri": st.stdb_uri(), "module": st.stdb_module},
            "public_origin": st.public_origin(),
        }

    @app.post("/api/games/{gid}/join")
    async def join(gid: str, body: Join) -> dict[str, Any]:
        g = await game(gid)
        if not hmac.compare_digest(g.get("join_key", ""), body.join_key):
            raise HTTPException(403, "bad join key")
        try:
            role = normalize_role(body.role)
        except TokenError as e:
            raise HTTPException(422, str(e)) from None
        cam_id = body.cam_id
        if not (cam_id and ids.is_cam_id(cam_id) and _s(await app.state.r.hget(cam_key(cam_id), "game_id")) == gid):
            cam_id = ids.new_cam_id()
        device = {k: v for k, v in body.device.items() if isinstance(v, str | int | float | bool)}
        await app.state.r.hset(
            cam_key(cam_id),
            mapping={
                "game_id": gid,
                "label": body.label or cam_id,
                "role": role,
                "ua": str(device.get("ua", ""))[:200],
                "connected": "0",
                "audio_offset_ms": _s(await app.state.r.hget(cam_key(cam_id), "audio_offset_ms")) or "0",
            },
        )
        await app.state.r.expire(cam_key(cam_id), GAME_TTL_S)
        await publish(
            make_ctl(
                "register_camera",
                gid,
                {"cam_id": cam_id, "label": body.label or cam_id, "role": role, "device": device},
            )
        )
        token, exp = mint(st.token_secret, gid, cam_id, role, st.cam_token_ttl_s)
        jlog("joined", game_id=gid, cam_id=cam_id, role=role)
        return {
            "cam_id": cam_id,
            "cam_token": token,
            "exp_ms": exp,
            "t0_ms": float(g["t0_ms"]),
            "stdb": {"uri": st.stdb_uri(), "module": st.stdb_module},
            "public_origin": st.public_origin(),
            "frame": FRAME_DEFAULTS,
        }

    # ------------------------------------------------------------ control commands
    @app.post("/api/ctl", status_code=202)
    async def ctl(body: CtlBody, c: Claims = Depends(auth)) -> dict[str, str]:
        if not role_allows(c.role, body.cmd):
            raise HTTPException(403, f"role {c.role} may not send {body.cmd}")
        try:
            args = CLIENT_ARGS[body.cmd].model_validate(body.args).model_dump(exclude_none=True)
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json())) from None
        if body.cmd in {"bookmark", "clip_that", "review_call"}:
            allowed = {
                "bookmark": {"t_game_s", "label"},
                "clip_that": {"t_game_s"},
                "review_call": {"call_id", "result", "replacement"},
            }[body.cmd]
            if set(body.args) - allowed or ("t_game_s" in args and not math.isfinite(args["t_game_s"])):
                raise HTTPException(422, "invalid command arguments")
            if body.cmd == "review_call" and args["result"] == "correct" and not args.get("replacement"):
                raise HTTPException(422, "correct requires a replacement outcome")
        await game(c.game_id)
        req_id = await publish(make_ctl(body.cmd, c.game_id, args, by_cam_id=c.cam_id))
        jlog("ctl", game_id=c.game_id, cam_id=c.cam_id, cmd=body.cmd, req_id=req_id)
        return {"req_id": req_id}

    # ------------------------------------------------------------ calibration (§6)
    @app.get("/api/cams/{cam_id}/still")
    async def still(cam_id: str, c: Claims = Depends(auth)) -> Response:
        if await cam_game(cam_id) != c.game_id:
            raise HTTPException(403, "camera belongs to another game")
        got = await app.state.r.xrevrange(frames_key(cam_id), count=1)
        if not got:
            raise HTTPException(404, "no frames yet")
        f = {_s(k): v for k, v in got[0][1].items()}
        return Response(
            f["data"],
            media_type="image/jpeg",
            headers={
                "X-Seq": _s(f["seq"]),
                "X-W": _s(f["w"]),
                "X-H": _s(f["h"]),
                "X-T-Game-S": _s(f["t_game_s"]),
                **({"X-Crop": _s(f["crop"])} if "crop" in f else {}),  # calibrate only on uncropped stills
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/calibrate")
    async def calibrate(request: Request, c: Claims = Depends(auth)) -> dict[str, Any]:
        try:
            req = CalibrationRequest.model_validate(await request.json()).model_dump(by_alias=True, mode="json")
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json())) from None
        if req["game_id"] != c.game_id:
            raise HTTPException(403, "calibration for another game")
        try:
            resp = await app.state.http.post(f"{st.adapter_url}/calibrate", json=req, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code < 500:
                raise HTTPException(resp.status_code, resp.text[:300])
            reason = f"adapter HTTP {resp.status_code}"
        except httpx.HTTPError as e:
            reason = f"adapter unreachable ({type(e).__name__})"
        try:
            out = calib_stub.calibrate(req)
        except ValueError as e:
            raise HTTPException(503, f"{reason}; stub: {e}") from None
        jlog("calibrate stub used", game_id=c.game_id, cam_id=req["cam_id"], reason=reason)
        return out

    @app.post("/api/cams/{cam_id}/calibration")
    async def save_calibration(cam_id: str, request: Request, c: Claims = Depends(auth)) -> dict[str, Any]:
        if await cam_game(cam_id) != c.game_id:
            raise HTTPException(403, "camera belongs to another game")
        if not (c.has("judge") or c.cam_id == cam_id):
            raise HTTPException(403, "only the judge or the camera itself can set its calibration")
        try:
            cal = Calibration.model_validate(await request.json())
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json())) from None
        if cal.cam_id != cam_id or cal.game_id != c.game_id:
            raise HTTPException(422, "calibration is for another camera or game")
        doc = cal.model_dump(by_alias=True, exclude_none=True, mode="json")
        await app.state.r.set(calib_key(cam_id), json.dumps(doc))
        await app.state.r.hset(cam_key(cam_id), "calib_trusted", "1" if cal.trusted else "0")
        await app.state.r.publish(CTL_CALIB, cam_id)
        await publish(make_ctl("set_calibration", c.game_id, {"cam_id": cam_id, "calibration": doc}))
        jlog("calibration saved", game_id=c.game_id, cam_id=cam_id, trusted=cal.trusted)
        return {"ok": True, "trusted": cal.trusted}

    # ------------------------------------------------------------ frames (§5)
    @app.websocket("/api/ws/frames")
    async def ws_frames(ws: WebSocket, token: str | None = None) -> None:
        try:
            c = claims_from(token)
        except HTTPException:
            await ws.close(code=4401)
            return
        if not c.has("cam"):
            await ws.close(code=4403)
            return
        t0 = _s(await app.state.r.hget(game_key(c.game_id), "t0_ms"))
        if not t0:
            await ws.close(code=4404)
            return
        t0_ms = float(t0)
        cam = rt(c.cam_id)
        await ws.accept()
        jlog("frames connected", game_id=c.game_id, cam_id=c.cam_id)
        errors = 0
        key = frames_key(c.cam_id)
        try:
            while True:
                buf = await ws.receive_bytes()
                t_arrival = now_ms()
                try:
                    hdr, jpeg = parse_message(buf)
                    if cam.clock.ready:
                        t_srv, err = cam.clock.to_srv(hdr.t_capture_phone_ms), cam.clock.sync_err_ms
                    else:
                        t_srv, err = t_arrival, UNSYNCED_ERR_MS
                    fields = frame_fields(
                        game_id=c.game_id,
                        cam_id=c.cam_id,
                        seq=hdr.seq,
                        t_phone_ms=hdr.t_capture_phone_ms,
                        t_srv_ms=t_srv,
                        t_game_s=(t_srv - t0_ms) / 1000.0,
                        sync_err_ms=err,
                        jpeg=jpeg,
                        source="ws",
                        flags=hdr.flags,
                        crop=hdr.crop,
                    )
                except ValueError as e:
                    errors += 1
                    if errors in (1, 10, 100):
                        jlog("bad frame", cam_id=c.cam_id, error=str(e), errors=errors)
                    if errors > 300:
                        await ws.close(code=4400)
                        return
                    continue
                await app.state.r.xadd(key, fields, maxlen=FRAMES_MAXLEN, approximate=True)
                cam.w, cam.h = int(fields["w"]), int(fields["h"])
                cam.frames += 1
                if t_arrival - cam.window_start_ms >= 1000:
                    cam.fps = cam.frames * 1000 / (t_arrival - cam.window_start_ms)
                    cam.frames, cam.window_start_ms = 0, t_arrival
                if t_arrival - cam.last_health_ms >= HEALTH_EVERY_MS:
                    await health_ctl(c, cam, True)
        except WebSocketDisconnect:
            pass
        finally:
            cam.fps = 0.0
            await health_ctl(c, cam, False)
            jlog("frames disconnected", game_id=c.game_id, cam_id=c.cam_id)

    # ------------------------------------------------------------ control socket (§13): clock, onsets, health, acks
    @app.websocket("/api/ws/ctl")
    async def ws_ctl(ws: WebSocket, token: str | None = None) -> None:
        try:
            c = claims_from(token)
        except HTTPException:
            await ws.close(code=4401)
            return
        g = {_s(k): _s(v) for k, v in (await app.state.r.hgetall(game_key(c.game_id))).items()}
        if not g:
            await ws.close(code=4404)
            return
        t0_ms, sport = float(g["t0_ms"]), g["sport"]
        audio_offset_ms = float(_s(await app.state.r.hget(cam_key(c.cam_id), "audio_offset_ms")) or 0)
        cam = rt(c.cam_id)
        cam.ctl_ws = ws
        await ws.accept()
        try:
            while True:
                raw = await ws.receive_text()
                t1 = now_ms()
                try:
                    m = json.loads(raw)
                    kind = m.get("type")
                except (ValueError, AttributeError):
                    continue
                if kind == "ping":
                    await ws.send_json({"type": "pong", "t0": m.get("t0"), "t1": t1, "t2": now_ms()})
                    p = m.get("prev")
                    valid = isinstance(p, dict) and all(
                        isinstance(p.get(k), int | float) for k in ("t0", "t1", "t2", "t3")
                    )
                    if valid and cam.clock.add(p["t0"], p["t1"], p["t2"], p["t3"]):
                        await ws.send_json(
                            {"type": "sync", "offset_ms": cam.clock.offset_ms, "sync_err_ms": cam.clock.sync_err_ms}
                        )
                        await app.state.r.hset(
                            cam_key(c.cam_id),
                            mapping={
                                "offset_ms": f"{cam.clock.offset_ms:.2f}",
                                "sync_err_ms": f"{cam.clock.sync_err_ms:.2f}",
                                "drift_ppm": f"{cam.clock.drift_ppm:.1f}",
                            },
                        )
                elif kind == "onset" and c.has("cam"):
                    if not cam.clock.ready or not isinstance(m.get("t_phone_ms"), int | float):
                        continue  # an onset is useless without a clock fit
                    t_srv = cam.clock.to_srv(m["t_phone_ms"], audio_offset_ms)
                    ev = make_event(
                        game_id=c.game_id,
                        t_game_s=(t_srv - t0_ms) / 1000.0,
                        sport=sport,
                        type="audio_onset",
                        source="audio",
                        cams=[c.cam_id],
                        conf=1.0,
                        payload={
                            "peak": float(m.get("peak", 0)),
                            "energy": float(m.get("energy", 0)),
                            "cam_id": c.cam_id,
                        },
                    )
                    await app.state.r.xadd(
                        EV_AUDIO, {"json": event_json(ev)}, maxlen=EVENT_STREAM_MAXLEN, approximate=True
                    )
                elif kind == "health":
                    keep = {k: str(m[k])[:40] for k in ("fps", "w", "h", "battery", "thermal", "ua") if k in m}
                    if keep:
                        await app.state.r.hset(cam_key(c.cam_id), mapping={f"phone_{k}": v for k, v in keep.items()})
                elif kind == "call_ack":
                    call_id = m.get("call_id")
                    if isinstance(call_id, str) and CALL_ID_RE.match(call_id):
                        tp = m.get("t_phone_ms")
                        t_ack = cam.clock.to_srv(tp) if cam.clock.ready and isinstance(tp, int | float) else t1
                        asyncio.create_task(log_ack(c, call_id, t_ack, t0_ms))
        except WebSocketDisconnect:
            pass
        finally:
            if cam.ctl_ws is ws:
                cam.ctl_ws = None

    async def stdb_sql(query: str) -> list[dict[str, Any]]:
        if not app.state.stdb_read_token:
            resp = await app.state.http.post(f"{st.stdb_http}/v1/identity", timeout=3.0)
            app.state.stdb_read_token = resp.json()["token"]  # an anonymous, read-only identity
        resp = await app.state.http.post(
            f"{st.stdb_http}/v1/database/{st.stdb_module}/sql",
            content=query,
            headers={"Authorization": f"Bearer {app.state.stdb_read_token}"},
            timeout=3.0,
        )
        res = resp.json()[0]
        names = [e["name"]["some"] for e in res["schema"]["elements"]]
        return [dict(zip(names, row, strict=True)) for row in res["rows"]]

    async def log_ack(c: Claims, call_id: str, t_ack_srv_ms: float, t0_ms: float) -> None:
        """call_ack latency (§10): ack - created_at (engine -> phone) and ack - event time (bounce -> phone)."""
        row: dict[str, Any] = {
            "call_id": call_id,
            "cam_id": c.cam_id,
            "game_id": c.game_id,
            "t_ack_srv_ms": t_ack_srv_ms,
        }
        try:
            got = await stdb_sql(f"SELECT created_at_ms, t_game_s FROM call WHERE call_id = '{call_id}'")
            if got:
                row["ack_latency_ms"] = round(t_ack_srv_ms - got[0]["created_at_ms"], 1)
                row["event_to_ack_ms"] = round(t_ack_srv_ms - (t0_ms + got[0]["t_game_s"] * 1000), 1)
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
            row["lookup_error"] = type(e).__name__
        jlog("call_ack", **row)
        out = st.data_dir / "logs"
        out.mkdir(parents=True, exist_ok=True)
        with (out / "call_ack.jsonl").open("a", encoding="utf8") as f:
            f.write(json.dumps(row) + "\n")

    # ------------------------------------------------------------ voice (§16) and ask the ref (§17)
    @app.get("/api/voice/token")
    async def voice_token(c: Claims = Depends(auth)) -> dict[str, Any]:
        if not st.cartesia_api_key:
            raise HTTPException(503, "voice is not configured")
        try:
            resp = await app.state.http.post(
                "https://api.cartesia.ai/access-token",
                json={"grants": {"tts": True, "stt": True}, "expires_in": st.voice_token_ttl_s},
                headers={"Authorization": f"Bearer {st.cartesia_api_key}", "Cartesia-Version": st.cartesia_version},
                timeout=5.0,
            )
            resp.raise_for_status()
            token = resp.json()["token"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            jlog("voice token failed", cam_id=c.cam_id, error=type(e).__name__)
            raise HTTPException(502, "could not mint a voice token") from None
        # Cartesia library voices, the same defaults as services/referee: Daniel (calls), Gemma (ref)
        default_calls, default_ref = "47c38ca4-5f35-497b-b1a3-415245fb35e1", "62ae83ad-4f6a-430b-af41-a9bede9286ca"
        return {
            "access_token": token,
            "expires_at_ms": now_ms() + st.voice_token_ttl_s * 1000,
            "cartesia_version": st.cartesia_version,
            "voices": {
                "calls": st.cartesia_voice_calls or default_calls,
                "ref": st.cartesia_voice_ref or default_ref,
            },
        }

    @app.post("/api/ask")
    async def ask(body: AskBody, c: Claims = Depends(auth)) -> dict[str, Any]:
        g = await game(c.game_id)
        sport = body.sport or g["sport"]
        t = time.perf_counter()
        try:
            resp = await app.state.http.post(
                f"{st.rules_url}/ask",
                json={
                    "question": body.question,
                    "sport": sport,
                    "game_id": c.game_id,
                    "by_cam_id": c.cam_id,
                    "context": body.context,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            out = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            jlog("ask failed", game_id=c.game_id, error=type(e).__name__)
            raise HTTPException(503, "the referee service is unavailable") from None
        out.setdefault("latency_ms", round((time.perf_counter() - t) * 1000, 1))
        if out.get("kind") == "pending":
            # the referee answers later (a Droid writes the check) and logs the ask itself (§20)
            return out
        args = {
            "question": body.question,
            "answer": str(out.get("answer", "")),
            "citations": out.get("citations", []),
            "latency_ms": float(out["latency_ms"]),
        }
        if isinstance(out.get("moss_ms"), int | float):
            args["moss_ms"] = float(out["moss_ms"])
        for k in ("speech", "kind", "check", "p", "calibrated"):
            if out.get(k) is not None:
                args[k] = out[k]
        try:
            await publish(make_ctl("ask_logged", c.game_id, args, by_cam_id=c.cam_id))
        except ValidationError:
            jlog("ask_logged skipped: referee response doesn't match the contract", game_id=c.game_id)
        return out

    # ------------------------------------------------------------ challenge clips (phone-side high-quality recording)
    def clip_dir(game_id: str, call_id: str):
        return st.data_dir / "clips" / game_id / call_id

    async def probe(path) -> dict[str, Any]:
        """w, h, duration and codec via ffprobe; empty if ffprobe isn't installed or fails."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,codec_name:format=duration",
                "-of",
                "json",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            d = json.loads(out)
            v = (d.get("streams") or [{}])[0]
            return {
                "w": v.get("width"),
                "h": v.get("height"),
                "codec": v.get("codec_name"),
                "duration_s": float(d.get("format", {}).get("duration") or 0) or None,
            }
        except (TimeoutError, OSError, ValueError):
            return {}

    @app.post("/api/clips", status_code=201)
    async def upload_clip(
        request: Request,
        call_id: str,
        seg: int,
        t_start_phone_ms: float,
        t_end_phone_ms: float,
        c: Claims = Depends(auth),
    ) -> dict[str, Any]:
        """One high-quality segment from a camera phone, covering part of a challenged call's evidence window."""
        if not c.has("cam"):
            raise HTTPException(403, "only cameras upload clips")
        if not CALL_ID_RE.match(call_id) or not 0 <= seg < 100000 or t_end_phone_ms <= t_start_phone_ms:
            raise HTTPException(422, "bad clip parameters")
        ctype = (request.headers.get("content-type") or "").split(";")[0].strip()
        if ctype not in CLIP_TYPES:
            raise HTTPException(415, f"clip type must be one of {sorted(CLIP_TYPES)}")
        cam = rt(c.cam_id)
        if not cam.clock.ready:
            raise HTTPException(409, "no clock sync for this camera yet")
        t0_ms = float((await game(c.game_id))["t0_ms"])
        d = clip_dir(c.game_id, call_id)
        d.mkdir(parents=True, exist_ok=True)
        name = f"{c.cam_id}_{seg:05d}.{CLIP_TYPES[ctype]}"
        tmp = d / (name + ".part")
        size = 0
        with tmp.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > CLIP_MAX_BYTES:
                    f.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, "clip too large")
                f.write(chunk)
        if size == 0:
            tmp.unlink(missing_ok=True)
            raise HTTPException(422, "empty clip")
        tmp.replace(d / name)
        t_start = cam.clock.to_srv(t_start_phone_ms)
        t_end = cam.clock.to_srv(t_end_phone_ms)
        meta = {
            "name": name,
            "cam_id": c.cam_id,
            "call_id": call_id,
            "seg": seg,
            "mime": ctype,
            "bytes": size,
            "t_start_srv_ms": t_start,
            "t_end_srv_ms": t_end,
            "t_game_start_s": (t_start - t0_ms) / 1000.0,
            "t_game_end_s": (t_end - t0_ms) / 1000.0,
            "sync_err_ms": cam.clock.sync_err_ms,
            "uploaded_at_ms": now_ms(),
            **await probe(d / name),
        }
        (d / (name + ".json")).write_text(json.dumps(meta), encoding="utf8")
        jlog("clip uploaded", game_id=c.game_id, cam_id=c.cam_id, call_id=call_id, seg=seg, bytes=size)
        return meta

    @app.get("/api/clips/{game_id}/{call_id}")
    async def list_clips(game_id: str, call_id: str, c: Claims = Depends(auth)) -> dict[str, Any]:
        if game_id != c.game_id and not c.has("service"):
            raise HTTPException(403, "clips of another game")
        if not CALL_ID_RE.match(call_id):
            raise HTTPException(422, "bad call id")
        d = clip_dir(game_id, call_id)
        clips = []
        for meta in sorted(d.glob("*.json")) if d.exists() else []:
            m = json.loads(meta.read_text(encoding="utf8"))
            m["url"] = f"/api/clips/{game_id}/{call_id}/{m['name']}"
            clips.append(m)
        clips.sort(key=lambda m: (m["cam_id"], m["seg"]))
        return {"game_id": game_id, "call_id": call_id, "clips": clips}

    @app.get("/api/clips/{game_id}/{call_id}/{name}")
    async def get_clip(
        game_id: str, call_id: str, name: str, token: str | None = None, authorization: str | None = Header(None)
    ) -> FileResponse:
        # <video> can't send headers, so the token may come as ?token=
        c = claims_from(token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None))
        if game_id != c.game_id and not c.has("service"):
            raise HTTPException(403, "clips of another game")
        if not CALL_ID_RE.match(call_id) or not CLIP_NAME_RE.match(name):
            raise HTTPException(404, "no such clip")
        path = clip_dir(game_id, call_id) / name
        if not path.exists():
            raise HTTPException(404, "no such clip")
        ext = name.rsplit(".", 1)[1]
        mime = {v: k for k, v in CLIP_TYPES.items()}[ext]
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

    # ------------------------------------------------------------ health
    @app.post("/api/client_log", status_code=204)
    async def client_log(request: Request) -> Response:
        """A phone's startup error (apps/pwa/index.html), so a blank page on a device we can't inspect is
        diagnosable from the stack log. Unauthenticated, size-capped, never stored."""
        raw = (await request.body())[:4000]
        try:
            d = json.loads(raw)
        except ValueError:
            d = {"msg": raw.decode("utf8", "replace")}
        jlog(
            "client error",
            error=str(d.get("msg", ""))[:2000],
            ua=str(d.get("ua", ""))[:300],
            url=str(d.get("url", ""))[:200],
        )
        return Response(status_code=204)

    @app.get("/api/healthz")
    async def healthz() -> JSONResponse:
        async def probe(url: str) -> bool:
            try:
                return (await app.state.http.get(url, timeout=1.0)).status_code < 500
            except httpx.HTTPError:
                return False

        try:
            redis_ok = bool(await app.state.r.ping())
        except Exception:
            redis_ok = False
        adapter, rules, stdb = await asyncio.gather(
            probe(f"{st.adapter_url}/healthz"), probe(f"{st.rules_url}/healthz"), probe(f"{st.stdb_http}/v1/ping")
        )
        recorder = bool(redis_ok and await app.state.r.exists("recorder:heartbeat"))
        body = {
            "ok": redis_ok,
            "redis": redis_ok,
            "spacetime": stdb,
            "adapter": adapter,
            "rules": rules,
            "recorder": recorder,
        }
        return JSONResponse(body, status_code=200 if redis_ok else 503)

    app.include_router(replay_router(st))
    app.include_router(demo_router(st))
    app.include_router(scenario_router(st))
    return app
