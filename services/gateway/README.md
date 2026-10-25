# Gateway (Agent 1)

**py3.11 FastAPI on 127.0.0.1:8000** (+ `PORT_OFFSET`), behind Caddy at `https://trophy.photo/api/*`. It holds **no game logic**: client actions become `ctl:engine` commands (`trophy.ctl.v1`), frames go to Redis `frames:{cam}`, audio onsets go to `ev:audio`. The Cartesia key never leaves this process.

```bash
cd services/gateway && uv sync
uv run python -m gateway                 # reads ../../.env (TROPHY_TOKEN_SECRET, REDIS_URL, CARTESIA_*, ...)
uv run pytest -q                         # 9 tests: tokens, join/ctl allowlist, frames WS, clock fit, onsets, acks, calibration, voice, ask
uv run python scripts/live_check.py      # acts like a phone against https://trophy.photo (needs Redis, Caddy, the gateway)
```

| Route (all under `/api`)                                           | Auth                     | What                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------ | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /games` `{sport, teams?, params?}`                           | none                     | → `{game_id, join_key, join_url, t0_ms}`; sends `create_game`                                                                                                                                                                                                                                                  |
| `GET /games/{id}/public`                                           | none                     | → `{game_id, sport, status, t0_ms, stdb: {uri, module}}`                                                                                                                                                                                                                                                       |
| `POST /games/{id}/join` `{join_key, label, role, cam_id?, device}` | join key                 | → `{cam_id, cam_token, exp_ms, t0_ms, stdb, frame}`; roles `cam,display,judge`; reuses a stored `cam_id`                                                                                                                                                                                                       |
| `POST /ctl` `{cmd, args}`                                          | Bearer                   | role allowlist (§9) + args validated against `ctl.schema.json` → `202 {req_id}`                                                                                                                                                                                                                                |
| `WS /ws/frames?token=`                                             | `cam` role               | 16-byte header + JPEG → clock-mapped `t_srv_ms`/`t_game_s` → `frames:{cam}`; `camera_health` every 2 s. Before the clock fit exists, frames are stamped by arrival with `sync_err_ms = 1000`                                                                                                                   |
| `WS /ws/ctl?token=`                                                | any                      | `ping {t0, prev?}` → `pong {t0, t1, t2}` + `sync {offset_ms, sync_err_ms}` (min-RTT fit, `trophy.timebase.ClockFit`); `onset` → `ev:audio` (needs a fit; adds `audio_offset_ms`); `health`; `call_ack` → `data/local/logs/call_ack.jsonl` with `ack_latency_ms` and `event_to_ack_ms` (looked up in Spacetime) |
| `GET /cams/{cam}/still`                                            | same game                | newest JPEG + `X-Seq`, `X-W`, `X-H`, `X-T-Game-S`                                                                                                                                                                                                                                                              |
| `POST /calibrate`                                                  | same game                | → courtcam-adapter (:8050); if it's down, a 4-point table-tennis homography stub, **always `trusted: false`** (calls capped at BETA)                                                                                                                                                                           |
| `POST /cams/{cam}/calibration`                                     | judge or that cam        | stores `calib:{cam}`, publishes `ctl:calib`, sends `set_calibration`                                                                                                                                                                                                                                           |
| `GET /voice/token`                                                 | any                      | → `{access_token, expires_at_ms, cartesia_version, voices: {calls, ref}}` (TTS + STT grants, 10 min)                                                                                                                                                                                                           |
| `POST /ask` `{question, sport?}`                                   | any                      | → rules service (:8100) `/ask`; then `ask_logged`                                                                                                                                                                                                                                                              |
| `GET /healthz`                                                     | none                     | `{ok, redis, spacetime, adapter, rules, recorder}`                                                                                                                                                                                                                                                             |
| `POST /clips?call_id=&seg=&t_start_phone_ms=&t_end_phone_ms=`      | `cam`                    | one high-quality phone segment for a challenged call (D-27); mapped onto game time with the camera's clock fit; stored in `data/local/clips/{game}/{call}/` with a JSON sidecar (ffprobe: w, h, codec, duration)                                                                                               |
| `GET /clips/{game}/{call}`, `GET /clips/{game}/{call}/{name}`      | same game (`?token=` ok) | list, and the file with Range support                                                                                                                                                                                                                                                                          |
| `GET /replay/...`                                                  |                          | **not yet**: comes with the recorder (§12)                                                                                                                                                                                                                                                                     |

The gateway doesn't write to Spacetime (D-14); the engine turns its ctl commands into rows. Audio onsets are not mirrored into `observation` (they're high-rate and raw; the vision module references them as `onset_id`). `python -m gateway.tokens` prints a 30-day `service` token for internal callers (the replay frames API).

## Preloaded games (`/api/demo/library`)

Multi-camera recordings already on the Mac play into a game with one click, no upload: `GET /api/demo/library` lists
`data/local/clips/library/<id>/preset.json` presets, `GET /api/demo/library/{id}/{label}/frame0.jpg` shows a camera's first
streamed frame, and `POST /api/demo/library/{id}/live {speed?, first_server?}` starts the game and streams every camera
through `scripts/stream_clips.py`, exactly like an upload: the tracker, the sport module and the engine recompute every call
on each run. Build presets with `uv run python scripts/build_library.py tt3d --game game_00` and
`uv run python scripts/build_library.py edmonton2015` (sources and licenses: `docs/licenses.md`, D-42); `... check` lists
what the gateway will see. Each preset folder gets an `overlay_<label>.jpg` with the corners drawn to eyeball.

## Recorder replay and Watch API

Start `services/recorder` before the cameras. These routes read its local archive:

| Route                                                         | Result                                                                                                                    |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/replay/{game}/clip?cam=&t0=&t1=`                    | H.264 MP4 with frame-boundary re-encoding, HTTP Range support                                                             |
| `GET /api/replay/{game}/overlay?cam=&t0=&t1=&call_id=`        | source ball/player samples, projected call bounce marks and one-sigma ellipses, calibration lines and explicit warnings   |
| `GET /api/replay/{game}/frames?cam=&t0=&t1=&n=4&crop=x,y,w,h` | 1–4 distinct original-frame JPEG crops with timestamps/seq; JPEG and base64 payload each <1 MB; **service role required** |
| `GET /api/watch/{game}/manifest`                              | game, teams, available final score, camera HLS/sprite URLs and timing, track availability                                 |
| `GET /api/watch/{game}/hls/{cam}/index.m3u8`                  | playlist; segment/init/sprite files share the same route                                                                  |
| `GET /api/watch/{game}/tracks?cam=&kind=ball&t0=&t1=`         | `replay.tracks.v1`: game-time frames, normalized boxes and optional court positions                                       |

