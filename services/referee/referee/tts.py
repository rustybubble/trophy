"""Cartesia Sonic over one WebSocket, server side (interfaces-v1 §16; research card §6).

One socket, many `context_id`s (one per line), two voices (`calls`, `ref`), `cancel` on interrupt, inline
`<emotion .../>` tags, `max_buffer_delay_ms: 0` for first audio as early as possible. Audio chunks (PCM s16le,
24 kHz mono by default) are fanned out to sinks: a WAV file, this machine's speaker, or `/ws/audio` listeners.
Authentication uses a short-lived access token minted with the API key (the browser path the spike verified).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
import uuid
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
import websockets

log = logging.getLogger("referee.tts")

TokenProvider = Callable[[], Awaitable[str]]


class TTSError(RuntimeError):
    pass


class Sink(Protocol):
    async def on_chunk(self, ctx: str, seq: int, pcm: bytes, done: bool, voice: str) -> None: ...


@dataclass
class SpeechResult:
    context_id: str
    text: str
    voice: str
    ttfa_ms: float | None  # request -> first audio chunk
    total_ms: float
    pcm: bytes
    sample_rate: int
    cancelled: bool = False
    error: str | None = None

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / (2 * self.sample_rate)


@dataclass
class _Ctx:
    text: str
    voice: str
    t0: float
    first: float | None = None
    pcm: bytearray = field(default_factory=bytearray)
    seq: int = 0
    done: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False
    error: str | None = None


class AccessTokens:
    """Mints Cartesia access tokens with the API key (`POST /access-token`), refreshing before they expire."""

    def __init__(self, api_key: str, version: str, http: httpx.AsyncClient | None = None, ttl_s: int = 3600) -> None:
        self.api_key, self.version, self.ttl_s = api_key, version, ttl_s
        self.http = http or httpx.AsyncClient(timeout=10)
        self._token: str | None = None
        self._exp = 0.0

    async def get(self) -> str:
        if self._token and time.monotonic() < self._exp - 120:
            return self._token
        r = await self.http.post(
            "https://api.cartesia.ai/access-token",
            json={"grants": {"tts": True, "stt": True}, "expires_in": self.ttl_s},
            headers={"Authorization": f"Bearer {self.api_key}", "Cartesia-Version": self.version},
        )
        r.raise_for_status()
        self._token = str(r.json()["token"])
        self._exp = time.monotonic() + self.ttl_s
        return self._token


class CartesiaTTS:
    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        version: str = "2026-08-14",
        voices: dict[str, str],
        model_id: str = "sonic-3.6",
        sample_rate: int = 24000,
        url: str = "wss://api.cartesia.ai/tts/websocket",
        line_timeout_s: float = 20.0,
    ) -> None:
        self.tokens = token_provider
        self.version = version
        self.voices = voices
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.url = url
        self.line_timeout_s = line_timeout_s
        self.sinks: list[Sink] = []
        self._ws: Any = None
        self._reader: asyncio.Task[None] | None = None
        self._ctxs: dict[str, _Ctx] = {}
        self._current: str | None = None
        self._lock = asyncio.Lock()
        self.connect_ms: float | None = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def add_sink(self, sink: Sink) -> None:
        self.sinks.append(sink)

    async def start(self) -> None:
        await self._ensure()

    async def _ensure(self) -> Any:
        async with self._lock:
            if self._ws is not None:
                return self._ws
            t0 = time.perf_counter()
            token = await self.tokens()
            sep = "&" if "?" in self.url else "?"
            ws = await websockets.connect(f"{self.url}{sep}cartesia_version={self.version}&access_token={token}")
            self._ws = ws
            self.connect_ms = (time.perf_counter() - t0) * 1000
            self._reader = asyncio.create_task(self._read(ws))
            log.info("tts socket open in %.0f ms", self.connect_ms)
            return ws

    async def stop(self) -> None:
        ws, self._ws = self._ws, None
        if self._reader:
            self._reader.cancel()
            self._reader = None
        if ws is not None:
            await ws.close()

    async def _read(self, ws: Any) -> None:
        try:
            async for raw in ws:
                try:
                    m = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                await self._dispatch(m)
        except Exception as e:  # noqa: BLE001 - the socket died; lines in flight are failed, the next speak reconnects
            log.warning("tts socket closed: %s", type(e).__name__)
        finally:
            if self._ws is ws:
                self._ws = None
            for c in self._ctxs.values():
                if not c.done.is_set():
                    c.error = c.error or "socket_closed"
                    c.done.set()

    async def _dispatch(self, m: dict[str, Any]) -> None:
        ctx_id = str(m.get("context_id") or "")
        c = self._ctxs.get(ctx_id)
        if c is None:
            return  # a cancelled or unknown context
        t = m.get("type")
        if t == "chunk" and isinstance(m.get("data"), str):
            pcm = base64.b64decode(m["data"])
            if pcm and c.first is None:
                c.first = time.perf_counter()
            c.pcm += pcm
            c.seq += 1
            for s in self.sinks:
                await s.on_chunk(ctx_id, c.seq, pcm, False, c.voice)
        elif t == "error":
            c.error = f"{m.get('title') or m.get('error_code') or 'error'}: {m.get('message', '')}".strip()
            log.error("tts error on %s: %s", ctx_id, c.error)
        if m.get("done") is True or t == "error":
            for s in self.sinks:
                await s.on_chunk(ctx_id, c.seq, b"", True, c.voice)
            c.done.set()

    async def speak(
        self,
        text: str,
        *,
        voice: str = "ref",
        emotion: str | None = None,
        interrupt: bool = True,
        speed: float | None = None,
    ) -> SpeechResult:
        text = text.strip()
        if not text:
            raise TTSError("empty line")
        voice_id = self.voices.get(voice) or next(iter(self.voices.values()))
        ws = await self._ensure()
        if interrupt and self._current and self._current in self._ctxs:
            await self.cancel(self._current)
        ctx_id = str(uuid.uuid4())
        c = _Ctx(text=text, voice=voice, t0=time.perf_counter())
        self._ctxs[ctx_id] = c
        self._current = ctx_id
        transcript = text
        if speed:
            transcript = f'<speed ratio="{speed:.2f}"/>' + transcript
        if emotion:
            transcript = f'<emotion value="{emotion}"/>' + transcript
        await ws.send(
            json.dumps(
                {
                    "model_id": self.model_id,
                    "transcript": transcript,
                    "voice": {"mode": "id", "id": voice_id},
                    "language": "en",
                    "context_id": ctx_id,
                    "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": self.sample_rate},
                    "max_buffer_delay_ms": 0,
                    "continue": False,
                }
            )
        )
        try:
            await asyncio.wait_for(c.done.wait(), timeout=self.line_timeout_s)
        except TimeoutError:
            c.error = c.error or "timeout"
        finally:
            self._ctxs.pop(ctx_id, None)
            if self._current == ctx_id:
                self._current = None
        total = (time.perf_counter() - c.t0) * 1000
        return SpeechResult(
            ctx_id,
            text,
            voice,
            (c.first - c.t0) * 1000 if c.first else None,
            total,
            bytes(c.pcm),
            self.sample_rate,
            c.cancelled,
            c.error,
        )

    async def cancel(self, ctx_id: str) -> None:
        c = self._ctxs.get(ctx_id)
        if c is None:
            return
        c.cancelled = True
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.send(json.dumps({"context_id": ctx_id, "cancel": True}))
        for s in self.sinks:
            await s.on_chunk(ctx_id, c.seq, b"", True, c.voice)
        c.done.set()


# ---------------------------------------------------------------- sinks


class WavSink:
    """Writes every finished line to `<dir>/<context_id>.wav` (for tests, measurement and the demo video)."""

    def __init__(self, directory: Path, sample_rate: int = 24000) -> None:
        self.dir = directory
        self.sample_rate = sample_rate
        self._buf: dict[str, bytearray] = {}
        self.written: list[Path] = []

    async def on_chunk(self, ctx: str, seq: int, pcm: bytes, done: bool, voice: str) -> None:
        self._buf.setdefault(ctx, bytearray()).extend(pcm)
        if done:
            data = self._buf.pop(ctx, bytearray())
            if not data:
                return
            self.dir.mkdir(parents=True, exist_ok=True)
            p = self.dir / f"{ctx}.wav"
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.sample_rate)
                w.writeframes(bytes(data))
            self.written.append(p)


class FanoutSink:
    """Relays chunks to `/ws/audio` listeners as `{type: 'tts', ctx, seq, pcm_b64, voice, done}` (research card §6)."""

    def __init__(self, maxsize: int = 512) -> None:
        self.queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self.maxsize = maxsize

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self.maxsize)
        self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self.queues.discard(q)

    async def on_chunk(self, ctx: str, seq: int, pcm: bytes, done: bool, voice: str) -> None:
        if not self.queues:
            return
        msg = {
            "type": "tts",
            "ctx": ctx,
            "seq": seq,
            "pcm_b64": base64.b64encode(pcm).decode(),
            "voice": voice,
            "done": done,
        }
        for q in list(self.queues):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                self.queues.discard(q)  # a listener that can't keep up is dropped, never blocks the speaker


class SpeakerSink:
    """Plays the ref voice on this machine's default output (needs the `speaker` extra: sounddevice/PortAudio)."""

    def __init__(self, sample_rate: int = 24000) -> None:
        import sounddevice as sd  # noqa: PLC0415 - optional dependency

        self.stream = sd.RawOutputStream(samplerate=sample_rate, channels=1, dtype="int16")
        self.stream.start()
        self._lock = asyncio.Lock()

    async def on_chunk(self, ctx: str, seq: int, pcm: bytes, done: bool, voice: str) -> None:
        if pcm:
            async with self._lock:
                await asyncio.to_thread(self.stream.write, pcm)
