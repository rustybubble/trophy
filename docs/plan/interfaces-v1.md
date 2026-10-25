# Trophy interfaces v1: the contracts the three agents build against

*Planning lead, 2026-10-23; revised 2026-10-24 for the **Cal Hacks demo weekend**. Status: **v1 agreed**. Companion to [three-agent-plan.md](three-agent-plan.md). The weekend additions are §15 (`decide()` voters: Claude, Gemini, Bitdeer), §16 (Cartesia voice), §17 (ask the ref: Apify → Moss → Claude) and §18 (the Factory Droid compiler). SubQ, Firecrawl and Deepgram are not used.*

This file is the source of truth for wire formats **until Agent 1 lands checkpoint C0**. After that, the JSON Schemas in `packages/contracts/` and the generated types win, and this file is the narrative. If they disagree, whoever notices fixes this file. **[OPEN]** marks unresolved items.

**Principle (D-18): perception emits measurements; rule packs decide.** An event states what was observed, with uncertainty: "bounce at (x, y), σ = 1.8 cm, top-edge p = 0.71" or "left toe 3 cm inside the kitchen at contact". Whether that is a point, a fault or a foul is decided only by the engine, from CEL conditions and scoring templates in `rulepacks/*.yaml`. That is what lets the Droid add house rules without touching perception code.

