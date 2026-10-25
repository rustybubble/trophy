# Implement full-clip 3D reconstruction and demo-video exports in Trophy

Work in **`/Users/mudu/Developer/trophy`**. Implement and run an end-to-end recorded-video reconstruction pipeline using the tested prototype in **`/Users/mudu/Developer/calhacks`**. The goal is **complete video clips rendered as 3D players plus the tracked 3D ball, with exports we can use in our Trophy demo video**. The existing 2.9-second reconstruction proves the components run; it is not the finished deliverable. Continue through full-clip processing, rendering and inspection, rather than stopping after scaffolding or another short successful sample.

## Inputs and repo integration

Use these actual recordings:

```text
/Users/mudu/Developer/trophy/data/ttClips/Adobe Express - IMG_4342.mp4
/Users/mudu/Developer/trophy/data/ttClips/IMG_2865 (1).mov
```

Probe the originals for exact duration, presentation timestamps, display rotation, frame rate and audio. They are approximately 108 and 113 seconds, both 4K/60 fps. Reconstruct **their entire synchronized common interval**, retaining original source-time mappings. Render a continuous timeline including dead time and unsupported observations; do not silently select only the easiest rally, truncate to the original 8–11 second test, or concatenate a short sequence repeatedly. Preserve and expose any non-overlapping source tails. Those tails can remain source-video-only, or use explicitly labelled monocular body estimates if implemented; they must not be described as measured two-camera ball reconstruction.

Read `AGENTS.md`, `CLAUDE.md`, current `packages/contracts/` schemas, `docs/plan/interfaces-v1.md`, `docs/plan/trophy-watch-postgame.md`, and relevant implementation/status docs. Inspect your current branch and preserve existing work. Adapt to current gateway, recorder, Flight, players and React/TypeScript replay conventions. Treat old planning text as context; current generated contracts and source win. Shared schema changes follow the existing contracts process. Do routine implementation and verification autonomously within the authorized local scope.

## Reuse the working implementation

Read `/Users/mudu/Developer/calhacks/HMR2_REPLAY.md` first. Useful source files, relative to that prototype root:

```text
trophy/model.py
trophy/pipeline.py
trophy/replay/multiview.py
trophy/replay/hmr2.py
scripts/probe_audio_sync.py
scripts/build_multiview.py
scripts/extract_poses.py
scripts/run_hmr2.py
scripts/fit_hmr2_multiview.py
scripts/render_hmr2_replay.py
scripts/prepare_user_multiview.py
requirements-hmr2.in
web/hmr2/viewer.js
tests/test_multiview.py
tests/test_audio_sync_probe.py
tests/test_hmr2_reconstruction.py
```

The executed artifacts are in `/Users/mudu/Developer/calhacks/artifacts/user-two-camera/reconstruction/`. The preparation script and calibration config contain clip-specific assumptions and crop boxes; generalize them instead of shipping them as automatic calibration/tracking. Trophy already has a shared Python package named `trophy`; port into an appropriate service/module without replacing or shadowing `packages/py-trophy`.

The official HMR2 checkpoint is already downloaded:

```text
/Users/mudu/Developer/calhacks/weights/hmr2-assets/logs/train/multiruns/hmr2/0/checkpoints/epoch=35-step=1000000.ckpt
SHA256: c9ea09c834161468638c9de7a782c614e300c622709bf52967274c543ec72fcf
```

The tested adapter uses the SMPL buffers embedded in this checkpoint with `smplx.lbs`; a separate SMPL download was unnecessary. Use real official HMR2 inference and mesh surfaces. Preserve source notices and record separate code/weights/body-asset provenance and terms. Isolate the worker dependencies from Flight/courtcam/shared APIs. Reuse the model across batches, explicitly select and report actual MPS/CPU execution, and avoid silent device fallback.

## Build the full pipeline

1. **Two-video import and synchronization.** Integrate selection/upload and local asset registration with Trophy. Store originals and derived assets in ignored recording storage. Use actual media timestamps, including VFR inputs. Estimate coarse audio alignment over the full available overlap, reject weak/ambiguous/unrelated matches, and provide synchronized preview with manual correction. Refine using credible visual correspondences. Measure windowed offsets throughout the clips to detect drift; apply drift only when supported. Store one documented media-time→game-time mapping per camera. Do not hardcode the prototype's approximately 80 ms offset or replace the live gateway's clock fit.

2. **Calibrated ball reconstruction without labels.** Run the existing pretrained BlurBall model across the full interval with its correct RGB/consecutive-frame preprocessing and source-frame identity. Labels are not required for inference. Make the tested orange-ball preprocessing an explicit option. Obtain full camera geometry with inspected/assisted table landmarks as needed; a table homography alone cannot recover airborne ball height. Respect the actual distortion model and calibration trust status. Triangulate with timing, reprojection, cheirality, conditioning and physical plausibility checks. Keep missing/rejected samples null with reason codes. Never fill long gaps with an invented physics trajectory. Detect camera motion over the full recording and update, segment or invalidate calibration rather than reusing the first-frame camera pose indiscriminately.

