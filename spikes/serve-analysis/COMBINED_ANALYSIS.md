# Combined two-camera analysis

The first tab in `app.py` combines the existing local models without changing the
single-camera analysis API or the existing reconstruction and serve-review CLIs.
Each analysis writes to a new `artifacts/sessions/<session-id>/` folder.

## Use your own recordings

1. Start `.venv/bin/streamlit run app.py --server.address 127.0.0.1` and open
   [the local app](http://127.0.0.1:8501/).
2. Upload Camera 1 and Camera 2, or enter existing local paths. Each file can be
   up to 500 MB. Choose the Camera 1 start time and analysis duration; start with
   six seconds because the body model processes both players in both cameras.
3. Use audio matching for recordings with common sound. For silent footage or
   ambiguous audio, enter the coarse offset: the same instant at 8.0 seconds in
   Camera 1 and 8.4 seconds in Camera 2 means **+0.4 seconds**. Both modes then
   refine the offset using measured ball detections and calibrated image geometry.
4. The demo automatically segments the tabletop in both camera previews and
   initializes its four corners and approximate focal length from image evidence.
   Check the highlighted surface. No corner entry is needed for a detected table.
   If needed, drag the automatically placed A–B–C–D markers to refine the outline.
   A and D are at Player 1's end; B and C at Player 2's end. A–B and D–C run along
   the long edges. Drag markers to refine their positions; use **Undo last corner**
   or **Use automatic outline** to correct a selection. Selections automatically map to the
   source resolution and remain separate for each camera. Four matching visible
   corners are required; no corner coordinates need to be typed. If automatic
   detection cannot find a stable outline, the clickable picker remains available.
5. Player regions are initialized from the detected table ends. Adjust each
   player's bounding region if needed to cover their movement. Player 1 and
   Player 2 must refer to the same people in both views, even if image sides reverse.
   Open the setup overlay to check corner labels and region coverage.
6. Select **Analyze both cameras**, then **Open combined 3D replay**. The replay
   offers orbit/recording/overhead views, slow motion, paired source video, ball
   coordinates, serve-candidate seek buttons, annotated ball videos and CSV export.
   The linked serve reviewer retains confirmation, rejection, actor/time corrections,
   manual additions, browser persistence and reviewed JSON export.

All uploads, inference, reports and playback stay on the local machine. Partial
stages and logs remain available when a stage fails. A failed stage cannot be
reported as a completed combined analysis. Existing results are never overwritten.

## Model setup

The workflow checks these existing assets/environments before analysis:

- `.venv`: BlurBall and orchestration; `weights/blurball_best`.
- `.venv-pose`: MediaPipe Pose; `weights/pose_landmarker_full.task`.
- `.venv-hmr2`: official HMR2 inference and differentiable two-view SMPL fit;
  `weights/hmr2-assets/model_config.yaml` and the released checkpoint.
- `.venv-serves`: trained serve spotter; `weights/serves/table-tennis-final.pt`.

See `README.md`, `HMR2_REPLAY.md` and `SERVES.md` for their existing setup steps.
The workflow never substitutes geometric figures for HMR2 if an environment is
missing. Device choices are auto/MPS/CPU, respecting the existing explicit device
handling. MediaPipe remains an explicit native CPU stage.

## Shared geometry and clock

`trophy/table_detection.py` segments the demo's gray/blue tabletop using image
line intersections, visible boundary support and surface appearance. It scores
full-table quadrilaterals so the net is not mistaken for the far edge. This is a
demo-specific computer-vision heuristic, not a general trained segmentation model.
Initial end ordering uses dark clothing evidence near each end, matching the demo's
starting views; player identities still need to remain consistent between cameras.
The highlighted polygon is editable. A moderate focal prior and the known table
dimensions initialize approximate camera calibration; automatic-demo calibration
allows a resolution-scaled corner residual and records that residual in the report.
Manual calibration retains its existing eight-pixel acceptance threshold.

`trophy/session.py` validates table marks and player regions. It estimates a
square-pixel centered pinhole camera from the known 1.525 × 2.74 m table. If the
four corners cannot constrain focal length, the UI requests a calibrated focal
length in pixels. Degenerate, crossing, off-image and below-table solutions fail.

The original-video coarse clock is `t2 = t1 + offset`. The pipeline selects the
overlapping source interval and converts both excerpts to browser-compatible
30 FPS H.264. Pose extraction and BlurBall therefore observe the exact same
normalized video frames. It verifies their timestamps before reconstruction.
Pose synchronization initializes the measured-ball epipolar refinement. Geometry,
body fitting, serve merging and source playback all use the same residual offset
between these normalized excerpts. The original-video offset and excerpt start
times are recorded separately in `synchronization.json` and `scene.json`.

`scripts/fit_hmr2_multiview.py --inputs <directory>` now accepts any prepared
geometry/inference folder. Its previous input/output defaults remain supported.
The fit is restricted to shared observed body time; it does not extrapolate body
tracks beyond either camera. `web/hmr2` accepts source sizes, start times and serve
events; its legacy scene format remains supported.

When the first fitting frame lacks a usable hip triangulation, body initialization
now searches the shared clip for valid observed hip anchors for each player.
Interior gaps use time-based interpolation; leading/trailing gaps use the nearest
observed anchor solely as an optimizer starting point. The body fit still uses
current visible landmarks. These starting estimates are identified per frame and
counted in the report; a player with no usable anchors anywhere fails explicitly.
This fixes the room videos where the second player enters after recording starts.
Completed results for matching inputs and segment settings are restored in the UI.

## Outputs and CLI

`session-report.json` records completion or failure. `session-config.json` records
inputs and settings; `synchronization.json` records timing evidence. Per-camera
ball detections, poses, HMR2 predictions and logs are retained. `replay/` contains
meshes, scene metadata, source clips, annotated ball clips, `ball-3d.csv` and the
portable `review/` serve page. Serve corrections remain in the browser until
exported, matching the existing standalone reviewer.

The configuration downloaded from the UI can be run again into a new directory:

```bash
.venv/bin/python scripts/analyze_two_camera.py \
  --config path/to/session-config.json --output artifacts/sessions/new-run
.venv/bin/python scripts/serve_replay.py \
  --directory artifacts/sessions/new-run/replay --port 8506
```

Uploaded sources are retained under `artifacts/ui/uploads/`; local sources must
still exist when a saved configuration is rerun.

## Executed validation

On October 24, 2026, an actual two-camera TT3D clip was run through all stages:
`artifacts/combined-smoke-config.json` → `artifacts/combined-smoke-run/`.
Calibration corners for this developer smoke run were projected from the supplied
camera calibrations; no reference ball track was used by the pipeline. This checks
integration, not the accuracy of a user's manual corner measurements.

- Both real recordings decoded and normalized from different source frame rates.
- BlurBall, the trained serve model and HMR2 executed on Apple MPS; MediaPipe on CPU.
- 59 body frames exported with two SMPL meshes each; 20 of the 60 analyzed frames
  had accepted triangulated ball observations. Missing observations stayed missing.
- Residual camera offset: +7.57 ms. Median ball reprojection error: 0.80 px.
- Median visible-body reprojection error improved from 31.80 px to 2.77 px.
- No serve candidates were found in this two-second rally segment. This does not
  evaluate serve recall; the existing serve evaluation is documented in `SERVES.md`.
- Total processing: 56.9 seconds. This is a local measurement, not a runtime guarantee.
- Browser checks confirmed rendered meshes, playback, both source videos, exports
  and the linked serve reviewer with portable source URLs.
- Python regressions: 81 passed. Placement regressions: 12 passed. The new tests
  cover calibration, positive/negative clock offsets, overlap rejection, reversed
  player image sides, packaging, missing ball preservation, model-stage failure
  and coexistence of the combined and existing Streamlit tools. Source-preview
  controls were also exercised in the pinned NumPy environment. The original HMR2
  command's default input path was rerun into a separate output folder successfully.

## Limits

The automatic table setup was also checked on both newly uploaded 4K room videos.
Both views produced a full-table outline and passed approximate demo calibration
without entered coordinates. Regression checks after this change: 120 Python
tests and 15 JavaScript tests passed, including a net-crossing segmentation test,
source-resolution click mapping, incomplete/reset selections and existing placements.

The new arbitrary-upload path assumes fixed cameras and a visible full table in
both views. The original specialized handheld-footage experiment and its scripts
remain available; its hard-coded motion masks are not reused on arbitrary uploads.
Pinhole calibration assumes centered principal points, square pixels and no lens
distortion. Audio uses the first 120 seconds with a ±30-second coarse search; it
does not correct clock drift or rolling shutter. Low visual evidence fails instead
of accepting an audio-only clock for 3D. Body shape, hidden joints and table
calibration remain estimates. Reprojection agreement is not independent metric
accuracy. Serve detection still does not establish toss height or legality.
