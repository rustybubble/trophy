# CLAUDE.md: context for every agent working on Trophy

Read this file, then your brief in `docs/plan/prompts/agent-{1,2,3}.md`. Explicit user instructions take precedence over repository guidance. Plans, owners, stack and priorities are starting points that agents may improve as they work.

## What we're building
**Trophy** is a universal AI referee for pickup games, built for **Cal Hacks 13.0 (Fri 10/23 to Sun 10/25, 2026)**. There is no fixed internal deadline: we stop when the MUSTs pass C3, then freeze, rehearse, record the video and write up (the user, 2026-10-24).
- **Phones become cameras.** Players open `https://trophy.photo/cam/`, and each phone streams 720p JPEG to the Mac.
- **It keeps score and identifies fouls with honest confidence:** **AUTO** at p ≥ 0.90; **BETA** shows p and can be challenged; **PLAYERS DECIDE** when the sensors can't judge; judgment fouls are `foul_flag`, capped at BETA (D-17).
- **Every call is spoken** (Cartesia Sonic; Ink-2 STT for push-to-talk).
- **A challenge** opens an instant replay with an AI second opinion: Claude votes in the background next to the geometry and never delays a call (D-23, D-41).
- **Ask the ref:** a voice question goes to the referee service (D-37): judge phrases route to a geometry check over the ball track; rules questions are answered by Claude grounded only in the sport's `rules.yaml` plus approved house rules; the answer is spoken.
- **House rules** are typed or spoken; a Factory Droid edits the rule pack in a sandbox, gates it with `replay_test`, and the engine hot-loads it after the judge approves. The Droid also specialises a golden geometry-check library to each camera setup at calibration time (D-36); it is never on the per-call path.

**Ping-pong serve law (D-31):** ITTF Law 2.6.2: the toss rises **at least 16 cm** from the open palm, **within 30° of vertical on the way up** (the ITTF review criterion, not law text), and is struck as it falls; plus hidden serve (2.6.5), position (2.6.4) and net let (2.9.1.1).

**The weekend cut:**
- **MUST:** live ping pong on one phone (rally scoring, the edge rule, illegal serves), spoken calls, challenge → replay → AI votes, Droid house rules, voice ask-the-ref.
- **SHOULD:** Trophy Watch post-game for every game (built; needs a live game); recorded basketball 2s/3s on the CC BY clip (not started); the CC BY ping-pong clip as a backup demo.
- **Coming next (labelled not built):** basketball fouls, pickleball, tennis, badminton, volleyball, two-hand touch.

**Prize tracks:** Factory Droid SDK, Cartesia, Spacetime, Anthropic, Meta, MLH (GoDaddy/.Tech domain, Commit Fellowship), Cal Hacks overall. **Dropped (the user, 2026-10-24):** Moss, Apify, Vultr, Gemini, Bitdeer (D-41). Not used: SubQ, Firecrawl, Deepgram, Convex.