3. **Human tracking and HMR2 over the entire interval.** Replace fixed crops with persistent person tracks and explicit cross-camera player mapping. Allow a small initial confirmation/correction step when identity is ambiguous. Retain player IDs across occlusion, re-entry and chunk boundaries; spectators must not silently become a player. Run actual HMR2 inference and two-view body fitting with a consistent per-player shape, shared field-frame root/orientation, visibility weighting and temporal constraints. The prototype used controlled identities and did not validate full PHALP or automatic cross-camera re-identification. Suppress unsupported body estimates or mark them unavailable instead of freezing a stale body indefinitely. Keep tabletop z=0 distinct from the floor below it.

4. **Long-clip execution.** Use configurable chunks with context overlap for detector windows, body fitting and temporal continuity. Process context but assign each output timestamp to exactly one chunk; reconcile identities, shape and rotations so joins do not pop. Retain trustworthy timing/identity/calibration state between chunks. Bound memory: do not load both full 4K recordings plus every float32 mesh into RAM. Sample human inference at a practical documented rate and interpolate only valid supported display intervals. Preserve the full duration; reducing inference rate must not shorten playback. Save resumable stage/chunk checkpoints keyed by input, model, alignment, calibration and settings. A restart must reuse compatible work and invalidate stale outputs. Surface stage progress, errors and incomplete ranges, and mark completion only after final artifacts are verified.

5. **Shared artifacts and replay UI.** Define a versioned job/scene manifest in current repo conventions with source mappings, overlap, IDs, calibration, asset references, validity masks and diagnostics. Store video/meshes as local artifacts behind existing scoped access; Spacetime holds metadata, not large arrays. Use the rule pack's metre, right-handed z-up field frame, with one explicit renderer conversion. Integrate a replay entry point with both source videos and the actual reconstructed meshes/ball: play/pause, seek across the full timeline, frame step, 0.25×/0.5×/1×, orbit, overhead and calibrated source-camera views. Load mesh chunks on demand. Preserve synchronization after buffering/seeking and render missing ball samples as missing. Use a 0.02 m ball radius. Keep source playback usable if reconstruction fails.

6. **Render assets for the demo video.** Export full-duration H.264 MP4s at 1920×1080/30 fps: a stable 3D presentation view, a synchronized source/3D comparison layout, and a source-overlay diagnostic view. Use a clean consistent table/player palette, smooth deliberate camera movement, readable minimal labels and a small “Estimated 3D reconstruction” badge. Avoid per-chunk camera resets, flicker and sudden identity/shape changes. Include source/game-time metadata and encode with broadly playable pixel format plus fast-start metadata. Make camera paths, output resolution, FPS and selected range configurable. After the full renders exist, export 2–3 particularly clear 10–20 second excerpts for editing when the footage supports them, and record their time ranges. Excerpts supplement the full exports. Do not delay these outputs for optional heatmaps or scoring features.

## Verification and completion

First use a short smoke run to catch model/geometry failures, then run the complete common interval on these recordings. Process locally on available hardware; paid cloud resources require separate approval. Keep perception/reconstruction separate from engine scoring.

Test the meaningful failure cases: timestamp offset sign/drift, unsupported overlap, rejected triangulation, axis/scale conversion, missing observations, identity continuity, chunk boundary continuity, restart/cache invalidation and seeking between asset chunks. Verify model/body buffer parity where applicable. Run the relevant repo checks and a browser smoke test.

Use ffprobe or equivalent to verify exported duration, frame count, resolution and decodability. The 1× full exports must match the computed common interval within one output frame. Verify timeline accounting has no duplicate or dropped output timestamps, including chunk joins. Inspect the beginning, middle, end and every chunk join with source overlays; publish a contact sheet and coverage/error summaries by interval. Report all-frame coverage and failures, not only low residuals from accepted samples. Separate successful video generation from reconstruction validity: a rendered empty interval is not a successfully reconstructed interval.

Do not claim verified centimeter-level accuracy on these videos. The prototype's 5.2 px body residual is agreement with model-generated 2D landmarks, not independent 3D ground truth. HMR2 does not recover the ball, racket, spin or true contact physics. Keep unsupported outputs explicit while making the best supported reconstruction visually useful.

Finish with concrete local links to the full MP4s, selected excerpts, interactive Trophy replay, manifest and diagnostics; give a reproducible command, measured processed duration, valid body/ball coverage, runtime, actual device, tests and limitations. Update relevant repo docs/status. **The task is complete when full-interval exports have actually been generated and inspected, not merely when the code accepts a longer duration argument.**
