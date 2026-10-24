# Trophy: three-agent implementation plan

*Planning lead, 2026-10-23 (revised the same day around the product outline below; **cornhole is out of scope**). Inputs: [CLAUDE.md](../../CLAUDE.md), [build-plan.md](build-plan.md), [concept-v3.md](concept-v3.md), [clip-library.md](clip-library.md), the research cards in `docs/research/`, and a **direct source review of Replay `2db92c0` and courtcam `b2f5ff5`** ([replay-source-review-2026-10-23.md](../research/replay-source-review-2026-10-23.md)). Wire formats: [interfaces-v1.md](interfaces-v1.md). Agent prompts: [`docs/plan/prompts/`](prompts/).*

## 0. The product outline this plan implements

A **universal referee** that **keeps score** and **identifies fouls**:

| Sport | Calls in scope |
|---|---|
| **Basketball** | 2- vs. 3-pointers (and the score), fouls, outs |
| **Ping pong** | Illegal serves (toss **≥ 16 cm / 6 in**, toss within **30° of vertical**), the **edge rule** (top edge good, side bad), point scoring |
| **Two-hand touch football** | Two-hand touch, outs, scoring |
| **Pickleball** | The kitchen (non-volley zone) rule, outs |
| **Tennis / badminton** | Outs |
| **Volleyball** | Hand over the net, outs |
| **Droid** | "Add your own rule": a house rule typed or spoken, compiled into the rule pack, replay-tested, approved, then enforced |
| **Replay** | Instant and challenge replays with slow-mo and overlays, multi-angle, then post-game Trophy Watch |

**Rule notes:**
- **16 cm** is the ITTF law (Law 2.6.2). The **30°** limit is the user's house tolerance: ITTF officiating guidance, as quoted secondhand, is stricter ("within a few degrees" of vertical). Both are rule-pack parameters.
- Volleyball "hand over the net" follows FIVB 2025–2028 rule 11.1 (the text was read secondhand; numbering differs between sources). Reaching over is legal only when blocking, or on the follow-through after your own attack hit. Touching the ball in the opponent's space before or during their attack hit is a fault. The pack carries a casual-league parameter for stricter play.
- Everything else in `rulepacks/sports.yaml` is out of scope for this plan.

**Foul policy (D-17, revising the earlier "fouls are never called" default at the user's request):**
- **Measurable violations** follow the normal confidence gate and can be AUTO when the geometry is confident: serve toss, kitchen volley, edge/side, outs, reach-over-net with ball contact.
- **Judgment fouls**, such as basketball personal contact, are *identified* as `foul_flag` calls, shown as "Possible foul, 64%" with evidence (who moved first, minimum distance, contact frame). They are **capped at BETA and never AUTO**, and players accept or overturn them.

---

## 1. Where the repository actually is

| Category | What exists |
|---|---|
| **Working code** | **None.** No service, app or module contains source code. `scripts/smoke.sh` only echoes TODOs |
| **Scaffolding** | Service and app READMEs; four thin JSON Schemas (`packages/contracts`); a rule-pack template and catalog; a `docker-compose.yml` that references Dockerfiles which don't exist; a Caddyfile; `.env.example`; the clip manifest `data/clips/clips.yaml` (no footage; `segments` and `expected_calls` are empty) |
| **Proposed** | All of build-plan F1–F19 and §5B; the effort estimates there are guesses |
| **Unverified assumptions** | GCP and Vultr credits (the user has authorized **AWS** and an **M5 Pro Mac** only); every latency budget; Mac FPS for every model; BlurBall/WASB/TrackNetV3 weight licenses (unstated upstream); SubQ Snap behaviour; whether ball sounds are audible in the CC BY clips (never checked); all of Replay's accuracy numbers (measured on Replay's AMD/ROCm box) |
| **Verified 2026-10-23** | SpacetimeDB 2.13.0 has a macOS arm64 CLI and TypeScript modules (npm `spacetimedb@2.13.0`). RF-DETR 1.11.2 auto-selects MPS and has a native CoreML export (Roboflow measured RF-DETR-S at 11.6 ms on an M4 Max). **BlurBall asserts `device == "cuda"`.** aiortc 1.15 needs `av<18`, so pin `av==17.1.0`. AWS G/VT quotas default to 0 vCPU. g6.xlarge (L4) costs $0.805/h on demand |

