# Executed validation — October 23, 2026 (Los Angeles)

The prototype **does track a real white table-tennis ball** through the held-out rally. The full CLI pipeline, browser playback, local UI analysis, CPU inference, MPS inference, and export consistency checks have all been executed on this Mac. This is evidence from one small official test clip, not an estimate of general phone-camera accuracy.

## Machine and environment

Native arm64 macOS 26.6.2, Apple M5 Pro (15 CPU cores / 16 GPU cores), 24 GB unified memory. About 737 GiB disk was available at inspection. System Python was 3.14.7, with no system uv, FFmpeg, or ffprobe. We reused the bundled native Python 3.12.14 to create the isolated `.venv`.

Working versions: PyTorch 2.9.0, NumPy 1.26.4, OpenCV headless 4.11.0.86, PyAV 16.0.1, Streamlit 1.50.0, PyYAML 6.0.3, imageio-ffmpeg 0.6.0 with native arm64 FFmpeg 7.1, pytest 8.4.2, uv 0.13.5. Every application dependency is pinned in `requirements.lock`; `uv pip check` reports compatible packages. Environment details are in `artifacts/environment.json`.

The initial package download was unusually slow. The completed installation used official PyPI wheels verified against their published SHA-256 hashes. The normal setup helper uses the pinned dependency lock and ordinary uv installation.

## Source and model verification

The unmodified upstream snapshot is pinned to `2f0f5496f7ba4b5b1a36790749935121b2ce972d`. All vendored file checksums were checked after implementation. Official `blurball_best` checkpoint SHA-256:

`3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`

The checkpoint loads safely with `weights_only=True` and `strict=True` into the original architecture. It contains `model_state_dict`, losses, prior evaluation metrics, and epoch. The adapter handles the original config's mixed dictionary/attribute access without modifying the model.

The first smoke test used the first three real frames of official `00/001`. It returned three 288×512 heatmaps on MPS, with centers around (620.6, 406.0), (620.7, 406.4), (620.6, 406.8), close to the official labels. First cold warmup was 2138 ms; the next measured forward was 28.6 ms. The raw smoke output is `artifacts/smoke-mps.json`.

MPS is built and available. The full forward and sigmoid executed successfully on MPS with CPU fallback disabled. **No unsupported model operations or model CPU fallbacks were observed.** RGB conversion, affine preprocessing/normalization, connected components/PCA, video decoding, drawing, and encoding are explicitly CPU stages. This is GPU model inference, not a claim that the whole application runs on GPU.

## Full real clip results

Official `22/rallies_videos/003.mp4` is in the repository's configured **test** split. It has 272 real frames, 1280×720 resolution, and a white ball in an indoor scene. Frame rate reported by OpenCV/average_rate is 59.720499 FPS; the container base rate is 60000/1001 (59.940060). One irregular frame interval makes the average differ from the base rate. Exports retain all 272 frames and the source reported average rate; per-frame CSV/JSON retain source timestamps. CFR preview timestamps are normalized to that average, so they do not preserve every irregular source interval. The output duration is about 4.55 seconds.

The exact commands executed were:

```bash
.venv/bin/python scripts/smoke.py --device mps
.venv/bin/python -m trophy samples/official-22-003.mp4 \
  --output artifacts/official-22-mps --device mps --threshold 0.7 --max-frames 600
.venv/bin/python -m trophy samples/official-22-003.mp4 \
  --output artifacts/official-22-cpu --device cpu --threshold 0.7 --max-frames 600
.venv/bin/python scripts/validate_sample.py --output artifacts/official-22-mps \
  --video samples/official-22-003.mp4 --labels samples/official-22-003.csv
.venv/bin/python scripts/compare_devices.py samples/official-22-003.mp4 \
  --output artifacts/device-comparison.json --starts 0,90,230
.venv/bin/python -m pytest -q
```

Output directories are intentionally protected against overwrite; use fresh names when repeating commands.

| Measurement | Full MPS run | Full CPU run |
|---|---:|---:|
| Analyzed source frames | 272 | 272 |
| Temporal windows (stride 1) | 270 | 270 |
| Detections | 264 | 264 |
| Detection coverage (not accuracy) | 97.06% | 97.06% |
| Mean model forward + sigmoid | 22.50 ms | 247.81 ms |
| Median model latency | 22.39 ms | 242.56 ms |
| P95 model latency | 23.68 ms | 270.27 ms |
| End-to-end processing | 30.96 FPS | 3.92 FPS |

MPS timings synchronize before and after the measured forward. Model-only timings exclude transfers, warmup and loading. End-to-end timing includes model load, a real-window warmup, two decode passes, preprocessing, inference, postprocessing, original and annotated video encoding, exports, and decoding both outputs for verification. It starts at the pipeline function and excludes Python process startup/imports, dependency setup, weight downloads and UI idle time.