> **C0 landed (2026-10-24, Agent 1).** The schemas in `packages/contracts/` are now the source of truth; generated types are `@trophy/contracts` (TS) and `trophy.contracts` (Pydantic). Changes from the text below:
> - **Event (§7):** every payload in the table is a typed `$def` (`BouncePayload`, `ServeTossPayload`, …); `trophy.events.make_event` validates it. `serve_toss` points use `pos_m: {x, y, z}` like everything else. Any payload may carry `calib_untrusted`.
> - **Call (§10):** adds optional `rally_no`, `emotion` (Cartesia, game/match point only), `suggested` (the decide() verdict, advisory) and `overlay.serve_toss_event_id` (the toss trace the replay draws).
> - **`ai_vote` (§11) is keyed by `(call_id, backend)`**, with `challenge_id` nullable: votes start speculatively before any challenge exists (D-23). See D-25.
> - **Reducer args (§7.1, §11):** reducers take one JSON string argument (e.g. `post_observations(batch_json)`, a JSON array). The HTTP body is the args array, so it's `["<json text>"]`. Verified in the Spacetime latency spike (removed in the 2026-10-24 cleanup; numbers in `docs/status/a1.md`).
> - **Vision identity:** `trophy.world` writers send `Authorization: Bearer $SPACETIME_VISION_TOKEN` (new `.env` key).
> - **`TrophyState` (§11)** adds `synthetic`, `label`, `calls()`, `scores()`, `onObservation` and `onTrackSample` (the world view), and every `on*` replays known rows first. `MockState` scripts are `trophy.mock_script.v1`.
> - **`/api/ws/ctl` (§13):** `ping {t0, prev?}` carries the previous completed exchange `{t0, t1, t2, t3}` so the gateway can fit the clock (`trophy.timebase.ClockFit`).
> - **RulePack:** requires `version` and `teams`; adds `params`, `variants` (e.g. `ittf_strict`), `field.frame`, `field.landmarks [{name, pos_m, prompt}]`, and per-rule `kind`, `p`, `team`, `points`, `text`, `speech`, `requires`. `family` may be `resting`.
> - **Serve (2026-10-24, D-31):** `serve_toss` follows ITTF Law 2.6.2 (height from palm release to apex, angle on the rise, `struck_on_descent`, `TossMark` intervals with σ, `evidence_missing[]`, `estimator`); new `serve_hidden` (2.6.5) and `serve_position` (2.6.4) events; `net` gains `serve` for lets (2.9.1.1). Rule-pack params `toss_min_height_m: 0.16`, `toss_max_from_vertical_rad: 0.5236`, `toss_angle_segment: rise`; the old house values are the `house` variant.
> - **Post-game state (2026-10-24, rustybubble/trophy#10):** `moment`, `commentary` (keyed `(moment_id, voice)`), `droid_run` and `sport_module` tables; see §11.
> - **State rows:** `game.status` ∈ `lobby|live|paused|ended`; `house_rule.steps` items are `{t_ms, kind: plan|edit|test|repair|message|error, text}`.

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
| `net` | A2 | `{kind: "touch"\|"into"\|"over", from_side, serve?}` | `serve = true` on the served ball's crossing. A serve with `kind: touch` that then bounces correctly is a **let** (Law 2.9.1.1); the pack decides |
| `ball_dead` | A2 | `{reason: "lost"\|"floor"\|"stopped"\|"out_of_view", last_side}` | A hint that the rally has ended |
| `serve_toss` | A2 | `ServeTossPayload`: `{server_side, release, apex, contact?, height_m, sigma_height_m, angle_from_vertical_rad, sigma_angle_rad, angle_segment: "rise", struck_on_descent: bool\|null, struck_on_descent_p, touched_before_strike_p?, palm_still_s?, observable_plane?, house_hand_to_hit_angle_rad?, evidence_missing[], estimator: {name, version}}`; `release`/`apex`/`contact` are `TossMark {t_s, t0_s, t1_s, sigma_t_s, pos_m, sigma_m}` | **Weekend MUST; ITTF Law 2.6.2 (D-31).** `release` is when the ball leaves the still open palm behind the end line; `apex` is the top of the toss; `contact` is the racket strike. `height_m = apex.z − release.z` (**≥ 0.16 m** is legal). `angle_from_vertical_rad` is the **upward** segment release → apex (near vertical = **within 30°**, the ITTF review criterion). `struck_on_descent` says the ball was struck while falling. Anything not observed goes in `evidence_missing` (e.g. `spin`, which a camera can't judge), and a rule that needs it is PLAYERS DECIDE. With one camera, depth comes from the ball's 40 mm diameter + calibration; `observable_plane` says which plane is well measured. **Put the camera side-on at the net line** |
| `serve_hidden` | A2 | `ServeHiddenPayload`: `{server_side, t0_s, t1_s, visible_fraction, sigma_visible_fraction, min_visible_t_s?, occluder: none\|server_body\|server_clothing\|free_arm\|partner\|racket\|other\|unknown, cams_used: [{cam_id, view: receiver_side\|side_on\|server_side\|overhead, visible_fraction}], evidence_missing[], estimator}` | **Law 2.6.5:** the ball must stay visible to the receiver from the start of service until it is struck, and the free arm must leave the space between ball and net once the ball is projected. `visible_fraction` is the minimum over release → strike, seen from the receiver's side. Without a receiver-side view, add `receiver_view` to `evidence_missing` |
| `serve_position` | A2 | `ServePositionPayload`: `{server_side, t0_s, t1_s, min_above_surface_m, min_behind_end_line_m, worst_above_t_s?, worst_behind_t_s?, sigma_m, p_above, p_behind, evidence_missing[], estimator}` | **Law 2.6.4:** from the start of service until struck, the ball is above the playing surface and behind the server's end line. Signed distances, + = legal, minimised over the window |
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
| `bookmark` | `{t_game_s, label?}` | ✓ any role | A `moment` of kind `bookmark` |
| `clip_that` | `{t_game_s}` | ✓ any role | The trigger-to-play rule (the moment ending in [t − 8 s, t + 0.5 s]) → that moment gets the `clipped` tag |
| `review_call` | `{call_id, result: "confirm"\|"correct", replacement?}` | ✓ judge | A post-game review: updates the call and appends a label to `evals/labels/<sport>/<game>.jsonl` (`source: review`) |

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
- **As built (2026-10-24, `spacetime/src/index.ts`; full reducer table in `spacetime/README.md`):** every table has typed columns plus `json` (the full contract object), which `SpacetimeState` parses for clients. Composite keys are string columns (`rally_key = game_id:rally_no`, `score_key = game_id:team_id`, `vote_key = call_id:backend`); `track_sample` has an auto-increment id and the module itself keeps the last 120 s per camera. Roles: the owner registers service identities (`register_service`) as `engine`, `vision` or `compiler`; tokens come from `spacetime/scripts/provision.py`. `open_challenge` / `resolve_challenge` also update the call's status, and `open_challenge` links the call's speculative votes. The compiler's `update_house_rule_progress` takes `append_steps` for streaming. Caddy exposes only the subscription WebSocket, identity and ping at `/stdb`; reducer calls go to 127.0.0.1:3000.

| Table | Key | Columns |
|---|---|---|
| `game` | `game_id` | `sport, pack_version, status, t0_ms, period_no, rally_no, server_team_id?, teams_json, params_json, created_at_ms` |
| `camera` | `cam_id` | `game_id, label, role, device_json, calibration_json?, calib_trusted, connected, fps_in, sync_err_ms, last_seen_ms` |
| `rally` | `(game_id, rally_no)` | `status, t_start_s, t_end_s?, winner_team_id?, summary_json?` (possessions use the same table) |
| `call` | `call_id` | the full Call (§10); `evidence_json`, `overlay_json`, `cue_json` |
| `score` | `(game_id, team_id)` | `points, games?, sets?, display, updated_at_ms` (`display` is a sport-formatted string, e.g. `"10–9"` or `"40–30, 3–2"`) |
| `challenge` | `challenge_id` | `game_id, call_id, by_cam_id, status, result?, created_at_ms, resolved_at_ms?` |
| `house_rule` | `rule_version` | `game_id, sport, text, source, status (pending\|compiling\|ready\|approved\|rejected\|failed), backend (droid\|claude-fallback), plan_md, steps_json (streamed), diff, results_json ({tests:[{name, before, after, pass}], calls_changed:[…]}), pack_path, error?, created_at_ms, updated_at_ms` |
| `ai_vote` | `(call_id, backend)` | `challenge_id?, backend (claude\|gemini\|bitdeer), model, choice, probs_json, latency_ms, error?, rationale (≤ 140 chars)` |
| `observation` | `event_id` | `game_id, cam_id(s), t_game_s, sport, type, source, track_id?, team_id?, side?, pos_json?, sigma_m?, conf, payload_json, supersedes?` (one row per Event, §7.1) |
| `track_sample` | `(cam_id, t_game_s)` | `game_id, object (ball\|player:<id>), pos_json?, px_json?, conf` (10 Hz, rolling 120 s) |
| `ask` | `ask_id` | `game_id, sport, question, answer, citations_json ([{rule_id, title, url, quote}]), latency_ms, created_at_ms` |
| `moment` | `moment_id` | `game_id, kind (point\|serve_fault\|edge\|challenge\|basket\|bookmark\|house_rule\|rally), t_game_s, t_start_s, t_end_s, label, team_id?, track_id?, call_id?, rally_no?, score_after, tags_json, highlight_score, reasons_json, is_best_play, thumb_t_s` (the engine writes these live as calls happen, so post-game works the moment the game ends; §19) |
| `commentary` | `(moment_id, voice)` | `game_id, voice (pbp\|colour), text, facts_json, validated, created_at_ms` (as built in #10 the key is `commentary_key = [moment_id, voice]`, so both voices survive; the reducer needs the **engine** identity until a `rules` role exists; A3 writes; grounded lines for broadcast mode) |
| `droid_run` | `run_id` | `game_id, sport, kind (compile\|house_rule\|retune), status (queued\|running\|ready\|failed\|approved\|rejected), updated_at_ms, json` (the full `DroidRun`, `droidrun.schema.json`; #10, built for the closed #6 design, so Agent 3 may reuse or drop it) |
| `sport_module` | `(game_id or empty, sport)` | `version, run_id, path, approved_at_ms, json` (`SportModuleRow`, `sportmodule.schema.json`; compiler modules need a matching approved run and commit) |
| `player_label` | `(game_id, track_id)` | `label, set_by, updated_at_ms` (a viewer-given name; never automatic; no face recognition) |
| `watch_session` | `session_id` | `game_id, host, playing, t_game_s, rate, updated_at_ms` (watch party) |
| `watch_reaction` | `reaction_id` | `session_id, emoji, t_game_s, by, created_at_ms` |
| `player` (later) | `player_id` | `game_id, name, team_id, consent_name, consent_face` |

**Reducers.**
- *Engine identity:* `upsert_game`, `upsert_camera`, `open_rally`, `close_rally`, `post_call`, `update_call_status`, `set_score`, `open_challenge`, `resolve_challenge`, `post_ai_vote`, `insert_house_rule`, `set_house_rule_status`, `post_ask`.
- *Compiler identity:* `update_house_rule_progress` (plan, steps, diff, results, status ∈ compiling/ready/failed only).
- *Vision identity:* `post_observations`, `post_track_samples`. *Engine:* `prune_track_samples`, `upsert_moment`, `set_best_play`. *Engine (for the rules service until it has its own role):* `post_commentary`. *Compiler:* `update_droid_run` (never approves). *Engine:* `set_droid_run_status`, `upsert_sport_module`.
- *Client-callable (the one exception to "clients don't write", scoped and non-game state):* `watch_create`, `watch_join`, `watch_set_state` (host only), `watch_react`, `set_player_label`. Rate-limit them in the module.

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
- **Recorder:** reads `frames:{cam}` and writes **HLS** (ffmpeg `h264_videotoolbox` on the Mac, `libx264` elsewhere; 2 s fMP4 segments + `index.m3u8`, which is a live playlist during the game and finalised at `end_game`) to `data/local/recordings/{game_id}/{cam_id}/`.
  - It also writes a JSONL index `{seq, t_game_s, seg, pts}` per frame, with `t_game_s` at media time 0 stored in `meta.json`.
  - A **storyboard sprite** (`sprite_{n}.jpg`: a 10×10 grid of 160×90 thumbnails, one every 2 s) and `sprite.json`.
  - Copies of `trk:*` in `tracks_{ball|players}.jsonl`.
  - Recorded games (clips) are recorded the same way. Post-game playback (§19) uses this HLS stream.
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
| `POST /clips?call_id=&seg=&t_start_phone_ms=&t_end_phone_ms=` | body = one video segment (`video/mp4`, `video/webm` or `video/quicktime`, ≤ 250 MB); `cam` role; needs the camera's clock fit (409 otherwise) → `201` meta `{name, cam_id, seg, bytes, t_game_start_s, t_game_end_s, w, h, codec, duration_s}` (D-27) |
| `GET /clips/{game_id}/{call_id}` | → `{clips: [meta + url]}` for that call, every camera |
| `GET /clips/{game_id}/{call_id}/{name}` | the segment, with HTTP Range; `?token=` allowed because `<video>` can't send headers |

**As built (2026-10-24, `services/gateway`):** join and `/public` also return `t0_ms`; `/healthz` also reports `spacetime` and `rules`; client `ctl` args are validated against the `*Args` schemas (422 otherwise); frames that arrive before the clock fit exists are stamped by arrival time with `sync_err_ms = 1000`; onsets need a fit and are dropped before one exists; audio onsets go to `ev:audio` only (not mirrored into `observation`); `call_ack` latencies go to `data/local/logs/call_ack.jsonl`. Replay routes come with the recorder.

## 14. Dev and runtime conventions (M5 Pro)
- **One HTTPS origin for phones** (OPEN-2). Caddy + a DNS-01 certificate for a real domain pointing at the Mac's LAN IP is required for WebRTC and best for 720p30. A tunnel (cloudflared/ngrok) works for WebSocket only and adds latency, so it's acceptable for day-1 UI work only.
- **Ports:** gateway 8000, courtcam-adapter 8050, SpacetimeDB 3000, Redis 6379, PWA 5173, dashboard 5174. Each worktree adds its offset (A1 +0, A2 +100, A3 +200).
- **Native processes** in per-service `uv` venvs, run under a `Procfile` (`make dev`). A tested compose stack for a later Linux deploy is on the closed rustybubble/trophy#16.
- **`.env`** is never committed: `TROPHY_TOKEN_SECRET`, `REDIS_URL`, `SPACETIME_URI`, `SPACETIME_MODULE`, `SPACETIME_ENGINE_TOKEN`, `SPACETIME_COMPILER_TOKEN`, `SPACETIME_VISION_TOKEN`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `BITDEER_API_KEY`, `BITDEER_BASE_URL=https://api-inference.bitdeer.ai/v1`, `BITDEER_VISION_MODEL`, `CARTESIA_API_KEY`, `CARTESIA_VERSION`, `CARTESIA_VOICE_CALLS`, `CARTESIA_VOICE_REF`, `FACTORY_API_KEY`, `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `APIFY_TOKEN`, optional `ROBOFLOW_API_KEY`. Ports for the new services: `rules` 8100, `compiler` 8200.

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
- **As built (2026-10-24, `apps/pwa`):** a new call cancels the line that's still playing (a fresh `context_id` per line, `cancel` on the old one, rather than one continued context per game). Push-to-talk **reuses the raw onset mic** when it's open instead of opening a second, echo-cancelled track, because iOS can mute an earlier capture when a second one starts; Ink-2 transcribed correctly without echo cancellation in the iPhone spike. Calls older than 15 s when they arrive (e.g. after a reconnect) are listed, not announced.

## 17. Ask the ref: Apify → Moss → Claude (Agent 3, `services/rules`)
> **Dropped (D-36, the user 2026-10-24):** Moss and Apify are out and `services/rules` was never merged. Ask the ref is the referee service (§20, D-37, rustybubble/trophy#19). This section is kept only as the record of the old design.

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

---

## 19. Post-game: Trophy Watch (Agents 1 and 3; full feature map in [trophy-watch-postgame.md](trophy-watch-postgame.md))
- **App:** `apps/watch` (Vite 7 + React 19 + strict TS, served at `/watch/`). It vendors Replay `packages/tv-core` (`types`, `follow`, `clock`, `retry`, `display`, `replays`) into `apps/watch/src/vendor/tv-core/` with the MIT notice. It reads Spacetime (`game`, `score`, `rally`, `call`, `moment`, `observation`, `ai_vote`, `commentary`, `player_label`, `watch_session`) through `@trophy/state-client` and video through the gateway watch API.
- **Gateway watch API** (watch token = a `cam_token` with role `viewer`, or a share token):
  - `GET /api/watch/{game_id}/manifest` → `{game, teams, final_score, duration_s, cams: [{cam_id, hls_url, sprite: {url_template, cols, rows, every_s, w, h}, t0_game_s}], has_tracks: {ball, players}}`;
  - `GET /api/watch/{game_id}/hls/{cam_id}/index.m3u8` (+ segments);
  - `GET /api/watch/{game_id}/tracks?cam=&kind=ball|players&t0=&t1=` → **Replay `replay.tracks.v1` shape** (`{t0, rate_hz, frames: [{t, p: [{id, bb: [x,y,w,h] normalised, ct?: [x_m,y_m], c?}]}]}`), so the vendored `follow.ts` works unchanged; `t` is `t_game_s`;
  - `POST /api/watch/{game_id}/clip {cam_id, t0, t1, aspect: "16:9"|"9:16"}` → `{share_url, expires_at_ms}` (ffmpeg cut from HLS; 9:16 crops along the ball or player track; **the UI asks for consent before sharing**);
  - `POST /api/watch/{game_id}/share-token` → an expiring viewer link for "open on another screen".
- **Moments are written live by the engine** (A3) as calls happen, one per point, serve fault, edge call, challenge, basket, bookmark and approved house rule. `highlight_score` and `reasons` come from event features only (rally length, game or match point, closeness `|p − 0.5|`, overturned challenge, serve near the limit, three-pointer, game-winning basket). There's no crowd audio, so say so. `set_best_play` runs at `end_game` (and provisionally during play).
- **Rules service** (A3):
  - `POST /search_moments {game_id, q}` → Moss query over the game's moment index (built incrementally from `moment` rows) → `{hits: [{moment_id, score}], mode: "semantic"|"keyword"}`;
  - `POST /coach {game_id, side|track_id}` → `{tips: [{text, facts}], validated: bool}` (Claude, grounded, run through the adapted Replay `narrate/grounding.py` validator, with a template fallback).
  - Commentary lines are written to `commentary` per moment (voices `pbp` and `colour`) and validated the same way. The Watch app speaks them with Cartesia in broadcast mode.
- **Stats** are computed in the client from `moment`, `call` and `observation` (tv-core `statLine` rule: show "not detected" rather than a guessed 0), labelled **auto-detected**:
  - **ping pong:** points by side, serve vs. receive points, serve faults (low or angled), edge balls, longest rally, challenges, a bounce heatmap;
  - **basketball:** points by team and player track, 2PT/3PT makes, a shot chart.
- **Reconstructed views** (PG-SHOULD) are drawn from `observation` + `tracks` only and always carry the badge "Reconstructed from tracking — not video".

---

## 20. The referee voice service (`services/referee`, :8100; D-37)

*Added 2026-10-24 on branch `voice/referee`. Replaces §17's `rules` service on :8100 (D-36 dropped Moss and Apify): the gateway's `POST /api/ask` proxy is unchanged, the target is now the referee.*

- **`POST /api/ask`** (gateway, cam token) body is `{question, sport?, context?}`. The gateway adds `game_id` and `by_cam_id` and forwards to **`POST :8100/ask`**. `context` is the phone's view of the game (`t_game_s`, `rally_no`, `server_team_id`, `teams`, `scores`, the three newest `last_calls` with `id, kind, outcome, text, why, p, tier, t_game_s, rally_no, status, rule_id`, approved `house_rules`), built by `apps/pwa/src/lib/askContext.ts`. The referee resolves "that" to the newest call's `t_game_s`, answers the score from it, and grounds rule answers in the approved house rules, with no Spacetime read of its own.
- **Response:** `{kind, answer, speech, citations, latency_ms, …}` with `kind ∈ check | rule | score | explain | pending | none`. For `check`: `check, verdict, p, calibrated, tier, evidence, inputs, check_ms`; `citations` carries one row `{rule_id: "check:<name>", title: "<name>(args)", quote: "<margin, σ, p, uncalibrated>"}` so the dashboard's transcript shows the evidence in its existing columns. `phrased_by ∈ claude | template` says who wrote the line (a Claude line that says a number it was not given is replaced by the template). `route_source ∈ regex | claude`.
- **Logging:** the gateway sends `ask_logged` (now also `speech, kind, check, p, calibrated`) for every answer except `kind: pending`. A pending answer is logged by the referee itself when the Droid's check comes back (`by_cam_id` set), and phones that asked speak it when the `ask` row arrives.
- **Referee → engine (Redis `ctl:engine`, new commands in `ctl.schema.json`):**
  - `run_check {check, args, reply_to, question?}` → the engine runs the session check over its `track3d` buffer and XADDs `{json: CheckResult}` to the stream `reply_to` once. `args.t_game_s` when known, else `args.ref ∈ last | last_rally | call:<call_id>` (+ `rally_no`, `t0_s`/`t1_s`). The referee waits 1.5 s.
  - `request_check {question, check_hint?, args, reply_to}` → no check fits: the engine opens a `droid_run` of kind `new_check`, and when the gate passes runs it and replies with the `CheckResult` (or `error`). The referee waits 95 s, then says "Players decide."
  - `CheckResult = {check, verdict?, p?, evidence?, inputs?, calibrated, tier?, error?, latency_ms}`: the check function's own `{verdict, p, evidence, calibrated}` plus provenance. `error ∈ no_such_check | no_data | failed:<reason> | timeout`.
- **Check catalog v1** (brief §6): `in_out(t)`, `bounce_side(t)`, `edge_hit(t)`, `net_touch(window)`, `serve_toss(rally)`, `double_bounce(rally)`, `phases(window)`, `rally_summary(rally)`. The referee routes common judge phrases to these without a model; the fast Claude model routes the rest and may propose a `new` check with a signature hint.
- **Server-side voice:** `POST :8100/speak {text, voice: ref|calls, emotion?}` speaks on the Mac (Cartesia Sonic; `REFEREE_SPEAKER=1` plays on the local output; `WS /ws/audio` relays PCM chunks to listeners). `POST /transcribe` runs Ink-2 on a WAV. Two library voices by default: Daniel (calls) and Gemma (ref), the same ids the gateway's `/voice/token` hands the phones.
