# CLAUDE.md: context for every agent working on Trophy

Read this file for project context, then consult the plan and research relevant to the task. Explicit user instructions take precedence over repository guidance. The plans, ownership table, stack and priorities are starting points that agents may improve as they work.

## What we're building
**Trophy** is a universal AI referee and post-game analyzer for casual pickup sports.

**During the game:** 2–4 phones open a PWA link and become cameras.
- Trophy tracks the ball, players and objects and makes calls with **honest confidence**:
  - **AUTO** at ≥ 0.90, called automatically;
  - **BETA**, which stands but can be challenged and shows its uncertainty;
  - **PLAYERS DECIDE**: rules the sensors can't judge.
  - **Fouls are identified** (D-17): measurable violations go through the normal gate, and judgment fouls are flagged as `foul_flag` calls capped at BETA, with evidence.
- Players challenge by voice, gesture or button, and get a multi-angle replay with an error ellipse.
- Calls are **spoken** (Trophy is a voice referee).
- House rules can be typed or spoken and are compiled into the rule pack by a Factory Droid.

**After the game:** the **Trophy Watch** web app (any browser) offers follow-a-player, moments, the ★ best play, a condensed game, broadcast mode, replay angles, play search, stats and coach cards, clips and 9:16 reels, and a watch party.

**28 sports, three perception families:**
- **Flight:** table tennis, pickleball, badminton, tennis, volleyball, roundnet, padel, squash, four square, cup pong.
- **Possession:** basketball, two-hand touch, soccer, ultimate, wiffle, kickball, cricket, dodgeball, hockey, touch rugby, handball.
- **Resting object:** cornhole, mini golf, bowling, darts, bocce, horseshoes, Kan Jam, ladder toss, disc golf.

Each sport is a **rule pack** (YAML) on top of one family pipeline.

**Demo:**
- **Current scope (user outline, 2026-10-23; see `docs/plan/three-agent-plan.md`):** basketball (2/3-pointers, fouls, outs); ping pong (illegal serves, the edge rule); two-hand touch football; pickleball (kitchen, outs); tennis/badminton (outs); volleyball (hand over the net, outs); the Droid "add your own rule"; replay features. **Cornhole and the other catalog sports are out of scope for now.**
- **Live demo:** table tennis and a typed house rule.
- **Recorded examples:** pickleball kitchen fault, badminton, two-hand touch rush count and touch, basketball.
- **Sport wall:** 28 tiles marked LIVE / VERIFIED / PACK, each verified sport showing its measured accuracy.

## Source-of-truth docs (in this repo)
- `docs/plan/three-agent-plan.md`, `docs/plan/interfaces-v1.md` and `docs/plan/prompts/`: the current scope, three-agent split, Milestone 1, checkpoints and wire contracts. They take precedence over older plan text. Read these first when you are one of the three implementation agents.
- `docs/plan/build-plan.md`: the working implementation plan: features F1–F19, §0 deployment architecture, §5B Trophy Watch, §7 milestones, §8 smoke tests.
- `docs/plan/concept-v3.md`: the product, sport catalog, demo script and §9 integration priorities.
- `docs/plan/clip-library.md`: licensed public clips per sport, and the license rules.
- `docs/research/`: integration cards with exact pins, weights, input/output shapes and known bugs for every model. **Check here before guessing an API.**
- `docs/decisions.md`: why things are the way they are. Record significant architecture changes so later agents have context.
- `docs/progress.md`: the milestone checklist. Tick items and write measured numbers.
- `docs/rules-compliance.md`: reuse, attribution and media permissions.

## Agent autonomy
- **Build on prior work.** Agents may learn from, extend, adapt, copy or vendor compatible licensed code from `subatomic-hamster/replay`, including its apps, renderers, services and infrastructure, as well as `courtcam`. There is no reference-only rule, mandatory rewrite or event-based implementation window. Preserve required notices and record the source/revision when incorporating code; see `docs/rules-compliance.md`.
- **Choose the implementation.** Change architecture, dependencies, models, priorities and directory boundaries when that helps the task. Owners are coordination hints, not exclusive permissions. Explain substantial departures in `docs/decisions.md` and update affected consumers and docs.
- **Choose where to run.** Local development, tests, inference, training and rendering are allowed when the hardware can handle them. GCP L4 and Vultr L40S remain useful defaults for GPU work; other providers are fine within the user's authorized resources and budget. Historical credit estimates are not spending authorization.
- **Proceed with routine work.** Make reversible implementation choices and run relevant checks without asking for approval. Ask only for missing information that blocks progress or actions outside the user's authorization, such as destructive operations or new spending commitments.
- **Treat research as dated evidence.** Verify APIs, compatibility and license terms when adopting them. Old recommendations, version pins and demo schedules are not permanent constraints.

