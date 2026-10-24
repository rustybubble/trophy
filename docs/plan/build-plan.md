# Trophy: build plan (feature by feature, on proven models)

*Updated 2026-10-23. This is a working plan with a cloud deployment baseline; local work and other suitable infrastructure are welcome. If a sport cannot be filmed, use the [clip library](clip-library.md). It builds on [Trophy v3](concept-v3.md). Scope, sequencing and implementation choices can evolve with the task.*

**Working approach:** prefer proven models and methods when they help, and build or experiment where needed. Agents may reuse compatible licensed code, including Replay, or write new implementations at any time. Validate the resulting behavior; [CLAUDE.md](../../CLAUDE.md) describes autonomy and safeguards.

Exact install pins, weight files, input/output shapes and known bugs are in three integration-card files (checked against source and docs today). This plan cites them as **[F]**, **[P]** and **[X]**:
- **[F]** [flight family](../research/build-cards-flight-family.md)
- **[P]** [possession and resting](../research/build-cards-possession-and-resting.md)
- **[X]** [platform and post-game](../research/build-cards-platform-and-post-game.md)

---

## 0. System shape: deployment baseline (updated 2026-10-23)

**Use suitable available hardware.** Local development, tests, inference, training and rendering are allowed. Cloud GPUs are useful when local hardware is insufficient. Phones run the PWA in the browser. The topology below is a starting point; validate changes against latency, capacity and the authorized budget.

**Budget snapshot (Oct 23):** the plan assumed $100 in AWS credits, $2k in Google credits and possible Vultr credits. Verify current balances and pricing before provisioning. Providers and workloads may change within authorized resources and spending.

**Current backend choices:**
- **SpacetimeDB** for shared real-time game state.
- **Factory Droid** for the house-rule compiler.
- **Moss** for rulebook lookup.