Use a game-scoped camera/display/judge/viewer token, or an internal service token; cross-game access is
rejected. Media URLs use expiring query tokens so video players can fetch segments. Do not log or share
those URLs. These endpoints do not create public share links. Crops require the engine's gateway service
HMAC token (`python -m gateway.tokens`), not a Spacetime identity token.

Replay windows are explicit, finite, increasing and at most 30 seconds. Clips need finalized segment coverage;
original-frame crops are available earlier. Media PTS zero maps to the camera's `t0_game_s`.
Track gaps stay empty. Planar bounce ellipses use the inverse homography's Jacobian; nonplanar marks require
an undistorted pinhole pose. Missing/untrusted calibration is reported, never silently replaced by guessed geometry.
Final score comes from Spacetime when the game has ended; otherwise it stays null. Local manifest playback
continues when Spacetime is offline. The archive is local; the manifest isn't a public listing.

`bookmark`, `clip_that`, and judge-only `review_call` now validate through `/api/ctl` and the wire parser.
A `correct` review requires a replacement outcome.

Existing-footage smoke check (no download or filming):

```bash
uv run --frozen --project services/gateway python services/gateway/scripts/clip_as_phone.py \
  "data/ttClips/Adobe Express - IMG_4342.mp4" --seconds 8 --check-replay \
  --report data/local/recordings/integration.json
```

`--base`, `--stdb`, `--module`, `--redis-url`, `--env-file` support isolated local services. The script posts
a visibly synthetic call on actual recorded video; it does not run the tracker or claim rule accuracy.
An installed `ffprobe` supplies optional metadata for the existing HQ phone-upload route.
