# Trophy interfaces v1: the contracts the three agents build against

*Planning lead, 2026-10-23; revised 2026-10-24 for the **Cal Hacks demo weekend**. Status: **v1 agreed**. Companion to [three-agent-plan.md](three-agent-plan.md). The weekend additions are §15 (`decide()` voters: Claude, Gemini, Bitdeer), §16 (Cartesia voice), §17 (ask the ref: Apify → Moss → Claude) and §18 (the Factory Droid compiler). SubQ, Firecrawl and Deepgram are not used.*

This file is the source of truth for wire formats **until Agent 1 lands checkpoint C0**. After that, the JSON Schemas in `packages/contracts/` and the generated types win, and this file is the narrative. If they disagree, whoever notices fixes this file. **[OPEN]** marks unresolved items.

**Principle (D-18): perception emits measurements; rule packs decide.** An event states what was observed, with uncertainty: "bounce at (x, y), σ = 1.8 cm, top-edge p = 0.71" or "left toe 3 cm inside the kitchen at contact". Whether that is a point, a fault or a foul is decided only by the engine, from CEL conditions and scoring templates in `rulepacks/*.yaml`. That is what lets the Droid add house rules without touching perception code.

---

## 0. Ownership of shared artifacts

| Artifact | Path | Maintainer | Change process |
|---|---|---|---|
| JSON Schemas | `packages/contracts/*.schema.json` | **Agent 1** | `contracts/<topic>` PR; merged by Agent 1 after the producer and consumer agents acknowledge it. Breaking changes bump `schema` (`…v1` → `…v2`) and go in `docs/decisions.md` |
| Generated TS types | `packages/contracts/gen/ts/` (`@trophy/contracts`) | Agent 1 | `make contracts`; never hand-edited |
| Generated Pydantic v2 models | `packages/py-trophy/trophy/contracts/` | Agent 1 | `make contracts`; never hand-edited |
| `packages/py-trophy` (`trophy.framebus`, `trophy.streams`, `trophy.tracks`, `trophy.ids`, `trophy.timebase`) | | Agent 1 | PR. Deps are only `pydantic>=2`, `redis>=5` and `python-ulid`; it must import on py3.11 and py3.12 |
| `@trophy/state-client` and the SpacetimeDB module | `packages/state-client/`, `spacetime/` | Agent 1 | Agent 3 acknowledges reducer changes |
| Rule packs (rules, scoring, params, teams) | `rulepacks/*.yaml` | **Agent 3** | PR |
| Field templates (`field:` block of each pack) | `rulepacks/*.yaml` → `field:` | **Agent 2** | PR; Agent 3 acknowledges |
| Event-type payload definitions | `packages/contracts/event.schema.json` → `$defs` | The producing agent drafts it, Agent 1 merges it | `contracts/*` PR |
| Synthetic fixtures | `evals/fixtures/synthetic/` | Agent 3 (event logs), Agent 2 (rendered clips) | Always labelled `synthetic` |
| Recorded fixtures and labels | `evals/fixtures/recorded/`, `evals/labels/<sport>/` | Whoever records or labels them | Labels from humans only |

Python services consume py-trophy as a uv path dependency: `trophy = { path = "../../packages/py-trophy", editable = true }`.

---

## 1. Identifiers

| Id | Format | Minted by |
|---|---|---|
| `game_id` | `g_` + 8 lowercase Crockford base32 chars | gateway `POST /api/games` |
| `join_key` | 22-char URL-safe random string (128 bit). It lives only in Redis `game:{id}` and the join QR code | gateway |
| `cam_id` | `c_` + 6 base32 chars. The PWA keeps it in `localStorage["trophy.cam." + game_id]` | gateway `POST /api/games/{id}/join` |
| `cam_token` | HMAC-SHA256 compact token `{game_id, cam_id, role, exp}`, 12 h; the secret `TROPHY_TOKEN_SECRET` stays server-side | gateway |
| `team_id` | Declared by the pack. Ping pong / pickleball / tennis / badminton / volleyball: `A`, `B`. Basketball / football: `home`, `away` | rule pack |
| `player_id` | `p_` + 6 base32 chars (an enrolled name is optional, with consent) | engine (`join_player`) |
| `track_id` | `{cam_id}:{int}`: a per-camera person or ball track. Multi-camera fusion (M2) assigns `f:{int}` | perception |
| `event_id`, `call_id`, `challenge_id`, `req_id`, `rule_version` | ULID | producer |
| `rally_no` / `possession_no` | Integer from 1 within a game: *rally* for net and racket sports, *possession* for basketball and football | engine |
| `seq` | uint32 per camera, from 0 at each WS connect | PWA |

