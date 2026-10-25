# Unlabeled two-camera footage and 4D Humans investigation

Executed 2026-10-24. The pretrained BlurBall inference pipeline needs videos and
weights, not ball labels. Reference labels are used by separate evaluation tools.
The current Streamlit upload interface accepts one video; the two-view builder
expects a prepared config, camera calibration, ball detections and pose estimates.

**Later execution:** actual HMR2 inference and a combined SMPL + ball replay were
subsequently completed on a short segment of these same two videos. See
[HMR2_REPLAY.md](HMR2_REPLAY.md) for the current result and measured limitations.
The prerequisite assessment below records the earlier investigation state.

## Test on the supplied recordings

Inputs, read without modifying the originals:

- `/Users/mudu/Developer/trophy/data/ttClips/Adobe Express - IMG_4342.mp4`
- `/Users/mudu/Developer/trophy/data/ttClips/IMG_2865 (1).mov`

Both are 3840 × 2160 at 60 fps, with audio, and show the same table-tennis session.
Container durations are approximately 107.67 and 113.03 seconds. Inspection at
0, 5, 10, 20, 30, 40 and 60 seconds confirms complementary side/oblique views.
Camera framing changes over the recording; supplied TT3D calibration is not
applicable to this room or these cameras.

For an initial inference test, the 8–14 second interval was exported at 1920 ×
1080 without cropping. BlurBall processed its first 180 frames (original 8–11
seconds) from each view, using the existing official checkpoint, threshold 0.65
and the existing max-channel grayscale adaptation for orange balls. No labels,
training, table annotations or camera calibration entered inference. Actual model
execution used CPU; no GPU performance result is claimed for this run.

| View | Frames with detections | Coverage |
| --- | ---: | ---: |
| Side / camera 1 | 171 / 180 | 95.0% |
| Oblique / camera 2 | 145 / 180 | 80.6% |

Coverage is not accuracy. The inspected annotated frames at original 8.5, 9.0,
9.5 and 10.0 seconds show the marker following the visible orange ball. This is
a small qualitative check, not a ground-truth accuracy benchmark. Table/player
occlusion is more difficult in the oblique view.

Outputs:

- `artifacts/user-two-camera/summary.json`: inputs, inference and alignment summary.
- `artifacts/user-two-camera/blurball-camera{1,2}/`: original/annotated previews,
  per-frame detections and execution reports.
- `artifacts/user-two-camera/detection-contact-sheet.jpg`: inspected detector frames.
- `artifacts/user-two-camera/paired-tracking-half-speed.mp4`: paired annotated
  preview, 178 frames at 30 fps, 1920 × 540, half-speed playback. The 40 ms audio
  estimate is rounded to two 60-fps frames (33.33 ms) for this visual preview.
  It is muted and is not a claim of frame-perfect or hardware synchronization.

No metric 3D ball or human reconstruction was generated for these recordings:
their camera intrinsics/extrinsics are not available and camera motion must be
accounted for. A table-plane homography alone does not recover the height of a
flying ball. Table geometry, camera intrinsics/distortion and relative camera
poses need to be established before triangulation; moving cameras require pose
updates or sufficiently stable calibrated segments. Our player pipeline also
currently requires per-view player crops and matching player IDs.

## Automatic synchronization

Added an isolated experimental diagnostic, `scripts/probe_audio_sync.py`. It mixes
audio to mono at 16 kHz, bandpasses 700–6000 Hz, computes a log-RMS envelope at
200 Hz, and searches normalized cross-correlation over overlapping audio.
It rejects weak matches, insufficient overlap and optima at the search boundary.
The score is not a calibrated confidence, and alternative-peak ambiguity is not
yet tested. Audio timestamps are retained; gaps/discontinuities are not modeled.

On the complete supplied clips, the estimate is:

`t_camera2 = t_camera1 + 0.040 seconds`

The overall correlation score is 0.687. Five 20-second windows give 40, 40, 55,
35 and 40 ms respectively. These differences do not establish clock drift;
acoustic propagation, recording latency and sound content also affect matching.
Use audio for coarse initialization and refine visually. This audio path is not
integrated into the upload UI or the existing replay builder.

Reproduce the audio test:

