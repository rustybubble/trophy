# Prompt 2 — unlabeled ball detection and calibrated 3D trajectories

Implement recorded two-camera ball reconstruction in **`/Users/mudu/Developer/trophy`**, consuming the import/alignment manifest from the previous task. If that contract is not present, inspect current work and define the smallest compatible producer/consumer contract with Agent 1. Keep the existing live Flight path functional; offline processing must not drop frames through the live newest-frame policy.

Read `AGENTS.md`, `CLAUDE.md`, current contract schemas, `docs/plan/interfaces-v1.md`, `docs/research/build-cards-flight-family.md`, and `docs/research/ball-tracking-calibration-multi-view.md`. Agent 2 owns Flight and court calibration. Reuse these research sources:

- `/Users/mudu/Developer/calhacks/trophy/model.py` and `trophy/pipeline.py`
- `/Users/mudu/Developer/calhacks/trophy/replay/multiview.py`
- `/Users/mudu/Developer/calhacks/scripts/build_multiview.py`
- `/Users/mudu/Developer/calhacks/scripts/prepare_user_multiview.py` — research harness only; contains clip-specific assumptions
- `/Users/mudu/Developer/calhacks/tests/test_multiview.py`, `MULTIVIEW.md`, `VALIDATION.md`, `HMR2_REPLAY.md`

Requirements:

1. Run pretrained BlurBall without requiring annotations or training. Preserve verified RGB preprocessing, consecutive three-frame context, source-frame identity, boundary handling, null detections and explicit device reporting. Keep optional `max-channel-gray` preprocessing explicit; the orange-ball experiment does not establish general accuracy. Do not treat a heatmap peak as a calibrated probability. Adapt to the Flight environment instead of copying the prototype's dependency lock or top-level `trophy` package over `packages/py-trophy`.
2. Obtain full camera geometry through current calibration APIs, with an assisted table-landmark workflow when automatic evidence is insufficient. A plane homography alone cannot recover an airborne ball. Four tapped corners fitting exactly do not establish independent accuracy. Respect the calibration's actual distortion model: courtcam's division coefficient is not interchangeable with OpenCV Brown distortion. Retain untrusted calibration flags and engine confidence gates.
3. Triangulate time-aligned observations with cheirality, ray-angle/conditioning, reprojection and plausible-volume checks. Interpolate only short, supported intervals; preserve missing/rejected samples and reason codes. Export timestamps, per-view pixels, acceptance/residuals and calibration provenance. Do not invent ballistic trajectories to fill gaps.
4. Refine the coarse synchronization using visual consistency only when enough credible correspondences exist. Search around the imported estimate, detect ambiguity, and report the change and support. The prototype's narrow search is not a general alignment solution. Use held-out correspondences for diagnostics when geometry/timing are fitted from ball data; report all-pair errors and rejection coverage as well as accepted-sample residuals. Detect or invalidate camera motion instead of assuming a static camera forever.
5. Convert coordinates once into the rule pack's field frame. Current table tennis uses tabletop-centre origin, +x toward end B, +y left facing A→B, z up, metres. Verify the current pack/schema. The prototype uses different raw axes; do not copy its viewer transform blindly. Send perception measurements through existing writers; scoring remains in the engine.

Acceptance: test triangulation on known synthetic cameras, axis/scale conversion, mismatched timing, near-parallel rays, behind-camera points, missing detections and excessive gaps. Process the supplied two recordings over a reproducible short interval and export a source overlay plus ball-only replay artifact. Report coverage and diagnostics separately from accuracy; do not claim centimeter accuracy on user footage without independent ground truth. Record model/source revisions, checksum and separate code/weight license status in repo docs. Leave a documented CLI/service entry point and manifest for the viewer and body worker.
