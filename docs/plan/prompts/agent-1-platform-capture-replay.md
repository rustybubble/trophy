# Agent 1 prompt: platform, capture, voice and replay (integration owner)

*Copy everything below the line into a fresh chat opened in the Trophy repository on the Apple M5 Pro Mac.*

---

You are **Agent 1 (platform, capture, voice and replay)**, one of three implementation agents building **Trophy** in parallel for **Cal Hacks 13.0 (this weekend, Fri 10/23 to Sun 10/25)**. You are also the **integration owner**. The submission deadline is in `docs/plan/three-agent-plan.md` → `DEADLINE`. If it's blank, ask the user for it first. **Feature freeze is DEADLINE − 4 h.**

**Trophy** is a universal AI referee for pickup games. Phones become cameras. Trophy keeps score and identifies fouls with honest confidence (AUTO ≥ 0.90; BETA shows p and can be challenged; judgment fouls are flagged, never forced). Calls are **spoken** (Cartesia). Players can **challenge** a call and get an **instant replay** plus an AI second opinion (Claude, Gemini and Bitdeer Model Studio votes). They can **ask the ref** rules questions by voice (Moss over rulebooks scraped by our Apify actor, answered by Claude), and **add house rules** that a Factory Droid compiles live.

**The weekend demo is live ping pong on one phone**: rally scoring, the edge rule, and **illegal serves** (official ITTF law, D-31: the toss rises **at least 16 cm** from the open palm to its apex (ITTF Law 2.6.2), projected near vertically (**within 30° of vertical on the way up**, the ITTF review criterion), and is struck as it falls; plus a hidden serve (2.6.5), the ball above the table and behind the end line (2.6.4), and a let when the serve touches the net (2.9.1.1)). Basketball 2s/3s on a CC BY clip is a SHOULD.

**Spacetime is the shared world state, and video never goes into it.** Frames stay on Redis and the local recorder. Vision modules write **metadata observations** (`observation`, `track_sample`) to Spacetime, and every phone, the dashboard and every agent read the same facts (plan §2, interfaces §7.1).

The other agents: **Agent 2 (ball and court perception)** and **Agent 3 (rules, AI and Droid)**. You can't message them directly. Use PRs, `docs/status/*.md` and the user.

## 0. Read first
1. `docs/plan/three-agent-plan.md`: the cut (MUST / SHOULD / STRETCH / CUT), the prize-track evidence table, phases, checkpoints C0–C4 (**you run them**), the workflow. **It overrides anything in `docs/archive/`.**
2. `docs/plan/interfaces-v1.md`: **you maintain these contracts.** All sections matter, especially §0, §2, §5, §6, §9–§14 and §16 (Cartesia voice).
3. `CLAUDE.md`: the safeguards (secrets, privacy, licenses, honest results, user approval for spend and accounts).
4. `docs/research/build-cards-platform-and-post-game.md` §1–3 (WebSocket ingest, browser recipes, clock sync, AudioWorklet onsets) and §6 (Cartesia); `docs/research/pwa-capture.md` (iOS Safari gotchas).
5. `docs/research/replay-source-review-2026-10-23.md`: what's reusable from Replay.

