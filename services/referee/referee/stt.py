"""Cartesia Ink-2 speech-to-text, server side: a PCM s16le 16 kHz clip -> transcript (turn detection built in).

The phones transcribe in the browser (apps/pwa/src/lib/voice.ts); this is for the CLI, tests and a dashboard mic.
"""

from __future__ import annotations

import asyncio
import json
import time
import wave
from pathlib import Path

import websockets

from .tts import TokenProvider

STT_URL = "wss://api.cartesia.ai/stt/turns/websocket"


class STTError(RuntimeError):
    pass


def read_wav_16k(path: Path) -> bytes:
    """Reads a mono 16-bit WAV; resamples by decimation/duplication to 16 kHz when needed (good enough for speech)."""
    with wave.open(str(path), "rb") as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        frames = w.readframes(w.getnframes())
    if sw != 2:
        raise STTError("only 16-bit WAV is supported")
    import array

    a = array.array("h")
    a.frombytes(frames)
    if ch > 1:
        a = array.array("h", a[::ch])
    if sr != 16000:
        n = int(len(a) * 16000 / sr)
        a = array.array("h", (a[min(len(a) - 1, int(i * sr / 16000))] for i in range(n)))
    return a.tobytes()


async def transcribe_pcm16(
    tokens: TokenProvider,
    pcm: bytes,
    *,
    version: str = "2026-08-14",
    url: str = STT_URL,
    realtime: bool = True,
    timeout_s: float = 30.0,
) -> tuple[str, float]:
    """Returns (transcript, ms from the end of the audio to `turn.end`)."""
    token = await tokens()
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}model=ink-2&encoding=pcm_s16le&sample_rate=16000&cartesia_version={version}&access_token={token}"
    audio = pcm + b"\x00\x00" * 16000 * 2  # 2 s of trailing silence so the turn ends
    chunk = 16000 * 2 // 10  # 100 ms

    async with websockets.connect(full) as ws:

        async def send() -> None:
            for i in range(0, len(audio), chunk):
                await ws.send(audio[i : i + chunk])
                if realtime:
                    await asyncio.sleep(0.1)
            await ws.send(json.dumps({"type": "close"}))

        sender = asyncio.create_task(send())
        audio_end = time.perf_counter() + (len(pcm) / 32000 if realtime else 0.0)
        turns: list[str] = []
        try:
            async with asyncio.timeout(timeout_s):
                async for raw in ws:
                    m = json.loads(raw)
                    t = m.get("type")
                    if t == "turn.end":
                        turns.append(str(m.get("transcript", "")))
                        break
                    if t == "error":
                        raise STTError(f"{m.get('title')}: {m.get('message')}")
        except TimeoutError as e:
            raise STTError("no turn.end before the timeout") from e
        finally:
            sender.cancel()
        return " ".join(turns).strip(), (time.perf_counter() - audio_end) * 1000
