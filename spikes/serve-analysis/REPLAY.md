# Trophy 3D replay demo

The recorded point now has an interactive local 3D replay with two simple figures, a fitted ball trajectory, an original-video reference, a shared timeline, slow motion, orbit/zoom controls and four camera presets. Three H.264 videos export the same motion from an orbit, overhead, and courtside view.

## Run

From the project directory:

```bash
bash scripts/bootstrap_replay.sh
bash scripts/build_demo.sh
.venv/bin/python scripts/serve_replay.py
```

Open [http://127.0.0.1:8502/](http://127.0.0.1:8502/). The existing Streamlit ball-tracking interface at port 8501 links to the 3D viewer. Both servers bind to localhost. The viewer bundles Three.js 0.180.0 locally and needs no CDN or hosted inference at playback time.

The bootstrap keeps pose inference in `.venv-pose` so MediaPipe's OpenCV/matplotlib dependencies cannot alter the validated PyTorch/MPS environment. Pose dependencies are pinned in `requirements-pose.lock`. Reconstruction and video export use the existing `.venv` and SciPy. No models are trained.

## How the reconstruction is built

1. **Ball observations:** actual pretrained BlurBall outputs from the previously validated 272-frame official scene `22/003`. These are reused without changing their coordinates, missing flags, or scores.
2. **Player observations:** actual pretrained MediaPipe Pose Landmarker full, 33 joints per player, run on every source frame in two explicitly configured player regions. The regions preserve identity for this side-view recording. There is no synthetic gait or scripted swing.
3. **Camera:** manually selected table corners, known 2.74×1.525 m tabletop, centered principal point, equal x/y focal lengths and zero lens distortion. A joint focal/pose fit gives approximately 595.3 px focal length and 0.64 px corner coordinate RMSE. These assumptions are not measured camera intrinsics and do not establish metric accuracy.
4. **Player depth and placement:** the pose model's hip-relative 3D landmarks are rotated into the table frame. Reliable feet anchor the body to the estimated floor. When table occlusion makes the feet unreliable, an explicit 0.73 m hip-height prior and a playing-zone prior anchor translation. Uncertain legs use a neutral stance and are rendered dimly. Upper-body articulation continues to come from model predictions. Root and joint smoothing reduce jitter.
5. **Ball depth:** joint event positions are optimized so piecewise gravity trajectories project near the real 2D detections. Approximate hit/bounce boundaries were selected from observed direction changes and are recorded in the configuration. Bounce height is constrained to table height plus ball radius. Gravity is modeled; drag, spin, and racket dynamics are not. Missing 2D observations stay missing in the tracking exports; replay gap estimates are labeled separately and colored amber.
6. **Rendering:** `scene.json` contains one reconstructed state for every original frame, with original timestamps. The browser reads the source video's time to select the matching scene state. Exports resample this same estimated motion to 30 FPS, with the camera moved around the 3D scene.

## Executed results

- Pose model: MediaPipe **1.1.1**, official `pose_landmarker_full/float16/1` task asset.
- Pose execution: native **CPU / XNNPACK**, explicitly separate from BlurBall's MPS inference.
- Full clip: **272 frames**, left player detected on **270**, right on **272**. Detection coverage is not pose accuracy.
- Pose processing: **3.47 seconds**, mean **5.15 ms per player inference** on this Mac.
- Lower-body stance prior: **92 left-player frames**, **0 right-player frames**. This is an important limitation caused by table occlusion.
- Ball fit: median **4.13 px**, P95 **9.81 px** reprojection error on the observed 2D detections. This measures image agreement, **not 3D accuracy**. The 8 missing ball observations are fitted gaps.
- Browser: actual WebGL figures/table render; synchronized playback advances to the end; scrubbing to 2.50 seconds and switching to overhead were exercised.
- Exports: local H.264/yuv420p 1280×720 MP4s, verified by decoding the completed files.
- Automated suite: **22 tests pass**, including the existing 17 tracking tests and 5 camera/reconstruction tests.

The inference runtime emitted MediaPipe warnings that feedback tensors are disabled for this model and about its internal normalized-ROI projection. Inference completed successfully. No pose GPU acceleration is claimed. The most obvious observed pose error is unreliable hidden legs; the explicit stance prior prevents their guessed foot locations from placing the player metres into the background.

## Outputs

In `artifacts/replay/demo/`:

- `index.html`, `viewer.js`, `style.css`, bundled Three.js modules: standalone local viewer.
- `source.mp4`: unmodified official real recording used as the reference.
- `scene.json`: per-frame estimated 3D joints, roots, ball states, uncertainty/provenance flags and source timing.
- `reconstruction-report.json`: camera assumptions, pose measurements, stance-prior counts and ball fit errors.
- `orbit.mp4`, `overhead.mp4`, `courtside.mp4`: rendered views of the same reconstructed point.
- `calibration.jpg`: manually selected tabletop corners over the real first frame.

`artifacts/replay/poses.json` retains the model's raw 2D and hip-relative 3D outputs before world placement and stance regularization. The original BlurBall detection files remain under `artifacts/official-22-mps/`.

## Rebuild individual stages

```bash
.venv-pose/bin/python scripts/extract_poses.py samples/official-22-003.mp4 \
  --config configs/official-22-003.json --output artifacts/replay/poses.json

.venv/bin/python scripts/build_replay.py samples/official-22-003.mp4 \
  --detections artifacts/official-22-mps/detections.json \
  --poses artifacts/replay/poses.json --config configs/official-22-003.json \
  --output artifacts/replay/demo

.venv/bin/python scripts/render_replay.py artifacts/replay/demo/scene.json \
  --output artifacts/replay/demo/orbit.mp4 --view orbit

.venv/bin/python -m pytest -q
```

For another video, create a separate calibration configuration with its displayed resolution, four matching table corners, two player regions and approximate trajectory event boundaries. Then run real ball/pose inference on that video. This demo does not claim automatic reconstruction of arbitrary recordings.

## Asset provenance

- Pose documentation: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python
- Official pretrained pose task: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
- Pose task SHA-256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.
- Three.js: pinned npm release **0.180.0**, bundled locally with MIT license in `web/replay/THREE-LICENSE.txt`. File hashes/origins are in `web/replay/ASSETS.json`.
- The reconstruction code is Trophy's simplified approximation, informed by the TT3D problem formulation. It does **not** run the official TT3D, MotionBERT, GVHMR, or TT4D pipelines or reproduce their reported accuracy.

This fulfills the visual demonstration: real observed player articulation and ball detections produce a viewable 3D replay. Camera calibration, hidden limbs, event timing and depth remain approximate; this output is unsuitable as evidence for close line calls or precise contact timing.
