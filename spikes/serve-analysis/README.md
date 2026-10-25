# Trophy: local table-tennis ball tracking

> This standalone recorded-video prototype lives in `spikes/serve-analysis`.
> Run its commands from this directory so its `trophy` package stays separate
> from the platform services. See [CHECKOUT.md](CHECKOUT.md) for demo inputs,
> checkpoint setup, checks, and the source-only publication boundary.

## Combined two-camera upload and analysis

Open [the local app](http://127.0.0.1:8501/) and choose **Two-camera · Combined
analysis**. Upload both angles of the same rally, check the automatically segmented
table and initialized player regions, and select **Analyze both cameras**. Drag
corner markers if the outline needs adjusting. The workflow connects
camera synchronization, BlurBall detections, serve detection and actual 4D Humans
meshes in one interactive 3D replay, with synchronized source footage and linked
serve corrections/export. Existing single-camera tracking and standalone serve
review remain in the second tab; existing demo commands still work.

```bash
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

The upload workflow requires fixed cameras, visible table corners in both views,
and the existing local model environments/assets. Audio initializes synchronization;
silent footage can use an entered coarse offset. Both modes refine alignment using
measured ball detections. See [COMBINED_ANALYSIS.md](COMBINED_ANALYSIS.md) for setup,
calibration, CLI use, executed integration checks and limits.

## Serve detection and source-video review

The recorded-video serve spotter uses a trained temporal video model alongside
ball tracking. It merges evidence from the two cameras and exports reviewable
serve candidates. The review page supports synchronized video, slow motion,
player crops, corrections and JSON export. See [SERVES.md](SERVES.md) for the
trained local model, commands, evaluation, provenance and limitations. Serve
recognition does not establish toss height or legality.

Toss height/direction review, rule references, 3D overlays, and evidence exports
are described in [SERVE_LEGALITY.md](SERVE_LEGALITY.md). Current phone footage
still needs validated camera geometry and timing for supported fault decisions.

A recorded-clip technical prototype using the **actual pretrained BlurBall model**, running natively on Apple Silicon with PyTorch MPS or CPU. No training, hosted inference, scoring, or live streaming. The two-camera replay triangulates the ball and reconstructs articulated solid player figures with rackets from real footage.

## Two-camera 3D reconstruction

**Your footage with 4D Humans:** the first HMR2 + BlurBall replay is at
[http://127.0.0.1:8505/](http://127.0.0.1:8505/) while its server is running.
It reconstructs original seconds 8.00–10.87 of the supplied two-camera recordings
with actual SMPL meshes, source overlays and a measured-ball replay. See
[HMR2_REPLAY.md](HMR2_REPLAY.md) for executed results, reproduction and accuracy limits.

Open [the tested multi-view demo](http://127.0.0.1:8503/) while its local server is running. Two official TT3D rallies were tested against reference ball tracking: held-out median ball errors **2.6 cm and 2.5 cm**, with 95th-percentile errors **5.4 cm and 8.6 cm**. Body motion and wrist-attached racket orientation are estimates, with no 3D ground truth. The replay supports orbiting, recording-camera views, slow motion, paired source playback, and solid articulated figures.

```bash
bash scripts/bootstrap_replay.sh
bash scripts/build_multiview_demo.sh
.venv/bin/python scripts/serve_replay.py --directory artifacts/multiview/demo --port 8503
```

See [MULTIVIEW.md](MULTIVIEW.md) for sources, exact execution commands, measured accuracy, tests, and limitations. Calibration, timestamp alignment, real model predictions, and reference evaluation are separate; reference ball positions do not drive the simulation.

## Placement heatmaps

The [placement analysis panel](http://127.0.0.1:8503/#placementHeading) shows each player's estimated shot landings. Customize time ranges, court zones, heat spread, colours, player names/ends, and detection thresholds; review/correct contacts; save presets; export PNG and CSV. The sample has three included placements per player. See [PLACEMENTS.md](PLACEMENTS.md) for the algorithm, executed browser checks, CLI, and limits.

## 3D replay demo

A rotatable replay of the real sample is available at [http://127.0.0.1:8502/](http://127.0.0.1:8502/) while its server is running. It includes simple pose-driven figures, the fitted ball path, synchronized original video, timeline/slow motion, and downloadable MP4s from three viewpoints. Depth and hidden joints are explicitly inferred.

```bash
bash scripts/bootstrap_replay.sh
bash scripts/build_demo.sh
.venv/bin/python scripts/serve_replay.py
```

See [REPLAY.md](REPLAY.md) for executed results, reconstruction assumptions, commands and limitations.

## Setup

Python **3.12**, native arm64 macOS. Setup creates `.venv` and installs the pinned dependency lock. It uses an existing Python 3.12 or the Codex bundled Python; set `TROPHY_PYTHON` to select another interpreter.

```bash
cd spikes/serve-analysis
bash scripts/bootstrap.sh --sample
```

For an existing environment, download or verify assets separately:

```bash
.venv/bin/python scripts/setup_assets.py --sample
```

The unmodified upstream source is vendored at a pinned commit. The official 6 MB checkpoint is checksum-verified before loading. `imageio-ffmpeg` provides a native FFmpeg binary; no global FFmpeg installation is required. See [PROVENANCE.md](PROVENANCE.md) for source inspection, licensing, exact preprocessing, decoding, and adaptations.

## CLI

```bash
.venv/bin/python -m trophy samples/official-00-001.mp4 \
  --output artifacts/my-first-run --device auto --threshold 0.7 \
  --max-frames 600 --max-duration 20
```

Use a new or empty output directory for each run. `--device auto|mps|cpu` selects the device. `auto` chooses MPS when available; the first real temporal window warms up and verifies model execution. If a model operation fails on MPS, analysis fails explicitly; choose `cpu` to run separately. Do not set `PYTORCH_ENABLE_MPS_FALLBACK=1` (the adapter rejects it). CPU preprocessing and video encoding remain explicit even during GPU model inference.

The default cap is 600 source frames. `--max-duration` additionally caps the analyzed prefix. Output previews include just that prefix. Use `--max-frames` to increase it for longer clips. Runtime memory is bounded by the temporal buffers plus small per-frame prediction records; the source video is decoded twice rather than held in RAM.

## Local UI

```bash
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

Open [http://127.0.0.1:8501](http://127.0.0.1:8501). Select a local path or upload a clip; choose device, threshold, and limits; then start analysis. Original and annotated previews, progress, metrics, and file downloads appear in the same page. Results persist under `artifacts/ui/`. The server binds to localhost by default in `.streamlit/config.toml`.

## Outputs

- `annotated.mp4`: H.264 / yuv420p / faststart at source reported average FPS. Green marker, short yellow trail, blue heatmap-derived blur streak, and score. Missing detections draw no ball marker and clear the trail.
- `original.mp4`: browser-playable unannotated preview of the same analyzed frames. Both previews omit audio. Odd dimensions are padded by at most one pixel on the right/bottom.
- `detections.csv` and `detections.json`: one row for **every source frame**, zero-based frame index, decoder timestamp, display-oriented original-image x/y pixels, detection status, component peak score, heatmap peak, component mass, blur orientation/length, temporal-context count, and duplicate mapping. Missing coordinates/scores are null in JSON and blank in CSV.
- `report.json`: selected device, versions, model/source identity, source resolution/FPS/rotation, coverage, synchronized model timing, CPU stage timing, model setup and warmup, total processing FPS, and verified output frame count/codec/FPS.

The threshold applies to sigmoid heatmap pixels, matching upstream. The score is the selected component's peak, **not a calibrated confidence**. Candidate ranking uses upstream's summed component heatmap mass. Blur length is the full PCA extent in source pixels, estimated from the thresholded heatmap. Coverage only measures how often a detection exists; it is not accuracy.

The three-input/three-output model uses every complete chronological window at stride one. First/last frames use available real output heads. Clips with fewer than three unique frames export missing detections with `insufficient_temporal_context`, without padding or extrapolation. Exact consecutive duplicate frames are removed from model windows and mapped back to their original playback indices; near duplicates remain.

Portrait and rotation metadata are supported for decode/render/export. Full-frame letterboxing avoids cropping portrait input. Tracking accuracy on portrait phone footage still needs validation. Constant-frame-rate clips are the initial target: variable-frame-rate source timestamps remain in the data exports, while previews use the source reported average frame rate.

## Tests and reproducible checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke.py --device mps
.venv/bin/python scripts/compare_devices.py samples/official-22-003.mp4 \
  --output artifacts/device-comparison.json --starts 0,30,60
.venv/bin/python scripts/validate_sample.py \
  --output artifacts/official-22-mps \
  --video samples/official-22-003.mp4 --labels samples/official-22-003.csv
```

Unit tests use clearly named model fixtures to isolate temporal alignment and export behavior. Real inference validation uses the official checkpoint and released real MP4 footage. Test cases cover RGB/normalization, chronological channel order, affine round trips, thresholded missing detections, boundary windows, duplicates, short clips, rotation metadata, frame/duration limits, CSV/JSON consistency, encoded FPS/frame count, and encoding failure.

See [VALIDATION.md](VALIDATION.md) for executed commands, measurements, observed failures, and readiness assessment. A small official test clip is useful evidence of integration, not a substitute for a 10–20 second recording from the intended phone/camera placement.
