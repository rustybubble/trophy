"""`referee serve | speak | transcribe | ask`. Reads .env; every subcommand needs the real keys."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .config import Settings


def _speak(st: Settings, a: argparse.Namespace) -> int:
    from .tts import AccessTokens, CartesiaTTS, WavSink

    async def run() -> int:
        tokens = AccessTokens(st.cartesia_api_key, st.cartesia_version)
        tts = CartesiaTTS(tokens.get, version=st.cartesia_version, voices=st.voices, sample_rate=st.sample_rate)
        out_dir = Path(a.wav_dir) if a.wav_dir else st.data_dir / "referee" / "voice"
        sink = WavSink(out_dir, st.sample_rate)
        tts.add_sink(sink)
        if a.play:
            from .tts import SpeakerSink

            tts.add_sink(SpeakerSink(st.sample_rate))
        await tts.start()
        print(f"socket open {tts.connect_ms:.0f} ms", file=sys.stderr)
        for line in a.text:
            res = await tts.speak(line, voice=a.voice, emotion=a.emotion, interrupt=False)
            if res.error:
                print(f"error: {res.error}", file=sys.stderr)
                return 1
            print(
                f"{a.voice}: first audio {res.ttfa_ms:.0f} ms, done {res.total_ms:.0f} ms, {res.duration_s:.2f} s audio"
                + (f" -> {sink.written[-1]}" if sink.written else "")
            )
        await tts.stop()
        return 0

    return asyncio.run(run())


def _transcribe(st: Settings, a: argparse.Namespace) -> int:
    from .stt import read_wav_16k, transcribe_pcm16
    from .tts import AccessTokens

    async def run() -> int:
        tokens = AccessTokens(st.cartesia_api_key, st.cartesia_version)
        pcm = read_wav_16k(Path(a.wav))
        text, ms = await transcribe_pcm16(tokens.get, pcm, version=st.cartesia_version, realtime=not a.fast)
        print(json.dumps({"text": text, "turn_end_ms": round(ms, 1)}))
        return 0

    return asyncio.run(run())


def _ask(st: Settings, a: argparse.Namespace) -> int:
    import httpx

    body = {"game_id": a.game, "question": a.question, "sport": a.sport}
    if a.context:
        body["context"] = json.loads(Path(a.context).read_text("utf8"))
    r = httpx.post(f"{a.url}/ask", json=body, timeout=30)
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0 if r.status_code == 200 else 1


def _serve(st: Settings, a: argparse.Namespace) -> int:
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(st), host=a.host, port=a.port or st.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="referee", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the HTTP service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=0)
    s = sub.add_parser("speak", help="say lines through Cartesia; writes WAVs and prints first-audio latency")
    s.add_argument("text", nargs="+")
    s.add_argument("--voice", default="ref", choices=["ref", "calls"])
    s.add_argument("--emotion")
    s.add_argument("--play", action="store_true", help="also play on this machine (needs the speaker extra)")
    s.add_argument("--wav-dir")
    s = sub.add_parser("transcribe", help="Ink-2 transcript of a WAV file")
    s.add_argument("wav")
    s.add_argument("--fast", action="store_true", help="send faster than real time")
    s = sub.add_parser("ask", help="POST a question to a running referee")
    s.add_argument("question")
    s.add_argument("--game", required=True)
    s.add_argument("--sport", default="table_tennis")
    s.add_argument("--context", help="JSON file with the game context (scores, last_calls ...)")
    s.add_argument("--url", default="http://127.0.0.1:8100")
    a = p.parse_args(argv)
    st = Settings.from_env(
        require=("CARTESIA_API_KEY",) if a.cmd in ("speak", "transcribe") else ("ANTHROPIC_API_KEY", "CARTESIA_API_KEY")
    )
    sys.exit({"serve": _serve, "speak": _speak, "transcribe": _transcribe, "ask": _ask}[a.cmd](st, a))
