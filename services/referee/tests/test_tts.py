"""A local websocket server plays Cartesia: it streams two PCM chunks per line, honours cancel, and reports errors."""

from __future__ import annotations

import asyncio
import base64
import json
import wave
from pathlib import Path

import pytest
import websockets

from referee.tts import CartesiaTTS, FanoutSink, WavSink


class FakeCartesia:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.cancelled: list[str] = []
        self.url = ""
        self.query = ""

    async def handler(self, ws) -> None:
        self.query = ws.request.path
        async for raw in ws:
            m = json.loads(raw)
            if m.get("cancel"):
                self.cancelled.append(m["context_id"])
                continue
            self.requests.append(m)
            ctx = m["context_id"]
            if "boom" in m["transcript"]:
                await ws.send(
                    json.dumps(
                        {"type": "error", "context_id": ctx, "title": "Bad voice", "message": "no", "done": True}
                    )
                )
                continue
            for i in range(2):
                await asyncio.sleep(0.01)
                pcm = bytes([i] * 480)  # 240 samples
                await ws.send(
                    json.dumps(
                        {"type": "chunk", "context_id": ctx, "data": base64.b64encode(pcm).decode(), "done": False}
                    )
                )
            await ws.send(json.dumps({"type": "done", "context_id": ctx, "done": True}))


@pytest.fixture
async def fake():
    f = FakeCartesia()
    async with websockets.serve(f.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        f.url = f"ws://127.0.0.1:{port}/tts/websocket"
        yield f


async def _tts(fake: FakeCartesia, tmp_path: Path) -> tuple[CartesiaTTS, WavSink, FanoutSink]:
    async def tokens() -> str:
        return "ct_test"

    tts = CartesiaTTS(
        tokens, version="2026-08-14", voices={"calls": "v-calls", "ref": "v-ref"}, url=fake.url, sample_rate=24000
    )
    wav, fan = WavSink(tmp_path / "voice", 24000), FanoutSink()
    tts.add_sink(wav)
    tts.add_sink(fan)
    await tts.start()
    return tts, wav, fan


async def test_speak_streams_chunks_measures_ttfa_and_writes_wav(fake, tmp_path):
    tts, wav, fan = await _tts(fake, tmp_path)
    q = fan.subscribe()
    res = await tts.speak("Out. Point, A.", voice="calls", emotion="excited")
    assert res.error is None and len(res.pcm) == 960 and res.ttfa_ms is not None and res.ttfa_ms < res.total_ms
    assert res.duration_s == pytest.approx(960 / 48000)
    req = fake.requests[0]
    assert req["voice"] == {"mode": "id", "id": "v-calls"} and req["model_id"] == "sonic-3.6"
    assert req["transcript"] == '<emotion value="excited"/>Out. Point, A.' and req["max_buffer_delay_ms"] == 0
    assert req["output_format"] == {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000}
    assert "cartesia_version=2026-08-14" in fake.query and "access_token=ct_test" in fake.query
    with wave.open(str(wav.written[0]), "rb") as w:
        assert w.getframerate() == 24000 and w.getnframes() == 480
    msgs = [q.get_nowait() for _ in range(q.qsize())]
    assert [m["done"] for m in msgs] == [False, False, True] and msgs[0]["voice"] == "calls"
    await tts.stop()


async def test_interrupt_cancels_the_previous_line(fake, tmp_path):
    tts, _, _ = await _tts(fake, tmp_path)
    first = asyncio.create_task(tts.speak("first line", interrupt=False))
    await asyncio.sleep(0.005)
    second = await tts.speak("second line", interrupt=True)
    r1 = await first
    assert r1.cancelled is True and second.cancelled is False and second.error is None
    assert fake.cancelled == [r1.context_id]
    await tts.stop()


async def test_error_messages_surface(fake, tmp_path):
    tts, _, _ = await _tts(fake, tmp_path)
    res = await tts.speak("boom")
    assert res.error and res.error.startswith("Bad voice") and res.pcm == b""
    await tts.stop()
