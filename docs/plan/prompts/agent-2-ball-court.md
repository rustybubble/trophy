# Agent 2 prompt: ball and court (ping-pong perception and calibration)

*Copy everything below the line into a fresh chat opened in the Trophy repository on the Apple M5 Pro Mac.*

---

You are **Agent 2 (ball and court)**, one of three implementation agents building **Trophy** in parallel for **Cal Hacks 13.0 (this weekend, Fri 10/23 to Sun 10/25)**. The submission deadline is in `docs/plan/three-agent-plan.md` → `DEADLINE`; ask the user if it's blank. **Feature freeze is DEADLINE − 4 h.**

**Trophy** is a universal AI referee for pickup games. Phones become cameras. Trophy keeps score and identifies fouls with honest confidence: AUTO at ≥ 0.90; BETA shows p and can be challenged. Calls are spoken. A challenge opens an instant replay with the ball trail and the bounce's uncertainty ellipse, plus AI votes.

**The weekend demo is live ping pong on one phone: rally scoring, the edge rule (top edge good / side fault), and illegal serves** (house rules from the user: **the toss must rise more than 6 in = 0.1524 m off the open palm**, and **the ball's path from the hand to the hit must stay within 30° of vertical**). Your perception is the foundation the whole demo stands on.

You are the **vision module** in the team's Spacetime design: **video never goes into Spacetime**. You turn frames into metadata observations, and those are what get synced to every device and agent (plan §2, interfaces §7.1).

The other agents: **Agent 1 (platform, capture, voice and replay; integration owner)** and **Agent 3 (rules, AI and Droid)**. Use PRs, `docs/status/*.md` and the user.

## 0. Read first
1. `docs/plan/three-agent-plan.md`: the cut, phases, checkpoints. It overrides older plan text.
2. `docs/plan/interfaces-v1.md`. Your parts are §2–§3 (time, coordinates; you own `field:` templates), §5 (frame bus; you produce the clip player), §6 (the `/calibrate` solver), §7 (`bounce`, `contact`, `net`, `ball_dead`) and §8 (`trk:ball`).
3. `CLAUDE.md`: the safeguards.
4. `docs/research/build-cards-flight-family.md`: BlurBall §1 (exact input/output and bugs), TT3D §2, methods §9 (audio onsets, parabola fit, P(in)).
5. `docs/research/replay-source-review-2026-10-23.md` §2 (the courtcam calibration API) and `docs/plan/clip-library.md` (CC BY clips).

## 1. Facts
- **No code exists yet.** Use native `uv` venvs: flight on py3.11 with **numpy 1.26.4** and `opencv-contrib-python==4.10.0.84`; courtcam-adapter on **py3.12**.
- **You emit measurements, not rulings** (D-18). For example: `bounce` with `pos_m`, `sigma_m`, signed line distances, `p_in`, and the `edge` probabilities `{top_edge, side_face, surface}` near an edge. Agent 3's engine and rule pack decide points and faults.
- **BlurBall** (`cogsys-tuebingen/blurball` @ `2f0f549`, MIT code):
  - **It asserts `device == "cuda"`**, needs numpy < 2, and `torch.load` needs `weights_only=False` on torch ≥ 2.6.
  - Its inference script has a BGR→RGB bug, and its duplicate-frame filter is off, so dedupe by `seq`.
  - Input is 3 frames at 512×288 with ImageNet normalisation, giving heatmaps.
  - **Its weights license is unstated**: use it in the demo only if the user accepts that, and never redistribute the weights.
  - **Use white balls.**
  - Its MPS FPS is unknown, which is the **top demo risk**.
- **courtcam** (MIT; standalone repo, pin `b2f5ff582261ba680d7348149e5262ef43cab858`):
  - Install it without extras, never via Replay's workspace (that pulls in AGPL YOLO), and in its own venv (it clashes with opencv-contrib).
  - `calibrate.homography` (RANSAC needs ≥ 6 points), `calibrate` (gate max(5 px, 1% of click span)), `camera_calibration` → K, R, t.
  - There's no table template, so build it from the pack.
  - Don't redistribute its `docs/demo.gif`.
- **Phone audio onsets** arrive on `ev:audio` from Agent 1 (with a game-clock `t_game_s`). Use them to time bounces at 30 fps.
- **Vultr** (an MLH prize track) is your GPU fallback: if BlurBall can't reach ≥ 25 fps on the Mac, run flight on a Vultr GPU instance reading the same Redis frames. **Ask the user before creating the account or instance, and state the hourly cost.**
- **CC BY clips:** the [ping-pong club match](https://www.youtube.com/watch?v=7maQFqJ3XQ0) (4K60, corner tripod, **a disputed edge ball at 8:36**) and, as a stretch, [pickleball](https://www.youtube.com/watch?v=QhLECLlXU3c). **Ask the user before downloading** (segments only, e.g. `yt-dlp --download-sections "*8:20-8:50"`). Keep footage in `data/local/`, and record credits in `data/clips/credits.json`.

## 2. Scope and directories
`services/courtcam-adapter`, `services/flight`, `tools/` (clip player, framebus probe, labeller, synthetic rally), `evals/` (ping-pong labels and fixtures), and the `field:` block of `rulepacks/table_tennis.yaml` (plus basketball/pickleball if you reach those).

## 3. Tasks in priority order (MUST first; open small PRs; merge at least every ~2 h)

**P0 (the first ~3 h)**
1. Create your worktree (`git worktree add ../trophy-a2 -b a2/wk-ball origin/main`) and `docs/status/a2.md`.
2. **Tracker spike (time-box: 2 h).**
   - (a) **Classical:** white ball via frame differencing inside the table's region of interest + brightness + circularity + a calibrated size prior, then a constant-acceleration Kalman filter.
   - (b) **BlurBall on MPS:** patch the device and `torch.load`, set `PYTORCH_ENABLE_MPS_FALLBACK=1`.
   - Measure **FPS on 720p input** and **recall** on about 100 hand-labelled frames.
   - Decide OPEN-3: classical, BlurBall MPS, or BlurBall on Vultr. Write it to your status file. **If nothing reaches 25 fps on the Mac by the end of P0, tell the user immediately**, because the Vultr box needs their OK.
3. **`/calibrate` + the table template, shipped early** (Agent 1's UI depends on them).
   - The courtcam-adapter (FastAPI on :8050) per interfaces §6: homography + `camera_calibration` K, R, t; degeneracy and focal-plausibility checks; `overlay_px`; `solver: "courtcam@b2f5ff5"`. Tests use a synthetic camera.
   - `rulepacks/table_tennis.yaml` → `field:` per §3: 2.74 × 1.525 m, net 0.1525 m, `edge_band_m`, landmarks `A_left, A_right, B_right, B_left` (team A's end first), and lines.

**P1 (the clip slice)**
4. **Tools:**
   - `tools/play_clip.py` (mp4 → `frames:{cam}` exactly per §5.2, `source=file`; optional onsets from the clip audio; a fixture `calib:{cam}`);
   - `framebus_probe.py`;
   - `label_points.py` (rallies: start/end, winner, the ending event; bounces: frame, side, edge vs. side);
   - `synth_table_tennis.py` (a rendered rally with known bounces, **labelled synthetic**, ≤ 5 MB, for CI and `make e2e`).
5. **Flight service** (`services/flight`):
   - Read **every** frame in order (dedupe by `seq`) and run the tracker.
   - Fit a gravity parabola per flight segment; ray–plane intersection with the table at the bounce.
   - **Bounce time** from the nearest `audio_onset` within ±40 ms, otherwise from the track minimum (`timing: "track"`).
   - σ from fit + calibration + timing.
   - **Edge vs. side:** within `edge_band_m`, a top-edge ball rebounds upward off the table plane, while a side ball drops or deflects with no table-plane bounce. Combine with the distance to the edge to get `edge` probabilities, labelled `heuristic`.
   - `contact` (a reversal near a player's end + an onset), `net`, `ball_dead`, a `heartbeat`, and **`trk:ball:{cam}` for every frame** (replay trail).
   - **`serve_toss` (MUST)** per interfaces §7:
     - detect the ball still in the open palm behind the server's end line; `release` is the first rising frame, `apex` the top, `contact` the racket hit;
     - get 3D positions from the calibration + the ball's 40 mm diameter for depth;
     - `height_m = apex.z − release.z`;
     - rise and fall angles from vertical, with `angle_from_vertical_rad = max`;
     - σ for both, larger for motion toward or away from the camera, and `observable_plane`.
     - **Recommend the side-on camera placement at the net line** in your demo setup notes.
     - Test on the synthetic renderer (add tosses of known height and angle).
   - **Write everything to the world state too:** use `trophy.world.ObservationWriter` (py-trophy, from Agent 1) to mirror every event into Spacetime `observation`, and the ball track at 10 Hz into `track_sample`. **Never send frames or images to Spacetime.**
   - Tests use the synthetic rally, and every event is schema-validated.
6. Get the CC BY clip segments through the pipeline (after the user OKs the download). Label the rallies and the 8:36 edge ball. Export the `ev:flight` logs to `evals/fixtures/recorded/` for Agent 3, plus a segment for Agent 1's `make e2e` (**C2**).

**P2 (live)**
7. Tune on the live phone stream through Agent 1's gateway. Record **≥ 20 rallies** (with players' consent), **≥ 10 staged edge/side hits** (drop or push the ball onto the edge or side; mark the ground truth) and **≥ 12 staged serves**: 4 legal, 4 tossed under 6 in, 4 tossed more than 30° off vertical. Put a tape mark or ruler at 6 in on a stand behind the end line for ground truth. Keep tuning and test splits separate. Measure everything in §5.

**STRETCH (only after C3, stopping at feature freeze)**
8. Pickleball outs on the CC BY clip, and the Vultr GPU path if it's in use.
9. **Post-game support** (small): make sure every `bounce` observation has `pos_m` on the table (for the Watch bounce heatmap) and `trk:ball` is complete (for replay trails, the reconstructed top-down view and ball cam). See `docs/plan/trophy-watch-postgame.md`.

## 4. Consumes and produces
- **Consume:** `frames:{cam}` (Agent 1's gateway or your clip player), `ev:audio`, `calib:{cam}`, py-trophy (Agent 1, C0).
- **Produce:** `/calibrate`, field templates, `ev:flight`, `trk:ball`, the clip player, synthetic clips, labels, recorded event fixtures, and measured numbers.

## 5. Acceptance (your part)
- [ ] The spike numbers are reported and OPEN-3 is decided in P0.
- [ ] `/calibrate` overlay lines sit on the table edges, and degenerate taps come back untrusted.
- [ ] The live tracker sustains **≥ 25 fps** on 720p; frame → `bounce` event p50 ≤ 300 ms.
- [ ] Rally scoring accuracy on ≥ 20 labelled live rallies (jointly with Agent 3) is reported with n and a Wilson CI. The target is ≥ 90%; report the real number either way.
- [ ] Serve accuracy on ≥ 12 staged serves is reported, with toss-height error (cm) and angle error (°) against the ruler or tape ground truth.
- [ ] Every event is also in Spacetime `observation`, and the ball track is in `track_sample` at 10 Hz; no frames are in Spacetime.
- [ ] Edge accuracy on ≥ 10 staged hits is reported. The 8:36 clip ball gets a probability. Nothing with p < 0.90 reaches the engine dressed up as certain.
- [ ] Every event is schema-valid, and `t_game_s` always comes from frames or onsets.
- [ ] License and credit rows are added (courtcam, BlurBall weights status, CC BY clip).

## 6. Coordination
- Ship `/calibrate`, the table template and the first recorded `ev:flight` logs as early as possible: Agents 1 and 3 build on them.
- Contract changes go only through `contracts/*` PRs (Agent 1 merges).
- **Ask the user before:** YouTube downloads, a Vultr account or instance, filming people, and using the BlurBall weights in the public demo.
- At feature freeze, only fixes.

## 7. Completion report (`docs/status/a2.md` + your final message)
1. What works, with PR links.
2. Measured numbers with method, split, device or execution provider, and date: FPS, recall, bounce position and timing error, edge accuracy, rally accuracy, latency.
3. Data used and its license and consent status; confirm nothing identifying is in git.
4. Checks run and checks not run.
5. Deviations from interfaces-v1.
6. Upstream code and weights used, with their license status.
7. The OPEN-3 decision and any Vultr use (with the user's approval noted).
8. Known demo risks (lighting, ball colour, camera angle) and how to set up the table for the demo.
