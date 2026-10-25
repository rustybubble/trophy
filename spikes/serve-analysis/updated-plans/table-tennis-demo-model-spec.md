# Trophy table tennis: model stack and demo specification

This is a build recommendation for the recorded, two-phone table tennis demo. Read alongside `agent-2-ball-court-updated-prompt.md` and the new repo's current interfaces and ownership plan. It specifies the intended experience and implementation choices; it does not report new benchmark results or claim the user's footage has been inspected.

## 1. Lock the first-demo architecture

Use three pretrained perception bundles: **BlurBall**, **MediaPipe Pose Landmarker Full**, and **MediaPipe Hand Landmarker Full**. Each MediaPipe bundle contains a detector and a landmark model; these are three bundles, not exactly three neural networks. Use existing local assets and adapters where available. Benchmark the classical ball-tracker baseline as required by OPEN-3, but use BlurBall as the initial accuracy reference. Public use of its weights still requires the user's approval.

The remaining components are timestamp processing, calibrated geometry, event estimation, a versioned deterministic referee engine, a rigged 3D asset, and a renderer. The first demo does not require a new learned referee model, a body-shape recovery model, an embedding service, or a separately trained table/paddle detector. This is a scoped engineering choice, not a claim that all rules become observable with this stack.

Process the original recordings ahead of playback for the dependable recorded demo. Preserve native timestamps, resolution, and audio for measurement. Show an explicit recorded/preprocessed label. Keep the 25 FPS tracking experiment as a separately reported capability; smooth browser playback is not evidence of real-time analysis.

## 2. Exact perception choices

### A. Ball: official BlurBall checkpoint

