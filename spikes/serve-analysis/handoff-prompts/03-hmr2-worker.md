# Prompt 3 — integrate the tested 4D Humans reconstruction worker

Add an **offline human reconstruction worker** to **`/Users/mudu/Developer/trophy`** that combines official HMR2 estimates from two calibrated, synchronized videos with the independently reconstructed ball. Consume the shared import/reconstruction manifest and field-frame geometry. Keep heavy fitting outside the live scoring and instant challenge paths.

Read `AGENTS.md`, `CLAUDE.md`, current contracts, the players-service implementation and `/Users/mudu/Developer/calhacks/HMR2_REPLAY.md`. Coordinate with the players/perception owner and Agent 1 for shared artifact contracts. Reference:

- `/Users/mudu/Developer/calhacks/trophy/replay/hmr2.py`
- `/Users/mudu/Developer/calhacks/scripts/run_hmr2.py`
- `/Users/mudu/Developer/calhacks/scripts/extract_poses.py`
- `/Users/mudu/Developer/calhacks/scripts/fit_hmr2_multiview.py`
- `/Users/mudu/Developer/calhacks/scripts/render_hmr2_replay.py`
- `/Users/mudu/Developer/calhacks/requirements-hmr2.in`
- `/Users/mudu/Developer/calhacks/tests/test_hmr2_reconstruction.py`
- `/Users/mudu/Developer/calhacks/artifacts/user-two-camera/reconstruction/` for the executed output format

Requirements:

1. Use the real official HMR2 backbone/head and SMPL surfaces. The pinned upstream source is `vendor/4D-Humans` at `efe18deff163b29dff87ddbd575fa29b716a356c` in the prototype. Reuse the cached checkpoint at `/Users/mudu/Developer/calhacks/weights/hmr2-assets/logs/train/multiruns/hmr2/0/checkpoints/epoch=35-step=1000000.ckpt`, verifying SHA256 `c9ea09c834161468638c9de7a782c614e300c622709bf52967274c543ec72fcf`. The tested adapter obtains body buffers from this official checkpoint and uses `smplx.lbs`; a separate SMPL download was not needed. Preserve notices and verify/document code, weights and body-asset terms separately.
2. Isolate dependencies in a worker environment. Preserve Trophy's shared Python API and existing Flight/courtcam environments; do not copy the prototype's `trophy` package wholesale. Make device selection explicit, report actual execution, and fail clearly when a requested device is unavailable. Do not silently enable MPS→CPU fallback. Support bounded clip ranges, reusable model loading and resumable per-stage outputs keyed by inputs/config/model/calibration.
3. Parameterize source selection, frame sampling, camera geometry and fitting. The research scripts hardcode user-demo paths and controlled player crops: remove those assumptions. Provide player-track selection/confirmation and stable cross-view identity mapping. The experiment did not validate automatic cross-camera identity or run the complete PHALP/ViTDet pipeline. Handle occluded/missing people without silently swapping identities or duplicating bodies.
4. Initialize one consistent body shape per player from actual HMR2 outputs, transform camera orientations into the shared field frame, and fit against both views with temporal/visibility constraints. Separate tabletop z=0 from the floor below it. Do not use a tabletop homography to position feet. Treat image landmarks, hidden joints, floor contact and anatomy as estimates. Keep the ball pipeline independent of body fitting.
5. Export a versioned artifact containing timestamps, stable player IDs, faces and mesh sequence or a documented equivalent, field-frame transform, validity masks, source/calibration/model provenance, and residual/coverage diagnostics. Store meshes in local artifact storage, not Spacetime rows. Add source-overlay output for inspection. Any interpolation of body poses is display interpolation, not new measured motion.

Acceptance: retain strict model loading and parity checks against the same official body buffers, test coordinate transforms and identity/missing-data handling, and run a short real two-camera reconstruction. Confirm source overlays and mesh/ball timestamps agree. Report image fitting residuals as image agreement against model landmarks, not 3D accuracy. The prototype's 87-frame output is a reproducibility baseline; full-video support requires chunking with stable identities and boundary continuity. Return a working invocation, artifacts, measured runtime/device use and remaining limitations. Do not synthesize racket contact, spin or scoring claims.
