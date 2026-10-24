# Two-phone recorded demo

> **Current status: failed demo acceptance (2026-10-24).** Ball detections can jump to unrelated objects across the screen; 3D rendering is below the requested quality and has no real ball trajectory; the point list is an activity heuristic and does not reliably detect/score real points. The instructions below describe how to inspect the failing prototype, not a validated demo. Read the [failure report](status/tt-demo-failure-report-2026-10-24.md).


Run `make tt-demo`, then open **http://127.0.0.1:8765/**. Playback needs Python 3.11+ and the prepared local files under `data/local/tt-demo`; it has no paid API or database dependency. The current demo is local/private. BlurBall checkpoint public-demo use remains unapproved; no source media, model weights, or identifying derived files are versioned.

The source recordings are `data/ttClips/Adobe Express - IMG_4342.mp4` (side, 107.6167 s) and `IMG_2865 (1).mov` (diagonal, 113.0167 s). Both are 3840×2160, 60 FPS, H.264 with audio. Every decoded ball frame retains its native PTS/time base and source sequence. Preview files are 1280×720 H.264 with audio; paused source crops load the original 4K recording. The manifest pins both original checksums and the local-use permission.

## Walkthrough

1. Select **Your two recordings**, then choose the second candidate interval (the first long serve/rally, around 6.45–13.75 s). Play both angles together. Use 0.25×, frame steps and the shared seek bar.
2. Select **Challenge / review** or **Go to evidence**. Click either source view to position its crop. A paused crop uses the original 4K pixels; enlargement does not add detail. Evidence times are candidate bookmarks, not independently verified contact times.
3. Inspect the estimated cyan mesh players. Orbit/zoom or select a recording-camera, overhead, serve or edge preset. Both continuous bodies follow observed body poses. Hidden people and missing ball positions remain hidden. These avatars and wrist-attached paddles cannot supply rule evidence.
4. Resolve a real interval with **Point A**, **Point B** or **Let** after source review. The backend updates score/service, speaks a local browser voice call and persists a labeled player/official decision. A correction recomputes the score once and retains history. Seeking does not score. The initial 0–0 and server A are explicit demo setup assumptions, not recovered match state.
5. Switch to **Synthetic rule fixtures**. Seven known-geometry cases show a short toss, exact 16 cm boundary, angle above 30°, exact 30° boundary, height uncertainty, angle uncertainty and missing release. Exactly two supported synthetic faults score. Passing the two toss checks does not establish complete service legality. Synthetic and real score/audit state are separate.

## Measured results and what they mean

Native Apple Silicon/MPS, 2026-10-24. Full details remain in local reports; small shareable summaries are in `evals/reports/`. No real 3D, edge, toss-height, angle, or rally-winner ground truth was available.

| Measurement | Result | Scope |
|---|---|---|
| Classical baseline, short 720p comparison | 150.0 / 162.5 source FPS; sequential paired 78.0 FPS | 180 frames/view, original 4K decode + 720p processing; conservative color/motion tracker. Speed is not accuracy. |
| BlurBall RGB, sliding windows | 30.85 / 26.68 FPS; sequential paired 14.31 FPS | 180 frames/view, MPS; about 25.05 / 28.24 ms model-only per 3-frame window. |
| Selected grayscale BlurBall, block-three heads | 44.62 / 44.44 source FPS; sequential paired **22.26 FPS** | All 6,457 / 6,781 frames; 144.71 / 152.59 s. Each head maps to a real source frame, no synthesized neighbors. Model mean 26.38 / 26.98 ms/window. Recorded preprocessing, below 25 paired FPS. |
| Ball localization, development slice | Side 39/44; diagonal 36/45; total **75/89** visible labels | 96 reviewed frames at 7.4–9.75 s; 7 unassessable. Manually read source centers without detector overlays, tolerance 32 px in original 4K. Includes toss/contact/bounce/rally. Three wrong localizations and eleven missing detections. Not held-out or overall clip accuracy. |
| Ball localization, held-out slow/held-ball slices | Side 2/12; diagonal 4/7; total **6/19** | 48 reviewed frames at 40–41.1 and 87–88.1 s; 29 unassessable/occluded. No settings changed after these labels. Not an active-rally benchmark. Establishes a serious slow-ball/release limitation. |
| Shared audio alignment | Diagonal source time = side/session time + **0.039 s**; conservative estimate ±**0.0276 s** | Seven windows; offsets 0.037–0.062 s. No stable drift established. Exposure synchronization, sound travel and rolling shutter remain unverified. |
| Pose extraction | 1,615 sampled frames; Green 1,463 / Blue 1,574 detected | CPU/XNNPACK, mean 6.93 ms/person; 36.72 s including decoding/crops. Coverage, not pose accuracy. |
| Avatar rendering | Green 1,458 / Blue 1,573 source-aligned frames | Approximate monocular placement, table-region image stabilization, bounded display priors, separate display smoothing. No metric ball shown. |
| Hands around first serve | 120 source frames per camera | Side 466/480 crops with model hand outputs; diagonal 118/240. Overlapping crops can duplicate hands. Pixel landmarks only; no validated release/open-palm classification. |

The current private playback uses an **experimental hybrid**: keep every observed grayscale-model position, and use a conservative observed orange candidate only when the model is missing and its color ranking score is at least 0.6. Fallback markers are amber and source-labeled. This recovers 41/44 side and 41/45 diagonal development labels (**82/89**), with three wrong localizations and four missing detections. It does not move model detections or fill frames without an observed color component. Activity segmentation retains the primary neural track so carried-ball/color fragments do not merge otherwise separate intervals. Because the fallback was selected after inspecting both component evaluations, **all existing labels are development data for the hybrid; it has no held-out accuracy result**. No joint pipeline throughput is claimed: the two components were preprocessed separately, and the cached fusion time is not inference speed.

