# Trophy: tested reconstruction from two real cameras

The runnable demo is at **http://127.0.0.1:8503/** while its local server is running. It contains solid articulated human figures, wrist-attached rackets, a triangulated ball, two synchronized source videos, orbit/zoom and recording-camera views, a seek bar, slow motion, and downloads. All analysis and rendering run locally.

This implements a **two-camera prototype**, not a claim that arbitrary phone footage can already be reconstructed accurately. Ball accuracy was measured on two short real rallies. Player and racket 3D accuracy cannot be established from these data because no corresponding ground truth is supplied.

## Sources and input footage

- [TT3D project](https://cogsys-tuebingen.github.io/tt3d/) and [official raw recordings](https://cloud.cs.uni-tuebingen.de/index.php/s/SCKq85JZEmKoC6J): real side and oblique video, per-game camera parameters, and separate reference ball tracking. The authors' raw README documents tracking gaps and a table-centred coordinate system.
- [TT3D paper, §7.2](https://arxiv.org/html/2504.10035v1#S7.SS2): the recording system uses orange balls, and the original BlurBall detector was not trained for them. The GitHub evaluation benchmark uses **simulated 2D projections**. We instead analyze the **real raw MP4 pixels**.
- [Official BlurBall](https://github.com/cogsys-tuebingen/blurball): actual pretrained network, original source and checkpoint. Upstream commit `2f0f5496f7ba4b5b1a36790749935121b2ce972d`; weight SHA256 `3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`. Source remains unmodified under `vendor/blurball`; adapters live in `trophy/`.
- [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python): actual full pretrained model extracts 33 image landmarks per player per view. Existing isolated pose environment and official checksum-verified checkpoint are reused.
- [OpenCV calibration and reconstruction](https://docs.opencv.org/4.11.0/d9/d0c/group__calib3d.html): pinhole projection, camera poses, epipolar constraints, and triangulation. Our implementation adds confidence weighting, robust reprojection fitting, temporal alignment, and explicit rejection.

Downloaded rally pairs: `side/game_00/010.mp4` + `oblique/game_00/010.mp4`, and the corresponding `038.mp4` pair. All four are **1920 × 1080**, side **50 FPS**, oblique **60000/1001 FPS**. Rally 010 has 308/369 frames; rally 038 has 214/256. Reference ball tracking is nominally 200 Hz, **not the video frame rate**. The camera pair is side + oblique, not overhead + side.

Exact download paths, sizes and SHA256 checksums are versioned in `configs/tt3d-assets.json`. `scripts/download_multiview_samples.py` verifies existing files or downloads from the official public WebDAV share. It refuses changed checksums.

## Executed reconstruction

1. Run BlurBall separately on each camera. The unchanged RGB runner produced false detections, including the net and a shoe in the inspected serve frames. A generic full-image transform, **max-channel grayscale**, sets each RGB channel to the maximum original channel value. This suppresses the orange/white color-domain difference while preserving geometry. It does not locate objects, draw a ball, use reference positions, or train a new network. It is an experimental adaptation validated on these clips, not a general guarantee for orange balls. Detection threshold is **0.65** in both clips and views.
2. Run independent MediaPipe inference in two explicit player crops per view. Crop IDs identify the same two people across cameras; this is a configured two-player scene, not automatic player re-identification.
3. Load the authors' per-game calibration without fitting it to reference ball positions. `f`, `rvec`, and `tvec` define a centred-principal-point, square-pixel pinhole camera; no lens-distortion parameters are supplied. Verified the supplied table pose against visible table corners.
4. Estimate the camera time offset from moving-arm epipolar consistency; refine using measured ball detections. No reference 3D tracking enters this step. Different video rates are handled through timestamps and short linear interpolation between consecutive valid detections. Offsets are **approximately +3.03 ms** for 010 and **+39.93 ms** for 038, where `t_oblique = t_side + offset`. These are estimates of effective image alignment, not verified hardware synchronization.
5. Triangulate ball rays, refine reprojection residuals, and reject behind-camera, near-parallel, excessive-reprojection and implausible positions. The per-view reprojection gate is **8 px**. This rally prototype gates ball height to -0.10…2.50 m relative to the tabletop and horizontal radius to 5 m; it does not track floor bounces. Isolated large temporal outliers are rejected. **No gravity path, hit annotations, reference positions, or simulated motion supplies the ball. Missing positions remain null.**
6. Triangulate corresponding body landmarks and fit robust per-clip bone lengths. Where one camera hides a leg, the other view's pretrained relative-depth estimate supplies an initialization anchored to triangulated hips; a two-view reprojection and bone-length fit refines it. No scripted swing or neutral walking animation is used. The export identifies which joints had accepted two-view triangulation. Two-view agreement still cannot prove an occluded joint is correct.
7. Animate a single continuous procedural human surface, smoothly bound to the reconstructed joints. Both players are visibly right-handed in the source and have right-wrist-attached paddles. **The racket is not independently detected**: its position follows the wrist, and handle/face orientation is an illustrative forearm-based estimate. We do not claim measured racket-face angles, impact contact, or spin.

World conversion is explicit: TT3D `[X_width, Y_length, Z_above_table]` becomes viewer `[-Y, X, Z + 0.76]` in metres. The floor is at zero. Body shape is a procedural mannequin, not an estimated SMPL mesh or personalized anatomy. WebGL ball radius is enlarged to 2.5 cm for visibility.

## Measured ball accuracy

The reconstruction CLI does **not accept reference data**. `scripts/evaluate_multiview.py` evaluates its completed output separately. Reference timestamps have a different origin. A single reference-clock translation is fitted using the **first second of reference positions projected into camera 1**, without changing any camera geometry or reconstructed positions. Later reference times are held out. Reference rows numbered `Frame=-1` are excluded; repeated timestamps are deduplicated, and reference gaps >25 ms are excluded.

| Real rally | Held-out reference frames | Reconstructed / available | Median 3D error | Mean | 95th percentile | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| game_00 / 010 | 159 | 156 / 159 (98.1%) | **2.59 cm** | 2.80 cm | **5.38 cm** | 9.30 cm |
| game_00 / 038 | 105 | 104 / 105 (99.0%) | **2.53 cm** | 3.06 cm | **8.58 cm** | 10.41 cm |

146/159 available held-out frames in 010 and 91/105 in 038 have a valid prediction within 5 cm. Conditional on a prediction, those counts are 146/156 and 91/104. Coverage is reported separately from localization error. Across the entire clips, accepted triangulation is **286/308** frames and **186/214** frames; serve/occlusion/end intervals are more difficult than the reference-covered rally intervals.

Reference-clock fitting is less clean for 038: the first reference second includes missing detector observations and tracking gaps, with a clipped mean projected alignment residual of about **32.5 px**, versus **4.0 px** for 010. The 038 result is encouraging, but its reference-clock alignment is less certain. These are two rallies from the **same camera arrangement and players**, not a broad benchmark, and the reference system's own error is not independently known.

A timing perturbation test keeps the reference clock fixed and deliberately offsets camera 2:

| Added timing error | Rally 010 median | Rally 038 median |
|---|---:|---:|
| 0 ms | 2.59 cm | 2.53 cm |
| +5 ms | 4.55 cm | 4.96 cm |
| +10 ms | 8.28 cm | 11.17 cm |
| +20 ms | 16.51 cm | 18.97 cm |

Reprojection rejection also reduces coverage under larger offsets. With **no camera-offset correction**, rally 038 has only 41/105 valid held-out predictions and a **42.24 cm median error**. This is direct evidence that synchronizing by frame number or assuming both clip starts match is insufficient. Full records are in `artifacts/multiview/sync-sensitivity.json`.

## Player/racket checks and observed errors

For 010, both figures are present on **307/308** frames; the final frame lies beyond the second camera's usable interpolation interval. About 18,834/20,328 joint observations initially pass two-view triangulation, including face and hand landmarks. This is **coverage, not accuracy**. The constrained body fit has about **2.1 px median / 8.3 px 95th-percentile** reprojection error on sufficiently visible landmarks.

Inspected source/overlay/reconstruction frames at **0.6, 1.5, 2.5, 3.5, 4.5 and 5.5 seconds**, plus the browser playback and overhead view. Movement follows the recorded crouches, steps, leans and swings. The serve toss has missing/rejected ball frames; leg placement and body proportions are less certain under table occlusion; joint jitter remains; the wrist-attached paddles do not always coincide with the actual paddle heads or their orientation. Linear cross-view interpolation is most vulnerable near hits and bounces. Missing ball samples make the marker disappear rather than silently filling a trajectory.

`artifacts/multiview/demo/contact-sheet.jpg` and `diagnostics.mp4` show both original views with the reconstructed joints and ball reprojected, beside the 3D render in the sheet. The original video remains visible beneath every marker. Reference tracking is not drawn into these overlays.

## Execution and performance

Native M5 Pro / macOS arm64. Main environment: Python 3.12.14, Torch 2.9.0, NumPy 1.26.4, OpenCV headless 4.11.0.86, SciPy 1.13.1, PyAV 16.0.1, imageio-ffmpeg 0.6.0 / FFmpeg 7.1. Separate pose environment: MediaPipe 1.1.1 and the previously pinned `requirements-pose.lock`.

- BlurBall model execution was verified on **MPS**, with device synchronization and **no model CPU fallback enabled**. In 010 the mean model-only times are approximately **23.4 / 23.4 ms per three-frame window** for side/oblique; exact values and CPU decode, preprocessing, postprocessing and render stages are in each inference `report.json`.
- CPU versus MPS comparison on six actual temporal windows from both cameras has identical heatmap argmax coordinates, with maximum absolute heatmap difference **2.81e-6**. This checks numerical agreement, not accuracy. Warm-up is included in the first probe timing, so those probe timings are not a benchmark.
- MediaPipe runs on **native CPU / XNNPACK**, approximately 5–6 ms per player inference. Both players are detected in every source frame in both views; visibility of individual joints varies.
- Two-camera body/ball reconstruction took roughly **40–45 s** for the 6.16 s rally in the executed builds, separate from model inference and MP4 export. This is currently an **offline demo**, not a real-time pipeline.
- H.264/yuv420p exports were decoded and verified: each 3D view is **185 frames, 30 FPS, 1280 × 720**; paired diagnostic playback is **308 frames, 50 FPS, 1920 × 540**. Source videos retain their own frame rates. The viewer was tested at 0.25× playback; source clocks differed by the estimated ~3.03 ms during playback.

A secondary published pretrained ball model was smoke-tested from [RacketVision](https://github.com/OrcustD/RacketVision), pinned at `c44af2a08524d3cb54d818f19686f4cdea4d2793`. Official TrackNetV3 checkpoint SHA256 `00d707b9db7a49561c411e4765956e79bcd7c7e20c7a0a535073440b3e972342`. It located the inspected active-rally ball but gave a low-confidence serve-toss result; it is **not used** in the delivered reconstruction. `scripts/probe_tracknet.py` follows the BGR training loader's median + four frames ending at the target, correcting an apparent one-frame offset in the upstream inference runner without editing its model source. The official checkpoint contains mmengine training metadata and is loaded only after checksum verification. Optional research-only packages are recorded in `requirements-research.in`; the core replay does not need them. Full current installed versions are in `artifacts/multiview/environment.freeze.txt`.

## Reproduce and launch

```bash
cd /Users/mudu/Developer/calhacks
bash scripts/bootstrap_replay.sh
bash scripts/build_multiview_demo.sh
.venv/bin/python scripts/serve_replay.py --directory artifacts/multiview/demo --port 8503
```

`build_multiview_demo.sh` verifies/downloads inputs, reuses completed per-camera ball inference when present, reruns body inference and reconstruction, evaluates both rallies, exports all videos, and runs the tests. It fails on errors. On a fresh workspace it runs ball inference with `--device auto`; use `cpu` explicitly in the corresponding CLI commands if needed. It does not silently substitute CPU for a failed MPS operation. The existing 2D UI remains on localhost:8501 and the earlier monocular replay on localhost:8502.

Core individual commands:

```bash
.venv/bin/python scripts/download_multiview_samples.py --verify-only
.venv/bin/python -m trophy samples/tt3d/game_00/side-010.mp4 \
  --output artifacts/my-side-run --device auto --threshold .65 \
  --max-frames 1000 --photometric max-channel-gray
.venv-pose/bin/python scripts/extract_poses.py samples/tt3d/game_00/side-010.mp4 \
  --config configs/tt3d-side.json --output artifacts/my-side-poses.json
.venv/bin/python scripts/build_multiview.py \
  --config configs/tt3d-multiview.json --output artifacts/multiview/demo
.venv/bin/python scripts/evaluate_multiview.py \
  --ball artifacts/multiview/demo/scene.json \
  --detections artifacts/multiview/gray-side/detections.json \
  --reference samples/tt3d/game_00/reference-010.csv \
  --camera samples/tt3d/game_00/side.yaml --output artifacts/multiview/demo/accuracy.json
.venv/bin/python scripts/check_multiview_devices.py
.venv/bin/python scripts/check_sync_sensitivity.py
.venv/bin/python -m pytest -q
```

For another camera pair, supply two per-view video paths, matching original-pixel calibration parameters, per-frame detections and pose files in a new config following `configs/tt3d-multiview.json`. Configure player crops for those videos. The current build CLI explicitly supports **two views**; the triangulation primitive accepts more, but end-to-end processing of additional views is not implemented or validated. Uncalibrated phone videos, automatic person matching, lens distortion, clock drift, and rolling shutter need further work.

The 36 passing tests include calibrated reconstruction, epipolar geometry, behind-camera/parallel-ray rejection, different-rate timestamp alignment, synchronization boundary failure, missing detections, metric coordinate conversion, JSON/CSV consistency, reference-input separation, and regression thresholds against both real reference comparisons. Synthetic unit geometry is used only to test math, never as evidence of real ball tracking.

## Assessment

**Yes: these two calibrated real camera views support a ball reconstruction accurate to a few centimetres on the reference-covered intervals, and a viewable replay of estimated player movement with solid figures and rackets.** This validates the direction for an offline demo. It does not establish accurate full-body motion capture, racket-face recovery, exact impact timing, or accuracy on arbitrary phone recordings. A next live-stream experiment should first preserve fixed camera calibration and verify synchronization on a white-ball recording, then address speed and rolling-shutter errors. The current full reconstruction is not real time.


## Continuous models and movement smoothing

The current viewer replaces separate body primitives with a single connected, watertight surface, smoothly bound to 15 pose controls. Both mesh resolutions are verified to have one connected component and exactly two faces per edge. The browser uses a 6,640-vertex / 13,276-triangle mesh with smooth normals and GPU skinning; MP4 export uses a lower-resolution version of the same surface and smooth normal interpolation. Rackets remain separate props.

Player display motion uses symmetric Savitzky–Golay filters (9-frame root, 7-frame body, 5-frame arm windows at 50 FPS), then retargets stable limb lengths. Browser playback and MP4 export interpolate between neighboring display poses instead of stepping between them. The filter operates on contiguous detected-pose runs and does not fill missing people. Head/neck placement is retargeted to mannequin proportions using the nose landmark's direction.

The display pose's second-difference RMS drops from 0.02398 m to 0.01163 m, a **51.5% reduction** in this acceleration/jitter proxy; this is not a motion-capture accuracy metric. Median joint adjustment is **0.81 cm**, with **4.42 cm at the 95th percentile**. Raw `joints`, timestamps, ball positions, detection status, and reference accuracy remain unchanged. Smoothed motion is exported separately as `render_joints`.

The update was applied without rerunning inference:

```bash
.venv/bin/python scripts/update_player_presentation.py
.venv/bin/python -m pytest -q
```

There are now **36 passing tests**, including mesh connectivity/watertightness, skin-weight normalization, rest-pose deformation, smoothing without time lag or filling missing people, stable limb lengths, and preservation of the original tracking. `artifacts/multiview/demo/motion-smoothing-report.json` records the measured changes. The three 3D MP4s were regenerated with the continuous models and filtered motion.

Procedural mesh assets are checked in under `web/multiview/avatar-*.json`; normal playback needs no new dependency. To regenerate the assets, install the pinned optional `requirements-mesh.in` and run `.venv/bin/python scripts/build_avatar_mesh.py`. The surface is created locally using scikit-image marching cubes and smooth implicit unions; it contains no downloaded character asset or recovered personal anatomy.
