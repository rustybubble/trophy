# CLAUDE.md: context for every agent working on Trophy

Read this file for project context, then the plan docs listed below. Explicit user instructions take precedence over repository guidance. Plans, owners, stack and priorities are starting points that agents may improve as they work.

## What we're building
**Trophy** is a universal AI referee for pickup games, built for **Cal Hacks 13.0 (Fri 10/23 to Sun 10/25, 2026)**.
- **Phones become cameras.** Players open a link, and each phone streams video to the Mac.
- **It keeps score and identifies fouls with honest confidence:**
  - **AUTO** at p ≥ 0.90, called automatically;
  - **BETA** shows p and can be challenged;
  - **PLAYERS DECIDE** for what the sensors can't judge;
  - judgment fouls are flagged as `foul_flag`, capped at BETA (D-17).
- **Every call is spoken** (Cartesia).
- **A challenge** opens an instant replay with an AI second opinion: Claude, Gemini and Bitdeer Model Studio vote in the background and never delay a call.
- **Ask the ref:** a voice question gets an answer drawn from official rulebooks (an Apify actor → Moss → Claude, with citations).
- **House rules** can be typed or spoken; a Factory Droid compiles them into the rule pack, tests them, and applies them after the judge approves.

**Scope** (the user's outline): basketball (2/3-pointers, fouls, outs); ping pong (serve evidence: the official profile uses a toss rise of **at least 0.16 m** and near-vertical upward projection; a separately identified TTR review profile uses **30°**; the edge rule); two-hand touch football; pickleball (kitchen, outs); tennis and badminton (outs); volleyball (hand over the net, outs); the Droid; replay.

**The weekend cut** (`docs/plan/three-agent-plan.md`):
- **MUST:** live ping pong (scoring, the edge rule, illegal serves), spoken calls, challenge → replay → AI votes, Droid house rules, voice ask-the-ref.
- **SHOULD:** recorded basketball 2s/3s on a CC BY clip; **Trophy Watch** post-game analysis for every game (highlights + ★ Play of the game, condensed, moments, stats, replay, voice search; then broadcast mode, watch party, clips), translated from Replay's Fire TV app (`docs/plan/trophy-watch-postgame.md`).
- Everything else is "coming next", and is labelled as not built.

**Prize tracks targeted:** Factory Droid SDK, Cartesia, Spacetime, Anthropic, Meta, Moss, Bitdeer AI Model Studio, Apify, and MLH (Gemini, Vultr, the GoDaddy/.Tech domain, Commit Fellowship), plus Cal Hacks overall. SubQ, Firecrawl, Deepgram and Convex are **not used**.

## Read these first
- `docs/plan/three-agent-plan.md`: scope, cut, track evidence, architecture, phases, checkpoints, workflow, open decisions.
- `docs/plan/interfaces-v1.md`: the wire contracts (ids, time, coordinates, frame bus, calibration, events, observations, calls, Spacetime tables, replay, gateway API, `decide()`, voice, ask the ref, the Droid compiler).
- `docs/plan/prompts/`: one prompt per implementation agent, plus `KICKOFF.md`.
- `docs/decisions.md`: why things are the way they are (D-1 to D-23). Record significant changes there.
- `docs/progress.md`: the weekend checklist. Write **measured** numbers only.
- `docs/research/`: integration cards with exact pins, shapes and known bugs. **Check here before guessing an API.** These are dated evidence; re-verify before relying on them.
- `docs/research/replay-source-review-2026-10-23.md`: what to reuse from Replay and courtcam, from a direct source review.
- `docs/plan/clip-library.md`: CC BY clips per sport. `docs/rules-compliance.md`: reuse and media permissions.
- `docs/archive/`: superseded plans, kept for history. **Don't treat them as current.**

## Agent autonomy
- **Build on prior work.** Agents may learn from, extend, adapt, copy or vendor compatible licensed code from `subatomic-hamster/replay` and `courtcam`. Preserve required notices and record the source and revision; see `docs/rules-compliance.md`.
- **Choose the implementation.** Change architecture, dependencies and boundaries when that helps the task. Owners are coordination hints. Explain substantial departures in `docs/decisions.md` and update the affected consumers.
- **Choose where to run.** The M5 Pro Mac is the default. Vultr is the GPU fallback. Any cloud spend needs the user's per-resource approval.
- **Proceed with routine work.** Make reversible choices and run checks without asking. Ask only when information is missing and blocks progress, or for actions outside your authorization: spend, account actions, publishing, downloading third-party media, or filming people.
- **Treat research as dated evidence.** Verify APIs and license terms when adopting them.

## Safeguards to retain
1. **Protect credentials and access.** Keep secrets out of source control and logs; use `.env` or a secret store. Clients get scoped, short-lived tokens (for example, Cartesia access tokens), never server keys.
2. **Represent results honestly.** Label mock data, synthetic fixtures and generated views. Report accuracy only from labelled evaluations, and distinguish measurements from estimates and upstream benchmarks. Label uncalibrated AI vote probabilities as uncalibrated.
3. **Respect licenses and permissions.** Preserve notices and attribution, check code, weights and media separately, and record adopted components in `docs/licenses.md`. BlurBall/WASB weights have unstated licenses, so the user decides whether to use them in the public demo.
4. **Protect participant privacy.** Get consent from everyone filmed. Keep footage in `data/local/` (gitignored), and blur non-consenting people in anything shared. Never copy Replay's `docs/media/` or `samples/real/`, or courtcam's `docs/demo.gif` (real people).
5. **Preserve user work and resource limits.** Keep unrelated changes intact, stay within authorized spending, and isolate risky experiments.

Geometry-first measurable calls, the confidence gate and the AUTO / BETA / PLAYERS DECIDE tiers are product defaults. AI models never make a line call alone; they vote alongside geometry, and the judge decides.

## Architecture at a glance (details in the plan §2 and interfaces-v1)
```
Phones (PWA, HTTPS via the MLH domain → Caddy on the Mac) ─JPEG over WSS + audio onsets─▶ gateway ─▶ Redis frames:{cam}
   video stays on Redis + the local recorder; it NEVER goes into Spacetime
vision module (flight: ball tracker, bounce, edge, serve toss) ─▶ observations ─▶ Spacetime observation/track_sample  (+ Redis ev:* hot path)
engine (rule packs, CEL, scoring, gate; background decide(): Claude ‖ Gemini ‖ Bitdeer + geometry) ─reducers─▶ Spacetime
compiler (Factory Droid; trigger = house_rule row) ─▶ Spacetime ; rules (Apify actor → Moss → Claude) ◀─ gateway /api/ask
Spacetime ─subscriptions─▶ phones (Cartesia voice, banner, replay), dashboard (score, votes, Droid panel, ask transcript, world view)
```
- **Spacetime is the shared world state:** metadata from every camera plus game state, synced to every device and agent (D-21).
- **Writers are backend services only:** vision (observations), engine (game state), compiler (house-rule progress).
- **Perception emits measurements; only rule packs decide** (D-18).

| Service | Dir | Port | Env |
|---|---|---|---|
| gateway (frames, clock, ctl, calibrate proxy, voice token, ask proxy, replay) | `services/gateway` | 8000 | py3.11 FastAPI |
| recorder | `services/recorder` | — | py3.11 + ffmpeg (`h264_videotoolbox`) |
| ingest (WebRTC; only if JPEG-WS < 25 fps) | `services/ingest` | — | py3.11, `aiortc==1.15.0`, `av==17.1.0` |
| courtcam-adapter (`/calibrate`) | `services/courtcam-adapter` | 8050 | **py3.12**, courtcam @ `b2f5ff5` (no extras) |
| flight (vision module, ping pong) | `services/flight` | — | py3.11, numpy 1.26.4, opencv-contrib 4.10.0.84, torch (MPS) |
| engine (+ `decide/`) | `services/engine` | — | py3.11, cel-python |
| compiler | `services/compiler` | 8200 | Node 20, `@factory/droid-sdk` |
| rules (+ `actors/rulebook-scraper`) | `services/rules` | 8100 | py3.11, Apify SDK, Moss SDK |
| players / possession (SHOULD: basketball) | `services/players`, `services/possession` | — | py3.11, rfdetr 1.11.2 (CoreML), trackers 2.6.1, supervision 0.30.9, rtmlib 0.0.16 |
| spacetimedb | `spacetime/` (TS module) | 3000 | SpacetimeDB 2.13 (`spacetime start`) |
| redis | — | 6379 | redis 7 |
| PWA, dashboard, Trophy Watch | `apps/pwa`, `apps/dashboard`, `apps/watch` | `/cam`, `/`, `/watch` | Vite 7 + React 19 + strict TS; Watch vendors Replay `tv-core` |

Everything runs **natively on the M5 Pro** (D-12) under a `Procfile` (`make dev`). Docker on a Mac can't reach the GPU, so `docker-compose.yml` is only the later Linux path.

## Owners (this weekend)
| Agent | Area |
|---|---|
| **1: platform, capture, voice and replay** (integration owner) | Contracts, py-trophy, state client, Spacetime module, gateway, recorder, PWA, dashboard, Cartesia client, domain + Caddy, `make dev`/`e2e`, CI, checkpoints, video + README |
| **2: ball and court** | Calibration, the ping-pong vision module (ball, bounce, edge, serve toss), observations, clip tools, labels, Vultr fallback |
| **3: rules, AI and Droid** | Engine, rule packs + scoring, `decide()` voters, Factory Droid compiler, Apify actor + Moss + ask the ref, sponsor README sections; basketball (SHOULD) |

## Gotchas
These are compatibility notes from research; check whether they still apply.
- **Pins:** numpy 2.x, OpenCV 5 and torch ≥ 2.6 (`torch.load` `weights_only`) break BlurBall. supervision 0.31 removed `sv.ByteTrack`. Keep Roboflow's `inference` package out of live environments.
- **BlurBall:** it asserts `device == "cuda"` (patch it for MPS); fix the BGR→RGB bug; dedupe frames by `seq`; use **white** balls.
- **On the Mac, onnxruntime/CoreML can silently fall back to the CPU.** Log the providers actually used.
- **RF-DETR:** on the Mac, use the CoreML fp32 export (not fp16). Print COCO `class_id`s before hard-coding them.
- **ByteTrack ignores class:** run separate person and ball trackers.
- **aiortc:** drain receive queues into a latest-frame slot. It offers only H.264 CB or VP8. Tunnels don't carry its UDP.
- **iOS Safari:** about 30 fps (read back `getSettings()`); no vibration; pin the rear lens by `deviceId`; landscape only; HTTPS is required.
- **Claude API:** `temperature` is rejected, and forced `tool_choice` returns 400 on Opus/Sonnet 5.5, so use `output_config.format`. Models: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`.
- **Bitdeer Model Studio:** OpenAI-compatible at `https://api-inference.bitdeer.ai/v1`; vision via `image_url`; base64 images < 1 MB.
- **Cartesia:** Sonic TTS over WebSocket (`context_id` continuations, `cancel`, inline `<emotion value="excited"/>`). Ink-2 STT at `wss://api.cartesia.ai/stt/turns/websocket` (turn detection, English only). Browsers use an access token + version as query params; verify the current version string.
- **Factory Droid SDK:** `@factory/droid-sdk` (Node ≥ 18) drives the `droid` CLI. The import path differs between the docs and the README, so check the shipped types.
- **Moss:** package names conflict between sources; check docs.moss.dev before pinning.
- **SpacetimeDB 2.13:** `spacetime start` has no TLS (proxy it at `/stdb/*`). Reducers over HTTP: `POST /v1/database/{db}/call/{reducer}`.

## How to work in this repo
- Work in your agent worktree, on short-lived branches, with small PRs to `main`. Rebase before each PR, and merge at least every ~2 h this weekend (plan §6).
- Contract changes go through `contracts/*` PRs, which Agent 1 merges.
- Run checks proportional to the change. Report the checks you couldn't run.
- Commit format: `<feat|fix|chore|docs>: message`.
- Tooling: Python uses `uv`, ruff and pytest, with a `pyproject.toml` per service. TypeScript uses Vite + React + strict TS, prettier and eslint.
- Store weights, footage and recordings in ignored local paths. Only small, licensed, non-identifying synthetic fixtures (≤ 5 MB) are versioned.
