"""P0 Cartesia check (server side): mint a short-lived access token the way the gateway will, then use
*only that token* (the browser path) for one Sonic TTS line and an Ink-2 STT transcript of the same audio.

    uv run --with websockets==15.0.1 python spikes/cartesia-voice/server_check.py

Reads CARTESIA_API_KEY from .env. Never prints the key or the token.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
VERSION = os.environ.get("CARTESIA_VERSION") or "2026-08-14"
VOICE = os.environ.get("CARTESIA_VOICE_CALLS") or "a0e99841-438c-4a64-b679-ae501e7d6091"  # docs example voice
LINE = "Edge ball. Good. Point, B."
SR = 16000


def env_key() -> str:
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if line.startswith("CARTESIA_API_KEY="):
            return line.split("=", 1)[1].split("#")[0].strip()
    raise SystemExit("CARTESIA_API_KEY missing from .env")


def mint_token(key: str) -> tuple[str, float]:
    t = time.perf_counter()
    req = urllib.request.Request(
        "https://api.cartesia.ai/access-token",
        data=json.dumps({"grants": {"tts": True, "stt": True}, "expires_in": 300}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Cartesia-Version": VERSION, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.loads(r.read())
    return body["token"], (time.perf_counter() - t) * 1000


async def tts(token: str) -> tuple[bytes, float, float]:
    url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version={VERSION}&access_token={token}"
    async with websockets.connect(url) as ws:
        t0 = time.perf_counter()
        await ws.send(
            json.dumps(
                {
                    "model_id": "sonic-3.6",
                    "transcript": LINE,
                    "voice": {"mode": "id", "id": VOICE},
                    "language": "en",
                    "context_id": str(uuid.uuid4()),
                    "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": SR},
                    "max_buffer_delay_ms": 0,
                    "continue": False,
                }
            )
        )
        pcm, first = bytearray(), None
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "chunk":
                first = first or time.perf_counter()
                pcm += base64.b64decode(msg["data"])
            elif msg.get("type") == "error":
                raise RuntimeError(f"TTS error: {msg.get('title')}: {msg.get('message')}")
            if msg.get("done"):
                break
        return bytes(pcm), (first - t0) * 1000, (time.perf_counter() - t0) * 1000


async def stt(token: str, pcm: bytes) -> tuple[str, float]:
    url = (
        "wss://api.cartesia.ai/stt/turns/websocket?model=ink-2&encoding=pcm_s16le"
        f"&sample_rate={SR}&cartesia_version={VERSION}&access_token={token}"
    )
    audio = pcm + b"\x00\x00" * SR * 2  # 2 s of trailing silence so the turn ends
    chunk = SR * 2 // 10  # 100 ms
    async with websockets.connect(url) as ws:

        async def send():
            for i in range(0, len(audio), chunk):
                await ws.send(audio[i : i + chunk])
                await asyncio.sleep(0.1)  # real time, like a phone mic
            await ws.send(json.dumps({"type": "close"}))

        sender = asyncio.create_task(send())
        speech_end = time.perf_counter() + len(pcm) / (SR * 2)
        transcript = ""
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "turn.end":
                transcript = msg.get("transcript", "")
                break
            if msg.get("type") == "error":
                raise RuntimeError(f"STT error: {msg.get('title')}: {msg.get('message')}")
        sender.cancel()
        return transcript, (time.perf_counter() - speech_end) * 1000


async def main() -> None:
    token, mint_ms = mint_token(env_key())
    print(f"access token minted ({mint_ms:.0f} ms, grants tts+stt, 300 s), version {VERSION}")
    pcm, ttfa_ms, total_ms = await tts(token)
    print(f"TTS sonic-3.6 via access_token: {len(pcm) / (SR * 2):.2f} s audio, first chunk {ttfa_ms:.0f} ms, done {total_ms:.0f} ms")
    out = ROOT / "data" / "local" / "spikes"
    out.mkdir(parents=True, exist_ok=True)
    (out / "cartesia_tts_line.pcm").write_bytes(pcm)
    text, end_ms = await stt(token, pcm)
    print(f"STT ink-2 via access_token: turn.end {end_ms:.0f} ms after speech ended -> {text!r}")


if __name__ == "__main__":
    asyncio.run(main())