These can change when alternatives better serve the product. See [integration priorities in v3 §9](concept-v3.md#9-integration-priorities) and [cloud architecture research](../research/cloud-architecture.md).

### Where everything runs
| Piece | Runs on | Why |
|---|---|---|
| Live perception + ingest + engine + gateway + SpacetimeDB | **GCP Compute Engine `g2-standard-8`** (1× NVIDIA L4 24 GB, 8 vCPU), **on-demand** in **us-west1 (Oregon)**. Google's pricing page lists about **$0.85/h**, so 40 h ≈ $34 of credits. Use `g2-standard-16` if software decoding of 3–4 phone streams saturates 8 vCPU | Our live models are small (BlurBall is 6 MB; RF-DETR-S, rtmlib, WASB), so an L4 is plenty. A full VM keeps **UDP for WebRTC**, which Cloud Run can't do. Ada-generation GPUs keep the pinned torch/CUDA 12 stacks working |
| Post-game: RIFE, GVHMR, ReCamMaster | **Vultr Cloud GPU L40S 48 GB** (about $1.67/GPU-hour from third-party trackers), started only for render jobs | 48 GB of VRAM for ReCamMaster; it keeps heavy jobs off the live box. Vultr's new-account credit (reported as $250–300) is **unverified**, so check current account terms |
| Dev | **One shared dev VM** (`g2-standard-4` **spot**, about $0.34/h, 1× L4), plus the live VM outside demo windows, using **VS Code or Cursor Remote-SSH** | Local development is also welcome. Stop the VMs when idle |
| Containers | GCP **Deep Learning VM image** (CUDA 12, NVIDIA driver and container toolkit) + **docker compose, one image per service** | Solves the version clashes. The shared-memory frame rings need `ipc: host`; ingest needs `network_mode: host` |
| HTTPS | **Caddy** on the VM's static external IP with the domain (any suitable registrar) | Automatic Let's Encrypt; no LAN certificate problems |
| Phone video in | **aiortc** on the static IP. A **VPC firewall rule opens UDP 32768–60999** (aiortc picks random ports). Google's STUN server gives the right public address | Phones on 5G don't need TURN when the server has a public IP |
| TURN (only for networks that block UDP) | **coturn** in a container on the live VM, TURN over TLS on 443 | aiortc can't fall back to TCP itself. The JPEG-over-WebSocket path on 443 is the other fallback |
| Recordings | **Google Cloud Storage** with resumable/signed uploads from the phones. Upload challenge and closing-rally chunks right away, the full game afterwards | Same cloud as the GPU, so no egress fees. About 216 GB in the example recording workload is about $5 of storage |
| **Live game state** | **SpacetimeDB**, self-hosted (`spacetime start`) in a container **on the live VM**, with Maincloud as the fallback. The free tier pauses idle databases, but they resume in under a second | **The current real-time backend**. Tables: `game`, `player`, `camera`, `rally`, `event_summary`, `call`, `challenge`, `score`, `house_rule`, `highlight`. Phones and the dashboard subscribe with the **TypeScript SDK**; the Python engine calls **reducers over HTTP**. **Calls and beeps flow through SpacetimeDB subscriptions** (same VM, so one short hop). Redis stays internal for the high-rate perception → engine events. Supabase is dropped |
| Detector training | **Roboflow cloud**: fork the Universe datasets and train RF-DETR (1 credit = 30 min, so set an epoch cap). Then run it in **Roboflow's inference container on our VM** | Running a model on your own hardware uses no Roboflow credits |
| Trophy-clip rendering | **Remotion Lambda** on **AWS** (one of the few AWS uses left; pennies per render) | Check `npx remotion lambda quotas`, because new accounts may get about 10 concurrent Lambdas. Fallback: render with the Remotion CLI on the Vultr box |
| Decisions | **SubQ Snap → Gemini (Flash, Google credits) → Claude votes → geometry only** | All hosted |
| Voice | **Cartesia** (Pro, because the free tier allows only 2 concurrent requests). **Trophy is a voice referee**: calls, commentary, verdicts and "ask the ref" answers are all spoken. **Deepgram Nova-3** streaming STT for voice commands ("Trophy, challenge!", "Trophy, what's the rule on…?", with keyterm "Trophy"). **Deepgram Aura-2** as the backup voice | Voice is the core interface |
| House-rule compiler | **Factory Droid SDK** (`@factory/droid-sdk`, TypeScript; it runs the `droid` CLI as a subprocess) in a **sandboxed container on the live VM**, triggered by new `house_rule` rows in SpacetimeDB | Triggered rule compilation with scoped access and visible plan, diff and test results (F10) |
| Rulebooks | **Firecrawl** scrapes the official rules (USA Pickleball, BWF, ITTF, USA Football flag, …) and chunks them by rule into **Moss** indexes, one per sport (`moss-minilm`; sub-10 ms semantic + keyword search) | Feeds "ask the ref", challenge verdicts that cite rule text, and the Droid compiler (F19). Check the SDK package names at docs.moss.dev, because sources disagree |
| LLM tracing and evals | **Langfuse**: trace every Snap, Gemini, Claude and Droid decision; keep the labelled-call eval sets; manage prompts | Free cloud tier allows 2 users; self-hosting is free |
| Recap email | **AgentMail**: each game gets an inbox that emails players their recap, highlights and coach cards | Cheap, visible extra |
| Code review | **Greptile** on PRs | |
| Optional | **Tavus** "virtual ref" avatar that reads challenge verdicts (Echo mode speaks our exact text; billed from creation with a 30 s minimum); **Vapi** "ask the ref" voice line; **Blaxel** sandboxes | Only after P1 is done |
| Skip | Razorpay, écentic, Corsair, Gumloop, Bolna, Coinbase/Base, Browser Use, sync., Sarvam (unless you want multilingual commentary) | Don't help Trophy |

### Latency budget for a live call (estimates; measure in hour 0)
| Step | Time |
|---|---|
| Phone → GCP us-west1 over 5G | 40–80 ms |
| Waiting for the frames after the event | 100–250 ms |
| Perception + rules | 50–150 ms |
| Snap (only for ambiguous calls) | 0.3–1.0 s (vendor's figure) |
| Engine → SpacetimeDB reducer → subscription → phone beep | 50–100 ms |
| **Total** | **0.3–0.7 s** for geometry-only calls, **0.6–1.6 s** with Snap |

Snap has a 2.0 s timeout; on timeout the call falls back to a challengeable geometry call.

**Phone uplink:** each phone streams on **its own 5G** (median upload about 13 Mbps, and 720p30 needs about 2–3 Mbps), so venue Wi-Fi is only a backup. Clock sync is noisier over the internet (my estimate is ±5–15 ms), so **lean on the optical QR-timecode calibration** (F2).

### Example cost for 40 hours (historical estimates)
| Where | Spend | Budget |
|---|---|---|
| **GCP** | Live L4 VM about $34 + dev spot VM about $15 + storage about $5 | **~$55 of the $2k** Google credits |
| **Vultr** | L40S about 10–15 h of render jobs ≈ $17–25 | Vultr credits (check the amount) |
| **AWS** | Remotion Lambda renders (cents each) + a little S3/CloudWatch | **≪ $20 of the $100** |
| **Out of pocket** | Cartesia Pro ($5), Roboflow if the free credits run out | Under ~$50 |

### Fallbacks
| If… | Then |
|---|---|
| **GCP GPU quota is 0** (new projects often need `GPUS_ALL_REGIONS` and `NVIDIA_L4_GPUS` in us-west1 raised to at least 1–2) | Move the **live box to Vultr** (L40S). Then **Cloud Run with an L4 GPU** (no UDP, so phones stream over **WebSocket on 443**). Then AWS `g6.xlarge` (L4, about $0.80/h) only if AWS approves G quota, inside the $100. Last resort: CPU at 360p with calls after each point |
| Venue Wi-Fi is down | Phones use 5G; TURN on 443; WebSocket video |
| Snap is down | Gemini, then Claude, then geometry |
| SpacetimeDB container dies | Restart it from the compose file. Then fail over to **Maincloud** (same module published there) |
| Droid is slow or fails | Fall back to the **Claude-only compiler** (same schema and replay tests, no agent loop) |
| The live box dies | Recreate it from a **recent validated machine image** |

### Initial setup (adapt to available resources)
1. **GPU quota on GCP:** in the console, under IAM & Admin → Quotas, raise **`GPUS_ALL_REGIONS` to 2** and **NVIDIA L4 GPUs in us-west1 to 2** (also us-central1 as a backup). Confirm the $2k credits are on that billing account. In parallel, **create a Vultr account** and check that a GPU instance can launch (and what MLH credits apply).
2. Domain (GoDaddy Registry) and DNS records pointing at the VM's static IP.
3. Fork the Roboflow Universe datasets (Cornhole Referee, minigolf, roundnet, flag football) and start **capped** RF-DETR training. Training and implementation can start whenever useful; cap resource use to the authorized budget.
4. Install the `spacetime` CLI on the dev VM, and create a Maincloud account for the fallback.
5. Get keys: SubQ, Cartesia Pro, Deepgram, Gemini, Anthropic, **Factory** (`FACTORY_API_KEY`), **Moss** (project ID + key from portal.usemoss.dev), Langfuse, Firecrawl, AgentMail.
6. Deploy Remotion Lambda on AWS and run `npx remotion lambda quotas`.
7. **Cache model weights on the compute host over a reliable connection before a demo.**
8. At the venue, test phone round-trip time and UDP reachability on both 5G and Wi-Fi.

### Processes (each in its own container, connected through Redis)
Pins clash: BlurBall and WASB need numpy 1.x, librosa 1.0 needs numpy ≥ 2.1, vLLM needs Python ≥ 3.11, GVHMR needs 3.10 and RIFE needs ≤ 3.11. So each part is a **separate process with its own venv**:
- **Redis Streams** carry events, calls and control messages.
- Frames move through **shared-memory ring buffers** (`multiprocessing.shared_memory`, one per camera, attachable from any venv).

| Process | Env | Does |
|---|---|---|
| `gateway` | py3.11 FastAPI | Video signaling (WebRTC offers), clock sync, signed upload URLs for GCS; serves the PWA and web app behind **Caddy** (HTTPS). Game state, calls and challenges go through **SpacetimeDB** |
| `spacetimedb` | `spacetime start` container + our module (Rust or C#; a TypeScript module if the current version supports it, so check the docs) | Live game state: tables + reducers (`join_game`, `register_camera`, `post_call`, `challenge`, `resolve_challenge`, `submit_house_rule`, `approve_house_rule`, `post_highlight`) |
| `compiler` | Node 20 + `@factory/droid-sdk` | House-rule Droid (F10), in a sandboxed workspace container |
| `rules-index` | py3.11 + Firecrawl + Moss SDK | Scrape the rulebooks → chunk by rule → Moss indexes; answers rule queries (F19) |
| `ingest` | py3.11, aiortc 1.15.0 + av ≥ 17 | One peer connection per phone; decode frames; map RTP time to the game clock; write to that camera's ring buffer |
| `flight` | py3.11, numpy 1.26.4, opencv-contrib 4.10.0.84, torch (CUDA) | BlurBall / WASB / TrackNetV3, triangulation, bounces, P(in) |
| `possession` | py3.11, `rfdetr[train]==1.11.2`, `trackers==2.6.1`, `supervision==0.30.9`, `rtmlib==0.0.16` + onnxruntime-gpu | People, ball, pose with feet, teams, possession, snap |
| `resting` | same as `possession` | At-rest detection + zone scoring |
| `audio` | py3.11, librosa 0.11.0, panns_inference | Classifies phone-reported onsets (rim / net / ground / bag / chains) |
| `engine` | py3.11 | Rule packs, call tiers, `decide()` (Snap → fallbacks), coach, scoring |
| `broadcast` | py3.11 + Node | Claude commentary → Cartesia, highlights, replays; sends render jobs to **Remotion Lambda** |
| `dashboard`, `pwa`, `watch` web app | Vite + TypeScript (React + Three.js + Spark), served by Caddy on the GCP VM. The SpacetimeDB TypeScript SDK supplies live state | UI: capture PWA, live dashboard, post-game watch app (§5B) |
| post-game (Vultr L40S) | py3.10 / 3.11 containers | Practical-RIFE, GVHMR, ReCamMaster, SAM 2 cutouts |

All live containers run on the GCP Deep Learning VM image (Ubuntu, CUDA 12), so the Windows CUDA problems from the earlier draft no longer apply.

### Contracts (agree on these in the first hour)
```text
Event   {id, t_game_s, sport, type, cams[], pos_court_m{x,y,z}?, sigma_m?, actor_id?, target_id?, payload{}, conf}
        type ∈ bounce, wall_bounce, contact, contact_height, touch_count, rim_hit, possession, snap, step,
               in_zone, line_cross, net, catch, player_touch, at_rest, score_zone, timer, audio_onset
Call    {id, t_game_s, rule_id, outcome, p, tier(AUTO|BETA|PLAYERS), shown(auto|challengeable|replay|evidence),
         evidence{cams[], t0, t1, frames[]}, why}
Decide  decide(question, options[], state, images≤4) → {choice, probs{opt:p}, p_cal, backend, latency_ms}
```

**Rule pack** (one YAML file per sport, validated by a JSON Schema):
- `family`, `field` (dimensions, lines, zones) and `detectors` (weights).
- `scoring` (a template such as rally / side-out / innings / cumulative, plus parameters).
- `rules[]`, each with `id`, `tier`, a `when` condition, a `check: code | snap` method, Snap `question` and `options`, and how outcomes map to calls.
- `coach` (candidate generator, options) and `calibration.T`.

**Conditions are written in CEL** (Google's Common Expression Language, via `cel-python`): a safe, proven expression language. That lets Claude write conditions without our code running arbitrary Python, and it fits within Claude's structured-output limit of flat, non-recursive schemas **[X]**.

---

## 1. Platform features

### F1: PWA capture (owner A, P0, about 6 h)
**Built on:**
- getUserMedia with the rear camera pinned by `deviceId`, so iOS doesn't switch lenses mid-game.
- MediaRecorder with `timeslice` writing to OPFS from a worker.
- `requestVideoFrameCallback` for frame timestamps.
- Screen Wake Lock.
- `navigator.audioSession.type='playback'`.

Full browser recipes are in **[X] §2**.

**Steps:**
1. **Hour 1: a device-test page.** It logs lens labels, the resolution and fps actually delivered (`getSettings()`), recorder MIME types, WebRTC codecs, storage estimate, wake lock and beep behaviour on every demo phone. This settles 30 vs. 60 fps, H.264 vs. VP8, and which lens to use.
2. Join by QR (`/join?game=…&cam=…`), landscape only, one camera track used for everything.
3. Record 1080p at about 12 Mbps in 2 s chunks to OPFS, with resumable upload (one phone at a time, after the rally or game).
4. Audio: on the Join tap, unlock Web Audio. Request the mic with echo cancellation, noise suppression and auto gain **off**. An **AudioWorklet onset detector** (10 kHz high-pass + 1 ms energy, the method from arXiv 2409.11760, precision 0.98 **[F]**) sends `audio_onset{t_phone, energy}` plus a 150 ms PCM snippet over the WebSocket.
5. Feedback: a beep, a **full-screen color flash** and a call banner. `navigator.vibrate` on Android only, because iOS can't vibrate from the web. A big **Challenge** button.

**Done when:** 3 phones (iPhone + Android mix) join, stay awake 30 minutes, record without dropouts, and beep within 300 ms of a server-sent call.

**Fallback:** if WebRTC gives trouble on a phone, it sends JPEG over WebSocket (F2B).

### F2: Ingest and clock sync (owner A, P0, about 5 h)
**Built on:**
- **aiortc** `examples/server`: one RTCPeerConnection per phone, non-trickle ICE. Frame `pts` uses a 1/90000 time base.
- **Clock sync:** an NTP-style offset/delay estimate with minimum-RTT filtering and a drift fit, accurate to about ±1–3 ms on a quiet LAN.
- **Camera-latency calibration:** the laptop shows a **60 Hz QR timecode** and each phone films it once. That gives each camera a per-track mapping from pts to game time, and display latency cancels out between cameras **[X] §1, §3**.

**Steps:**
- **F2B first (about 2–3 h):** JPEG over WebSocket. Send a 16-byte header (camera id, sequence number, phone capture time) at 640×360 and 10–15 fps, keeping only the latest frame.
- **Then F2A:** aiortc at 720p.
  - Only H.264 Constrained Baseline or VP8 are offered, and decode is in software.
  - **Drain the receive queues into a latest-frame slot**, because aiortc's queues are unbounded.
- Write frames into per-camera shared-memory rings: `(t_game, frame)` × 4 s.
- **Rally clip fetch:** when a point ends, `engine` asks each phone for the 2 s recording chunks covering the rally. Those 1080p frames feed precise post-point calls and the challenge replay.

**Done when:** 3 streams at 720p reach the laptop at 25+ fps with under 200 ms glass-to-ring latency, and the QR-measured offsets between cameras are stable to within ±1 frame for 10 minutes.

### F3: Field and court calibration (owner B builds the shared module, P0, about 3 h)
**Built on:** `cv2.solvePnP` with known field dimensions (a regulation table is 2.74 × 1.525 m; pickleball, badminton and other courts come from each rule pack's template), plus `cv2.findHomography` for ground planes.

**Steps:**
- **Primary:** the PWA shows a still frame, the user taps 4 corners (or more), and we solve PnP with the template points.
- **Suggestions only:** proposed corners the user drags into place. Sources: the TT3D table segmenter, Good-Pickleball's classical court detector, TennisCourtDetector keypoints 0–3, or CourtKeyNet's 4 corners. These detectors are trained on broadcast footage and **fragile from low phone angles [F]**.
- Store the camera pose per phone and show **reprojected court lines** as an overlay check.

**Done when:** the reprojection error is under 3 px on every phone, and the overlay lines sit on the real lines.

---

## 2. Perception families

### F4: Flight family (owner B, P0 for table tennis, P1 for pickleball, badminton and roundnet)
**Built on:**

| Sport | Model | Proof |
|---|---|---|
| Table tennis | **BlurBall** | F1 96.5–97.2, 72–79 FPS on a 2080 Ti, and blur length as an uncertainty estimate **[F]** |
| Pickleball, tennis | **WASB** tennis weights | Tennis F1 94.0 |
| Badminton | **TrackNetV3** | F1 98.56 |
| Volleyball | fast-volleyball-tracking | F1 0.90, about 150 FPS on CPU |
| Bounce timing | Audio onsets | arXiv 2409.11760 |

**Steps:**
1. **Tracker wrapper:** `track(frames)->[(t, x, y, conf, blur_len)]`.
   - BlurBall input is 3 frames at 512×288 with ImageNet normalisation, and it outputs heatmaps.
   - **Fix its inference script's BGR→RGB bug**, and **turn its duplicate-frame filter on** (the README says it's on by default; it isn't) **[F]**.
   - **Use white balls** (BlurBall was never trained on orange ones).
   - Blur half-length is in 512-wide pixels: multiply by 2.5 for 1280 wide.
2. **WASB** has weights for all five sports but **no inference code**, so load them through BlurBall's runners **[F]**.
3. **TrackNetV3** is **post-game only** (its inpainting needs future frames, and the stock script runs at 0.3–3 FPS). For live badminton calls, use WASB badminton weights.
4. **3D:**
   - With 2+ cameras: N-view DLT triangulation (OpenCV `triangulatePoints`, or `aniposelib` with RANSAC for 3+ cameras). Fit each flight between bounces to a **gravity parabola** using each camera's own timestamps.
   - With 1 camera: ray–plane intersection at the bounce (`intersect_ray_plane`, from TT3D).
5. **Bounce event:** the nearest audio onset sets the time, which matters most at 30 fps. The fitted flight at that time gives the position. Uncertainty σ combines fit residual, calibration reprojection, blur and timing error **[F] Methods**.
6. **Line-call probability:** **P(in) = Φ(d/σ)**, with d the signed distance to the line. Show the uncertainty ellipse.

**Done when:** on 40 staged table-tennis bounces (20 clear, 20 near the edge), every clear one is correct and the near-edge ones carry a calibrated P(in). The mean 3D bounce error, measured against tape marks, is under 2 cm with 2 phones.

**Fallback:** single-camera ray–plane bounces, with the call downgraded to BETA.

### F5: Audio classifier (owner B, P0 for table-tennis bounces, P1 for roundnet rim and cornhole)
**Built on:** **PANNs** CNN14 embeddings plus logistic regression, a standard transfer-learning recipe. The bounce paper's mel-spectrogram CNN reached F1 0.97 at telling surfaces apart **[F]**.

**Steps:**
- Record about 50 snippets per class with the PWA itself during development: table, racket, floor, net, **rim**, bag-on-board, bag-in-hole, chains.
- Embed them and fit one classifier per family.
- PANNs downloads its weights with `wget`, which Windows lacks, so **pre-place the weight files**.

**Done when:** class accuracy is at least 90% on a held-out set of 20 per class.

### F6: Possession family (owner C, P0 for basketball, P1 for two-hand touch, P2 for soccer, ultimate and dodgeball)
**Built on:**
- **RF-DETR** detection: on a T4 with TensorRT FP16, Small runs at 3.5 ms. COCO class ids: person 1, frisbee 34, sports ball 37, baseball bat 39, glove 40. **Print `class_id` once before hard-coding them**, because one docs page numbers them differently **[P]**.
- **roboflow/trackers ByteTrack**.
- **rtmlib `BodyWithFeet`** (Halpe26): wrists 9/10, ankles 15/16, big toes 20/21, heels 24/25 **[P]**.
- The **roboflow/sports** SigLIP + UMAP + KMeans team classifier, which assumes 2 teams. **Bring pinnies.**

**Steps:**
1. Use TensorRT for RF-DETR, because the ONNX CUDA path is slow **[P]**.
2. Run **separate trackers** for people and for the ball (ByteTrack ignores class).
   - Set the ball tracker's activation threshold well below the default 0.7, and use a simple gate tracker or BIoU matching.
   - Pass in capture timestamps; a backwards timestamp skips the whole frame.
3. Run pose **only on players near the ball**, passing in tracked boxes so ids line up (rtmlib's own PoseTracker returns no ids).
4. **Field homography:** about 30 lines of cv2, the ViewTransformer pattern from roboflow/sports.
5. **Possession / contact:**
   - Ball near a wrist keypoint (within an adaptive radius scaled by box height) → `contact(actor)`.
   - Ball crosses a boundary polygon → `line_cross` (supervision `PolygonZone`, or `LineZone` for cone goals).
   - **Multi-view:** choose the best phone per event instead of triangulating people. Full triangulation needs ChArUco calibration and matching people across phones, which takes hours **[P]**.
6. **Basketball make/miss:** reimplement the shot-tracker rule. The ball crosses the rim's top edge moving down, within the rim span, then is seen below it, bridging up to 4 frames for net occlusion. It went **23/23** on the author's clips, which were also its tuning set **[P]**.
   - Train our own ball + hoop RF-DETR on about 300 frames, roughly 5–10 min on the laptop by estimate. The original repos have no license, so **reimplement their logic rather than copy it**.

**Done when:** on 20 recorded basketball shots, make/miss gets at least 19 right. The person id-switch rate is under 1 per 30 s in a 3v3.

### F7: Resting-object family (owner A after F1/F2, P0 for cornhole, P2 for mini golf and bowling)
**Built on:**
- A fixed phone plus a homography to the board's coordinates.
- An **"at rest" test:** tracker speed below a threshold for N frames, or frame differencing.
- **RF-DETR fine-tuned** on **Cornhole Referee** (CC BY 4.0, 394 images with bag-in-hole classes; there's no pretrained model, so we must fine-tune) **[P]**.
- **Mini golf:** `minigolf-ball-detection/5` (mAP50 71.7) as a Roboflow dataset export.

**Steps:**
1. Export the datasets tonight (needs a free Roboflow key) and **fine-tune locally**, so nothing depends on a key at runtime.
2. Zone scoring in board coordinates: hole = 3, board = 1, off = 0; cancellation scoring to 21.
3. The bag-in-hole sound from F5 confirms the hole class.

**Done when:** 30 throws on the tabletop board are scored with at least 28 right.

---

## 3. The priority calls (ranked) and how each is built

Each call is a rule in a pack, made from family events. Tiers follow the confidence gate: ≥ 0.90 auto, 0.60–0.90 challengeable, < 0.60 replay the point. Snap's probability is **calibrated** (F9) before the gate.

| Rank | Call | Built from (proven pieces) | Logic | Test (done when) |
|---|---|---|---|---|
| 1 | **Pickleball near-line in/out** (BETA) | F4 WASB tennis weights + F3 + F5 bounce time | `bounce` → d to the nearest line → P(in) = Φ(d/σ); \|d\| < 2σ → challengeable | 30 staged bounces near the baseline, judged against tape-mark ground truth: reliability curve within ±10% |
| 2 | **Kitchen volley foot fault** (AUTO) | F6 rtmlib toes/heels + F3 kitchen polygon + F5 paddle-contact onset | Volley = paddle contact with no bounce on that side since the last crossing. Fault if a toe or heel keypoint is inside or on the kitchen polygon (with margin σ_px) at contact, **or from contact until the player has re-established balance outside** (1.0 s window) | 20 staged volleys (10 faults, 10 clean): at least 18 right |
| 3 | **Table tennis edge vs. side** (BETA) | F4 BlurBall 3D + F5 (table vs. edge sound) | Bounce lands within 2σ of the table edge → classify by the trajectory's deflection (an edge ball keeps an upward rebound; a side ball drops off) and the audio class. If ambiguous, Snap `choice{EDGE_IN, SIDE_OUT}` with 4 crops | 20 staged edge hits: at least 16 right, the rest shown as "replay" |
| 4 | **Two-hand touch** (BETA) | F6 rtmlib wrists + ByteTrack ids + carrier from possession | Touch = **both** of a defender's wrists inside the carrier's box (expanded 10%), each held ≥ 2 frames, **with \|Δt\| ≤ 0.25 s between hands**, before the throw. Gray zone → Snap `noul` (yes/no) "both hands touched before the throw?" with 4 frames + the event log | 20 staged plays (10 two-hand, 5 one-hand, 5 after the throw): at least 16 right |
| 5 | **Roundnet rim vs. pocket** (BETA) | F5 rim classifier + F4 WASB volleyball weights / roundnet fine-tune (861 images, CC BY 4.0) | Contact near the net's edge ring: rim-sound probability + the trajectory's deflection angle → P(rim) → Snap `choice{RIM, POCKET, CLEAN}` when 0.3–0.7 | 20 staged hits: at least 16 right |
| 6 | **"Off you"** (BETA) | F6 contact events + `line_cross` | Last `contact(actor)` before `line_cross` (out) → possession to the other team; low contact confidence → challengeable | 15 staged out-of-bounds plays: at least 12 right |
| 7 | **Travel step counter** (BETA) | F6 ankles + ball possession (gather = ball in both hands) | Count ground contacts (vertical-velocity minima of ankles or heels, as in Stenum 2021 for 2D gait, about 0.02 s error from a side view) between the gather and the dribble or release; > 2 → travel. Always challengeable (expect false travels **[P]**) | Show the step overlay; report precision on 15 clips |
| 8 | Double dribble (BETA) | F6 ball-height reversals + wrists | A dribble is a ball-height reversal of ±18 px (ayushpai's method, reimplemented). Two-hand contact then a dribble → violation | 10 clips |
| 9 | **Rush count, "you counted too fast"** (AUTO) | **Snap detection:** frame-difference MSE + 5-tap median; the formation frame is the last before MSE rises steadily (CVPRW 2013: 94.5% within 1 s). **Line of scrimmage** = peak player density along the field (97.5–97.9% within 10 px) **[P]**. Plus ball displacement and a "hike" audio onset | Timer from the snap; a rusher crossing the line of scrimmage before 5.0 s → penalty | 15 snaps within ±0.3 s |
| 10 | Badminton in/out (AUTO) | F4 WASB badminton (live) / TrackNetV3 (post-game) + F3 | The shuttle falls nearly straight down → landing point + P(in) | 20 landings: at least 18 right |
| 11 | Cornhole scoring (AUTO) | F7 | Zone + cancellation | F7 test |
| 12 | Basketball make/miss (AUTO) | F6 | Shot-tracker rule | F6 test |
| 13 | **Fouls: evidence mode** (PLAYERS) | F6 tracks + pose | **Never rules.** Shows slow-mo of the contact, **who moved first** (velocity onset), the minimum distance between bodies, and a timeline | Qualitative |

**More sports (P2):**
- Soccer cone-goal: `LineZone` between the cone bases, plus a ball-height estimate for "over the bar".
- Dodgeball hit or catch: ball–person box overlap plus wrist proximity.
- Wiffle strike zone: BaseballCV's geometry (17 in plate, knee to the shoulder–hip midpoint) on rtmlib keypoints.
- Ultimate stall count: a possession timer.

---

## 4. Decisions, rules and AI features

### F8: Rule engine and packs (owner D, P0, about 6 h)
**Built on:**
- Rule packs as **data** (JSON Schema + YAML), conditions in **CEL**.
- Scoring templates as small state machines (the `transitions` Python library, MIT, widely used).

**Steps:**
1. Event fusion: dedupe across cameras, keep the most confident.
2. Rule evaluation per rally.
3. The confidence gate, and call emission to `gateway`.
4. **Auto-tag "players decide":** any rule whose condition uses an event type the pack can't sense becomes PLAYERS automatically.
5. Write the P0 packs by hand: table tennis, basketball, cornhole. **Claude drafts the other 25**, and we review the P1 ones (pickleball, badminton, two-hand touch, roundnet).

**Done when:** recorded event logs, replayed through the engine, give the expected calls for every P0 pack. These replays are the unit tests.

### F9: `decide()`, SubQ Snap and calibration (owner D, P0, about 4 h)
**Built on:**
- **SubQ Snap 1.1** `POST https://api.subq.ai/v1/systemone`, `model: subq-snap-1.1`.
  - `choice` questions (2–255 options) return **probabilities for every option**. `noul` returns P(yes).
  - At most 4 images, 4 MiB each and 8 MiB total, **downscaled**, so send tight crops.
  - Retry only 429 and 5xx **[X] §4**.
- **Temperature scaling** (Guo et al., ICML 2017, the standard calibration method).

**Steps:**
1. Write the ~40-line HTTP wrapper.
   - Use `probabilities[choice]` as the probability. Don't use `confidence`, which only measures how peaked the distribution is.
   - On borderline calls, **ask twice with the options shuffled** and average, to cancel order bias.
2. Fallback chain behind the same interface (all hosted):
   1. Snap: 2 s timeout, 1 retry.
   2. **Gemini Flash** (Google credits) with a constrained choice and up to 4 frames.
   3. **Claude** with `output_config.format` structured output and 5 votes in shuffled option order, vote share as the probability. Claude now rejects `temperature`, and forced `tool_choice` returns 400 on Opus 5.5 / Sonnet 5.5 **[X]**.
   4. Geometry only.
   - Optional, only if the GPU has headroom: Qwen3-VL-8B-FP8 on vLLM in a container on the live box, using per-option logprobs.
   - Trace every decision in **Langfuse** and keep the labelled calls there as eval datasets.
3. **Calibration:** label about 60 calls per Snap-judged rule type during development, fit `T` with `softmax(log p / T)`, and plot a **reliability diagram**. That plot goes on the slides.

**Done when:** p50 latency is ≤ 1.5 s for referee calls, the fallback switches over automatically (test by pulling the network), and the calibration plot exists.

### F10: House-rule compiler, run as a Factory Droid (owner D, P1, about 5 h)
**Built on:**
- The **Code World Models** method (DeepMind, arXiv 2510.04542): the rule is written as code, **tested against recorded traces**, failing traces are fed back, and the loop repeats until every test passes.
- That loop runs inside a **Factory Droid**: the Droid TypeScript SDK `@factory/droid-sdk` (`createSession()` for multi-turn, Node 18+, `FACTORY_API_KEY`), which drives the `droid` CLI as a subprocess. The Python SDK is the alternative.

**Why a Droid:** the compiler benefits from an iterative agent loop with these capabilities:

| Capability | How the compiler provides it |
|---|---|
| Droid does real work in the running product | It writes the rule the engine enforces on the next rally |
| A trigger we designed | A new `house_rule` row in SpacetimeDB |
| Controlled access with safety | The sandbox and approval gate below |
| Visible work | Plan, diff and test results streamed to the dashboard |

**Steps:**
1. **Trigger.** A judge types or **says** a house rule ("Trophy, house rule: hangers count two"). The PWA calls the reducer `submit_house_rule(text, sport)`. A `compiler` service subscribed to `house_rule WHERE status='pending'` picks it up.
2. **Sandbox.** The service starts a Droid session in a **throwaway container workspace** that holds:
   - the sport's rule-pack YAML;
   - the JSON Schema;
   - a `replay_test` harness, which replays the last 10 recorded rallies' event logs through the engine;
   - the relevant official rule clauses retrieved from **Moss** (F19).

   **Runtime scope:** edit `rules/<sport>.yaml` and run `replay_test` in an isolated workspace, with no network and a 90 s timeout by default. Configure autonomy for that task. This boundary isolates user-supplied rules; repository agents may revise the compiler design and scope when needed.
3. **Work.** Droid drafts the rule (CEL condition + tier + outcome), runs `replay_test`, reads the failures ("rally 7 would now score 2 for a bag touching the ground"), repairs the rule, and repeats until every test passes or it has made 3 attempts.
4. **Make it visible.** Stream Droid's **plan, each step, the YAML diff and the test table** into `house_rule.plan/diff/results`. The dashboard shows them live, along with "Calls that would change: rally 3 (1 → 2 points)."
5. **Human approval.** The judge taps **Approve**. A reducer hot-loads the new pack version, and Cartesia says "House rule added: hangers count two."

**Fallback:** the same schema and replay tests with **Claude only** (`claude-opus-5-5`, structured output, no agent loop).

**Done when:** 5 prepared house rules (table tennis, cornhole, pickleball, basketball, flag football) each compile through Droid in under 90 s, show the plan, diff and tests on the dashboard, and apply on the next rally. The README explains where and how Droid is used, because Factory requires it.

### F11: Coach, "wrong move vs. better move" (owners D + B/C, P1, about 5 h)
**Built on:** Snap `choice` over candidate options, using the **whole game log** as context. Coach requests run 40–60K tokens, about $0.004 each **[X]**. Candidates come from geometry the family modules already compute.

**Candidate generators:**
- **Flight:** a 3×3 grid of target zones on the opponent's side × {soft, hard}, ruling out zones the opponent covers (their position at contact).
- **Possession:** {shoot, pass to the most open teammate (largest defender distance), drive}. In football, the most open receiver at release.
- **Resting:** aim offsets from your miss pattern.

**Steps:**
1. Always include **the move the player actually made**, and shuffle the options.
2. Flag when **p_best − p_actual ≥ 0.30 and p_actual ≤ 0.15**, and only if the session's win-rate stats point the same way.
3. Claude writes two sentences.
4. The 3D or 2D replay draws the better option as a **ghost trajectory**.

**Done when:** at least 5 coach cards per demo sport are generated, and teammates agree with at least 70% of them.

### F12: Commentary (owner D, P0, about 3 h)
**Built on:**
- Claude streaming over the **structured event log**, so it can't invent plays.
- **Cartesia `sonic-3.6` WebSocket** (`wss://api.cartesia.ai/tts/websocket?cartesia_version=…`):
  - `context_id` + `continue:true` for one flowing voice.
  - `cancel` for lines a newer event has made stale.
  - Lower `max_buffer_delay_ms` from its 3000 ms default.
  - Use the inline `<emotion value="excited"/>` tag (the schema's emotion list doesn't include "excited").
  - **Phones get a short-lived `/access-token`, never the key.**
  - Test both auth header forms, because the docs disagree **[X] §6**.

**Steps:** one play-by-play voice and one colour voice. Use players' names from the join screen. A **one-line accessibility mode** reads every call aloud.

**Done when:** a call is spoken in under 1.5 s from the event, and lines cut off cleanly when the next point starts.

**Voice interface:** Trophy is a **voice referee**. Players mid-rally can't look at a phone, so **every call, verdict and answer is spoken**, which makes voice core rather than a demo feature.
- **Two distinct voices:** play-by-play and colour.
- **Voice in:** challenges and questions (Deepgram), with spoken answers.
- **Audio-description mode:** for blind and low-vision players and spectators.
- **Submission:** a **2-minute demo-first video**, plus a README listing the Cartesia features used: Sonic-3.6 WebSocket streaming, `context_id` continuations, `cancel`, emotion tags, word timestamps, and a cloned announcer voice if you use one.

### F19: Rulebook lookup and "ask the ref", with Moss (owner D, P1, about 3 h)
**Built on:**
- **Firecrawl** (scrape official rulebook pages and PDFs).
- **Moss** (YC F25; a Rust/WASM semantic + keyword index, about 10 ms per query, JS and Python SDKs; `moss-minilm` default, `moss-mediumlm` more accurate; hybrid `alpha`).
- **Deepgram Nova-3** STT, **Claude** for the grounded answer, **Cartesia** for speech.

**Steps:**
1. Scrape the official rules for the P0 and P1 sports: USA Pickleball, BWF, ITTF, USA Football flag, the American Cornhole Organization, FIBA/streetball conventions.
2. Chunk them **one rule per document**, with metadata {sport, rule_id, title, url}.
3. Build **one Moss index per sport** and load it into memory in the `rules-index` service.
4. **Ask the ref:** "Trophy, can I volley from the kitchen line?" → Deepgram → Moss `query(top_k=5, alpha=0.6)` → Claude answers **only from the retrieved clauses** and cites rule numbers → Cartesia speaks the answer. Show the quoted clause on the dashboard.
5. **Verdicts cite the rule:** every challenge verdict and house-rule diff shows the official clause it relates to.
6. The **Droid compiler** (F10) gets the top-k clauses, so house rules are written relative to the official rule.

**Done when:** 10 prepared questions across 4 sports are answered with the correct rule citation, Moss p95 is under 20 ms, and the spoken answer starts within 2 s of the end of the question.

---

## 5. Replays and broadcast

### F13: Challenge replay and evidence mode (owner A, P0, about 4 h)
**Built on:** the per-rally 1080p chunks (F2), the tracked ball and pose overlays (supervision annotators), and the calibrated call.

**Steps:**
1. Tapping *Challenge* fetches the clip from each camera (±1.5 s).
2. The **auto-director** picks the best angle (F14).
3. Show slow-mo (F14), a **2D or 3D bounce mark with its uncertainty ellipse**, and the verdict with its confidence.
4. **Evidence mode for fouls** (no verdict): side by side, the contact frame highlighted, who moved first, the minimum distance.
5. Limit challenges per player.

**Done when:** a challenge resolves on the judge's phone within 6 s of the tap.

### F14: Auto-director, slow-mo and trophy clip (owner A, P1, about 5 h)
**Built on:**
- **Auto-director:** Arev et al., SIGGRAPH 2014, which edits multiple handheld cameras with dynamic programming over a trellis graph. Our version is **Viterbi over (camera, shot duration)** with each camera scored on ball and actor visibility, player facing, sharpness and distance to the play, plus minimum and maximum shot lengths and a switching cost that's cheaper at action boundaries **[X] §8**.
- **Practical-RIFE v4.25** at 4× (MIT; needs Python ≤ 3.11; weights on Google Drive). Browsers can't record 120 fps, so slow-mo comes from interpolation.
- **Remotion 4.0.538** for a 9:16 composition: score bug, captions from Cartesia word timestamps, speed ramp. It's free for teams of 3 or fewer employees, and on Windows `--props` must be a file path.

**Steps:**
1. Pick the "Play of the Game" from the highlight score (F15).
2. Cut it with the auto-director.
3. Interpolate the 1-second hero moment.
4. Render with **Remotion Lambda** on AWS.
5. Send a link to the judge's phone.

**Done when:** the trophy clip renders in under 90 s after the game ends.

### F15: Highlights (owner A or D, P1, about 2 h)
**Built on:** **PANNs** AudioSet tags (Cheering 66, Applause 67, Crowd 69) + loudness peaks + call events (challenges, close calls, long rallies) + motion energy. Re-rank the top 10 with Claude looking at keyframes.

**Done when:** the top 3 highlights of a 20-minute game include the 2 moments the team picked by hand.

### F16: 3D replay (owner B or D, P2, about 6 h)
**Built on:**
- **Three.js** for the court and ball trail, using the fitted parabolas.
- **Spark 2.4.0** (needs Three ≥ 0.180) for an optional court splat scanned before the game.
- **Players:** skeletons from rtmlib keypoints lifted onto the ground plane. **GVHMR** (static-camera `-s`) on AWS only if there's time: it tracks one person at a time, resamples to 30 fps, and needs the **SMPL** license.

**Camera presets:** courtside, top-down, broadcast-high, and **first-person from the head joint**.

**Done when:** the challenge view shows a 3D bounce mark plus the ball trail with presets.

### F17: Privacy blur (P2, about 1 h)
**Built on:** **deface** CLI (CenterFace, MIT). People who didn't enrol at join are blurred in shared clips, and when unsure it blurs.

### F18: Generative re-shoot (stretch)
**Built on:** **ReCamMaster** (weights at `KlingTeam/ReCamMaster-Wan2.1`, 81+ frames, `metadata.csv`) on AWS. Render one trophy clip, labelled "AI-generated view." Skip it unless everything else is done.

---

## 5B. Build on Replay for Trophy's post-game web app

Source: [subatomic-hamster/replay](https://github.com/subatomic-hamster/replay) (MIT). It films a pickup game with one phone and plays it back on Fire TV like a broadcast. Its computer-vision core is **[courtcam](https://github.com/subatomic-hamster/courtcam)** (MIT, published as its own repo). Full inventory (49-row mapping, measured numbers): [Replay repository inventory](../research/replay-repo-inventory.md).

> **Reuse is encouraged.** Build on Replay and courtcam ideas and compatible licensed code, including `apps/`, `render/`, `services/` and `infra/`. Adapt, copy, vendor or reimplement as appropriate; preserve required notices and record incorporated sources/revisions in `docs/licenses.md`. No event window or organizer approval is required. Code licensing does not grant access to private footage or infrastructure; use media with permission and authorized compute. Check Python and GPU compatibility when integrating courtcam.

### Format change: a web app that works after the game, not a TV app
The current **Trophy Watch** target is a web app. Replay's interfaces and code can be adapted to it; Fire TV or Alexa support can be revisited if useful:
- Responsive React (Vite).
- Works in **any browser**: phone, laptop, or a TV's browser via cast or HDMI.
- Opened from the **recap link** (AgentMail email or QR) as soon as post-processing finishes.
- Touch, mouse and keyboard controls.
- Voice commands go through Deepgram in the browser ("Trophy, clip that"), not Alexa.

### courtcam methods Trophy reuses (as a library)
| courtcam method | Measured (Replay's own docs, on footage) | Improves Trophy |
|---|---|---|
| `calibrate.py`: fit from any 4+ landmarks, with a reprojection gate that scales with click spread and a fix for mirrored labels. `distortion.py`: one-parameter lens model. `camera_calibration`: focal length from the homography + `solvePnP` | Synthetic: focal error 0.25–0.64 %, rotation 0.11–0.28°, camera position 4–8 cm | **F3** calibration (in place of our hand-written solvePnP tool). **Fixes the fisheye clips** in the clip library |
| `templatefit.py` auto court fit | **Refused on every real basketball clip**, so use it **only to suggest corners** | F3 suggestions |
| `court.fit_check`: flags the calibration as untrusted when player positions disagree with it | — | **F8**: automatically demote calls to BETA when calibration is untrusted |
| `ball.py` make/miss at the rim, **classical CV, no model** | Shots P/R 0.90/0.90, make/miss 8/9 (Nottingham Q1); hold-out 0.80/1.0, 7/8 | **F6 basketball make/miss.** Replaces the unlicensed repos. **"Can't tell" at the rim edge maps to BETA** |
| Filter for players actually on court (drops benches, spectators, neighbouring courts). **Teams** from torso colour (HSV 8×4×4), net side, or who guards whom in 2v2/3v3 | Team accuracy 0.98, player recall 0.876 | **F6**: handles **pickup games with no pinnies**. Plug RF-DETR in through courtcam's `Detector` interface, which keeps YOLO (AGPL) out |
| **Sport profiles**: YAML + a court template in metres + play grammars (state machines and sequences), with the core never branching on the sport. Rally segmentation from player speed; side-out and server rules | Badminton rallies P/R 1.00/0.86 | **F8** rule packs: reuse its **profile and grammar format and rally segmenter** for the flight family's scoring templates |
| **Grounded commentary**: template lines + an LLM paraphrase that ships only if a validator finds every name, number and action in the event facts | 28/28 template, 26/28 LLM lines accepted | **F12**: add the **validator** in front of Cartesia, so no line can invent a play |
| **X-gesture detector** (crossed arms) | 22/22 on ground-truth poses; 0 false triggers in 480 s | **F13**: a **hands-free "challenge"** gesture (cross your arms) next to the voice command and the button |
| **Trigger-to-play rule** (the play that ended in [T−8 s, T+0.5 s]) | 73/73 | F13 (which call a challenge refers to) and "clip that" |
| Hype meter, best-play rule, director cut rules with smoothed virtual cameras, score bug, telestrator | — | **F14/F15** (as a design guide) |
| MOT metrics, event evaluation against hand play logs, `eval_moments`, `eval_scene`, **`courtcam synth`** (labelled synthetic games for 4 sports) | — | **§6 accuracy** and **rule-engine test fixtures** (always labelled synthetic) |
| 2.5D scene package: **SAM 2.1 cutouts** (Apache) → Player's view, Orbit, Broadcast high | About 1 GPU-minute per 8 s play | **F16**: a licence-clean alternative to GVHMR/SMPL, run on the **Vultr** box. With **2+ phones**, Trophy can do the true multi-view 3D that Replay's own "Tier D" notes wanted |

### Trophy Watch features (adapted from Replay ideas and code)
| Feature | What it does | Built on | Priority |
|---|---|---|---|
| **Follow a player** | Pick a player; the video crops and pans to follow them ("Following Anshul") | courtcam tracks + a smoothed crop path; with several phones, the auto-director (F14) picks the best camera for that player | P1 |
| **Moments browser + ★ Best play** | Jump to plays: scores, calls, challenges, "Lost his man", bookmarks | Trophy events + calls + courtcam play grammar; best-play rule + the highlight score (F15) | P1 |
| **Condensed game + rally browser** | Every rally or possession back to back, dead time removed | Rally segmentation (courtcam) + ffmpeg concat | P1 |
| **Broadcast mode** | Score bug, captions, spoken play-by-play, **Trophy's calls overlaid** | F12 commentary + Remotion/WebGL overlays | P0 (it's the trophy clip's look) |
| **Replay angles** | Real cameras + **virtual angles** (Player's view, Orbit, Broadcast high, top-down), 0.5× slow-mo | F14 RIFE, F16 3D / 2.5D | P2 |
| **Plain-English play search** | "Show every kitchen fault by Sam", "Joseph's threes" | **Moss** index over moments (sub-10 ms) + Claude query parsing → filters. This supports search over recorded game events | P1 |
| **Stats panel + player card** | Per-player stats, shot chart and heatmap, calls against, challenge record, coach cards (F11) | Trophy events + courtcam heatmap | P1 |
| **"Can't tell" review queue** | Every BETA or low-confidence call and every unlabelled moment, for a human to confirm. **This builds the labelled set for calibration** | §6 accuracy + F9 calibration | P1 |
| **Clips: trim, share, 9:16 reels** | Clip any moment, trim it, share a link; vertical highlight reel | F14 Remotion; signed GCS links | P1 |
| **Voice + gesture commands** | "Trophy, clip that", "Trophy, challenge", X-gesture | Deepgram STT (Replay used Whisper) + courtcam X-gesture + the trigger-to-play rule | P1 |
| **Profiles with consented naming** | Players enrol a face or jersey at join; **everyone else stays anonymous** (and blurred in shares) | F17 blur + enrolment (Replay's privacy rule) | P2 |
| **Pickup scoring modes** | Make-it-take-it, by 1s/2s, win by 2, game to 11/15/21 | Rule-pack scoring templates (F8) | P1 |
| **Watch party** (new, not in Replay) | Friends open the same game link; **playback, cursor and reactions stay in sync** through SpacetimeDB | **SpacetimeDB** shared state for synchronized viewing | P2 |
| QR / phone handoff | Open any moment on another device with a scoped, expiring token | Gateway signed tokens | P2 |

**Dropped:** the Fire TV app (react-native-tvos, D-pad focus), the Alexa skill, Replay's AWS CDK stack (Lambda/CloudFront; Trophy uses GCP + Caddy), and Kokoro TTS (Cartesia replaces it).

**Suggested owners:** A (web app, clips) + D (search, stats, review queue). Schedule Trophy Watch alongside the trophy clip after the core capture and event pipelines work; adjust P1 scope to the current milestone.

## 6. Sport wall and accuracy (owner D, P1, about 3 h)
**Built on:** our own labelled calls (a keyboard-shortcut labeler over the rally clips) and Wilson confidence intervals.

**Steps:**
- 28 tiles: **LIVE / VERIFIED / PACK**.
- Each VERIFIED tile shows "n = 20, 18/20 correct (95% CI 0.70–0.97)".
- One slide with the reliability diagram and the confidence-gate bands.

---

## 7. Suggested milestones

Sequence and owners are flexible; there is no fixed implementation window or submission deadline.

| Block | A: PWA + resting + replays | B: Flight + audio + calibration | C: Possession | D: Engine + AI |
|---|---|---|---|---|
| **Foundation** | Device-test page; Caddy HTTPS; join by QR; JPEG-over-WebSocket stream; NTP sync | Envs + weights smoke tests (BlurBall/WASB) on recorded clips; solvePnP tap-corner tool | Envs; RF-DETR TensorRT, ByteTrack, rtmlib feet on a sample clip; print COCO ids | Contracts, **SpacetimeDB module (tables + reducers)**, Redis, rule-pack schema + CEL, `decide()` with Snap + Claude fallback; table-tennis pack; start the Firecrawl → Moss rule indexes |
| **First vertical slice** | MediaRecorder → OPFS, chunk upload; QR timecode calibration | Live table-tennis bounce → 2D call; audio-onset fusion | Basketball ball+hoop fine-tune (record 300 frames on site, label, train); make/miss | Engine replaying event logs; commentary → Cartesia |
| **Live integration** | aiortc 720p path; challenge UI | 2-camera triangulation + P(in) ellipse; edge-ball logic | Possession/contact, "off you", step counter | Cornhole + basketball packs; calibration harness |
| **P0 checkpoint** | **Each P0 family makes ≥ 1 correct live call, or switch to "calls within 2 s after the point"** | | | |
| **Expand coverage** | Cornhole fine-tune + zone scoring; **park trip with C** (basketball, pickleball, two-hand touch, soccer, ultimate) | Pickleball in/out + **kitchen fault with C**; badminton (WASB); roundnet rim audio | **Snap detector + rush count, two-hand touch**; kitchen feet | **House-rule Droid** (sandbox, trigger, plan/diff/test stream); "ask the ref" (Moss + Deepgram + Cartesia); coach (flight + possession candidates); sport wall |
| **Replays and evaluation** | Auto-director, RIFE, Remotion trophy clip; highlights | 3D replay of ball + presets (P2); roundnet live | P2 sports: dodgeball, soccer cone goal, wiffle zone | Label ~60 calls per type → fit `T`; accuracy tiles; 25 drafted packs reviewed |
| **Stabilization** | **Stabilize the chosen release scope** | | | |
| **Demo preparation** | Demo video | Demo-table rehearsal | Recorded-segment edit | Slides: architecture, calibration, sport wall |
| **Release** | **Share the validated demo or release when ready** | | | |

---

## 8. Hour-0 smoke tests (before writing features)

0. **The GCP L4 VM is up** (quota approved; otherwise use the Vultr fallback). `docker run --gpus all … nvidia-smi` works. A phone on **5G** opens `https://trophy.<domain>`, a WebRTC test stream reaches aiortc, and the round trip is measured.
1. In each container: torch reports CUDA. onnxruntime-gpu lists `CUDAExecutionProvider` **and actually uses VRAM** (rtmlib issue #46: it can silently run on the CPU) **[P]**.
2. BlurBall on a 3-frame sample → heatmap peak at the ball; WASB tennis weights load through the BlurBall runner.
3. RF-DETR-S TensorRT FPS at 720p on the laptop: target ≥ 40.
4. SubQ `/v1/models` lists `subq-snap-1.1`, and one `choice` call returns probabilities. Have **a spare key from a second teammate**.
5. The Cartesia WebSocket speaks one line (try both auth headers).
6. A phone opens `https://trophy.<domain>` (Caddy on EC2) with no certificate warning, and `wss://` connects on both 5G and venue Wi-Fi.
7. A SpacetimeDB reducer called from Python over HTTP reaches a phone's TypeScript subscription in under 100 ms. `npx remotion lambda quotas` shows the concurrency you'll get.
8. A Droid SDK session edits a toy file and runs a test command inside the sandbox container. A Moss query returns a rule clause in under 20 ms.

## 9. Things to fix now (from the integration checks)
- **Use white table-tennis balls**, not orange (BlurBall was trained on white). Update the gear list.
- **Pin versions; don't install latest.** numpy 2.5, OpenCV 5.0, librosa 1.0 and torch 2.14 break the repos **[F]**.
  - RTX 50-series laptops need torch ≥ 2.7 built for CUDA 12.8; set `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` or patch the `torch.load` calls.
  - Keep supervision at 0.30.9 (0.31 removed `sv.ByteTrack`).
  - Keep Roboflow's `inference` package **out** of the live environment (dependency conflicts) **[P]**.
- **Download onto the chosen compute host** with `gdown` (Google Drive throttles large files), using a reliable connection:
  - BlurBall (`blurball_best`, Nextcloud), WASB `wasb_<sport>_best.pth.tar`, RIFE 4.25, PANNs CNN14.
  - TT3D's ImageNet encoder.
  - Roboflow exports: Cornhole Referee, minigolf, roundnet, flag football.
  - Qwen3-VL-8B-FP8 (about 10 GB).
- **Licenses:** BlurBall and WASB weights have unstated licenses; the basketball repos have none, so reimplement their logic; YOLO-based weights are AGPL. Check permissions for each selected code, weight and dataset revision and record adopted components in `docs/licenses.md`.
