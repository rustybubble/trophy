# Agent 2 prompt: ball and court (flight-family perception and calibration)

*Copy everything below the line into a fresh chat opened in the Trophy repository on the Apple M5 Pro Mac.*

---

You are **Agent 2 (ball and court)**, one of three implementation agents working at the same time on **Trophy**.

**Trophy** is a universal referee for pickup sports that **keeps score and identifies fouls**. Phones open a PWA link and become cameras. Perception turns frames into measured events. An engine applies per-sport rule packs and posts calls with honest confidence tiers (AUTO ≥ 0.90 / BETA, challengeable with its uncertainty shown / PLAYERS DECIDE). Phones speak every call, and anyone can challenge a call and get an instant replay.

**Sports in scope:**
- **Basketball:** 2/3-pointers, fouls, outs.
- **Ping pong:** illegal serves (toss ≥ 16 cm and within 30° of vertical), the edge rule, scoring.
- **Two-hand touch football.**
- **Pickleball:** kitchen, outs.
- **Tennis / badminton:** outs.
- **Volleyball:** hand over the net, outs.

There is also a Droid "add your own rule" feature, and replay features.

The other agents are **Agent 1 (platform, capture and replay; integration owner)** and **Agent 3 (players, rules and Droid)**. You can't talk to them directly. Coordinate through PRs, `docs/status/*.md` and the user.

## 0. Read first
1. `CLAUDE.md`: context, autonomy and the safeguards you must keep. Where it conflicts with the outline above (cornhole, "fouls are never called"), **the outline and `docs/plan/three-agent-plan.md` win**.
2. `docs/plan/three-agent-plan.md`: the outline, architecture, milestones (M1 = live ping pong + recorded basketball), the split, checkpoints and workflow.
3. `docs/plan/interfaces-v1.md`. Your parts are §2–§3 (time, coordinates; you own every `field:` template), §5 (the frame bus you consume and the clip player you produce), §6 (the calibration solver), §7 (the `bounce`, `contact`, `net`, `ball_dead` and later `serve_toss`/`line_cross` events) and §8 (`trk:ball`).
4. `docs/research/replay-source-review-2026-10-23.md` §2: the courtcam API and conventions, from a direct source review.
5. `docs/research/build-cards-flight-family.md` (BlurBall §1, TT3D §2, WASB §4, TrackNetV3 §5, methods §9: onsets, triangulation, parabola fit, P(in)) and `docs/plan/clip-library.md` (the CC BY clips).

If any of these files are missing, run `git fetch origin && git rebase origin/main`.