## 2. Time
- **Server clock `t_srv_ms`**: epoch ms (float) on the gateway host. Every host must be NTP-synced. M1 is a single Mac.
- **Game epoch `t0_ms`** is set at `create_game`. **Game time `t_game_s = (t_srv_ms − t0_ms) / 1000`.** Every event, call and track sample carries `t_game_s`.
- **Phone clock:** `performance.timeOrigin + performance.now()`. Frame capture time is `timeOrigin + (rVFC captureTime ?? presentationTime)`. Audio onset time is `timeOrigin + performanceTime` mapped from AudioContext time via `getOutputTimestamp()`.
- **Mapping (gateway, per camera):** `t_srv_ms = t_phone_ms + a + b·(t_phone_ms − t_ref) + pipeline_offset_ms`. `a` and `b` come from the NTP-style min-RTT fit ([X] §3A); `pipeline_offset_ms` is 0 until the QR-timecode calibration (M2). The gateway publishes `sync_err_ms`. **Audio onsets use the same fit plus `audio_offset_ms`** (default 0; measured with a clap test in M1 and stored in `cam:{cam}`).
- **Perception copies `t_game_s` from the frames or onsets it uses**, interpolating for sub-frame events such as a bounce between frames. It never stamps from its own clock.
- **Clips:** the clip player sets `t_game_s = media_time_s + clip_offset_s` and writes `source=file`.
- Suffix `_ms` means milliseconds and `_s` means seconds.

## 3. Coordinates and units
- **Image pixels:** the frame as it is on the bus. Top-left origin, +x right, +y down. Anything with pixel coordinates also carries `image_size {w,h}`.
- **Field frame:** metres, right-handed, **z up**. Each pack's `field.frame` describes the origin and axes, `field.landmarks` gives the tap points (in tap order), and `field.lines` / `field.zones` give the geometry used by rules. Agent 2 maintains these:
  - **Table tennis:** origin at the centre of the table's top surface; +x toward **end B**, +y left when facing from end A to end B, z up. The table is 2.74 × 1.525 m; the net plane is x = 0; the net is 0.1525 m high. Landmarks in order: `A_left, A_right, B_right, B_left`, where **the user taps team A's end first**. Lines: `end_A, end_B, side_left, side_right`; `edge_band_m` is a pack param.
  - **Basketball (half court):** courtcam's `basketball_half` template: origin at the centre of the baseline under the hoop, +x toward the right sideline, +y into the court, z up. It carries the `three_point_arc` polyline, `rim` (centre, radius 0.2286 m at z = 3.05 m) and `boundary` polygon. The variant (FIBA/NBA/NCAA/NFHS/park) is a pack param, and Agent 2 measures the park court if it isn't standard.
  - **Pickleball / badminton / volleyball (M2/M3):** courtcam templates, re-based as documented in each pack. **Tennis and football (M3):** new templates.