The classical color-mask broadening experiment failed by locking onto skin; that variant was rejected. The selected neural component uses the prior prototype's experimental max-channel grayscale adaptation. Neither detector scores nor model coverage become probabilities of a correct call. There are no labeled absent-ball frames establishing a false-positive rate, and no claim of automatic winner accuracy. Whole-rally boundaries remain candidates; long noisy stretches can be split into review intervals, not asserted points.

## Rebuild

Create an isolated Python 3.12 environment and install `services/flight/requirements-demo.txt`. For GPU inference additionally install `torch==2.9.0`. Keep `mediapipe==1.1.1` in a separate pose environment. The executed runtime was the existing native `/Users/mudu/Developer/calhacks/.venv`; no package changes were made to it.

```bash
# Reuse existing local, checksum-pinned assets; no download or redistribution.
python tools/setup_tt_assets.py --from-directory /path/to/approved/local/weights
# Classical baseline, previews and initial session; all source frames by default.
python tools/build_tt_demo.py --force
# Optional LOCAL/PRIVATE neural preprocessing on native Metal, no CPU fallback.
python tools/track_tt_blurball.py --gray --suffix blurball-gray
# Select its cached measurements and retain the previews.
python tools/build_tt_demo.py --detector blurball-gray --skip-preview
python tools/evaluate_tt.py --detector blurball-gray
# Optional selected experimental fallback, with provenance and no held-out claim.
python tools/fuse_tt_tracks.py
python tools/build_tt_demo.py --detector hybrid --skip-preview
python tools/evaluate_tt.py --detector hybrid --output data/local/tt-demo/evaluation-hybrid-development.json
# Optional pose environment; source PTS and raw observations retained.
/path/to/pose-python tools/extract_tt_poses.py \
  'data/ttClips/Adobe Express - IMG_4342.mp4' --output data/local/tt-demo/poses-side.json
python tools/build_tt_scene.py 'data/ttClips/Adobe Express - IMG_4342.mp4' \
  --poses data/local/tt-demo/poses-side.json --output data/local/tt-demo/scene.json
# Metadata export does not claim publication.
python tools/export_tt_observations.py
make tt-demo
```

Use `python tools/extract_tt_poses.py --help` for native-resolution hand probes and `python tools/benchmark_tt.py --help` for the separately measured sliding-window comparison. Checkpoint hashes and official URLs are pinned in the scripts and license record. Playback itself loads no checkpoint. The local server binds only to 127.0.0.1, validates write origin/Host, supports byte ranges and persists atomic audited review state. Use a separate `--directory` for disposable UI tests; do not delete the real audit to reset an actual review session.

## Integration handoff and remaining gates

- C0 acknowledged. `trophy.event.v1` measurements export to `observations.jsonl`, with stable IDs, source frames, timestamps and explicit untrusted-calibration status. All 62 selected-hybrid event envelopes/payloads were schema-validated. `track-samples.jsonl` has 2,154 metadata-only samples at 10 Hz across the shared overlap. Confidence is zero for uncalibrated detector-derived rule hints; separate ranking scores remain labeled uncalibrated.
- `python tools/export_tt_observations.py --publish` uses the existing `ObservationWriter` and `TrackSampleWriter`, with `SPACETIME_VISION_TOKEN` and the other normal service configuration. It fails on delivery errors. **No live Spacetime/Redis publication was exercised.** Backend sponsor services are still stubs in this checkout; this demo uses explicitly local durable state and browser speech, not Cartesia.
- `/api/calibrate` proxies the callable OpenCV adapter. `services/courtcam-adapter/server.py` also exposes `/calibrate` on 8050. A plane homography alone remains untrusted for airborne metric measurements. Known rectified intrinsics plus independent elevated validation points can establish the adapter's metric gate. Recalibrate moving cameras.
- `flight/stereo.py` reconstructs only with trusted rectified calibration, explicit clock mapping, source provenance and quantified pixel/calibration/timing budgets. Synthetic tests cover projection, different-rate timing, drift, gaps, cheirality, weak rays and uncertainty rejection. The real phone cameras do not meet those gates.
- Shared `ServeTossPayload` still specifies the obsolete max(rise,fall) convention. This demo avoids emitting an incompatible official serve event. The production schema/engine owner must migrate it to upward-only angle, unavailable evidence and a versioned rule profile before integration.
- [The referee spec](rules/table-tennis-referee-spec.md) inventories all 116 numbered Chapter 2 sections/clauses. Scoring/state and supported-fact adapters are implemented/tested separately from detection. Doubles, accessibility/expedite/discipline administration and invisible triggers remain manual/unsupported. Official HMO full text was blocked by HTTP 403; no handbook interpretation is claimed.
- Real AUTO serve/edge/point calls need validated dynamic calibration/intrinsics, exposure alignment, release/contact localization, representative absent/visible and outcome labels, and held-out error bounds. Recording new fixed-camera calibration/staged serves or using paid compute requires the user approvals described in the kickoff. None occurred here.

## Checks

`make tt-demo-test` runs deterministic tests. The completed run has **75 passing tests** across referee sequences, replay idempotence/persistence, HTTP range/origin checks, calibration, source PTS, toss geometry and stereo rejection. Ruff check/format and JS syntax checks pass. Browser tests exercised paired playback, seek, 0.25× challenge, paused 4K crop, manual resolution/history, synthetic score-once behavior and both wireframe bodies without console errors. These checks do not certify the failed real-footage accuracy gates.