---

## 2. Architecture recommendation

Keep the build plan's shape: perception families → events → an engine with rule packs → shared live state → phones and screens. Then make these changes:

| # | Change | Why | Record |
|---|---|---|---|
| 1 | **Run natively on the M5 Pro first**: one `uv` venv per Python service and a `Procfile`. Compose remains the Linux/AWS path | Docker on macOS can't reach the Apple GPU or Neural Engine | D-12 |
| 2 | **Frames travel over Redis streams** (`frames:{cam_id}`, JPEG), and a **recorder** persists them for replay | Works across venvs, processes and hosts (an AWS GPU later), and the clip player feeds the same path | D-13 |
| 3 | **Only the engine writes game state.** Clients read subscriptions and write through gateway → `ctl:engine` | One writer and one authorization point; perception and the gateway don't depend on SpacetimeDB | D-14 |
| 4 | **Perception emits measurements, and rules live only in rule packs.** Events say what happened ("bounce at x, y with σ; p(in)"; "feet 4 cm inside the kitchen at contact"). Packs (CEL conditions + scoring templates) decide what it means | The **Droid "add your own rule"** feature edits YAML over a stable event vocabulary and never touches perception code. One engine serves all 7 sports | D-18 |
| 5 | **The SpacetimeDB module is TypeScript** | Shared types with the frontends | D-16 |
| 6 | **Foul policy as above** | User outline | D-17 |
| 7 | **The first live sport is ping pong; the first recorded sport is basketball**, both developed against CC BY clips first | Ping pong has the most-disputed measurable call (the edge rule) and the serve rules. Basketball 2/3-pointers exercise the people stack. Using clips first takes recording sessions off the critical path | D-15 |

```
Phone PWA ──HTTPS/WSS──▶ gateway ─▶ Redis frames:{cam} ─┬─▶ flight (ball, bounces, edge, serve toss)  ─▶ ev:flight
  (720p JPEG + audio onsets)                             ├─▶ players (people, pose, feet, reach, touch)  ─▶ ev:players
clip player (CC BY clips) ──────────────────────────────┤   └─ possession (basketball shots, football) ─▶ ev:possession
                                                         └─▶ recorder → replay segments + tracks
ev:* + ctl:engine ─▶ engine (rule packs, scoring, tiers, foul policy, Droid-compiled house rules)
engine ─reducers─▶ SpacetimeDB ─subscriptions─▶ PWA + dashboard (score, calls, speech, replay viewer)
```

