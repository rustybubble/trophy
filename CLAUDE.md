# CLAUDE.md: context for every agent working on Trophy

Read this whole file before doing anything. Then read the build-plan section for the feature you own.

## What we're building
**Trophy** is a universal AI referee and post-game analyzer for casual pickup sports, built at **Cal Hacks 13.0** (hacking Fri Oct 23 → **submit Sun Oct 25, 9:00 AM PT**; on site by 8:00 AM).

**During the game:** 2–4 phones open a PWA link and become cameras.
- Trophy tracks the ball, players and objects and makes calls with **honest confidence**:
  - **AUTO** at ≥ 0.90, called automatically;
  - **BETA**, which stands but can be challenged and shows its uncertainty;
  - **PLAYERS DECIDE**: fouls are never called, only shown in evidence mode.
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
- **Live at the judging table:** table tennis, a tabletop cornhole set, and a typed house rule.
- **Recorded at the event:** pickleball kitchen fault, badminton, two-hand touch rush count and touch, basketball.
- **Sport wall:** 28 tiles marked LIVE / VERIFIED / PACK, each verified sport showing its measured accuracy.

## Source-of-truth docs (in this repo)
- `docs/plan/build-plan.md` is **the** implementation plan: features F1–F19, §0 cloud architecture, §5B Trophy Watch, §7 schedule, §8 smoke tests.
- `docs/plan/concept-v3.md`: the product, sport catalog, demo script, **§9 prize map** (which prizes we target and what each judge wants).
- `docs/plan/clip-library.md`: licensed public clips per sport, and the license rules.
- `docs/research/`: integration cards with exact pins, weights, input/output shapes and known bugs for every model. **Check here before guessing an API.**
- `docs/decisions.md`: why things are the way they are. Add an entry when you make an architecture choice.
- `docs/progress.md`: the milestone checklist. Tick items and write measured numbers.
- `docs/rules-compliance.md`: Cal Hacks rules, prior-work disclosure, licenses.

## Hard rules (non-negotiable)
1. **All implementation happens during Cal Hacks.**
   - **Do not copy code from `subatomic-hamster/replay`** (a teammate's earlier Amazon-hackathon project).
   - Only the published MIT library **`courtcam`** may be used, as a **pinned, disclosed dependency**. Reimplement Replay's features from its design docs.
   - Record anything pre-existing in `docs/rules-compliance.md`.
2. **Cloud only.** Nothing heavy runs on the laptops; they edit and browse.
   - GPU work runs on the **GCP L4 VM** (live) or the **Vultr L40S** (post-game). Develop through Remote-SSH.
   - **AWS has only $100**: use it for Remotion Lambda only.
3. **No secrets in the repo.**
   - Configuration comes from environment variables (see `.env.example`).
   - Phones get short-lived tokens (Cartesia `/access-token`, signed GCS URLs); never API keys.
4. **No faked outputs.**
   - No hard-coded results or mock data shown as real.
   - Synthetic fixtures are always labelled synthetic.
   - Accuracy numbers come from labelled evaluations only.
5. **Footage and licenses.**
   - Only CC BY / CC0 clips go into the Devpost video; credit them from `data/clips/credits.json`.
   - Research datasets (CalTennis, PadelVic, OpenTTGames) are for the live judged demo only.
   - Never commit footage. Never use Replay's private footage or any clip with minors.
6. **Privacy.**
   - Names and faces only for players who enrolled at join.
   - Everyone else stays anonymous and is blurred in shared clips.
7. **Licenses in the core.**
   - Prefer MIT/Apache: RF-DETR, roboflow/trackers, supervision, rtmlib, WASB, BlurBall, OpenCV, courtcam core.
   - AGPL (Ultralytics/YOLO), GPL and non-commercial models are allowed only as documented optional pieces; list them in `docs/licenses.md`.
8. **Honest calls.** Claude, Gemini or Snap never make raw visual line calls. Geometry makes measurable calls; decision models judge only ambiguous ones, with **calibrated** probabilities.

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

**Contracts** live in `packages/contracts/` (JSON Schema): Event, Call, Decide, RulePack. Change them only with a note in `docs/decisions.md`, and tell the other owners.

**Redis streams:** `ev:flight`, `ev:possession`, `ev:resting`, `ev:audio` (family → engine); `ctl:engine` (control).

## Owners
| Owner | Area |
|---|---|
| **A** | PWA + ingest + clock sync + resting family + replays (challenge UI, auto-director, trophy clip) + Trophy Watch app |
| **B** | Flight family + audio + calibration (via courtcam) + 3D |
| **C** | Possession family (basketball, two-hand touch, soccer, ultimate, dodgeball) |
| **D** | Engine + rule packs + `decide()` / Snap / calibration + Droid compiler + Moss / ask-the-ref + commentary + sport wall + search/stats/review |

## Priorities and gates
- **P0:**
  - PWA join, record and stream; clock sync; beep/flash; challenge replay.
  - Flight on table tennis (live); resting on cornhole (live); possession on basketball (recorded).
  - Engine + 3 packs; `decide()`; commentary.
- **P1:**
  - Pickleball, badminton and two-hand touch verified; roundnet live.
  - House-rule Droid; ask-the-ref; coach.
  - Sport wall; trophy clip; Trophy Watch core (moments, best play, condensed, follow, search, stats, review queue); calibration slide.
- **P2:**
  - More verified sports; 3D / 2.5D angles; ReCamMaster; blur; watch party.
- **Gates:**
  - **Saturday noon:** each P0 family makes at least 1 correct call, or switch to "calls within 2 s after the point".
  - **3 AM Sunday:** feature freeze.
  - **8:30 AM Sunday:** Devpost submitted.

## Gotchas
Each is a real problem someone hit; ignore them and you lose hours.
- **Pin versions; never install latest.**
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
- Start each task by reading the matching F-section of `docs/plan/build-plan.md` and the relevant `docs/research/` card.
- Every feature has a **"Done when"** test in the plan. Meet it, then record the measured numbers in `docs/progress.md`.
- Keep changes inside your owner's directories, and use branches named `a/…`, `b/…`, `c/…`, `d/…`.
- Small PRs into `main`, which must never be broken.
- Commit format: `<feat|fix|chore|docs>: message`.
- Python: ruff + pytest, one `pyproject.toml` per service.
- TypeScript: Vite + React + strict TS, prettier + eslint.
- Each service has a `Dockerfile` and an entry in `docker-compose.yml`. GPU services use `deploy.resources.reservations.devices`, frame rings need `ipc: host`, and ingest uses `network_mode: host`.
- Run heavy jobs (inference, training, renders) on the VMs, never locally. Put large files (weights, footage, recordings) on the VM disk or in GCS, never in git.