The MPS run took 8.784 seconds overall. Measured stage totals: decode 0.195 s; preprocessing 0.397 s; input transfer/dispatch 0.281 s; model 6.076 s; output transfer 0.082 s; postprocessing 0.305 s; render/encode including the second decode pass 0.805 s; export verification 0.320 s. Model setup was 0.125 s and warmup wall time 0.172 s. Small remaining overhead includes progress callbacks, bookkeeping and report assembly. Source videos, result MP4s and per-frame data are available under `samples/` and `artifacts/official-22-{mps,cpu}/`.

Both encoded previews were actually decoded and verified: 272 frames, H.264, yuv420p, 1280×720, 59.720499 FPS. The annotated preview also played successfully in the browser.

## Label comparison and visual inspection

Official midpoint CSV labels align one-to-one with all 272 original frames at 1280×720. Using a **10-source-pixel** localization tolerance:

- 262 correctly localized detections.
- 2 incorrectly localized detections, at frames **0 and 1**, about **23.5 and 26.1 pixels** from the labels. Each counts as both a false positive and false negative in the matching statistics.
- 6 missed label-visible frames: **13, 14, 15, 18, 19, 30**.
- 2 correctly missing detections on label-invisible frames **16 and 17**.
- Precision 99.24%; recall 97.04% on this clip and tolerance only.
- Median localization error among visible detected frames: **1.01 px**; P95 **2.69 px**; maximum **26.14 px**. This conditional error statistic omits missed frames.

I inspected frames 0, 1, 12, 34, 68, 102, 136, 169, 203, 237 and 271 in the full-frame comparison sheet, and close-ups of 0, 1, 12–19, 30 and 150. The rally tracks the white ball across the table in both directions. The largest mistakes are near the serve preparation: early predictions select a paddle/hand-region spot rather than the ball in the open hand. Several toss frames near the player's hand/face are missing. No positions were filled into those missing frames. Official visibility labels around hands/occlusions can themselves be ambiguous.

Inspection artifacts:

- `artifacts/official-22-mps/validation-contact-sheet.jpg`: green predicted centers, magenta official centers, beginning/middle/end plus worst errors.
- `artifacts/official-22-mps/failure-crops.jpg`: magnified serve errors and a correct mid-rally detection.
- `artifacts/official-22-mps/label_validation.json` and `label_errors.json`: matching summary and every frame's error.

## CPU/MPS agreement

Three identical real temporal windows (starts 0, 90, 230) were run on both devices. All nine output detection statuses agreed. Maximum absolute heatmap difference was **5.96×10⁻⁷**; position differences were below **0.000065 px** for those windows.

The entire exported 272-frame CPU and MPS runs were also compared: **zero detection-status disagreements**, maximum selected-position difference **0.000146 px**, mean **0.000028 px**. See `artifacts/device-comparison.json` and `artifacts/full-clip-device-comparison.json`. These checks establish agreement for these inputs, not bitwise equality for arbitrary footage.

## UI and automated tests

The localhost Streamlit server was started and its health endpoint returned `ok`. The UI's initial render was checked using Streamlit AppTest. A real browser analysis of the full held-out clip used **auto → MPS**, completed all 272 frames, displayed 97.1% coverage, 24.3 ms mean model latency and 29.4 FPS end to end, and produced playable original/annotated previews and download controls. The annotated video was played in-browser. UI run output: `artifacts/ui/20261023-191841-23700617/`; screenshot: `artifacts/ui-playback.png`.

The automated suite passes **17 tests**. It covers temporal boundary coverage, RGB/normalization and channel ordering, affine mapping across landscape/portrait/4:3, compatibility with the upstream 16:9 transform, weighted connected components and missing/padding detections, frame/CSV/JSON/video alignment, exact duplicates, clips shorter than three unique frames, duration/frame limits, actual rotation metadata, invalid inputs, encoding failure, unavailable/corrupt weights, and explicit rejection of MPS CPU fallback. Unit fixture videos/model outputs are used only for isolated software checks, never as evidence of real-ball tracking. Real evidence is from the checkpoint and official MP4 above.

An initial rotation test fixture did not actually carry rotation metadata with FFmpeg 7.1's old `-metadata rotate=90` syntax. It was corrected to `-display_rotation 90`, after which the rotated decode/export check passed. The final code does not modify upstream source.

## Readiness

**Yes for the next controlled experiment; no evidence yet for robust phone-camera coverage.** The pretrained model tracks the rally well enough to justify testing a short landscape phone recording, then a bounded live-stream experiment around 30 FPS. At stride one the model averages roughly 44 windows/s and the full offline workflow roughly 31 source FPS, so this implementation does **not** keep up with this roughly 60 FPS source in real time. Live work will need measured ingest latency, bounded queues and an explicit cadence strategy; none has been implemented here.

Remaining risks include serve/hand occlusion, false components, small distant balls, lighting, near-duplicate re-encoding, camera motion, portrait domain shift, uncalibrated scores, and heatmap-derived blur estimates. Portrait rotation/export is tested; real portrait tracking accuracy is not. A 10–20 second clip from the intended phone position remains the most useful next validation, without retraining or expanding into scoring/refereeing.