## Safeguards to retain
1. **Protect credentials and access.** Keep secrets out of source control and logs; use environment variables or a secret store. Clients get scoped, short-lived tokens rather than server credentials. This prevents account and data exposure.
2. **Represent results honestly.** Label mock data, synthetic fixtures and generated views. Report accuracy from labelled evaluations and distinguish measured results from estimates or upstream benchmarks. This keeps users and later agents from relying on invented evidence.
3. **Respect licenses and permissions.** Preserve required notices and attribution. Check code, weights and media separately; record adopted components in `docs/licenses.md`. Copyleft and non-commercial components are allowed where their terms fit the intended use. A public repository or demo does not by itself grant reuse rights.
4. **Protect participant privacy.** Use consented identity and face data, keep private footage private, and anonymize or blur non-consenting people in shared clips. Use media involving minors only with appropriate permission. These protections apply regardless of which pipeline or hosting provider is chosen.
5. **Preserve user work and resource limits.** Keep unrelated changes and data intact, stay within authorized access and spending, and isolate experiments that could damage shared systems. Routine edits and checks need no extra approval.

Geometry-first measurable calls, calibrated decision models and the AUTO / BETA / PLAYERS DECIDE tiers are current product defaults. Agents may experiment with alternatives, but should validate changes before presenting them as reliable calls and continue to show uncertainty.

## Architecture at a glance
Full details are in build-plan §0.

```
Phones (PWA) ──WebRTC 720p / WS-JPEG fallback + audio onsets──▶ GCP g2-standard-8 (L4), docker compose:
  ingest (aiortc) → shared-memory frame rings → flight | possession | resting | audio  ──Redis Streams──▶ engine
  engine (rule packs, CEL, tiers, decide(): Snap → Gemini → Claude votes → geometry) ──reducers (HTTP)──▶ spacetimedb
  spacetimedb (live game state) ──TS SDK subscriptions──▶ phones (beep/flash/voice), dashboard, watch app
  broadcast (Claude commentary → fact validator → Cartesia), compiler (Factory Droid), rules-index (Firecrawl → Moss)
  gateway (FastAPI: WebRTC signaling, clock sync, signed GCS URLs) behind Caddy (HTTPS)
Post-game: Vultr L40S (RIFE, SAM 2.1 2.5D angles, GVHMR) · Remotion Lambda (AWS) · GCS (recordings, clips)
```

| Service | Dir | Port | Env |
|---|---|---|---|
| gateway | `services/gateway` | 8000 | py3.11 FastAPI |
| ingest | `services/ingest` | host network, UDP 32768–60999 | py3.11 aiortc 1.15.0, av ≥ 17 |
| flight | `services/flight` | — | py3.11, numpy 1.26.4, opencv-contrib 4.10.0.84, torch CUDA 12 |
| possession, resting | `services/possession`, `services/resting` | — | py3.11, rfdetr[train] 1.11.2, trackers 2.6.1, supervision 0.30.9, rtmlib 0.0.16 + onnxruntime-gpu |
| courtcam adapter | `services/courtcam-adapter` | 8050 | **py3.12** (courtcam needs `>=3.12,<3.13`) |
| audio | `services/audio` | — | py3.11, librosa 0.11.0, panns_inference |
| engine | `services/engine` | — | py3.11, cel-python, transitions |
| broadcast | `services/broadcast` | 8300 | py3.11 + Node (Remotion) |
| compiler | `services/compiler` | 8200 | Node 20, `@factory/droid-sdk` |
| rules-index | `services/rules-index` | 8100 | py3.11, Firecrawl, Moss SDK |
| spacetimedb | `spacetime/` | 3000 | `spacetime start` + our module |
| redis | — | 6379 | redis:7 |
| postgame | `services/postgame` | — | Vultr; py3.10/3.11 |
| PWA, dashboard, watch | `apps/pwa`, `apps/dashboard`, `apps/watch` | served by Caddy at `/cam`, `/`, `/watch` | Vite + React + TS (+ Three.js, Spark) |

**Contracts** live in `packages/contracts/` (JSON Schema): Event, Call, Decide, RulePack. Agents may evolve them; update affected producers, consumers and checks together, and document breaking changes in `docs/decisions.md`.

**Redis streams:** `ev:flight`, `ev:possession`, `ev:resting`, `ev:audio` (family → engine); `ctl:engine` (control).

