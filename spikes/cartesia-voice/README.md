# Spike: Cartesia voice (Sonic TTS + Ink-2 STT) through a server-minted token

P0, 2026-10-24. The API key stays on the server (`.env`); clients only ever get a short-lived access token.

## Verified API (2026-10-24)
- **Version:** `2026-08-14` (header `Cartesia-Version` for HTTP; query `cartesia_version` for WebSockets).
- **Token:** `POST https://api.cartesia.ai/access-token`, `Authorization: Bearer <API key>`, body `{"grants": {"tts": true, "stt": true}, "expires_in": <s>}` → `{"token": "..."}`.
- **TTS:** `wss://api.cartesia.ai/tts/websocket?cartesia_version=2026-08-14&access_token=<token>`; request `{model_id: "sonic-3.6", transcript, voice: {mode: "id", id}, language: "en", context_id, output_format: {container: "raw", encoding: "pcm_s16le"|"pcm_f32le", sample_rate}, max_buffer_delay_ms: 0, continue: false}`; replies are `chunk` (base64 `data`) … then `done: true`. Cancel: `{context_id, cancel: true}`.
- **STT:** `wss://api.cartesia.ai/stt/turns/websocket?model=ink-2&encoding=pcm_s16le&sample_rate=16000&cartesia_version=2026-08-14&access_token=<token>`; send binary PCM in ~100 ms chunks, then `{"type": "close"}`; events `connected`, `turn.start`, `turn.update` (cumulative `transcript`), `turn.eager_end`, `turn.resume`, `turn.end` (final `transcript`), `error`.

## Results (measured)
`server_check.py`, Windows 11 PC on campus Wi-Fi → Cartesia, three runs, using only the minted token:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| Token mint (HTTP) | 284 ms | 208 ms | 193 ms |
| TTS first chunk after request | 309 ms | 186 ms | 87 ms |
| TTS done (2.6–2.8 s of audio) | 435 ms | 436 ms | 343 ms |
| Ink-2 `turn.end` after speech ended (audio streamed in real time, then silence) | 768 ms | 957 ms | 1030 ms |
| Transcript of "Edge ball. Good. Point, B." | `Edge ball, good, point B.` | `Edge ball. Good. Point B.` | `Edge ball. Good. Point B.` |

`index.html` in the desktop browser pane (Chromium 152, Windows): TTS played; first chunk **112 ms** after the request and 444 ms after the tap (including a 218 ms token mint, which the product should prefetch). Single run.

Through `https://trophy.photo/spike/voice/` in **desktop Firefox 158 on Windows** (single runs, posted back by the page): TTS first chunk **110 ms** after the request (574 ms after the tap, including the token mint). Push-to-talk: the first try returned an empty transcript (the button was released during the mic permission prompt; fixed in the page); the second try transcribed "Hello." with `turn.end` **591 ms** after release.

**iPhone (iOS 18.7, Firefox for iOS 158, i.e. WebKit), on campus Wi-Fi through `https://trophy.photo/spike/voice/` → the Windows PC** (single runs, 2026-10-24 ~19:04 UTC):
- **TTS:** played; 2.64 s of audio at 48 kHz; first chunk **112 ms** after the request, **234 ms after the tap** (token already cached).
- **Ink-2 push-to-talk:** "This is on" (`turn.end` 82 ms after release), then "This is on my phone." (`turn.end` 2 ms after release; the turn detector had already ended the turn while the button was held).
- Not yet run in Safari itself (same WebKit engine, but its own permission and audio policies).

## Run it
```bash
uv run --no-project --with websockets==15.0.1 python spikes/cartesia-voice/server_check.py   # server-only check
python spikes/cartesia-voice/serve.py --port 8765    # page + /voice/token + /spike/result
```
Then open `https://trophy.photo/spike/voice/` on the phone (Caddy, `infra/caddy/Caddyfile.dev`). The phone POSTs its measurements to `data/local/spikes/cartesia-iphone.jsonl`.