- **Homography `H_img_to_field`:** 9 floats, row-major, image px → field metres on z = 0. **Camera pose:** `K` (9), `dist` (`[k1]`, courtcam's division model), `rvec` (3), `tvec` (3), with world = the field frame.
- **Uncertainty:** `sigma_m` is isotropic 1σ; `cov_m2` (2×2 or 3×3, row-major) is optional. **Angles are radians on the wire.** Probabilities are in [0, 1].

---

## 4. Process topology and boundaries

```
PWA (A1) ─HTTPS/WSS─▶ gateway (A1) ─▶ Redis: frames:{cam}, ev:audio, ctl:engine, game:{id}, cam:{cam}, calib:{cam}
clip player (A2) ────────────────▶ Redis: frames:{cam} (source=file), optional ev:audio from the clip audio
flight (A2)       reads frames, ev:audio, calib → writes ev:flight, trk:ball:{cam}
players (A3)      reads frames, calib, ev:flight → writes ev:players, trk:players:{cam}
possession (A3)   reads frames, trk:players, calib → writes ev:possession (basketball shots/outs, football)
recorder (A1)     reads frames, trk:* → writes data/local/recordings/{game}/{cam}/ segments + index
engine (A3)       reads ev:*, ctl:engine → reducers → SpacetimeDB (A1 module) → subscriptions → PWA, dashboard
courtcam-adapter (A2) ← POST /calibrate from the gateway
```
```
compiler (A3, Node + Factory Droid SDK) ◀─subscribes─ Spacetime house_rule rows ─▶ reducers (plan/diff/results) ; writes rulepacks/house/…
rules (A3, py3.11) ◀─ gateway POST /api/ask ; Apify actor output → Moss index ; Claude answers from retrieved clauses
engine (A3) ─ on challenge: decide() fan-out to Claude ‖ Gemini ‖ Bitdeer (crops from gateway /api/replay/.../frames)
```
**Rules:**
1. Only **backend services** write to SpacetimeDB: the **vision modules** (`observation` and `track_sample` only, D-21), the **engine** (game state, calls, votes, ask log) and the **compiler** (house-rule plan, diff and results only). Reducers check the caller's service identity. **Video frames never go into Spacetime.** They stay on the Redis frame bus and in the local recorder.
2. Clients read through `@trophy/state-client` and write through the gateway (`POST /api/ctl` → `ctl:engine`).
3. Perception reads Redis only.
4. The frame bus is transport-agnostic: JPEG-WS, aiortc and the clip player all write the same format.

**Redis keys:** `game:{game_id}` (hash: `sport`, `t0_ms`, `status`, `join_key`, `pack_version`), `cam:{cam_id}` (hash, §5.3), `calib:{cam_id}` (JSON) + pub/sub `ctl:calib`. Streams: `frames:{cam}`, `ev:flight`, `ev:players`, `ev:possession`, `ev:audio`, `trk:ball:{cam}`, `trk:players:{cam}`, `ctl:engine`.

---

## 5. Frame bus (A1 produces; the A2 clip player produces; A2, A3 and the A1 recorder consume)

### 5.1 Phone → gateway: `WSS /api/ws/frames?token=<cam_token>`
A binary, little-endian message: a 16-byte header, then the JPEG.
```
0 u8 version=1 | 1 u8 flags (bit0 calibration still, bit1 first after (re)start) | 2 u16 reserved | 4 u32 seq | 8 f64 t_capture_phone_ms | 16… JPEG
```
- **M1 default: 1280×720 at 30 fps, JPEG quality 0.7** (ball sports need frame rate). The gateway also accepts 640×360 to 1920×1080.
- **Latest frame wins:** the phone sends only if `ws.bufferedAmount === 0`.
- If the measured fps stays below 25, Agent 1 switches that phone to WebRTC (aiortc), which writes the same bus.

### 5.2 Gateway → `frames:{cam_id}`: `XADD MAXLEN ~ 300`
| Field | Meaning |
|---|---|
| `v` | `"1"` |
| `game_id`, `cam_id`, `seq` | |
| `t_phone_ms`, `t_srv_ms`, `t_game_s`, `sync_err_ms` | §2 |
| `w`, `h` | read from the JPEG SOF |
| `fmt` | `"jpeg"` |
| `source` | `"ws"` / `"webrtc"` / `"file"` |
| `data` | the JPEG bytes |

**Consumers process the newest frames and never a backlog.** Flight may read every frame (it needs consecutive frames, deduplicated by `seq`). Players reads about 10–15 fps. Use `trophy.framebus.FrameReader`.

### 5.3 Camera metadata: hash `cam:{cam_id}` (gateway)
`game_id, label, role (cam|display|judge, comma-combinable), ua, fps_in, w, h, sync_err_ms, offset_ms, drift_ppm, audio_offset_ms, last_seen_ms, connected`. The gateway forwards `camera_health` to the engine at most once every 2 s.

---

## 6. Calibration (A1: UI, proxy, storage; A2: solver)
1. The PWA gets `GET /api/cams/{cam}/still` (the newest JPEG + `X-Seq`, `X-W`, `X-H`) and asks the user to tap `field.landmarks` in order. For table tennis that is "tap team A's end first": `A_left, A_right, B_right, B_left`. Points can be dragged. M2 adds optional extra landmarks (net post tops) to improve the pose.
2. `POST /api/calibrate` (gateway → courtcam-adapter `POST /calibrate`):
```json
{"schema":"trophy.calibration_request.v1","game_id":"g_…","cam_id":"c_…","sport":"table_tennis","seq":812,
 "image_size":{"w":1280,"h":720},"points":[{"name":"A_left","px":[212.5,470.0]}, …]}
```
3. Response:
```json
{"schema":"trophy.calibration.v1","game_id":"g_…","cam_id":"c_…","sport":"table_tennis","created_at_ms":0,
 "image_size":{"w":1280,"h":720},"method":"homography+pnp",
 "H_img_to_field":[…9], "K":[…9], "dist":[0.0], "rvec":[…3], "tvec":[…3], "camera_position_m":[x,y,z],
 "reproj_err_px":1.4, "trusted":true, "warnings":[], "overlay_px":[[x1,y1,x2,y2], …],
 "solver":"courtcam@b2f5ff5"}
```
   - **Solver notes:** courtcam's `calibrate.homography` uses RANSAC only with ≥ 6 points, so 4 corners get a least-squares fit, which is exact. Add degeneracy checks (convexity, orientation, condition number, minimum tapped area) and a focal-length plausibility check for K. courtcam has no table template, so the adapter builds it from the pack. `trusted` uses the courtcam-style gate, max(5 px, 1% of the click span), plus those checks.
4. When the user confirms, `POST /api/cams/{cam}/calibration` → the gateway writes `calib:{cam}`, `PUBLISH ctl:calib {cam_id}`, and sends a `set_calibration` ctl command.
5. Perception reloads on `ctl:calib`. **Without a trusted calibration, events carry `payload.calib_untrusted = true` and the engine caps tiers at BETA** (the courtcam `fit_check` idea).

---

## 7. Events: `trophy.event.v1`

Streams `ev:flight` (A2), `ev:players` (A3), `ev:possession` (A3) and `ev:audio` (A1). Each entry has one field, `json`. The engine uses consumer group `engine`. **Perception services may also read other families' events**; for example, `players` reads `ev:flight` contacts for the kitchen rule.

**Common fields:**
- Required: `schema = "trophy.event.v1"`, `id` (ULID), `game_id`, `t_game_s`, `sport`, `type`, `source` (`flight|players|possession|audio|manual|synthetic|file`), `cams[]`, `conf`.
- Optional: `evidence` (`[{cam_id, seq0, seq1, t0_s, t1_s}]`), `track_id`, `actor_id` (player or track), `team_id`, `side` (`A|B`), `pos_m {x,y,z}`, `sigma_m`, `cov_m2`, `supersedes` (event id), `payload {}`.

**M1 event types and payloads** (anything not listed here is added through a `contracts/*` PR):

| `type` | Producer | Payload | Notes |
|---|---|---|---|
| `audio_onset` | A1 | `{peak, energy, cam_id}` | `t_game_s` comes from the clock fit + `audio_offset_ms` |
| `bounce` | A2 | `{surface: "table"\|"floor"\|"court", side: "A"\|"B", d_lines_m: {<line>: signed metres, + = inside}, p_in, edge: {top_edge, side_face, surface} \| null, timing: "audio"\|"track", onset_id?}` | `pos_m` is on the surface. `edge` is set only within `edge_band_m` of a table edge, and its probabilities sum to 1. `conf` = the probability that a bounce happened at all |
| `contact` | A2 | `{side, kind: "racket"\|"hand"\|"body"\|"unknown", height_m?, onset_id?}` | A ball reversal near a player, plus an onset |
| `net` | A2 | `{kind: "touch"\|"into"\|"over", from_side}` | |
| `ball_dead` | A2 | `{reason: "lost"\|"floor"\|"stopped"\|"out_of_view", last_side}` | A hint that the rally has ended |
| `serve_toss` | A2 | `{server_side, release: {t_s, pos_m}, apex: {t_s, pos_m}, contact: {t_s, pos_m}, height_m, sigma_height_m, rise_angle_rad, fall_angle_rad, angle_from_vertical_rad, sigma_angle_rad, palm_still_s, observable_plane: "xz"\|"yz"\|"mixed"}` | **Weekend MUST.** `release` is the first frame the ball rises from the still open palm behind the end line; `apex` is the top of the toss; `contact` is the racket hit (onset + reversal). `height_m = apex.z − release.z`. `angle_from_vertical_rad = max(rise, fall)`, the angles of the release→apex and apex→contact segments from vertical (the **"30° from the hand to the hit"** rule). With one camera, depth comes from the ball's known 40 mm diameter + calibration; σ is larger for motion toward or away from the camera, and `observable_plane` says which plane is well measured. **Put the camera side-on at the net line** |
| `person_feet` (M2) | A3 | `{player_id?, team_id?, feet_m: [[x,y], …], min_signed_dist_m: {<zone>: m}, sigma_m, airborne_p, ref_event_id}` | Emitted for referenced contacts (kitchen rule) |
| `shot` | A3 | `{shooter_track_id, team_id?, release_pos_m: [x,y], behind_arc_p, on_line_p, made: true\|false\|null, made_p, attempt_points_hint: 2\|3}` | `made = null` means courtcam's "can't tell", which caps at BETA |
| `line_cross` (M2) | A2/A3 | `{object: "ball"\|"player", boundary, holder_track_id?, p_out}` | Basketball and football outs |
| `player_contact` (M2) | A3 | `{a_track_id, b_track_id, min_dist_m, closing_speed_mps, first_mover_track_id?, during: "shot"\|"drive"\|"other"}` | Feeds `foul_flag` rules |
| `reach_over_net` (M3) | A3 | `{player_id?, team_id, beyond_m, sigma_m, touched_ball_p, before_opp_attack_p}` | Volleyball |
| `touch` (M3) | A3 | `{defender_track_id, carrier_track_id, both_hands_p, dt_s}` | Two-hand touch |
| `heartbeat` | all | `{service, fps, lag_ms, model, device, ep}` | At most 1 per 5 s per service per camera |

### 7.1 Observations in Spacetime (the shared world state, D-21)
Every event a vision module puts on `ev:*` is **also** written to the Spacetime `observation` table via `trophy.world.ObservationWriter` (py-trophy). That writer batches every 100 ms, or immediately for rally-ending types, through the reducer `post_observations(json[])`. Phones, the dashboard and the AI agents (LLM judge, Droid, ask the ref) all read this one sport-agnostic record. The engine keeps reading Redis `ev:*` for its millisecond hot path. The two carry identical event JSON, keyed by `id`, so they can't disagree.

## 8. Track streams (for replay overlays and later Watch)
- `trk:ball:{cam}` (A2), one entry per processed frame: `json = {t_game_s, seq, px: [x,y] | null, conf, pos_m?: [x,y,z], blur_len_px?, blur_angle_rad?}`. MAXLEN ~ 20000.
- `trk:players:{cam}` (A3), at 10–15 Hz: `json = {t_game_s, seq, players: [{track_id, team_id?, bb_px: [x,y,w,h], feet_m?: [[x,y],…], kp_px?: [[x,y,c]×26 Halpe-26]}]}`.
- The recorder (A1) persists both alongside the video for replay overlays.
- **Spacetime `track_sample`:** the vision module also writes the ball track **down-sampled to 10 Hz** (`{cam_id, t_game_s, pos_m?, px?, conf}`), with a rolling retention of the last 120 s that the engine prunes, so every device and agent can draw or reason about the live trajectory without video.

## 9. Control commands (gateway → engine): `ctl:engine`, `trophy.ctl.v1`
Each entry has one field, `json`: `{schema, req_id, cmd, game_id, t_srv_ms, by_cam_id, args{}}`. Clients may send only the commands their role allows (✓ below); the gateway enforces this.

| `cmd` | `args` | Client? | Effect |
|---|---|---|---|
| `create_game` | `{sport, teams?: [{team_id, name, color}], params?}` | gateway only | Game row (lobby), pack loaded |
| `register_camera` / `camera_health` / `set_calibration` | see §5.3 and §6 | gateway only | Camera row |
| `start_game` | `{first_server?: "A"\|"B"}` | ✓ judge | Status live |
| `set_server` | `{team_id}` | ✓ judge | Ping pong / pickleball serve state |
| `challenge` | `{call_id}` | ✓ any role | Call → `challenged`; challenge row opened |
| `resolve_challenge` | `{challenge_id, result: "upheld"\|"overturned", replacement?: {outcome, team_id?}}` | ✓ judge | Call → `upheld`/`overturned`; score is recomputed |
| `undo_last_call` | `{}` | ✓ judge | Call → `voided`; score recomputed |
| `adjust_score` | `{team_id, delta}` | ✓ judge | A manual correction, logged as an `info` call |
| `end_period` | `{}` | ✓ judge | End the game, set or half |
| `end_game` | `{}` | ✓ judge | |
| `submit_house_rule` | `{text, source: "typed"\|"voice"}` | ✓ judge | The engine inserts a `house_rule` row (status `pending`). **That row is the Droid's trigger** (§18) |
| `approve_house_rule` | `{rule_version}` | ✓ judge | The engine validates and hot-loads `rulepacks/house/{game_id}/{sport}.v{n}.yaml` from the next rally; an `info` call is spoken: "House rule added: …" |
| `reject_house_rule` | `{rule_version}` | ✓ judge | Status `rejected` |
| `ask_logged` | `{question, answer, citations, latency_ms}` | gateway only | The engine writes an `ask` row (dashboard transcript) |

## 10. Calls: `trophy.call.v1` (engine → SpacetimeDB `call` table)
| Field | Req | Notes |
|---|---|---|
| `schema`, `id`, `game_id`, `t_game_s`, `rule_id`, `rule_version` | ✓ | |
| `kind` | ✓ | `point` (rally result), `basket` (made shot with points), `line_call` (in/out), `edge_call`, `violation` (a measurable fault: serve, kitchen, reach-over-net, foot), `foul_flag` (a judgment foul; **BETA max**), `score_update`, `info` |
| `outcome` | ✓ | For example `point_A`, `in`, `out`, `edge_good`, `side_fault`, `made_3`, `made_2`, `illegal_toss_height` |
| `team_id`, `points` | | Who it favours and the points awarded |
| `p` | ✓ | Probability of `outcome`, calibrated where a calibration exists, otherwise labelled `p_source: "heuristic"` |
| `p_source` | ✓ | `geometry`, `heuristic`, `decide:ensemble` (geometry + voters, §15) or `manual` |
| `tier` / `shown` | ✓ | The gate (below) |
| `text` | ✓ | Display line (≤ 80 chars), e.g. `"Edge ball — good. Point A (71%)"` |
| `speech` | ✓ | Plain spoken line, e.g. `"Edge ball. Good. Point, A."` |
| `cue` | ✓ | `{beep: "short"\|"double"\|"long"\|"none", flash: "<team_id>"\|"#rrggbb"\|"none"}` |
| `event_ids`, `evidence` | ✓ | `evidence = [{cam_id, t0_s, t1_s}]`: the window the replay shows |
| `overlay` | | `{bounce_marks: [{pos_m, sigma_m, cov_m2?}], lines: [<line names>], highlight_track_ids: []}`: what the replay viewer draws |
| `status` | ✓ | `final`, `challenged`, `upheld`, `overturned`, `voided` |
| `supersedes`, `rule_ref`, `why` | | `why` is one short sentence based on event facts |
| `created_at_ms` | ✓ | For latency measurement |

**Gate (engine):**
- p ≥ 0.90 → `AUTO` / `auto`.
- 0.60 ≤ p < 0.90 → `BETA` / `challengeable`.
- p < 0.60 → `BETA` / `replay` ("replay the point" is suggested).
- The rule's `tier` is a **ceiling**.
- `foul_flag` is always ≤ BETA.
- Untrusted calibration → ≤ BETA.
- A rule needing an event type the pack can't sense → `PLAYERS` / `evidence`.

**`call_ack`:** the PWA sends `{type: "call_ack", call_id, t_phone_ms}` on `/api/ws/ctl` when it shows a call. The gateway logs `ack_latency_ms` and `event_to_ack_ms`.

## 11. Game state (SpacetimeDB 2.13 TypeScript module, Agent 1)
- Facts: native macOS arm64 CLI; npm client `spacetimedb`; reducers over HTTP with `POST /v1/database/{db}/call/{reducer}` (JSON args array, `Authorization: Bearer <token>`); `spacetime start` serves plain HTTP on :3000 behind the HTTPS origin's `/stdb/*`.
- Bindings are generated with `spacetime generate --lang typescript` into `packages/state-client/src/bindings/`.

| Table | Key | Columns |
|---|---|---|
| `game` | `game_id` | `sport, pack_version, status, t0_ms, period_no, rally_no, server_team_id?, teams_json, params_json, created_at_ms` |
| `camera` | `cam_id` | `game_id, label, role, device_json, calibration_json?, calib_trusted, connected, fps_in, sync_err_ms, last_seen_ms` |
| `rally` | `(game_id, rally_no)` | `status, t_start_s, t_end_s?, winner_team_id?, summary_json?` (possessions use the same table) |
| `call` | `call_id` | the full Call (§10); `evidence_json`, `overlay_json`, `cue_json` |
| `score` | `(game_id, team_id)` | `points, games?, sets?, display, updated_at_ms` (`display` is a sport-formatted string, e.g. `"10–9"` or `"40–30, 3–2"`) |
| `challenge` | `challenge_id` | `game_id, call_id, by_cam_id, status, result?, created_at_ms, resolved_at_ms?` |
| `house_rule` | `rule_version` | `game_id, sport, text, source, status (pending\|compiling\|ready\|approved\|rejected\|failed), backend (droid\|claude-fallback), plan_md, steps_json (streamed), diff, results_json ({tests:[{name, before, after, pass}], calls_changed:[…]}), pack_path, error?, created_at_ms, updated_at_ms` |
| `ai_vote` | `(challenge_id, backend)` | `call_id, backend (claude\|gemini\|bitdeer), model, choice, probs_json, latency_ms, error?, rationale (≤ 140 chars)` |
| `observation` | `event_id` | `game_id, cam_id(s), t_game_s, sport, type, source, track_id?, team_id?, side?, pos_json?, sigma_m?, conf, payload_json, supersedes?` (one row per Event, §7.1) |
| `track_sample` | `(cam_id, t_game_s)` | `game_id, object (ball\|player:<id>), pos_json?, px_json?, conf` (10 Hz, rolling 120 s) |
| `ask` | `ask_id` | `game_id, sport, question, answer, citations_json ([{rule_id, title, url, quote}]), latency_ms, created_at_ms` |
| `player` (later) | `player_id` | `game_id, name, team_id, consent_name, consent_face` |

**Reducers.**
- *Engine identity:* `upsert_game`, `upsert_camera`, `open_rally`, `close_rally`, `post_call`, `update_call_status`, `set_score`, `open_challenge`, `resolve_challenge`, `post_ai_vote`, `insert_house_rule`, `set_house_rule_status`, `post_ask`.
- *Compiler identity:* `update_house_rule_progress` (plan, steps, diff, results, status ∈ compiling/ready/failed only).
- *Vision identity:* `post_observations`, `post_track_samples`. *Engine:* `prune_track_samples`.

**Client interface** (`@trophy/state-client`; the apps code only against this):
```ts
export interface TrophyState {
  connect(gameId: string): Promise<void>; disconnect(): void;
  game(): Game | undefined;
  onGame(cb: (g: Game) => void): () => void;
  onCameras(cb: (c: Camera[]) => void): () => void;
  onCall(cb: (c: Call, change: "insert" | "update") => void): () => void;
  onScore(cb: (s: Score[]) => void): () => void;
  onRally(cb: (r: Rally) => void): () => void;
  onChallenge(cb: (c: Challenge) => void): () => void;
  onHouseRule(cb: (h: HouseRule) => void): () => void;
  onAiVote(cb: (v: AiVote) => void): () => void;
  onAsk(cb: (a: Ask) => void): () => void;
}
export function createState(impl: "mock" | "spacetime" | "ws", opts?: {uri?: string; module?: string; script?: MockScript}): TrophyState;
```
`MockState` replays `packages/state-client/fixtures/table-tennis-demo.json` and `basketball-demo.json`, both **labelled synthetic**.

**[OPEN-1] (Agent 1, by C2):** SpacetimeDB is the default. The `"ws"` implementation (an engine-side WebSocket fan-out of the same rows) is the fallback, with the interface unchanged.

## 12. Replay (Agent 1: recorder, API, viewer)
- **Recorder:** reads `frames:{cam}` and writes 2 s H.264 segments (ffmpeg `h264_videotoolbox` on the Mac, `libx264` elsewhere) to `data/local/recordings/{game_id}/{cam_id}/seg_{n}.mp4`. It also writes a JSONL index `{seq, t_game_s, seg, pts}` per frame, and copies `trk:*` to `tracks_{ball|players}.jsonl`. Recorded games (clips) are recorded the same way.
- **API (gateway, `cam_token` required):**
  - `GET /api/replay/{game_id}/clip?cam=&t0=&t1=` → `video/mp4` (cut on frame boundaries from segments; the default window is evidence ±1.5 s).
  - `GET /api/replay/{game_id}/overlay?cam=&t0=&t1=&call_id=` → `{frames: [{t_game_s, ball_px?, players?}], marks: [{t_game_s, px, ellipse_px: {cx, cy, rx, ry, angle_rad}}], lines_px: [...]}`. Field-frame marks are projected into image px with the camera's calibration (ellipses from `sigma_m` or `cov_m2`).
  - `GET /api/replay/{game_id}/cams?t0=&t1=` → the cameras with coverage (multi-angle, M2).
- **Viewer** (PWA and dashboard): plays the clip at 1×, 0.5× and 0.25× (`playbackRate`; RIFE interpolation in M3), frame-steps, and draws the overlay on a canvas synced with `requestVideoFrameCallback` mediaTime → `t_game_s`. It shows the call, `p`, the tier, and the judge's **Uphold / Overturn** buttons.
- **Privacy:** recordings stay in `data/local/` (gitignored) or access-controlled storage. Share links (M3) blur people who haven't consented.

## 13. Gateway HTTP API (Agent 1)
Everything is under `/api`. All routes except `POST /games`, `GET /games/{id}/public` and `GET /healthz` need `Authorization: Bearer <cam_token>`; WS routes use `?token=`.

| Route | Body → response |
|---|---|
| `POST /games` | `{sport, teams?, params?}` → `{game_id, join_key, join_url, t0_ms}` |
| `GET /games/{id}/public` | → `{game_id, sport, status, stdb: {uri, module}}` |
| `POST /games/{id}/join` | `{join_key, label, role, cam_id?, device}` → `{cam_id, cam_token, exp_ms, stdb, frame: {w, h, fps, quality}}` |
| `GET /cams/{cam}/still` | → JPEG + `X-Seq`/`X-W`/`X-H` |
| `POST /calibrate`, `POST /cams/{cam}/calibration` | §6 |
| `POST /ctl` | `{cmd, args}` → `202 {req_id}` (role allowlist, §9) |
| `WS /ws/frames` | §5.1 |
| `WS /ws/ctl` | Client → server: `ping {t0}`, `health {…}`, `onset {t_phone_ms, peak, energy}`, `call_ack {…}`. Server → client: `pong {t0, t1, t2}`, `sync {offset_ms, sync_err_ms}`, `cmd {…}` |
| `GET /replay/...` | §12 |
| `GET /replay/{game_id}/frames?cam=&t0=&t1=&n=4&crop=x,y,w,h` | → JSON `{frames: [{t_game_s, jpeg_b64}]}`. Internal (engine service token); used for `decide()` crops, each JPEG kept < 1 MB |
| `GET /voice/token` | → `{access_token, expires_at_ms}`: a short-lived Cartesia token minted server-side (§16). Never the API key |
| `POST /ask` | `{question, sport?}` → proxied to the `rules` service `POST /ask` (§17) → `{answer, speech, citations, latency_ms}`; the gateway then sends an `ask_logged` ctl command |
| `GET /healthz` | → `{ok, redis, adapter, recorder}` |

## 14. Dev and runtime conventions (M5 Pro)
- **One HTTPS origin for phones** (OPEN-2). Caddy + a DNS-01 certificate for a real domain pointing at the Mac's LAN IP is required for WebRTC and best for 720p30. A tunnel (cloudflared/ngrok) works for WebSocket only and adds latency, so it's acceptable for day-1 UI work only.
- **Ports:** gateway 8000, courtcam-adapter 8050, SpacetimeDB 3000, Redis 6379, PWA 5173, dashboard 5174. Each worktree adds its offset (A1 +0, A2 +100, A3 +200).
- **Native processes** in per-service `uv` venvs, run under a `Procfile` (`make dev`). The `docker-compose.yml` is the Linux/AWS path.
- **`.env`** is never committed: `TROPHY_TOKEN_SECRET`, `REDIS_URL`, `SPACETIME_URI`, `SPACETIME_MODULE`, `SPACETIME_ENGINE_TOKEN`, `SPACETIME_COMPILER_TOKEN`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `BITDEER_API_KEY`, `BITDEER_BASE_URL=https://api-inference.bitdeer.ai/v1`, `BITDEER_VISION_MODEL`, `CARTESIA_API_KEY`, `CARTESIA_VERSION`, `CARTESIA_VOICE_CALLS`, `CARTESIA_VOICE_REF`, `FACTORY_API_KEY`, `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `APIFY_TOKEN`, optional `ROBOFLOW_API_KEY`. Ports for the new services: `rules` 8100, `compiler` 8200.

---

## 15. `decide()`: the AI second opinion on challenges (Agent 3)
- **When and how fast: never on the live path.**
  - The engine **speculatively** starts the voters **in the background** when it posts a call whose rule declares `check: ensemble` with 0.35 < p < 0.75 (the edge rule, serve-toss calls near the limits, can't-tell baskets), or when any such call is challenged and hasn't been voted on yet.
  - The spoken call is never delayed. The voters run **in parallel** (so the cost is the slowest one, not the sum), each with a **4 s timeout**.
  - A challenge's replay starts immediately, and votes stream into the panel as they arrive.
  - **Measure the voter latencies in P0.** If one stays slow, switch it to a faster model.
  - **Decision models never make a line call alone** (D-5): they vote on crops, and geometry stays in the blend.
- **Request** (`trophy.decide.v1`): `{question, options: ["EDGE_GOOD", "SIDE_FAULT"], context (event facts as text: distance to edge, σ, trajectory after contact, audio class if any), images: ≤ 4 JPEG crops from /api/replay/.../frames around the bounce or toss (each < 1 MB), observations: [the relevant `observation` rows as JSON], timeout_s: 4}`.
- **Fan out in parallel** to three voters through one `Voter` interface:
  - **Claude** (`claude-opus-5-5`; structured output via `output_config.format` = `{choice, probs{opt: p}, rationale}`; no `temperature`, no forced `tool_choice`);
  - **Gemini** (`GEMINI_MODEL`; enum or JSON structured output);
  - **Bitdeer Model Studio** (OpenAI-compatible `chat.completions` at `BITDEER_BASE_URL`, model `BITDEER_VISION_MODEL`, for example `Qwen/Qwen3.5-397B-A17B`; `image_url` with base64 data; JSON response parsed and validated).
- **Shuffle the option order per voter** to cancel position bias. On a timeout or error, the voter is recorded with `error`, and the others still count.
- **Blend:** `p_final = w_geo·p_geometry + Σ w_i·p_i`, normalised over the voters that answered. The default weights are geometry 0.5 and each voter 0.5/3. **These are uncalibrated heuristics until ≥ 60 labelled challenges exist; say so in the UI** (`p_source: "decide:ensemble"`, with a "votes" panel showing each backend's choice, p and latency).
- **Effect:** the engine posts one `ai_vote` row per voter and a *suggested* verdict. **The judge still taps Uphold or Overturn.** The AI advises and players decide.

## 16. Voice (Cartesia; Agent 1 client, Agent 3 text)
- **TTS:** **Sonic** over WebSocket from the phone and the dashboard, authenticated with a short-lived token from `GET /api/voice/token`. One `context_id` per game with `continue: true` for flowing speech; `cancel` lines that a newer call makes stale. Lower `max_buffer_delay_ms`. Two voices: **calls** (crisp) and **ref** (verdicts and ask-the-ref answers). Inline `<emotion value="excited"/>` only on game point and match point. Calls arrive with `speech` text from the engine.
- **STT:** **Ink-2** via `wss://api.cartesia.ai/stt/turns/websocket?model=ink-2&encoding=pcm_s16le&sample_rate=16000&access_token=…&cartesia_version=…`. It has built-in turn detection (`turn.end` gives the transcript) and is English only. **Push-to-talk** in the PWA (a big button; hands-free wake word is out for the weekend). Use a separate mic track with echo cancellation ON, because the onset detector's track has it OFF.
- **Intent parse** (client-side regex first, then the gateway falls back to a Claude Haiku classification): `challenge` · `ask:<question>` · `house_rule:<text>` · `score?` · `undo`. Each maps to `/api/ctl` or `/api/ask`.
- **Verify on day 1:** the header vs. query auth forms, and the current `cartesia_version` value (search results show `2026-03-01`). Record what worked in `docs/status/a1.md`.
- **Accessibility:** a "read everything" mode speaks every call and score change (Cartesia's "impact and responsibility" criterion).

## 17. Ask the ref: Apify → Moss → Claude (Agent 3, `services/rules`)
- **Apify actor "Sports Rulebook Scraper"** (`actors/rulebook-scraper/`, Python Apify SDK + Crawlee):
  - Input: `{sources: [{sport, url, kind: "html"|"pdf"}]}`.
  - Output dataset items, **one per rule**: `{sport, rule_id, title, text, url, source, license_note, fetched_at}`.
  - Sources to start with: ITTF Statutes/Laws (ping pong), USA Pickleball rulebook, FIBA or NFHS basketball, BWF laws, FIVB rules.
  - **Public pages only; no login or paywall.** Respect robots and terms.
  - Publish it on the Apify Store **after the user OKs it** (Best Actor).
- **Index:** a `rules index build` command pulls the dataset and builds **one Moss index per sport** (`moss-minilm`; metadata `{rule_id, title, url}`). Check the package name at docs.moss.dev.
- **`POST /ask {question, sport}`:**
  1. Moss `query(top_k=5)` (hybrid if available); log the Moss latency.
  2. Claude answers **only from the retrieved clauses**, citing `rule_id`s, ≤ 3 sentences, and says "I couldn't find that rule" when retrieval is weak.
  3. Return `{answer, speech, citations: [{rule_id, title, url, quote ≤ 25 words}], moss_ms, latency_ms}`.
- **Uses beyond ask-the-ref:** challenge verdicts and house-rule diffs show the closest official clause (`rule_ref`), and the Droid workspace gets the top-k clauses (§18).

## 18. Factory Droid house-rule compiler (Agent 3, `services/compiler`, Node 20 + `@factory/droid-sdk`)
- **Trigger** (the track's "trigger you designed"): the compiler subscribes to Spacetime `house_rule WHERE status = 'pending'`. A judge's typed or spoken `submit_house_rule` creates that row through the engine.
- **Sandbox** (the track's "control over what Droid can touch"): a fresh temp workspace per rule containing **only** the following. No network beyond the Factory API; a **90 s timeout**; autonomy limited to editing that one YAML and running the test command.
  - `rules/<sport>.yaml`, a copy of the current pack;
  - `schema/rulepack.schema.json`;
  - `replay_test`, a CLI from the engine package that replays the last ≤ 10 recorded rally event logs through the engine with the candidate pack, prints a before/after call table, and validates the schema;
  - `context/clauses.md`, the top-k official clauses from §17.
- **Loop:** Droid drafts the change (CEL `when`, outcome, tier ceiling, or scoring params), runs `replay_test`, reads the failures, and repairs, for at most 3 attempts.
- **Visible work** (the track's "plans, steps, diffs, results"): stream the plan, each step, the YAML diff and the test table into the `house_rule` row via `update_house_rule_progress`. The dashboard panel renders them live with "Calls that would change: rally 7 (point A → let)".
- **Human approval:** the judge taps Approve, then `approve_house_rule`, then the engine hot-loads it. Every later call carries `rule_version`.
- **Fallback:** a Claude-only compiler (`claude-opus-5-5`, structured output, same tests). The row records `backend`.
- **The README must explain where and how Droid is used** (a Factory requirement).
- **Logs** are JSON lines with `svc`, `game_id`, `cam_id`, `t_srv_ms` and `msg`. No frames, tokens or personal data.
