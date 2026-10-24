# courtcam adapter (owner B)

**Env:** **py3.12** · courtcam (MIT, pinned, disclosed) · port 8050

## Responsibilities
- Wraps the published **courtcam** library: `calibrate.py` (4+ landmarks, reprojection gate, mirrored-label fix), `distortion.py` (one-parameter lens model), `camera_calibration` (focal length from homography + solvePnP), `court.fit_check` (untrusted calibration → engine demotes calls), team assignment, the on-court filter, basketball `ball.py` make/miss, the X-gesture detector, the rally segmenter, sport-profile grammars and eval tools.
- Plug RF-DETR detections in through courtcam's `Detector` interface (the current permissive-license default; other backends are allowed when their terms fit the deployment).
- **Reuse and adapt Replay/courtcam code where useful.** Record incorporated sources/revisions in `docs/licenses.md` and preserve required notices; see `docs/rules-compliance.md`.
- Inventory: `docs/research/replay-repo-inventory.md`.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
