# Referee voice service (`services/referee`, py3.11, :8100)

**The referee that talks to the players.** Calls are spoken on every phone the moment the engine posts them (the PWA
speaks `call.speech` through Cartesia). This service is the *conversation* on top of that, D-36 §5 stage 3:

```
judge holds the mic ─Ink-2 STT (phone)─▶ gateway POST /api/ask {question, context} ─▶ referee POST /ask
   ├─ route (regex, else Claude Haiku) ─▶ score (from the phone's context, no model)
   │                                   ─▶ explain the last call (Claude phrases the call's why/p)
   │                                   ─▶ rules question (Claude, grounded ONLY in sports/<sport>/rules.yaml + approved house rules)
   │                                   ─▶ session check: ctl:engine run_check ─▶ engine runs it over the 3D track ─▶ reply:<id>
   │                                                      └─▶ Claude phrases the measurement ─▶ {answer, speech, evidence}
   └─ no check fits ─▶ "Give me a moment" + request_check ─▶ Droid writes and gates it (30–90 s) ─▶ phrase ─▶ ask_logged
gateway ─ask_logged─▶ engine ─post_ask─▶ Spacetime `ask` ─▶ every phone (speaks `speech` when the row arrives late) + dashboard transcript
```

Claude **never computes geometry**: it phrases a check's result with the numbers pre-formatted here, and the line is
checked afterwards (every digit it says must be one it was given, or the deterministic rendering of the same
measurement is used instead, labelled `phrased_by: "template"`). The referee never fabricates: a missing rule pack,
a stalled engine or a failed Droid run come back as errors with an honest spoken line.

## Run
```bash
cd services/referee && uv sync && uv run referee serve            # needs ANTHROPIC_API_KEY + CARTESIA_API_KEY in .env
uv run referee speak "Out by three centimetres. Clear." --voice ref   # Cartesia only; writes a WAV, prints first-audio ms
uv run referee speak "Edge ball. Good. Point, B." --voice calls --emotion excited --play   # --play needs `uv sync --extra speaker`
uv run referee transcribe question.wav                               # Ink-2
uv run referee announce --speaker                                   # Cartesia only: speak every call the engine posts (Redis ev:calls) on this Mac
uv run referee ask "was that out" --game <game_id> --context ctx.json
```
**Every call is spoken.** `referee announce --speaker` (the Procfile's `announcer`) reads the engine's `ev:calls` stream
from now on and speaks each call's `speech` with the calls voice (Daniel) on the Mac's output; measured 2026-10-24 on this
Mac: first audio 83-321 ms after the call row, 3.2-3.4 s of audio per call. It needs only `CARTESIA_API_KEY`, so it runs
when `serve` cannot (no Anthropic key). Voided calls are never spoken; a judge's `label_rally` correction is.

`REFEREE_SPEAKER=1` plays the ref voice on this machine's output (a Bluetooth speaker at the table). Without it the
voice still reaches `/ws/audio` listeners (`/listen` is a test page) and the phones speak through their own sockets.

## API
| Route | Body → response |
|---|---|
| `POST /ask` | `{game_id, question, sport?, by_cam_id?, context?}` → `{kind: check\|rule\|score\|explain\|pending\|none, answer, speech, citations, check?, verdict?, p?, calibrated?, evidence?, inputs?, phrased_by, route_source, route_ms, check_ms, phrase_ms, latency_ms, reply_to?, error?}` |
| `POST /speak` | `{text, voice: ref\|calls, emotion?, interrupt?}` → `{context_id, ttfa_ms, total_ms, duration_s}` (server-side Cartesia) |
| `POST /transcribe` | WAV (mono 16-bit 16 kHz) or raw PCM → `{text, turn_end_ms}` (Ink-2) |
| `GET /checks` | the check catalog the router knows |
| `WS /ws/audio` | `{type: tts, ctx, seq, pcm_b64, voice, done}` chunks of every server-spoken line |
| `GET /healthz` | redis, tts socket, models, pending count |

`context` is the phone's view of the game (`apps/pwa/src/lib/askContext.ts`): `t_game_s`, `rally_no`, `server_team_id`,
`teams`, `scores`, the three newest `last_calls`, approved `house_rules`. "That" resolves to the newest call's time.

## What the engine must implement (Agent 3; contract in `packages/contracts/ctl.schema.json`)
- `run_check {check, args, reply_to, question}`: run the session's `checks/<check>.py` over the track buffer; `args` carries
  `t_game_s` when the referee knew it, else `ref: last | last_rally | call:<id>` (+ `rally_no`, `t0_s`/`t1_s`); XADD
  `{json: CheckResult}` to `reply_to` once. `error: no_such_check` when the session lacks it (the referee then asks the Droid).
- `request_check {question, check_hint?, args, reply_to}`: open a `droid_run` of kind `new_check`; when the gate passes, run
  it and reply with the `CheckResult`; on failure reply with `error`. The referee waits up to 95 s.
- `_ctl_ask_logged`: pass `speech`, `kind`, `check`, `p`, `calibrated` through to the `ask` row if the module gains those
  columns (today the row's `json` keeps them; the PWA speaks `answer` otherwise).

Until then `/ask` answers score, explain and rules questions fully, and check questions return `error: timeout` after
1.5 s with "The check didn't come back in time." No fake check backend exists outside the tests.

## Cartesia features used (track README material)
- **Sonic (`sonic-3.6`) over WebSocket**, one socket, one `context_id` per line, `max_buffer_delay_ms: 0`, `cancel` when a
  newer line interrupts, `pcm_s16le` 24 kHz relayed to sinks (WAV, speaker, `/ws/audio`); inline `<emotion value=…/>`
  (and `<speed ratio=…/>`) tags; **two library voices**: Daniel (calls, crisp) and Gemma (ref, verdicts and answers),
  overridable with `CARTESIA_VOICE_CALLS` / `CARTESIA_VOICE_REF`.
- **Ink-2 STT** (`/stt/turns/websocket`, built-in turn detection) server-side for the CLI and `/transcribe`; the phones
  use the same endpoint in the browser.
- **Short-lived access tokens** (`POST /access-token`, grants tts+stt, ≤ 3600 s): the API key never leaves the Mac;
  the server uses the same token path the browsers use (verified by the P0 spike).
- **Measured here (this Mac, 2026-10-24, real key, single runs):** socket open 1.3–2.8 s (first connect, includes the
  token mint); first audio **201 / 723 ms** (ref voice, two lines) and **371 ms** (calls voice with `excited`); full line
  done 1.8–3.0 s for 2.7–3.5 s of audio. The PWA's own path measured 112 ms first chunk on an iPhone (docs/status/a1.md).
- **Known limitations:** English only (Ink-2); the server socket is opened lazily, so the first line after idle pays the
  connect; `generation_config.emotion` accepts only 5 values, so sports emotions go inline; iOS routes mic + playback
  awkwardly, so the table speaker is the primary output and phones are secondary; no wake word (push-to-talk).

## Honest limits
- Claude phrasing and routing are **not yet run live** here: `ANTHROPIC_API_KEY` was empty in `.env.local` at build time.
  Both are covered by tests with scripted JSON replies; the request shape (`output_config.format`, no `temperature`) is
  the one `services/rules` used on the closed branch.
- Routing regexes are English judge phrases; anything else goes to the fast model.
- The "pending" path depends on the engine's `request_check`, which the Droid agent has not built yet.
