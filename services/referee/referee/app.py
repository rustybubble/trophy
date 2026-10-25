"""FastAPI surface on :8100: the port the dropped `rules` service held, so the gateway's /api/ask proxy is unchanged."""

from __future__ import annotations

import io
import logging
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .catalog import CHECKS
from .config import Settings
from .llm import ClaudeJSON
from .service import AskRequest, Referee
from .stt import transcribe_pcm16
from .tts import AccessTokens, CartesiaTTS, FanoutSink, WavSink

log = logging.getLogger("referee.app")
STATIC = Path(__file__).parent / "static"


class AskBody(BaseModel):
    game_id: str
    question: str = Field(min_length=1, max_length=500)
    sport: str = "table_tennis"
    by_cam_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    voice: str = "ref"
    emotion: str | None = None
    interrupt: bool = True


def create_app(
    st: Settings,
    *,
    r: Any = None,
    llm: Any = None,
    tts: CartesiaTTS | None = None,
    checks: Any = None,
    start_tts: bool = True,
) -> FastAPI:
    fanout = FanoutSink()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.r = r if r is not None else aioredis.from_url(st.redis_url)
        app.state.llm = (
            llm
            if llm is not None
            else ClaudeJSON(
                st.anthropic_api_key,
                model=st.claude_model,
                fast_model=st.claude_fast_model,
                timeout_s=st.phrase_timeout_s,
            )
        )
        tokens = AccessTokens(st.cartesia_api_key, st.cartesia_version)
        app.state.tokens = tokens
        app.state.tts = (
            tts
            if tts is not None
            else CartesiaTTS(
                tokens.get,
                version=st.cartesia_version,
                voices=st.voices,
                model_id=st.tts_model,
                sample_rate=st.sample_rate,
            )
        )
        app.state.tts.add_sink(WavSink(st.data_dir / "referee" / "voice", st.sample_rate))
        app.state.tts.add_sink(fanout)
        if st.speaker:
            from .tts import SpeakerSink  # noqa: PLC0415

            app.state.tts.add_sink(SpeakerSink(st.sample_rate))
        if start_tts:
            try:
                await app.state.tts.start()
            except Exception as e:  # noqa: BLE001 - the next /speak reconnects; /ask does not need the socket
                log.warning("tts socket not open at start: %s", e)
        app.state.referee = Referee(st, r=app.state.r, llm=app.state.llm, checks=checks, tts=app.state.tts)
        yield
        await app.state.tts.stop()

    app = FastAPI(title="Trophy referee", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz(request: Request) -> dict[str, Any]:
        ok_redis = False
        try:
            ok_redis = bool(await request.app.state.r.ping())
        except Exception:  # noqa: BLE001
            ok_redis = False
        ref: Referee = request.app.state.referee
        return {
            "ok": True,
            "redis": ok_redis,
            "tts_connected": request.app.state.tts.connected,
            "tts_connect_ms": request.app.state.tts.connect_ms,
            "claude_model": st.claude_model,
            "router_model": st.claude_fast_model,
            "speaker": st.speaker,
            "pending": len(ref.pending),
            "checks": list(CHECKS),
        }

    @app.get("/checks")
    async def checks_catalog() -> dict[str, Any]:
        return {
            "checks": [
                {"name": s.name, "about": s.about, "args": list(s.args), "returns": s.returns, "tier": s.tier}
                for s in CHECKS.values()
            ]
        }

    @app.post("/ask")
    async def ask(body: AskBody, request: Request) -> dict[str, Any]:
        ref: Referee = request.app.state.referee
        return await ref.ask(AskRequest(body.game_id, body.question, body.sport, body.by_cam_id, body.context))

    @app.post("/speak")
    async def speak(body: SpeakBody, request: Request) -> dict[str, Any]:
        t: CartesiaTTS = request.app.state.tts
        if body.voice not in st.voices:
            raise HTTPException(422, f"voice must be one of {sorted(st.voices)}")
        try:
            res = await t.speak(body.text, voice=body.voice, emotion=body.emotion, interrupt=body.interrupt)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Cartesia: {type(e).__name__}: {e}") from None
        if res.error:
            raise HTTPException(502, f"Cartesia: {res.error}")
        return {
            "context_id": res.context_id,
            "voice": res.voice,
            "ttfa_ms": round(res.ttfa_ms, 1) if res.ttfa_ms is not None else None,
            "total_ms": round(res.total_ms, 1),
            "duration_s": round(res.duration_s, 2),
            "cancelled": res.cancelled,
            "listeners": len(fanout.queues),
        }

    @app.post("/transcribe")
    async def transcribe(request: Request) -> dict[str, Any]:
        raw = await request.body()
        if not raw:
            raise HTTPException(422, "empty body")
        ctype = request.headers.get("content-type", "")
        if "wav" in ctype or raw[:4] == b"RIFF":
            with wave.open(io.BytesIO(raw), "rb") as w:
                if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
                    raise HTTPException(422, "WAV must be mono 16-bit 16 kHz")
                pcm = w.readframes(w.getnframes())
        else:
            pcm = raw
        try:
            text, ms = await transcribe_pcm16(
                request.app.state.tokens.get, pcm, version=st.cartesia_version, realtime=False
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Cartesia STT: {type(e).__name__}: {e}") from None
        return {"text": text, "turn_end_ms": round(ms, 1)}

    @app.websocket("/ws/audio")
    async def ws_audio(ws: WebSocket) -> None:
        await ws.accept()
        q = fanout.subscribe()
        await ws.send_json({"type": "hello", "sample_rate": st.sample_rate, "encoding": "pcm_s16le"})
        try:
            while True:
                await ws.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            fanout.unsubscribe(q)

    @app.get("/listen", response_class=HTMLResponse)
    async def listen() -> str:
        return (STATIC / "listen.html").read_text("utf8")

    return app