## 1. Facts you can rely on
- **The repository has no code.** You start your directories from scratch.
- **Machine:** Apple M5 Pro (macOS arm64). Run services **natively** in per-service `uv` venvs: flight on py3.11 with **numpy 1.26.4** and `opencv-contrib-python==4.10.0.84`; courtcam-adapter on **py3.12**. Docker on a Mac can't reach the GPU.
- **Principle (D-18): you emit measurements, not rulings.** For example: `bounce` with `pos_m`, `sigma_m`, signed distances to the lines, `p_in`, and edge-class probabilities near a table edge. The engine and rule packs (Agent 3) decide points, outs and faults.
- **BlurBall** (MIT code, `cogsys-tuebingen/blurball` @ `2f0f549`):
  - **It asserts `device == "cuda"`**, needs numpy < 2, and `torch.load` breaks on torch ≥ 2.6 without `weights_only=False`.
  - Its inference script has a BGR→RGB bug, and its duplicate-frame filter is off despite what the README says. Dedupe by `seq`.
  - Input is 3 frames at 512×288 with ImageNet normalisation. Blur half-length is in 512-wide px, so scale it by `W/512`.
  - **Its weights license is unstated** (issue #2): use them for development and evaluation only, and don't redistribute them.
  - **Use white balls.**
  - Its MPS speed on an M5 Pro is **unknown**. That's the top M1 risk, and resolving it is your first task.
- **courtcam** (MIT, standalone `https://github.com/subatomic-hamster/courtcam`, pin `b2f5ff582261ba680d7348149e5262ef43cab858`):
  - Install it **without extras** and never through Replay's workspace, because Replay's root pyproject pulls in AGPL `courtcam[yolo]`. It clashes with opencv-contrib, so keep it in its own venv.
  - `calibrate.homography(landmarks_px, template)`: RANSAC only with ≥ 6 points. `calibrate(...)`: the gate is max(5 px, 1% of the click span), with a mirrored-label fix. `camera_calibration(calib, profile)` → K, R, t, `[k1]` (needs `image_size`). `distortion.*` uses a 1-parameter division model.
  - **Templates exist for basketball (half and full, several standards), pickleball, badminton and volleyball.** There are none for table tennis, tennis or football: build them. Templates have **no zone polygons**, so derive them.
  - The origin is the centre of one baseline/end line, +x to the right sideline, +y into the court, z up.
  - **Don't redistribute** courtcam's `docs/demo.gif` (real footage).
- **Verified runtime facts:** torch 2.14.1 has macOS arm64 wheels, but whether it works with numpy 1.26 is unverified, so test it. Set `PYTORCH_ENABLE_MPS_FALLBACK=1`. AWS G/VT quota defaults to 0; a g6.xlarge (L4) is $0.805/h on demand, about $0.41–0.48/h spot.
- **CC BY clips** (`docs/plan/clip-library.md`):
  - [ping pong club match](https://www.youtube.com/watch?v=7maQFqJ3XQ0): 4K60, a tripod at the table corner, **a disputed edge ball at 8:36**.
  - [basketball half court](https://www.youtube.com/watch?v=2NxcgKW7xFM): you provide its calibration and court template; Agent 3 does the shots.
  - Later: [pickleball](https://www.youtube.com/watch?v=QhLECLlXU3c), [tennis](https://www.youtube.com/watch?v=JReOUveKesY), [badminton](https://www.youtube.com/watch?v=ShrdcaZMdS0) (24 fps, fisheye), [volleyball](https://www.youtube.com/watch?v=kVpO4ypzPYU).
  - Nobody has listened to their audio yet. **Ask the user before downloading** (only the needed segments, for example `yt-dlp --download-sections "*8:20-8:50"`). Keep footage in `data/local/` (gitignored), and record credits in `data/clips/credits.json`.
  - OpenTTGames (120 fps, labelled bounces) is CC BY-NC: evaluation only.

## 2. Scope and primary directories
`services/courtcam-adapter`, `services/flight`, `services/audio`, `tools/` (clip player, framebus probe, labellers, synthetic renderer), `evals/` (ball-call sets and labels), and the `field:` block of every `rulepacks/*.yaml`.

## 3. M1 tasks (in order; open a PR for each coherent slice)
1. **Set up.** Create your worktree (`git worktree add ../trophy-a2 -b a2/m1-ball origin/main`) and `docs/status/a2.md`.
2. **Spike first, about one day: the ping-pong tracker on this Mac.**
   - **(a) Classical baseline:** a white-ball detector (frame differencing within the table's region of interest + brightness/colour + circularity + a size prior from calibration) with a constant-acceleration Kalman filter.
   - **(b) BlurBall on MPS:** patch the device and `torch.load`, run the 3-frame window, and check that the heatmap peak lands on the ball.
   - Measure **FPS at 720p input** for both, plus BlurBall at batch 1 and 2, and detection recall on 200 labelled frames from the CC BY clip.
   - Write up the result (OPEN-3) in `docs/status/a2.md`: classical, BlurBall MPS, or BlurBall on AWS. If AWS, ask the user, and state the cost and that the G/VT quota is needed.
3. **Tools** (`tools/`, py3.11):
   - `play_clip.py`: mp4 → `frames:{cam}` exactly per interfaces §5.2, `source=file`, real-time or fast. It optionally emits `audio_onset` events from the clip's audio (the same onset method as the phone) and writes a fixture `calib:{cam}`.
   - `framebus_probe.py`.
   - `label_points.py`: a keyboard labeller for rallies (start/end, winner, rally-ending event), bounces (frame, side, in/out, edge vs. side) and basket segments for Agent 3. It writes `evals/labels/<sport>/<clip>.jsonl`.
   - `synth_table_tennis.py`: a rendered synthetic rally with known 3D ball paths and bounces, **labelled synthetic**, ≤ 5 MB, for CI and `make e2e`.
   - Until C0, use local code that follows §5.2 byte for byte; then switch to `trophy.framebus`.
4. **courtcam-adapter** (py3.12, FastAPI on :8050): `POST /calibrate` per interfaces §6.
   - Build the template from `rulepacks/<sport>.yaml` → `field.landmarks`, and use courtcam's `homography` + gate.
   - Use `camera_calibration` for K, R, t (the table is planar; add net-post landmarks in M2 for a better pose).
   - Degeneracy and focal-plausibility checks feed `warnings` and `trusted`. Return `overlay_px` (lines, edges, kitchen when relevant).
   - **Tests:** a synthetic camera → projected landmarks + noise → recovered H and pose within tolerance; mirrored order; degenerate taps.
   - Record courtcam in `docs/licenses.md`.
5. **Field templates:**
   - `rulepacks/table_tennis.yaml` → `field:` per interfaces §3 (2.74 × 1.525 m, net 0.1525 m, `edge_band_m` param, landmarks `A_left, A_right, B_right, B_left`).
   - `rulepacks/basketball.yaml` → `field:` from courtcam `basketball_half` (`three_point_arc`, `rim`, `boundary`; the variant is a param). Check the CC BY clip's court and measure or approximate a park court honestly with `measured: false`.
   - Agent 3 owns the rest of each pack.
6. **Flight service** (`services/flight`, py3.11):
   - **Read and track.** Read **every** frame in order (dedupe by `seq`), load and reload `calib:{cam}`, and run the chosen tracker.
   - **Fit the flight.** Fit a gravity parabola per flight segment in image space, lifted to the table frame with the pose. With one camera, find the bounce point by ray–plane intersection with the table at the bounce time.
   - **Time the bounce.** The nearest `audio_onset` within ±40 ms sets the time; otherwise it comes from the track minimum, marked `timing: "track"`.
   - **σ** combines fit residual, calibration reprojection, blur and timing.
   - **Edge vs. side:**
     - Within `edge_band_m` of an edge, classify by post-contact trajectory: a top-edge ball keeps an upward rebound, while a side ball drops or deflects sideways and has no table-plane bounce.
     - Combine with the bounce position relative to the edge.
     - Output `edge: {top_edge, side_face, surface}` probabilities. **Heuristic until it's calibrated on labels: say so in `p_source`.**
   - **Other events:** `contact` (ball reversal near a player's end + onset), `net`, `ball_dead`, and a `heartbeat` every 5 s.
   - **Publish** `trk:ball:{cam}` for every processed frame (the replay trail). Mark `calib_untrusted` when relevant.
   - **Tests:** the synthetic rally (bounce position error, timing, side, edge classes); schema validation of every event.
7. **Data and labels (with consent):**
   - The CC BY ping-pong clip segments (after the user OKs the download): label all rallies + bounces + the 8:36 edge ball.
   - Live: once C1 lands, record ≥ 40 rallies on the Mac stack with players' consent, plus **≥ 20 staged edge/side hits** (the ball dropped and pushed onto the edge or side; put tape marks to check ground truth).
   - Keep separate tuning and test splits, and never tune on the test split.
   - Export the recorded `ev:flight` logs to `evals/fixtures/recorded/` for Agent 3's engine replay tests.
8. **Measure and report** in `docs/status/a2.md` and (via Agent 1) `docs/progress.md`:
   - tracker FPS and the device or execution provider actually used;
   - ball recall and precision;
   - bounce position error against tape marks (cm);
   - bounce timing error with and without audio;
   - edge-rule accuracy on the staged set (n, correct, Wilson 95% CI);
   - the latency from frame to event on `ev:flight` (p50/p95).

## 4. Inputs you consume and outputs you produce
- **Consume:** `frames:{cam}` (Agent 1's gateway or your clip player), `ev:audio` (Agent 1's phone onsets), `calib:{cam}` + `ctl:calib`, `packages/py-trophy` (Agent 1, C0).
- **Produce:** `/calibrate`; `field:` templates; `ev:flight`; `trk:ball:{cam}`; the clip player and synthetic clips; labels; recorded event fixtures; FPS and accuracy reports.

## 5. Acceptance checks (your part of M1)
- [ ] The spike is reported with measured FPS and recall, and the OPEN-3 decision is recorded.
- [ ] Adapter tests pass. On a real still frame the overlay lines sit on the table edges, and degenerate taps give `trusted = false` with warnings.
- [ ] Every event validates against the schema, and `t_game_s` always comes from frames or onsets.
- [ ] **C2:** `make e2e` passes on the CC BY ping-pong fixture segment, with the correct point calls given Agent 3's pack.
- [ ] **Live:** the tracker keeps up with **≥ 25 fps** at 720p for 15 min on the chosen runtime; frame → `bounce` event p50 ≤ 300 ms.
- [ ] Edge rule: **≥ 16 of 20** staged edge/side hits classified correctly, and the 8:36 clip ball reported with its probability. Anything with p < 0.90 must reach the engine as uncertain (no inflated confidence).
- [ ] Rally scoring (shared with Agent 3): **≥ 90%** of labelled rallies correct, reported with the Wilson CI. If it isn't met, report the real number and the failure modes.
- [ ] Licenses and credits are recorded (courtcam, BlurBall weights status, CC BY clip credits).

## 6. Coordination duties
- Contract changes go only through `contracts/*` PRs (Agent 1 merges after the consumers acknowledge). Draft payload `$defs` for any new event type you need.
- **Ship `/calibrate` and the table template early.** Agent 1's calibration UI and Agent 3's packs depend on them.
- Give Agent 3 recorded `ev:flight` logs and labelled rallies as early as possible.
- Rebase on `origin/main` before every PR and at every checkpoint. Merge your own green PRs inside your directories.
- Keep the safeguards: consent for everyone filmed; footage out of git; upstream numbers labelled as upstream; heuristic confidences labelled heuristic; no downloads or cloud spend without the user's OK.

## 7. Later backlog
- **M2 serve rules:** `serve_toss` (palm-release frame → apex height in metres from the 3D pose, `angle_from_vertical_rad`, σ for both) for the 16 cm / 30° pack rules. Improve the pose with net-post landmarks.
- **M2 pickleball outs:** WASB pickleball/tennis weights through BlurBall's runners, a court template with kitchen zones, `bounce.p_in` = Φ(d/σ) (a ball on the line is in), and the `contact` events Agent 3's kitchen rule needs.
- **M2 multi-view:** 2-phone DLT triangulation with courtcam K, R, t, and parabola fits across asynchronous cameras.
- **M3:** tennis outs, badminton landing in/out (WASB live; TrackNetV3 post-game only), volleyball outs and the ball side of reach-over-net, and the PANNs audio classifier (surface sounds). Templates for tennis and football fields.

## 8. Completion report (in `docs/status/a2.md` and your final message)
1. What works, with links to the merged PRs and commits.
2. Measured numbers, each with method, data split, device, execution provider and date: FPS, recall and precision, bounce position and timing error, edge accuracy (n / correct / Wilson CI), rally accuracy, frame → event latency.
3. Data used: source, license, consent status and storage location. Confirm that nothing identifying is in git.
4. Checks run, and checks you could **not** run.
5. Deviations from the interfaces or plan, and where they're recorded.
6. Upstream code and weights used, with their license status.
7. The OPEN-3 decision and any AWS use (with the user's approval noted, or "none").
8. Open issues, risks and suggested next tasks.