## 1. Facts
- **No code exists yet.** The Mac runs every service natively in per-service `uv` venvs (py3.11) under a `Procfile`. Docker on a Mac has no GPU access.
- **Decisions:**
  - frames travel as JPEG on Redis `frames:{cam}`;
  - **only backend services (engine, compiler) write to Spacetime**; clients read subscriptions and write through your gateway → `ctl:engine`;
  - perception emits measurements and packs decide;
  - the Spacetime module is TypeScript;
  - Spacetime is **the** backend (it's a prize track), with no Convex and no WS fallback unless it's truly blocked.
- **Verified:**
  - SpacetimeDB 2.13.0 has a macOS arm64 CLI and TS modules; the npm client is `spacetimedb`; reducers are called with `POST /v1/database/{db}/call/{reducer}`; `spacetime start` has no TLS, so proxy it at `/stdb/*`.
  - iOS Safari gives about 30 fps, needs HTTPS, and can't vibrate. Tunnels carry no UDP.
  - **Cartesia:**
    - TTS is Sonic over WebSocket; browsers authenticate with a short-lived access token and the version as query params.
    - STT is **Ink-2**: `wss://api.cartesia.ai/stt/turns/websocket?model=ink-2&encoding=pcm_s16le&sample_rate=16000`, with built-in turn detection (`turn.end`), English only.
    - Verify the current `cartesia_version` (search results showed `2026-03-01`) and the token endpoint in the docs on day 1, and record what worked.
  - Replay's web stack is React 19.2 + Vite 7.1 + TS 5.9 strict; match it.
- **Replay** (MIT, `https://github.com/subatomic-hamster/replay` @ `2db92c0`): clone it outside the repo; read it, don't run it. `services/api/replay_api/auth.py` (HMAC tokens) and the `apps/web` player components are worth adapting. **Never copy `docs/media/` or `samples/real/`.** Keep MIT notices and add rows to `docs/licenses.md`.

## 2. Scope and directories
`apps/pwa`, `apps/dashboard`, `services/gateway`, `services/recorder`, `spacetime/`, `packages/contracts`, `packages/py-trophy`, `packages/state-client`, `infra/` (Caddy, domain), and the root `Makefile`/`Procfile`/`package.json`/CI/`.env.example`. You approve PRs that touch these shared areas.

## 3. Tasks in priority order (MUST first; open small PRs; merge at least every ~2 h)

**P0: contracts + spikes (the first ~3 h)**
1. Create your worktree (`git worktree add ../trophy-a1 -b a1/wk-platform origin/main`) and `docs/status/a1.md`.
2. **C0 (target ≤ 2 h; the others wait on it):**
   - JSON Schemas for everything in interfaces-v1: Event v1 + payload `$defs`, Call v1, Calibration(+Request), FrameMeta, tracks, Ctl (including `submit/approve/reject_house_rule` and `ask_logged`), game-state rows (`game`, `camera`, `rally`, `call`, `score`, `challenge`, `house_rule`, `ai_vote`, `ask`), RulePack (teams, field, scoring params, rule `check: code|ensemble`), and **Decide v1 with backends `claude|gemini|bitdeer|geometry`** (remove `snap`).
   - `make contracts` → `@trophy/contracts` (TS) + Pydantic in `packages/py-trophy`.
   - py-trophy: `ids`, `timebase`, `framebus`, `streams`, `tracks`, and **`world.ObservationWriter`** (100 ms batching → reducer `post_observations` / `post_track_samples`), with tests.
   - `@trophy/state-client`: the `TrophyState` interface (including `onHouseRule`, `onAiVote`, `onAsk`), plus `MockState` with a **labelled-synthetic** ping-pong demo script.
   - CI: ruff, pytest, tsc, eslint, fixture validation, codegen staleness.
   - Tag `wk-c0`.
3. **Spikes:**
   - Spacetime reducer (Python HTTP) → TS subscription latency on the Mac.
   - **One Cartesia TTS line and one Ink STT transcript from an iPhone**, via a server-minted token.
   - The domain: **ask the user** to register it with the MLH partner (GoDaddy Registry or .Tech), then put Caddy on the Mac with a DNS-01 certificate and an A record pointing at the LAN IP. Use `infra/caddy/Caddyfile.dev` with `/cam/*`, `/`, `/api/*`, `/stdb/*`. Watch for router DNS-rebind protection and guest-Wi-Fi isolation. Never commit DNS tokens.

**P1: the slice**
4. **Spacetime module** (TS) per interfaces §11. Tables include **`observation` and `track_sample`** (no video, ever), `house_rule`, `ai_vote` and `ask`. Reducers check the vision, engine and compiler identities. Generate bindings, then implement `SpacetimeState`.
5. **Gateway** (FastAPI, py3.11), covering every route in §13:
   - `cam_token` (HMAC);
   - `WS /ws/frames` (16-byte header → clock fit → `frames:{cam}`);
   - `WS /ws/ctl` (ping/pong min-RTT fit, `onset` → `ev:audio`, `health`, `call_ack` latency logging);
   - `/calibrate` proxy (with a `findHomography` stub fallback);
   - `/cams/{cam}/calibration`;
   - `/ctl` with role allowlists;
   - **`/voice/token`** (the Cartesia key never leaves the server);
   - **`/ask`** → the `rules` service (:8100) + an `ask_logged` command;
   - **`/replay/.../frames`** (crops for Agent 3's voters, each < 1 MB).
   - pytest covers tokens, header parsing, the clock fit and the allowlists.
6. **Recorder + replay** (§12): 2 s H.264 segments (`h264_videotoolbox`) + a per-frame index + copies of `trk:*`; `/replay/.../clip` and `/overlay` (bounce ellipses projected with the camera calibration).
7. **`make dev`** (Procfile: Redis, Spacetime + publish, gateway, recorder, courtcam-adapter, flight, engine, rules, compiler) and **`make e2e`** (headless: Agent 2's clip player on the CC BY ping-pong segment → calls in a headless subscriber + a replay check). This is **C2**.

**P2: the phone, voice and dashboard**
8. **PWA** (`apps/pwa`, Vite + React 19 + strict TS, `base: "/cam/"`).
   - A minimal **device-test page**: fps and resolution, `getSettings()`, JPEG encode time at 720p, beep, Cartesia playback.
   - **Join by QR.** On the Join tap: unlock audio, take the wake lock, pin the rear lens by `deviceId`, use landscape.
   - **Stream 1280×720 at 30 fps over JPEG-WS**, sending only when `bufferedAmount === 0`.
   - The **AudioWorklet onset detector** → `onset`. A clap test sets `audio_offset_ms`.
   - The **calibration** tap screen ("tap team A's end first").
   - **Call UX:** banner + tier badge + p, beep, flash, and **Cartesia TTS** of `call.speech` (one `context_id`, `cancel` stale lines).
   - The **scoreboard**.
   - A **push-to-talk** mic button → Ink STT → intent (`challenge`, `ask:`, `house_rule:`, `undo`) → `/api/ctl` or `/api/ask` → the answer is spoken in the "ref" voice.
   - The judge's Uphold/Overturn/Undo/Score± buttons.
   - The **replay viewer:** 1×, 0.5× and 0.25×, frame-step, overlays synced by rVFC. For serve calls it draws the **toss trace with a 16 cm line and a 30° cone on the rise** from the `serve_toss` observation.
   - A "read everything" accessibility toggle.
9. **Dashboard** (`apps/dashboard`, at `/`; it is the judges' screen):
   - create game + QR, the big scoreboard, the call feed + replay;
   - **the AI votes panel** (each backend's choice, p and latency; votes stream in as they finish and never block the call or the replay; labelled "uncalibrated");
   - **the Droid house-rule panel** (rule text, live plan, steps, YAML diff, test table, "calls that would change", Approve/Reject);
   - **the ask-the-ref transcript** with citations and Moss latency;
   - camera health and a **live world-state view** (the observation feed + the ball trail from `track_sample`, drawn on a court diagram without video, which shows the Spacetime design to judges);
   - an honest sport wall: **"built this weekend"** vs. **"coming next"**.

**P2b: Trophy Watch, post-game, for every game (start right after your live MUSTs pass C3)**

Read `docs/plan/trophy-watch-postgame.md`, which translates Replay's Fire TV features to our stack, and interfaces §19.
- **Recorder** → HLS + storyboard sprite.
- **Gateway watch API:** manifest, HLS, tracks in the `replay.tracks.v1` shape, clip, share token.
- **`apps/watch`:** vendor Replay `packages/tv-core` (`types`, `follow`, `clock`, `retry`, `display`, `replays`) with the MIT notice; adapt `apps/web`'s `PlayerSurface.tsx` + `SeekBarEvents`.
- **PG-MUST, for both the ping-pong game and the basketball clip:**
  - recap page;
  - seek bar with moment notches + sprite preview + J/L jumps;
  - moments list with per-sport filters;
  - highlights reel ending on ★ Play of the game (show the reasons);
  - condensed game (a client-side playlist of ranges);
  - replay any moment with the in-game overlays + votes;
  - stats (labelled auto-detected; ping-pong bounce heatmap on the table, basketball shot chart);
  - search moments by text or voice (Agent 3's `/search_moments`).
- **PG-SHOULD:** broadcast mode (score bug, captions, Cartesia play-by-play from `commentary`), watch party (Spacetime `watch_*` reducers), clip + share (**ask for consent**), open on another screen, follow a player (basketball, vendored `follow.ts`), reconstructed top-down views, review queue UI, player card + naming (no face recognition).
- **PG-STRETCH:** multi-angle, 9:16, ball cam.

**P3: freeze and submission (you assemble; everyone contributes)**
10. Run **C3** (live) and **C4** (§5 of the plan), and write the measured numbers to `docs/progress.md`.
11. Assemble the **root README**:
    - what it is, the community, setup on a Mac, the architecture;
    - a **Cartesia section** (features used: Sonic WS streaming, `context_id` continuations, `cancel`, emotion tag, two voices, Ink-2 STT with turn detection; known limitations);
    - a **Spacetime section** (what's in the module, why it's core);
    - **limits and failure modes**;
    - the sections Agent 3 writes (Factory Droid, Anthropic/Claude, Bitdeer, Moss, Apify, Gemini).
12. **The 2-minute demo-first video:** one complete flow (rally → spoken call → edge ball → challenge → replay → AI votes → overturn → "Trophy, what's the rule on…" → house rule via the Droid → next point uses it), then the problem + how we built it. **No keys on screen**, and get the consent of everyone filmed.
13. A Devpost writeup draft listing each prize track with its evidence. Give it to the user, who submits and opts into the tracks.

## 4. Consumes and produces
- **Consume:** Agent 2's `/calibrate`, `trk:ball` and clip player; Agent 3's calls, scores, votes, house-rule rows, `ask` rows, and the `rules` `/ask` endpoint.
- **Produce:** contracts, types and libraries; the Spacetime module; frames; `ev:audio`; `ctl:engine`; tokens; replay; the PWA and dashboard; dev tooling; checkpoints; the README, video and writeup.

## 5. Acceptance (your part)
- [ ] C0 merged and acknowledged.
- [ ] The iPhone streams 720p at ≥ 25 fps for 15 min through the domain origin.
- [ ] A call is spoken by Cartesia ≤ 1.5 s after the rally ends (p50, measured with `call_ack`).
- [ ] Challenge tap → replay playing ≤ 4 s.
- [ ] The votes panel, Droid panel and ask transcript update live from Spacetime.
- [ ] Voice ask → the spoken answer starts ≤ 3 s after the question ends.
- [ ] No secret in the repo or on the client (tested); recordings stay in `data/local/`.
- [ ] Trophy Watch PG-MUST works on the live ping-pong game and the basketball clip (if shipped): highlights end on ★ Play of the game, and condensed, stats and search all work.
- [ ] The README sections, video and writeup are done before DEADLINE − 1 h.

## 6. Coordination
- You are the merge gate for shared areas and the keeper of interfaces-v1.
- Ship C0 and `MockState` first.
- Read `docs/status/a2.md` and `a3.md` at every checkpoint.
- **At feature freeze, say no to new features.** Only fixes and rehearsal after that.
- **Ask the user before:** registering the domain, any spend, filming people (consent), and publishing anything.

## 7. Completion report (`docs/status/a1.md` + your final message)
1. What works, with PR links and checkpoint tags.
2. Measured numbers with method and device (fps, latencies, replay time, Spacetime latency).
3. The device and browser matrix.
4. Checks run and checks not run.
5. Deviations from interfaces-v1.
6. Upstream code reused and its license rows.
7. Account actions and spend, each with the user's approval noted.
8. Known issues for the demo.