## Where things stand (2026-10-24, evening)
- **On `main`:** contracts + codegen + py-trophy + state client (C0, tag `wk-c0`); Spacetime module (world, game, post-game and Droid tables, identity-checked writers); gateway (games, cam tokens, frames + clock WS, ctl, calibrate stub, voice token, ask proxy, replay/Watch APIs); recorder (HLS + source JPEGs); capture PWA (+ phone-recorded challenge clips, table crop); judges' dashboard; Trophy Watch; `make dev` / `make e2e` (transport only: calls are PENDING); `trophy.photo` HTTPS via Caddy + Porkbun DNS-01; Mac bring-up prompt.
- **On rustybubble/trophy#19 (`demo/integration`, open, conflicts with main, changes requested):** `services/engine` (rule engine, scoring, gate, decide() voters, moments, commentary, 3D checks, ask), `services/compiler` (Factory Droid, live runs pass), `services/flight` (classical detector, 2D/3D track, events; synthetic numbers only), `services/referee` (ask the ref + server-side Cartesia), `sports/table_tennis/` (golden module + check library), a localhost clip-upload demo, `make e2e-synthetic`, decisions D-33..D-37. **Landing #19 is the critical path**; nothing referees a point on `main` until it does.
- **Evidence branch (`fix/evt-scoring-evidence`, D-42):** the engine exposes evidence (`rally.hit_since_last_bounce`, `t_since_last_bounce_s`, `last_bounce_side_p`, `ev.side_p`, `ev.n_cams`, `params.evidence_min_*`) and `trophy_engine.vocabulary` renders it for the Droid; the judge's `label_rally` (dashboard: "one rally, won by X") exports a labelled sample and files a `correction` Droid job; `trophy-droid compile-rules` writes the pack from `sports/<sport>/laws.md`; a recorded real rally is a versioned gate fixture (`evals/fixtures/recorded/`); every call is spoken on the Mac by `referee announce` (Procfile `announcer`).
- **Not built anywhere:** BlurBall on MPS and a live flight loop reading `frames:{cam}`; any accuracy measured on real footage; the engine's `run_check` / `request_check` handlers; live Claude calls; the README prize sections, video and writeup.
- **Status per agent:** `docs/status/a{1,2,3}.md`. Measured numbers: `docs/progress.md`.

## Read these
- `docs/plan/prompts/agent-{1,2,3}.md`: each agent's brief for the rest of the weekend. `mac-bringup.md`: bringing the backend up on the Mac.
- `docs/plan/three-agent-plan.md`: scope, tracks, architecture, checkpoints C0–C4.
- `docs/plan/interfaces-v1.md`: wire contracts (ids, time, coordinates, frame bus, calibration, events, calls, Spacetime tables, replay, gateway API, voice, Droid). §17 (Apify → Moss) is dropped.
- `docs/plan/trophy-watch-postgame.md`, `docs/plan/clip-library.md`, `docs/demo-setup.md` (filming setup and labelling).
- `docs/decisions.md`: why things are the way they are. Record significant changes there; D-33..D-37 arrive with #19, so the next free number after it lands is **D-38**.
- `docs/research/`: dated integration cards with pins, shapes and known bugs. **Check here before guessing an API**, and re-verify.
- `docs/rules-compliance.md`, `docs/licenses.md`: reuse, media and model permissions.