**AWS:** M1 needs none of it. Do these now or later:
- **Request an 8-vCPU G/VT quota in us-west-2 (on-demand + spot) now.** It's free, but the default is 0 and approval has no SLA. It is the fallback if BlurBall can't reach about 30 fps on the Mac GPU: a g6.xlarge spot at about $0.41–0.48/h, perception moving there, frames still on Redis.
- Later: S3 + CloudFront for Watch (adapting Replay's `cloud-stack.ts`) and Remotion Lambda for clips.
- Every provisioning step states its cost and waits for the user's OK.

### Replay and courtcam reuse
Full detail: [replay-source-review-2026-10-23.md](../research/replay-source-review-2026-10-23.md).
- **courtcam** (pin `b2f5ff5`, install **without `[yolo]`**, never through Replay's workspace):
  - calibration (`calibrate`, `distortion`, `camera_calibration` for K, R, t);
  - court templates for **basketball, pickleball, badminton and volleyball** (no table tennis, tennis or football field templates, so build those);
  - basketball `ball.arrivals` make/miss ("can't tell" → BETA);
  - teams via `identity` helpers;
  - the X-gesture challenge (`triggers`);
  - `fit_check` (→ tier cap);
  - eval tools and `synth` fixtures.
- **Replay:** vendor `packages/tv-core` (pure TS) and adapt `apps/web` components for the replay viewer and Trophy Watch. Also adapt `auth.py` (tokens), `render/replay_render` (director, condensed, vertical), `narrate/grounding.py` (commentary validator), the S3 job queue and `infra/lib/cloud-stack.ts`.
- **Don't take** Replay's `docs/media/` or `samples/real/` (frames of a private game with identifiable people) or courtcam's `docs/demo.gif` (real footage). Replay has no live capture, no face blur and no foul logic; all three are new work.

---

## 3. Milestones

### M1: score a real game and settle a disputed call
**Live ping pong (1 phone) + recorded basketball (CC BY clip).**

1. **Ping pong, live:**
   - A phone joins by QR code, streams 720p, and the user taps the 4 table corners.
   - The ball tracker runs, and bounces are timed by phone-mic onsets plus the trajectory.
   - **Rally scoring:** double bounce, missed return, ball into the net, off the table. Games to 11, win by 2, serve every 2 points, alternating at deuce.
   - **Edge rule:** a bounce near the edge is classified top edge (good) vs. side (fault) with a probability, shown as BETA when it's uncertain.
   - Calls are spoken; the scoreboard updates.
   - **Challenge → instant replay**: the clip around the call at normal speed and 0.25×, with the ball trail and the bounce mark + uncertainty ellipse overlaid. The judge upholds or overturns it.
2. **Ping pong, recorded:** the same pipeline on the CC BY [BenSucksAtPingPong club match](https://www.youtube.com/watch?v=7maQFqJ3XQ0), including its **disputed edge ball at 8:36**.
3. **Basketball, recorded:** the CC BY [JaiArtHub half-court](https://www.youtube.com/watch?v=2NxcgKW7xFM) through the clip player:
   - made shots classified **2 or 3** from the shooter's feet at release vs. the arc, with make/miss from courtcam's rim method;
   - the running score;
   - replay of each basket.

The clip's score overlay provides the ground truth.

**Deferred to M2+:** serve-toss rules, pickleball, outs and fouls in basketball, the Droid, multi-angle, `decide()`, and the remaining sports.

**M1 acceptance** (measured, recorded in `docs/progress.md`; report any target that isn't met as not met):

| Check | Target | Measured how |
|---|---|---|
| Live call latency (ping pong) | Point call shown and spoken **≤ 1.5 s** after the rally-ending event (p50), ≤ 2.5 s p95 | `event_to_ack_ms` via `call_ack` |
| Rally scoring | **≥ 90% of rallies** scored correctly on ≥ 40 labelled live rallies + the CC BY clip's rallies | Labels in `evals/labels/table_tennis/`, Wilson 95% CI |
| Edge rule | On ≥ 20 staged edge/side hits + the clip's 8:36 ball: ≥ 16 correct; every call with p < 0.90 shown as BETA | Labels + replay tests |
| Basketball 2/3 | **≥ 90% of made baskets** with the correct points on the labelled clip segment (≥ 30 makes), and the final score matching the overlay | Labels from the score overlay |
| Replay | Challenge → replay playing on the judge's phone **≤ 4 s** after the tap, with overlays aligned to ±1 frame | Logged timings, visual check |
| Capture | 1 phone streams 720p at **≥ 25 fps** to the bus for 15 min; `sync_err_ms` < 15 | Health logs |
| Reproducible | `make dev` and `make e2e` (clip → calls → state, headless) pass on a clean checkout | CI (CPU parts) + the Mac |

### M2: fouls and your own rules
- **Ping pong illegal serves:** toss height ≥ 16 cm and angle ≤ 30° (house tolerance), measured in 3D from the table pose (K, R, t).
- **Pickleball** (CC BY [BT Pickleball](https://www.youtube.com/watch?v=QhLECLlXU3c) + live): outs (P(in) = Φ(d/σ); a ball on the line is in) and the **kitchen rule** (volley with a foot in or on the kitchen, including the momentum window).
- **Basketball:** outs (ball or holder over the boundary) and **foul flags** (BETA, with evidence).
- **Droid "add your own rule"**: rule text → Droid edits the pack YAML → replay tests on recorded event logs → plan, diff and tests shown → approve → enforced from the next point. The fallback is Claude alone.
- `decide()` (Snap → Gemini → Claude → geometry) for gray-zone calls.
- **Multi-angle replay** from 2 phones (best angle chosen automatically) and phone-side 1080p recording.

### M3: the rest of the outline + Trophy Watch
- **Tennis and badminton** outs (CC BY [USTA doubles](https://www.youtube.com/watch?v=JReOUveKesY), [Tokyo badminton](https://www.youtube.com/watch?v=ShrdcaZMdS0)).
- **Volleyball:** outs + hand over the net ([Almost Volleyball](https://www.youtube.com/watch?v=kVpO4ypzPYU)).
- **Two-hand touch:** touch, outs and scoring. This must be filmed ourselves, because the public clips are weak.
- **Trophy Watch:** moments, best play, condensed game, follow a player, clips/share, slow-mo with RIFE.

---

## 4. Runtime and resources (M5 Pro + AWS, verified 2026-10-23)

| Component | Mac M5 Pro | Notes |
|---|---|---|
| Python | 3.11 per service; **3.12 for courtcam-adapter** | Flight (numpy < 2) gets its own venv, separate from players/possession |
| Ping-pong ball tracker | Classical baseline first (white ball, frame differencing + blob + Kalman), then **BlurBall on MPS** (patch `device == "cuda"` and `torch.load`, `PYTORCH_ENABLE_MPS_FALLBACK=1`) | **BlurBall's MPS FPS is unknown and is the top M1 risk.** Fallback: an AWS g6 L4. Its weights license is unstated: development use only until upstream answers |
| RF-DETR (people, basketball) | **CoreML fp32 export**, MPS as the fallback | Measure on the M5 Pro |
| rtmlib pose (feet, wrists) | onnxruntime **CoreML EP** | Log the EP actually used. rtmlib installs both OpenCV wheels, so keep only contrib |
| aiortc (if JPEG-WS can't reach 25 fps at 720p) | `aiortc==1.15.0`, `av==17.1.0` | WebRTC needs the LAN/Caddy origin, because tunnels don't carry UDP |
| SpacetimeDB | 2.13.0 native | `POST /v1/database/{db}/call/{reducer}` |
| Video segments | ffmpeg with `h264_videotoolbox` | For the recorder |

AWS prices (official price file, 2026-10-23): g6.xlarge $0.805/h on demand, about $0.41–0.48/h spot; g4dn.xlarge $0.526/h; S3/CloudFront cents per month at demo scale.

**Media:** clips in the clip library are CC BY (credits go in `data/clips/credits.json`; blur bystanders in anything shared). **Ask the user before downloading** them (`yt-dlp --download-sections` for just the needed segments), and keep footage in `data/local/` (gitignored). Our own recordings need the consent of everyone filmed.

---

## 5. The three workstreams (rebalanced for the outline)

The original split (capture / perception / state) would put all 7 sports' perception, ball *and* people, on one agent. So perception is split by what it tracks, and platform + integration go to the agent whose work is the glue.

| | **Agent 1: Platform, capture and replay** (integration owner) | **Agent 2: Ball and court** | **Agent 3: Players, rules and Droid** |
|---|---|---|---|
| Primary dirs | `apps/*`, `services/gateway`, `services/ingest`, `services/recorder`, `spacetime/`, `packages/contracts`, `packages/py-trophy`, `packages/state-client`, `infra/`, root `Makefile`/`Procfile`/CI/compose | `services/courtcam-adapter`, `services/flight`, `services/audio`, `tools/` (clip player, probe, labellers), `evals/` (ball-call sets), `rulepacks/*` → `field:` blocks (all court templates) | `services/players`, `services/possession`, `services/engine`, `services/compiler` (Droid), `services/rules-index`, `rulepacks/*` (rules, scoring, params), `evals/` (people/foul sets) |
| **M1** | Contracts C0 + codegen; py-trophy; state-client (mock → SpacetimeDB); SpacetimeDB module; PWA (join, 720p capture, clock sync, **audio onsets**, calibration taps, scoreboard, speech, challenge); gateway; **recorder + replay API + replay viewer** (slow-mo, overlays); dashboard; `make dev`/`make e2e`; CI; HTTPS; **integration and checkpoints** | Calibration service (4+ corners → H, plus K, R, t); **table and basketball half-court templates**; ping-pong ball tracker (classical → BlurBall); bounce detection fused with audio; net/off-table/dead-ball events; **edge vs. side**; ball track stream for overlays; CC BY clip prep + labels; the BlurBall Mac/AWS decision | People stack (RF-DETR CoreML + ByteTrack + rtmlib) in `players`; **basketball 2/3** (courtcam make/miss + shooter feet vs. arc) in `possession`; engine + **ping-pong and basketball packs** (scoring templates, tiers, foul policy, challenge flow); replay tests; basketball labels |
| **M2** | Multi-angle replay + auto-pick; phone 1080p MediaRecorder → upload; WebRTC if needed; Droid UI panel host; judge tools (score correction) | **Serve toss height and angle (3D)**; pickleball outs (WASB weights, Φ(d/σ)); 2-phone triangulation | **Kitchen rule** (feet at contact; uses A2's contact/bounce events); basketball outs + **foul flags**; **Droid compiler** + Claude fallback; `decide()`; pickleball pack |
| **M3** | **Trophy Watch** (vendored tv-core + adapted apps/web: moments, best play, condensed, follow, clips, share); RIFE slow-mo; deploy Watch on AWS | Tennis + badminton outs (WASB / TrackNetV3 post-game); volleyball outs; ball side of reach-over-net | **Volleyball hand over net**; **two-hand touch** (touch, outs, scoring); tennis/badminton/volleyball/football packs; rules-index (Moss) for citations |

### Produces and consumes

| Interface (interfaces-v1 §) | Producer | Consumer(s) | Stand-in until ready |
|---|---|---|---|
| Contracts + types (§0) | A1 | A2, A3 | interfaces-v1.md |
| `frames:{cam}` (§5) | A1 gateway; A2 clip player | A2, A3, A1 recorder | A2's clip player |
| `ev:audio` onsets (§7) | A1 (phone worklet → gateway) | A2 | A2 extracts onsets from clip audio |
| Calibration (§6) | A2 adapter | A1 UI and gateway; A2/A3 via `calib:{cam}` | A1's gateway `findHomography` stub |
| `ev:flight` + `trk:ball:{cam}` (§7, §8) | A2 | A3 engine and players; A1 replay overlays | A3's synthetic fixtures |
| `ev:players`, `ev:possession`, `trk:players:{cam}` | A3 | A3 engine; A1 overlays | — |
| `ctl:engine` (§9) | A1 gateway | A3 engine | A3's `trophy-ctl` CLI |
| Calls, score, state (§10–11) | A3 engine → A1 module | A1 apps | `MockState` |
| Replay API (§12) | A1 | A1 apps | — |
| Field templates (§3) | A2 | A3 packs; A1 tap UI | Rulebook dimensions |

### Concurrency
- **Day 1, all in parallel:**
  - A1: contracts (C0, about half a day first), the PWA shell and the gateway.
  - A2: the clip player and **the BlurBall-on-MPS spike**.
  - A3: RF-DETR CoreML + rtmlib on the basketball clip, and engine scoring templates against synthetic fixtures.
- **Waits on C0:** typed events and the state client everywhere.
- **Waits on C1** (phone frames on the bus): A2's live tuning. Clips cover everything before that.
- **Waits on C2** (clip → events → engine → state): A1 switching off `MockState`, and replay overlays.
- **Critical path:** ball tracker at ≥ 25 fps on the Mac (or AWS) → bounce events → engine rally scoring → live run.

---

## 6. Integration checkpoints (Agent 1 runs them, tags `m1-cN`, records results)

| CP | Acceptance check |
|---|---|
| **C0** | Schemas v1 merged (Event with the §7 vocabulary, Call, Calibration, FrameMeta, Track, Ctl, game-state rows, RulePack); `make contracts` generates TS and Pydantic; py-trophy `framebus`/`streams`/`ids`; `MockState` with a scripted ping-pong demo; synthetic fixtures; CI. A2 and A3 acknowledge |
| **C1** | A phone streams 720p at ≥ 25 fps into `frames:{cam}`, and audio onsets reach `ev:audio`. The clip player is indistinguishable apart from `source=file`. The recorder writes segments |
| **C2** | `make e2e`: the CC BY ping-pong clip segment → flight → engine → state yields the expected point calls, and the basketball segment → players/possession → engine yields 2/3 calls + score. The replay API returns a clip + overlay for a call |
| **C3** | The live M1 run meets the §3 acceptance table |
| **C4** | Sign-off: `docs/progress.md` measured numbers, decisions D-12 to D-18, licenses, status reports |

## 7. Branch, worktree and integration workflow
- **One worktree per agent** from `origin/main` of `github.com/rustybubble/trophy` (private):
  ```bash
  git worktree add ../trophy-a1 -b a1/m1-platform origin/main
  git worktree add ../trophy-a2 -b a2/m1-ball origin/main
  git worktree add ../trophy-a3 -b a3/m1-players-rules origin/main
  ```
  Venvs live inside each service directory (`.venv`, gitignored). Port offsets in `.env` (A1 +0, A2 +100, A3 +200) let all three stacks run at once.
- **Trunk-based:** short-lived `a1/*`, `a2/*`, `a3/*` branches and `contracts/*` for contract changes; PRs to `main` (aim for under ~600 lines); squash-merge.
- **Merge rights:** each agent merges its own green PRs inside its own directories. Anything in `packages/*`, `spacetime/`, the root build files, CI or compose needs **Agent 1's approval**. Rule packs need **Agent 3's** approval, except `field:` blocks, which need Agent 2's.
- **Stay current:** `git fetch && git rebase origin/main` before every PR and at every checkpoint. Never force-push `main`.
- **Coordination:** `docs/status/a1.md`, `a2.md` and `a3.md` (status, interface requests, blockers, measured numbers), PR descriptions, and GitHub issues labelled `interface`. The user relays when an agent is blocked on another.
- **CI** (A1, by C0): ruff + pytest per Python project, tsc + eslint per TS package, schema validation of fixtures, codegen staleness, and `make e2e` in its CPU form.

## 8. Open decisions and assumptions
| Id | Item | Default | Decider, deadline |
|---|---|---|---|
| OPEN-1 | SpacetimeDB vs. a gateway-WS state fallback | SpacetimeDB 2.13 | A1, by C2 (same client interface either way) |
| OPEN-2 | Phone HTTPS origin: Caddy + DNS-01 domain → LAN IP, or a tunnel | A tunnel for day 1. **720p30 JPEG or WebRTC needs the LAN path** | A1 with the user (a domain is needed), before C1 |
| OPEN-3 | Ping-pong ball tracker: classical, BlurBall MPS, or BlurBall on AWS | Whichever reaches ≥ 25 fps with the better labelled accuracy | A2, at the end of week 1 |
| OPEN-4 | BlurBall/WASB weights permission | Development and evaluation only; no redistribution or public demo until clarified | The user, before M2 sharing |
| OPEN-5 | Pickup basketball scoring | 2s and 3s (the outline), with 1s and 2s as a pack param | A3 |
| OPEN-6 | Serve-toss tolerance | 30° from vertical, 16 cm (house); an ITTF-strict variant as a param | The user, via the pack |
| OPEN-7 | Downloading CC BY clips from YouTube | Ask the user before downloading, and only the needed segments | The user |
| A-1 | Implementation agents run on the M5 Pro Mac (this plan was written on Windows) | | |
| A-2 | AWS spend needs per-resource approval; GCP and Vultr are unused | | |
| A-3 | One live game at a time | | |