```bash
.venv/bin/python scripts/probe_audio_sync.py \
  --videos '/Users/mudu/Developer/trophy/data/ttClips/Adobe Express - IMG_4342.mp4' \
           '/Users/mudu/Developer/trophy/data/ttClips/IMG_2865 (1).mov' \
  --output artifacts/user-two-camera/audio-sync-rerun.json
```

The existing visual alignment estimates moving-arm epipolar consistency over
±250 ms, then refines with measured ball detections within ±150 ms of its initial
estimate. It uses supplied camera calibration and no reference ball tracks.
On the original real TT3D rallies, it estimates approximately 3.03 and 39.93 ms.

A timestamp-shift stress test found that ±100 ms shifts were recovered, whereas
500–1000 ms shifts could either fail at the boundary or return a wrong offset
with low triangulation coverage. These are injected timestamp changes on the
same detections, not independent recording experiments. Details are in
`artifacts/unlabeled-investigation/sync-probe.json`.

The new audio initializer followed by existing visual refinement recovered
injected +0.5, +1, +2 and −0.5 second shifts on both TT3D rallies while preserving
286/308 and 186/214 accepted ball frames. No reference CSV was read. These tests
establish sign/search-range behavior on the existing data, not general accuracy
or synchronization on the supplied uncalibrated cameras. Full results are in
`artifacts/unlabeled-investigation/audio-visual-{010,038}.json`.

```bash
.venv/bin/python scripts/probe_audio_sync.py \
  --config configs/tt3d-multiview.json \
  --output artifacts/unlabeled-investigation/audio-visual-010-rerun.json \
  --shifts .5 1 2 -.5
```

## What 4D Humans could improve

[4D Humans](https://shubham-goel.github.io/4dhumans/) combines HMR 2.0 single-image
human mesh recovery with tracking through video. Its pretrained models do not
require labels for a new recording. The upstream code exports human meshes and
SMPL body pose/shape, and its PHALP-based video tracker maintains person IDs.
This is directly relevant to replacing our procedural mannequin with estimated
body shape and joint rotations. Better geometry is plausible, but an accuracy
or visual improvement on these table-tennis clips has not been measured.

It does not supply ball tracking, racket orientation, multi-camera video sync,
or a calibrated shared table coordinate system. Independently running it on each
view does not automatically produce one consistent metric 3D scene. Table
occlusion and fast arm motion still require checking against both source views.

Recommended integration experiment:

1. Establish camera geometry and refine sync on a short active rally.
2. Run HMR 2.0 on the two known player crops; the full PHALP tracker is optional
   for this first controlled experiment.
3. Keep a stable body shape per player. Transform the root pose into the calibrated
   table frame and fit pose to visible landmarks in both cameras, with temporal
   regularization. Keep BlurBall triangulation independent.
4. Export SMPL pose/shape and root motion to the viewer as an alternative player
   representation. Compare source-view overlays, silhouette fit, foot sliding,
   wrist motion and occlusion failures against the current reconstruction.

This is a reconstruction/replay improvement; physically correct dynamics,
ball/racket contact and racket-face measurements would need additional work.

Execution prerequisites remain unmet here. The main project environment does
not contain `hmr2`, `smplx`, `detectron2`, `phalp` or `pyrender`, and no SMPL model
asset was found in this workspace. The [official setup instructions](https://github.com/shubham-goel/4D-Humans)
require downloading the neutral SMPL model through its registration-gated site.
It cannot be replaced with a fabricated mesh and called 4D Humans.

The [upstream image demo](https://github.com/shubham-goel/4D-Humans/blob/main/demo.py)
selects CUDA when available and otherwise CPU; it does not select Apple MPS.
The [PHALP installation instructions](https://github.com/brjathu/PHALP)
describe a CUDA environment. Use an isolated environment for any experiment;
Apple GPU compatibility and runtime have not been established here. No 4D Humans
checkpoint inference or improved 3D simulation is claimed as completed.

## Validation

`python -m pytest -q` in `.venv`: 44 passed. Eight new diagnostic checks cover
positive/negative audio lag, zero lag, silence, search boundaries and explicit
missing-audio failure. Synthetic signals test clock math only. Real footage
results above come from the official pretrained BlurBall checkpoint and actual
decoded audio, with no reference labels read during inference or synchronization.
