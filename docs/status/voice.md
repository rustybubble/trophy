# Voice agent status: the referee that talks (Cartesia + Claude)

*Branch `voice/referee` in `../trophy-voice`, based on `a3/droid-realtime` @ `8c6711d`. Built 2026-10-24 alongside the
3D-map agent and the Droid agent, touching none of their files; merge all three together at the end.*

## What's built (D-32, interfaces-v1 §20)
| Piece | Where | Checked by |
|---|---|---|
| `services/referee`: router (regex → fast Claude), Redis `run_check`/`request_check` client with reply streams, Claude phrasing with a numbers guard and labelled template fallback, rule-pack Q&A grounded in `rules.yaml` + house rules, score/explain from the phone's context, the pending ("give me a moment") path that logs the late answer with `ask_logged` and speaks it, JSONL transcript log | `services/referee/referee/{router,checks,phrase,rules_qa,service}.py` | 37 pytest tests with a fake Claude, a fake engine on fakeredis and a fake Cartesia websocket server |
| Cartesia Sonic server-side client: one socket, per-line contexts, cancel on interrupt, emotion/speed tags, sinks (WAV, `/ws/audio` fanout, optional local speaker); Ink-2 transcription | `referee/tts.py`, `referee/stt.py`, `referee/cli.py` | `tests/test_tts.py`; **live:** `referee speak` with the real key (numbers in `docs/progress.md`) |
| FastAPI on :8100: `/ask`, `/speak`, `/transcribe`, `/checks`, `/ws/audio`, `/listen`, `/healthz` | `referee/app.py` | `tests/test_app.py` |
| Contracts: `run_check`, `request_check`, `CheckResult`, `RunCheckArgs`, `RequestCheckArgs`; `AskLoggedArgs` + `speech, kind, check, p, calibrated, by_cam_id` | `packages/contracts/ctl.schema.json` (+ codegen) | `make contracts`, codegen staleness |
| Gateway `/api/ask`: forwards `game_id`, `by_cam_id`, `context`; skips `ask_logged` for pending answers; two default voice ids | `services/gateway/gateway/app.py` | `test_ask_proxies_and_logs` |
| PWA: sends the game context with every question; shows the check, verdict, p and timings; speaks a late answer when its `ask` row arrives | `apps/pwa/src/lib/askContext.ts`, `LiveView.tsx`, `api.ts` | vitest `buildAskContext`, tsc, eslint |

## Not done / not verified
- **Claude not run live** (empty `ANTHROPIC_API_KEY`): routing and phrasing are tested with scripted replies only. First live run should check `output_config.format` on `claude-haiku-5-5` and `claude-opus-5-5` and the phrase latency (budget 0.5–1.5 s).
- **Engine side missing:** `run_check`, `request_check` handlers and `_ctl_ask_logged` pass-through of `speech/kind/check/p/calibrated` (requests to Agent 3 below). Until then check questions time out honestly after 1.5 s.
- **Pre-existing:** `services/gateway/tests/test_gateway.py::test_frames_ws_writes_bus_and_still` fails on this Mac with and without these changes (3 rows instead of 4); not touched.
- **Not measured:** voice ask → spoken answer end to end (needs the engine); Ink-2 server-side (`referee transcribe`) was not run live here.
- `REFEREE_SPEAKER=1` (sounddevice) not tried on this Mac.

## Requests to Agent 3 (Droid / engine, `a3/droid-checks`)
1. `Engine._ctl_run_check(g, args, by)`: resolve `args` (`t_game_s`, or `ref: last | last_rally | call:<id>`), run `session/checks/<check>.py`, XADD `{json: CheckResult}` to `args["reply_to"]`. Reply `error: no_such_check` when the session has no such check.
2. `Engine._ctl_request_check`: open a `droid_run` of kind `new_check` with `check_hint`; on gate pass run it and reply on `reply_to`; on failure reply `error: failed:<reason>`.
3. `_ctl_ask_logged`: keep `speech`, `kind`, `check`, `p`, `calibrated`, `by_cam_id` from `args` in the `ask` row (they are in the schema now).

## Requests to Agent 1 (when back)
- `ask` table columns for `speech`, `kind`, `check`, `p`, `calibrated` (today they ride in `json`).
- `docker-compose.yml` / Procfile: `referee` on :8100 replaces `rules`.
