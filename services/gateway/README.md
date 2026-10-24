# Gateway (Agent 1)
**py3.11 FastAPI on 127.0.0.1:8000** (+ `PORT_OFFSET`), behind Caddy at `https://trophy.photo/api/*`. It holds **no game logic**: client actions become `ctl:engine` commands (`trophy.ctl.v1`), frames go to Redis `frames:{cam}`, audio onsets go to `ev:audio`. The Cartesia key never leaves this process.

```bash
cd services/gateway && uv sync
uv run python -m gateway                 # reads ../../.env (TROPHY_TOKEN_SECRET, REDIS_URL, CARTESIA_*, ...)
uv run pytest -q                         # 9 tests: tokens, join/ctl allowlist, frames WS, clock fit, onsets, acks, calibration, voice, ask
uv run python scripts/live_check.py      # acts like a phone against https://trophy.photo (needs Redis, Caddy, the gateway)
```

| Route (all under `/api`) | Auth | What |
|---|---|---|
| `POST /games` `{sport, teams?, params?}` | none | → `{game_id, join_key, join_url, t0_ms}`; sends `create_game` |
| `GET /games/{id}/public` | none | → `{game_id, sport, status, t0_ms, stdb: {uri, module}}` |
| `POST /games/{id}/join` `{join_key, label, role, cam_id?, device}` | join key | → `{cam_id, cam_token, exp_ms, t0_ms, stdb, frame}`; roles `cam,display,judge`; reuses a stored `cam_id` |
| `POST /ctl` `{cmd, args}` | Bearer | role allowlist (§9) + args validated against `ctl.schema.json` → `202 {req_id}` |
| `WS /ws/frames?token=` | `cam` role | 16-byte header + JPEG → clock-mapped `t_srv_ms`/`t_game_s` → `frames:{cam}`; `camera_health` every 2 s. Before the clock fit exists, frames are stamped by arrival with `sync_err_ms = 1000` |
| `WS /ws/ctl?token=` | any | `ping {t0, prev?}` → `pong {t0, t1, t2}` + `sync {offset_ms, sync_err_ms}` (min-RTT fit, `trophy.timebase.ClockFit`); `onset` → `ev:audio` (needs a fit; adds `audio_offset_ms`); `health`; `call_ack` → `data/local/logs/call_ack.jsonl` with `ack_latency_ms` and `event_to_ack_ms` (looked up in Spacetime) |
| `GET /cams/{cam}/still` | same game | newest JPEG + `X-Seq`, `X-W`, `X-H`, `X-T-Game-S` |
| `POST /calibrate` | same game | → courtcam-adapter (:8050); if it's down, a 4-point table-tennis homography stub, **always `trusted: false`** (calls capped at BETA) |
| `POST /cams/{cam}/calibration` | judge or that cam | stores `calib:{cam}`, publishes `ctl:calib`, sends `set_calibration` |
| `GET /voice/token` | any | → `{access_token, expires_at_ms, cartesia_version, voices: {calls, ref}}` (TTS + STT grants, 10 min) |
| `POST /ask` `{question, sport?}` | any | → rules service (:8100) `/ask`; then `ask_logged` |
| `GET /healthz` | none | `{ok, redis, spacetime, adapter, rules, recorder}` |
| `GET /replay/...` | | **not yet**: comes with the recorder (§12) |

The gateway doesn't write to Spacetime (D-14); the engine turns its ctl commands into rows. Audio onsets are not mirrored into `observation` (they're high-rate and raw; the vision module references them as `onset_id`). `python -m gateway.tokens` prints a 30-day `service` token for internal callers (the replay frames API).
