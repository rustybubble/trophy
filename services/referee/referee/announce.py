"""`referee announce`: every call the engine posts is spoken through Cartesia, as it happens.

The engine's live loop appends each posted call to the Redis stream `ev:calls` (trophy.streams.EV_CALLS). This
reads the stream from "now" (a late start never replays old points) and speaks `call.speech` with the `calls`
voice, on this machine's output (`--speaker`, the table speaker) and to the service's `/ws/audio` listeners when
run inside `referee serve`. Cartesia only: it needs `CARTESIA_API_KEY` and nothing else, so it runs even when the
ask-the-ref service cannot (no Anthropic key). No fallback voice: without the key it refuses to start.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from redis import asyncio as aioredis

from .config import Settings
from .tts import AccessTokens, CartesiaTTS, WavSink

log = logging.getLogger("referee.announce")
STREAM = "ev:calls"
SPOKEN_STATUS = {None, "final", "upheld", "challenged", "pending"}


def line_for(call: dict[str, Any]) -> str | None:
    """What to say for a call row: its `speech` (the pack's spoken line), else its text; nothing for voided rows."""
    if call.get("status") not in SPOKEN_STATUS:
        return None
    line = str(call.get("speech") or call.get("text") or "").strip()
    return line or None


def emotion_for(call: dict[str, Any]) -> str | None:
    """Inline Cartesia emotion: a game or match point is exciting, a let or a correction is calm."""
    if call.get("outcome") == "let" or call.get("rule_id") in ("label_rally", "adjust_score"):
        return None
    cue = call.get("cue") or {}
    if cue.get("beep") == "long" or call.get("kind") == "basket":
        return "excited"
    return None


async def run_announcer(
    st: Settings,
    *,
    speaker: bool = False,
    stream: str = STREAM,
    tts: CartesiaTTS | None = None,
    r: Any = None,
    stop: asyncio.Event | None = None,
    start_id: str = "$",
) -> int:
    """Speak calls until `stop` is set. Returns how many lines were spoken. Owns the TTS socket and the Redis client
    only when it created them (`referee serve` passes its own)."""
    own_tts = tts is None
    if tts is None:
        tokens = AccessTokens(st.cartesia_api_key, st.cartesia_version)
        tts = CartesiaTTS(
            tokens.get, version=st.cartesia_version, voices=st.voices, model_id=st.tts_model, sample_rate=st.sample_rate
        )
        tts.add_sink(WavSink(st.data_dir / "referee" / "voice", st.sample_rate))
        if speaker:
            from .tts import SpeakerSink  # noqa: PLC0415 - optional dependency (sounddevice)

            tts.add_sink(SpeakerSink(st.sample_rate))
        await tts.start()
    own_r = r is None
    if r is None:
        r = aioredis.from_url(st.redis_url)
    last = start_id
    spoken = 0
    log.info(json.dumps({"svc": "announce", "msg": "started", "stream": stream, "speaker": speaker}))
    try:
        while stop is None or not stop.is_set():
            got = await r.xread({stream: last}, block=1000, count=20)
            for _key, entries in got or []:
                for entry_id, fields in entries:
                    last = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
                    raw = fields.get(b"json") if isinstance(fields, dict) else None
                    if raw is None and isinstance(fields, dict):
                        raw = fields.get("json")
                    try:
                        call = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    line = line_for(call)
                    if not line:
                        continue
                    t0 = time.perf_counter()
                    res = await tts.speak(line, voice="calls", emotion=emotion_for(call), interrupt=False)
                    spoken += 1
                    log.info(
                        json.dumps(
                            {
                                "svc": "announce",
                                "msg": "spoke",
                                "game_id": call.get("game_id"),
                                "call_id": call.get("id"),
                                "rule": call.get("rule_id"),
                                "text": line,
                                "ttfa_ms": round(res.ttfa_ms or 0.0, 1),
                                "total_ms": round(res.total_ms or (time.perf_counter() - t0) * 1000, 1),
                                "audio_s": round(res.duration_s, 2),
                                "error": res.error,
                            }
                        )
                    )
    finally:
        if own_tts:
            await tts.stop()
        if own_r:
            await r.aclose()
    return spoken