## Suggested owners
| Owner | Area |
|---|---|
| **A** | PWA + ingest + clock sync + resting family + replays (challenge UI, auto-director, trophy clip) + Trophy Watch app |
| **B** | Flight family + audio + calibration (via courtcam) + 3D |
| **C** | Possession family (basketball, two-hand touch, soccer, ultimate, dodgeball) |
| **D** | Engine + rule packs + `decide()` / Snap / calibration + Droid compiler + Moss / ask-the-ref + commentary + sport wall + search/stats/review |

## Priorities and gates
- **P0:**
  - PWA join, record and stream; clock sync; beep/flash; challenge replay.
  - Flight on table tennis (live); possession on basketball (recorded). M1 is defined in `docs/plan/three-agent-plan.md` §3.
  - Engine + 3 packs; `decide()`; commentary.
- **P1:**
  - Pickleball, badminton and two-hand touch verified; roundnet live.
  - House-rule Droid; ask-the-ref; coach.
  - Sport wall; trophy clip; Trophy Watch core (moments, best play, condensed, follow, search, stats, review queue); calibration slide.
- **P2:**
  - More verified sports; 3D / 2.5D angles; ReCamMaster; blur; watch party.
- **Milestones:**
  - Each P0 family makes at least 1 correct call; use "calls within 2 s after the point" as a fallback while improving latency.
  - Stabilize the selected demo or release scope and record measured results before sharing it.
  - Adjust scope and sequencing to the current task; there is no fixed submission deadline.

## Gotchas
These are compatibility notes from earlier research; check whether they still apply.
- **Use reproducible versions; upgrades are welcome after compatibility checks.**
  - numpy 2.x, OpenCV 5, librosa 1.0 and torch 2.14 break BlurBall and WASB.
  - supervision 0.31 removed `sv.ByteTrack`.
  - Keep Roboflow's `inference` package out of the live environments.
- **BlurBall:** fix the BGR→RGB bug in its inference script, turn its duplicate-frame filter **on**, and use **white** table-tennis balls.
- **WASB has no inference code:** run its weights through BlurBall's runners. TrackNetV3 is post-game only.
- **onnxruntime-gpu can silently run on the CPU.** Check that VRAM is actually used.
- **RF-DETR:** use TensorRT, because the ONNX CUDA path is slow. Print COCO `class_id`s before hard-coding them.
- **ByteTrack ignores class:** run separate person and ball trackers, and lower the ball activation threshold.
- **aiortc:** drain receive queues into a latest-frame slot (they're unbounded). It offers only H.264 Constrained Baseline or VP8.
- **iOS Safari capture:**
  - About 30 fps; Safari ignores `max` frameRate above 16, so read back `getSettings()`.
  - No vibration; use a beep plus a full-screen flash instead.
  - Pin the rear lens by `deviceId`, and use landscape only.
- **Claude API (2026-10-21+):** `temperature` is rejected, and forced `tool_choice` returns 400 on Opus/Sonnet 5.5, so use `output_config.format`. Model IDs: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`.
- **SubQ Snap:**
  - Endpoint `POST https://api.subq.ai/v1/systemone`, model `subq-snap-1.1`.
  - Use `probabilities[choice]`, not `confidence`.
  - At most 4 images, which it downscales.
  - Retry only 429 and 5xx.
- **Cartesia:** `sonic-3.6` WebSocket. Lower `max_buffer_delay_ms`; use the inline `<emotion value="excited"/>` tag; test both auth header forms.
- **vLLM:** `guided_choice` was removed in 0.12; use `structured_outputs.choice`.
- **Remotion:** pin 4.0.538; `--props` must be a file path on Windows. Lambda concurrency on a new account may be 10.

## How to work in this repo
- Consult the matching F-section and research card when useful; update the plan if the task needs a different approach.
- Use the feature's **"Done when"** criteria as a starting point. Run checks proportional to the change and record relevant measured results in `docs/progress.md`; documentation-only changes do not need inference runs.
- Work across directories as needed. Follow the active user's or environment's branch convention; owner-prefixed branches are optional.
- Prefer focused changes and keep shared workflows usable. Preserve unrelated work and report any checks you could not run.
- Suggested commit format: `<feat|fix|chore|docs>: message`.
- Current tooling: Python uses ruff + pytest and per-service `pyproject.toml`; TypeScript uses Vite + React + strict TS, prettier + eslint. Adapt tooling when justified.
- For services deployed through Compose, update the `Dockerfile` and `docker-compose.yml` together. The current GPU, frame-ring and ingest design needs GPU device reservations, `ipc: host` and `network_mode: host` respectively; revisit these when changing the design.
- Store large weights, footage and recordings in ignored local paths or suitable object storage. Small licensed, non-sensitive test fixtures may be versioned when useful; avoid bloating git with generated media.