## Agent autonomy
- **Build on prior work.** Agents may learn from, extend, adapt, copy or vendor compatible licensed code from `subatomic-hamster/replay` and `courtcam`, and from closed PRs (#6, #8, #9, #16; restore their branches from GitHub). Preserve required notices and record the source and revision; see `docs/rules-compliance.md`.
- **Choose the implementation.** Change architecture, dependencies and boundaries when that helps the task. Owners are coordination hints. Explain substantial departures in `docs/decisions.md` and update the affected consumers.
- **Choose where to run.** The live backend runs natively on the M5 Pro Mac with `make dev` (D-30 revised: no cloud box). Any cloud spend needs the user's per-resource approval.
- **Proceed with routine work.** Make reversible choices and run checks without asking. Ask only when information is missing and blocks progress, or for actions outside your authorization: spend, account actions, publishing, DNS changes, downloading third-party media, or filming people.
- **Treat research as dated evidence.** Verify APIs and license terms when adopting them.

## Safeguards to retain
1. **Protect credentials and access.** Keep secrets out of source control and logs; use `.env` or a secret store. Clients get scoped, short-lived tokens (for example, Cartesia access tokens), never server keys.
2. **Represent results honestly.** Label mock data, synthetic fixtures and generated views. Report accuracy only from labelled evaluations, and distinguish measurements from estimates and upstream benchmarks. Label uncalibrated AI vote probabilities as uncalibrated.
3. **Respect licenses and permissions.** Preserve notices and attribution, check code, weights and media separately, and record adopted components in `docs/licenses.md`. BlurBall/WASB weights have unstated licenses: the user accepted using them for the demo (D-30), but we never redistribute them.
4. **Protect participant privacy.** Get consent from everyone filmed. Keep footage in `data/local/` (gitignored), and blur non-consenting people in anything shared. Never copy Replay's `docs/media/` or `samples/real/`, or courtcam's `docs/demo.gif` (real people).
5. **Preserve user work and resource limits.** Keep unrelated changes intact, stay within authorized spending, and isolate risky experiments.

Geometry-first measurable calls, the confidence gate and the AUTO / BETA / PLAYERS DECIDE tiers are product defaults. AI models never make a line call alone; they vote alongside geometry, and the judge decides. Perception emits measurements; only rule packs decide (D-18).

## Architecture at a glance (details in the plan §2 and interfaces-v1)
```
Phones (PWA, https://trophy.photo → Caddy on the Mac) ─JPEG over WSS + audio onsets─▶ gateway ─▶ Redis frames:{cam}
   video stays on Redis + the local recorder; it NEVER goes into Spacetime
flight (ball detector → track → bounce/contact/serve-toss/edge, σ) ─▶ Redis ev:* (hot path) + Spacetime observation/track_sample
engine (sports/<sport>/rules.yaml, CEL, scoring, gate; background decide(): Claude + geometry) ─reducers─▶ Spacetime
compiler (Factory Droid; trigger = house_rule row; calibrate_checks per camera setup) ─▶ Spacetime
referee (router → run_check over Redis → Claude phrases → Cartesia) ◀─ gateway /api/ask
Spacetime ─subscriptions─▶ phones (voice, banner, replay), dashboard (score, votes, Droid panel, ask transcript), Watch
```
- **Spacetime is the shared world state** (D-21). **Writers are backend services only**, each with its own identity token (D-25): vision, engine, compiler.

| Service | Dir | Port | Env | Where |
|---|---|---|---|---|
| gateway (frames, clock, ctl, calibrate stub, voice token, ask proxy, replay, demo upload) | `services/gateway` | 8000 | py3.11 FastAPI | main |
| recorder | `services/recorder` | — | py3.11 + ffmpeg | main |
| flight (ping-pong vision) | `services/flight` | — | py3.11, numpy 1.26.4, opencv 4.10.0.84; BlurBall: torch (MPS) | #19 (classical); BlurBall not built |
| engine (+ `decide/`, `checks/`, `ask/`) | `services/engine` | — | py3.11, cel-python | #19 |
| compiler | `services/compiler` | — | Node 20+, `@factory/droid-sdk` 0.10 | #19 |
| referee (ask the ref, server-side voice) | `services/referee` | 8100 | py3.11 FastAPI | #19 |
| courtcam-adapter (`/calibrate`) | `services/courtcam-adapter` | 8050 | py3.12, courtcam @ `b2f5ff5` | not built; the gateway's untrusted stub answers |
| spacetimedb | `spacetime/` (TS module) | 3000 | SpacetimeDB 2.13 | main |
| redis | — | 6379 | redis 7 (brew on the Mac, Docker on Windows) | main |
| PWA, dashboard, Watch | `apps/pwa`, `apps/dashboard`, `apps/watch` | 5173, 5174, 5175 | Vite 7 + React 19 + strict TS | main |

Basketball (SHOULD, not started) would add a people stack: rfdetr 1.11.2 (CoreML fp32), trackers 2.6.1, supervision 0.30.9, rtmlib 0.0.16; see `docs/research/build-cards-possession-and-resting.md`.

Everything runs **natively on the M5 Pro** (D-12, D-30) under the `Procfile` (`make dev`; `python3 scripts/dev.py --stop`). **Agent 2 has the Mac**: it runs the live demo stack there (bring-up: `docs/plan/prompts/mac-bringup.md`) and every live measurement happens on it. Agent 1 works on the Windows PC, a dev machine and browser only; anything that must be checked on the Mac goes to Agent 2.

## Owners (this weekend)
| Agent | Area | Brief |
|---|---|---|
| **1: platform, capture, voice and replay** (integration owner; Windows PC) | Contracts, py-trophy, state client, Spacetime module, gateway, recorder, PWA, dashboard, Watch, domain + Caddy config, `make dev`/`e2e`, CI, checkpoints, merging, video + README | `docs/plan/prompts/agent-1.md` |
| **2: ball and court** (has the Mac) | The live stack on the Mac (bring-up, Caddy, live runs), the live ball tracker (BlurBall on MPS), the live flight loop, calibration, events + observations, labelled footage and accuracy | `docs/plan/prompts/agent-2.md` |
| **3: rules, AI and Droid** | Engine, sport modules + scoring, check library, `decide()` voters, Factory Droid compiler, referee service, sponsor README sections | `docs/plan/prompts/agent-3.md` |

## Gotchas
These are compatibility notes from research and the weekend; check whether they still apply.
- **Pins:** numpy 2.x, OpenCV 5 and torch ≥ 2.6 (`torch.load` `weights_only`) break BlurBall. supervision 0.31 removed `sv.ByteTrack`. Keep Roboflow's `inference` package out of live environments.
- **BlurBall:** it asserts `device == "cuda"` (patch it for MPS); fix the BGR→RGB bug; dedupe frames by `seq`; use **white** balls.
- **On the Mac, onnxruntime/CoreML can silently fall back to the CPU.** Log the providers actually used.
- **Phones send 4:2:0 JPEG** at q≈0.7: a 5–10 px ball loses colour; tune detectors on frames that went through the PWA path (`services/gateway/scripts/clip_as_phone.py`), not on the original video.
- **iOS Safari:** about 30 fps (read back `getSettings()`); no vibration; pin the rear lens by `deviceId`; landscape only; HTTPS is required. Handheld footage breaks a one-time calibration: phones need a fixed mount.
- **Claude API:** `temperature` is rejected, and forced `tool_choice` returns 400 on Opus/Sonnet 5.5, so use `output_config.format`. Models: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`.
- **Cartesia:** version `2026-08-14` verified; Sonic TTS over WebSocket (`context_id`, `cancel`, inline `<emotion value="excited"/>`); Ink-2 STT at `wss://api.cartesia.ai/stt/turns/websocket`; browsers pass `access_token` + `cartesia_version` as query params.
- **Factory Droid SDK:** `@factory/droid-sdk` drives the `droid` CLI. Autonomy "low" edits files without consulting the permission handler, so the sandbox is enforced by a PreToolUse hook plus a `git status` audit (D-35).
- **SpacetimeDB 2.13:** `spacetime start` has no TLS (Caddy proxies `/stdb/*`). Reducers over HTTP: `POST /v1/database/{db}/call/{reducer}` with body `["<json>"]`; unauthenticated calls get a fresh identity, so reducers check `ctx.sender`. SQL read-back wraps optional columns.

## How to work in this repo
- Work in your agent worktree (`../trophy-a{1,2,3}`), on short-lived branches, with small PRs to `main`. Rebase or merge `origin/main` before each PR, and merge at least every ~2 h.
- Contract changes (`packages/contracts/*`, `spacetime/`) go through Agent 1.
- Run checks proportional to the change (`make check`, plus each service's `uv run pytest`). Report the checks you couldn't run.
- Commit format: `<feat|fix|chore|docs>: message`.
- Tooling: Python uses `uv`, ruff and pytest, with a `pyproject.toml` per service. TypeScript uses Vite + React + strict TS, prettier and eslint.
- Store weights, footage and recordings in ignored local paths. Only small, licensed, non-identifying synthetic fixtures (≤ 5 MB) are versioned.
- Superseded plans, spikes and PR branches were removed in the 2026-10-24 cleanup; they remain in git history and on the closed PRs.