- Model: the official HRNet-based, multi-frame BlurBall network and the existing `blurball_best` checkpoint. Source: [official repository](https://github.com/cogsys-tuebingen/blurball).
- Reuse the pinned source and adapter in `/Users/mudu/Developer/calhacks/PROVENANCE.md`. Existing checkpoint SHA-256: `3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`.
- Existing adapter: three chronological RGB frames, 512×288 model input, three heatmaps, inverse mapping to source pixels. Run independently on each view. Preserve real temporal windows and source-frame identity.
- Output: observed 2D ball position or missing status, timestamp, detector score, blur attributes, and provenance. A heatmap peak is not a calibrated probability of a correct call.
- Purpose: the shared input to ball trajectory, bounce candidates, rally events, serve-toss measurements, and edge evidence. The model itself does not identify a legal bounce or award a point.
- Runtime target: PyTorch MPS, with separately measured CPU decode/preprocess and postprocess. Benchmark color adaptation against original RGB on the actual ball color; the prior grayscale adaptation is experimental.
- Compare against a CPU classical baseline using background/motion segmentation, ball-color candidates, size constraints, and temporal association. Select using end-to-end paired-camera throughput AND measured recall/false positives, including slow tosses; speed alone is insufficient.

Do not add multiple competing ball networks to the default pipeline. Reconsider alternatives only if this measured spike fails. Document exact versions and outcomes if an alternative is evaluated.

### B. Body: MediaPipe Pose Landmarker Full, float16 v1

- Bundle: `pose_landmarker_full.task`, already used by the old project. Official asset: `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task`.
- [Official documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) describes 33 estimated pose landmarks and Lite/Full/Heavy options. Choose Full initially to reuse the validated integration.
- For this fixed two-player scene, initialize player identity/crops during calibration and track them within each camera. Run the bundle per player crop where that is more reliable than multi-person inference. Do not confuse crop IDs or left/right handedness with player identity.
- Use image landmarks with calibrated cross-view geometry to estimate metric positions. Monocular model world coordinates are inferred local estimates, not automatic table-coordinate measurements.
- Purpose: drive the two animated bodies, locate wrist regions for hand crops, and provide supplementary player context. Pose estimates do not establish paddle impact or an open palm.
- Start with CPU execution in the existing isolated MediaPipe environment. For offline avatar motion, evaluate a reduced pose cadence such as 15 FPS and interpolate presentation only; retain original-rate ball measurement. These are scheduling choices to benchmark, not promised performance.

### C. Hands: MediaPipe Hand Landmarker Full, float16 v1

- Bundle: `hand_landmarker.task`, using the official palm detector plus 21-landmark hand model. Source: [official documentation and bundle link](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker). Pin the resolved asset URL and SHA-256 before use.
- Run on original-resolution wrist/hand crops around candidate serves, separately in both cameras. Use a padded search region and allow detection recovery if the wrist estimate is wrong. Preserve crop-to-source transforms.
- Output: image hand landmarks, handedness, hand association, detection status, and quality information. Reconstruct visible correspondences through the calibrated cameras where possible.
- Purpose: improve the estimated free-hand/palm location at release, distinguish a hand region from a wrist joint, and support hand detail in the evidence view.
- A hand skeleton does not prove the ball was resting on an open stationary palm. Establish release from a temporal sequence with visible ball/hand separation and uncertainty; retain a release-time interval if the exact frame is ambiguous. Do not infer metric release height solely from monocular hand world coordinates.
- Validate hand coverage and release-height error on actual serves before enabling height-based automatic outcomes. If the palm/ball is too small or occluded, use the video close-up and report insufficient evidence. No model can recover observed detail that the recording does not contain.

## 3. Required components that are not learned models

| Component | Chosen implementation | Output / role |
|---|---|---|
| Camera calibration | OpenCV camera intrinsics/distortion, per-camera extrinsics, manual table/corner confirmation, metric table template | Table coordinate system and validation residuals |
| Two-phone sync | Source presentation timestamps, shared-audio delay estimate when available, visual/epipolar refinement, drift checks, manual adjustment | Time mapping between each source and the session |
| 3D ball reconstruction | OpenCV triangulation plus robust reprojection fitting and explicit rejection | Metric positions with missing intervals and estimated uncertainty |
| Bounce/contact candidates | Piecewise trajectory fits and changes in direction near surfaces; audio transients as corroboration | Timestamp intervals, candidate type, surface/side, evidence quality |
| Rally segmentation | Event/state estimator using observed sequence and terminal-event evidence | Candidate start/end times and unresolved states |
| Referee | Deterministic state machine driven by the pinned official rule profile | Point/let/fault, score/service state, reasons, rule references |
| Rule retrieval | Indexed local rule IDs and text; simple text search is sufficient initially | Source passages for explanation and rule questions |
| Replay | Three.js, source-video clocks, event timeline, source crops, camera controls | Interactive evidence inspection |
| Spoken calls | Existing approved project speech integration; pre-render/cache fixed phrases, or local OS speech for development | A short spoken decision synchronized to the decision event |

[OpenCV calibration/reconstruction documentation](https://docs.opencv.org/4.11.0/d9/d0c/group__calib3d.html) describes the camera geometry APIs. A table-plane homography alone cannot recover a toss's height above the table. Four coplanar table corners also do not independently verify unknown intrinsics/distortion. Obtain or estimate intrinsics with explicit assumptions, validate reprojections, and report residual ambiguity. Recalibrate if the camera moves or zoom changes.

Do not smooth a trajectory across a bounce or paddle contact and then use that smoothed path as contact evidence. Audio transients can come from paddles, table, floor, or other sounds; audio alone does not assign event type or player. Paddle-contact time remains a candidate unless supported by the source views and trajectory. Racket illustrations cannot supply that evidence.

The rules-owning agent maintains authoritative referee state. Agent 2 emits observations and candidate boundaries only. Use stable observation/rally IDs, revisions, and idempotent consumption under the shared interfaces. Mirror measurement events to Spacetime; video remains outside it.

No LLM is required to issue the core calls. If the project already has an approved language-model integration, it can paraphrase the engine's structured decision and cite rule passages. It must not choose the winner from raw footage or invent missing facts. Do not provision a paid model or voice API without the existing required authorization.

## 4. The screenshot-style 3D bodies

The reference requires a **rigged character asset**, not a new AI model. Use the existing procedural skinned body initially, with a clean UV-grid material or an appropriate rigged mesh to improve the silhouette. Render through [Three.js SkinnedMesh](https://threejs.org/docs/pages/SkinnedMesh.html). Preserve asset/license provenance for any replacement.

Visual specification:

- Two continuous humanoid surfaces with readable head, shoulders, torso, limbs, hands, and feet; no disconnected capsule limbs.
- Dark shaded surfaces, restrained cyan surface-grid lines, dark floor grid, and a correctly proportioned table/net.
- Bodies crouch, lean, step, and swing in time with the source footage. Smooth retargeting should avoid obvious limb-length changes, foot sliding, mesh tearing, or independent floating grid lines.
- Hand detail uses validated hand observations where available; otherwise display an estimated neutral hand pose. Show the paddle near the estimated racket hand and disclose estimated orientation.
- Distinct player accents match the scoreboard. The ball and its local trail remain legible, with optional player-opacity reduction during a close-up.
- Orbit, side-camera, diagonal-camera, overhead, serve-close-up, and edge-close-up presets. No generative in-between images or invented ball frames.

Higher mesh detail does not improve measurement accuracy. Maintain a physically scaled ball for contact geometry and keep any enlarged display marker separate. Body-surface fitting, personalized anatomy, SMPL/GVHMR, face reconstruction, and measured racket orientation are outside the first-demo dependency list. They can be reconsidered if validated avatar quality is inadequate, rather than installed speculatively.

## 5. What the audience should see

Target a roughly 2–3 minute walkthrough with six selectable beats. Use real recorded evidence wherever validated; synthetic examples remain clearly labeled and selectable separately.

### Beat 1: establish this is our game, 10–15 seconds

Open a session with player names, initial score/server, the user's two source views, and an explicit recorded label. Show both phones on one timeline. A compact setup panel reports calibration and synchronization status with a manual fine-adjustment control. Do not display a fabricated exact-sync badge. The presenter says that two ordinary phones recorded the same rally.

### Beat 2: Trophy follows and scores a rally, 20–30 seconds

Play an uninterrupted rally at normal speed. The larger source view shows a subtle ball marker/trail; the second view remains visible. The scoreboard stays readable. Candidate events appear as small timeline ticks rather than a stream of technical messages.

At a verified terminal event, the rules engine emits one decision. The UI highlights the winner, increments the score exactly once, updates service state as applicable, and plays a short call such as “Point to Alex.” A reason is available on the decision card. If the end is not observable, show “Review needed” and leave the outcome pending under the agreed referee policy.

Each point becomes a selectable timeline segment with session start/end times, result status, and evidence bookmarks. Clicking it replays the point with a short pre/post-roll. Preserve the difference between video clip boundaries and candidate in-play boundaries.

### Beat 3: challenge and inspect an edge call, 25–35 seconds

Select Challenge on a point with suitable footage. Both cameras seek to the same session time and play at 0.25×. An evidence bookmark freezes the decisive interval. A source crop shows the contact region; an adjacent 3D inset shows the measured ball path, table top, and vertical side at a useful scale. Show uncertainty when quantified and the relevant official rule reference.

The interface explains whether the evidence supports the original outcome, supports a correction, or remains inconclusive. A challenge does not automatically overturn a call. If corrected, apply an audited score revision exactly once. A source crop enlarges existing pixels; it does not manufacture detail.

Edge assessment must consider ball size, surface geometry, localization error, timing uncertainty, and contact evidence. A centroid inside/outside the boundary alone is insufficient. If plausible contact regions overlap the top and side, remain inconclusive. Choose a real demonstrable event after inspecting the footage; do not promise that an arbitrarily close edge can be resolved.

### Beat 4: explain a short serve toss, 25–35 seconds

Select a serve. Source views and a hand crop remain visible. Mark the release-time interval and apex on the timeline. The 3D close-up shows a vertical ruler anchored to estimated release height, the ball path, and the applicable 0.16 m reference. Display the measured rise and uncertainty alongside the source frame evidence.

For illustration, a **synthetic** toss measured at 0.12 m with a validated interval of 0.11–0.13 m is clearly below the 0.16 m reference. A real demo may use this explanation only when its own measurements establish the result. A range crossing the threshold must not be presented as a certain fault. The rules engine determines the consequence and the UI speaks the decision with its rule citation.

### Beat 5: explain toss direction, 15–25 seconds

Show a separate serve with the upward-toss segment highlighted, a vertical reference, and an angle overlay. Display the estimator definition and the selected official/TTR rule profile in the evidence details. Keep the falling/hit segment separate. Use one clear supported example on either side of the configured criterion in testing; a synthetic example can demonstrate the overlay if real evidence is inadequate.

Do not declare full service legality solely from passing height and angle. Palm, visibility, position, sequence, and other applicable requirements may remain unverified. Do not label an unverified angular estimator as the official technical measurement convention.

### Beat 6: show trust and control, 10–20 seconds

Open one obscured event. Trophy says which observation is missing and offers the agreed player-resolution control. A player's resolution is labeled as a manual decision, retained in history, and updates the score through the same authoritative state path. Finish by orbiting the wireframe replay of a completed point, then switching back to the synchronized real views at that same instant.

## 6. One coherent screen

Use a persistent top score/server strip. The main area contains the larger selected camera or 3D view; beside it, keep the other evidence views accessible and time-aligned. A decision card contains outcome, concise reason, rule reference, evidence status, and Challenge/Review controls. The bottom timeline shows point segments and serve/contact/review bookmarks, plus shared play/pause, seek, frame inspection, and speed controls.

Keep detector diagnostics and calibration residuals in an expandable technical panel. Do not put uncalibrated “97% confident” labels on calls. Frame inspection should expose each source's actual selected frame timestamp so a shared clock does not imply simultaneous exposures.

## 7. Validation and release gates

- **Models:** pin checkpoints, hashes, adapters, runtime/delegates, and licenses. Reuse compatible isolated environments; do not assume MediaPipe executes on MPS because BlurBall does.
- **Tracker spike:** report per-view and paired-camera sustained throughput at 720p, source FPS, model input size, recall definition, manually labeled sample count, false positives, and performance around tosses/bounces/occlusion. Existing ~23.4 ms per-view model timing implies roughly 46.8 ms for sequential two-view inference before overhead; this is a bottleneck estimate, not a fresh 720p benchmark or proof of 25 paired FPS. Notify the user if the actual spike fails its agreed gate.
- **Sync/calibration:** verify independent moments throughout each recording and source reprojections. Report effective alignment uncertainty; minimize error without implying hardware synchronization.
- **Serving:** separately validate ball detection during tosses, release interval, hand reconstruction, height and angle estimates. Include synthetic threshold boundaries and real held-out annotated examples. Do not select arbitrary confidence bands to make a verdict certain.
- **Scoring:** manually review demonstration outcomes and evidence; test lets, service changes, repeated observations, seek/replay, corrections, and incomplete recordings. Human labels are evaluation data, not silently injected detector outputs.
- **3D:** verify source-time agreement, continuous meshes, correct handedness/identity, stable grids and limbs, missing-data behavior, and unmodified raw ball coordinates. Record visual limitations.
- **Coverage:** label each demo event as real validated evidence, synthetic fixture, manually resolved, or unsupported. Understand the full playing rules; publish which triggers the current sensors and implementation can actually evaluate.

Deliver this specification with the kickoff prompt and visual reference. In the new repo, incorporate it under `docs/plan/` and keep the authoritative contracts and agent ownership explicit.
