# Trophy: build integration cards (perception + possession)

Prepared 2026-10-22 for Trophy. These are integration research notes. They cover the following stack:

```
phones (PWA, 720p WebRTC ~30 fps iOS / up to 60 Android; 1080p local recordings)
   -> laptop (NVIDIA GPU, Python)
```

**How the facts were checked:**
- **GitHub:** READMEs, docs and source were read through `gh api` on 2026-10-22, including the default `develop` or `main` branch. Issues were read with `gh issue view`.
- **PyPI:** versions come from `pypi.org/pypi/<pkg>/json`.
- **Roboflow Universe:** pages return 403 to curl and WebFetch, so they were opened in the built-in browser on 2026-10-22 and their text was read. These are marked **(opened)**.
- **Tags:** **[V]** means verified in source or docs. **[E]** means my estimate or extrapolation; do not quote it as evidence.

---

## 0. Environment plan: read this first (version pins and conflicts)

### Current versions (PyPI, 2026-10-22)

| Package | Latest | Released | Python | Research baseline pin |
|---|---|---|---|---|
| rfdetr | 1.11.2 | 2026-10-04 | >=3.10 | `rfdetr[train]==1.11.2` |
| trackers | 2.6.1 | 2026-09-25 | >=3.10 | `trackers==2.6.1` |
| supervision | 0.31.1 | 2026-10-20 | >=3.10 | `supervision==0.30.9` (2026-10-08). 0.31.x is under 1 week old, and `inference` 1.8.x requires `<0.31`. |
| rtmlib | 0.0.16 | 2026-08-04 | >=3.10 | `rtmlib==0.0.16` |
| onnxruntime-gpu | 1.31.0 | 2026-10-09 | >=3.11 | Match it to your CUDA/cuDNN; see the gotcha below |
| inference / inference-gpu | 1.8.1 | 2026-10-19 | >=3.10,<3.14 | Only if you run Universe models by ID: `inference-gpu==1.7.4` or `1.8.0` |
| inference-models | 0.39.5 | 2026-10-20 | >=3.10,<3.14 | Pulled in by inference |
| aniposelib | 0.8.0 | 2026-05-07 | n/a | `aniposelib==0.8.0` |
| pose2sim | 0.10.49 | 2026-07-10 | >=3.11 | Reference / offline only |
| baseballcv | 0.1.28 | 2026-10-22 | 3.11+ | Optional; pulls in ultralytics (AGPL) |

Recommended: **Python 3.11 or 3.12** in one venv for the live pipeline (rfdetr + trackers + supervision + rtmlib + onnxruntime-gpu).

### Conflicts found in the dependency metadata [V]

1. **`inference-gpu` 1.8.1 pins strictly.** It requires the following, so it can fight with rfdetr's torch and with a newer onnxruntime-gpu:
   - `supervision<0.31`
   - `onnxruntime-gpu<1.22`
   - `inference-models[onnx-cu12,torch-cu124]==0.39.4`, which means torch for **cu124**

   **Recommendation:** keep `inference` **out of the live venv**. Use Universe for *datasets*, then fine-tune RF-DETR locally (section 8). If you must run a Universe-hosted model by ID, put it in a second venv or process.
2. **rtmlib depends on the CPU `onnxruntime` package.** If both `onnxruntime` and `onnxruntime-gpu` are installed, the CUDA provider can be missing or shadowed.
   - Install rtmlib, then `pip uninstall -y onnxruntime` and `pip install onnxruntime-gpu==<match>`. Alternatively, install with `pip install rtmlib --no-deps` plus opencv and numpy.
   - Verify with `onnxruntime.get_available_providers()`, which must contain `CUDAExecutionProvider`.
3. **onnxruntime-gpu on Windows needs CUDA 12.x plus cuDNN 9.x DLLs on PATH.** A GPU torch wheel bundles its own cuDNN, but ORT does not use it.
   - Symptom: `device='cuda'` runs at CPU speed with 0 MB of VRAM used, plus a garbled warning (rtmlib issue #46 [V]: "need cuda 12.x and cudnn 9.x"; the user also had to add `zlibwapi.dll`).
   - Pre-flight check: watch `nvidia-smi` while running.
4. **torch on Windows from plain `pip install torch` is CPU-only.** Install from the PyTorch CUDA index *before* `rfdetr`. Then check `torch.cuda.is_available()`.
5. **supervision >= 0.30 no longer installs OpenCV** (changelog [V]). Install `opencv-python` explicitly, exactly one OpenCV wheel family.
   - Note that rtmlib wants `opencv-python` + `opencv-contrib-python`. Having both is the usual conflict, so install only `opencv-contrib-python` if possible.
6. **supervision 0.31.0 removed `sv.ByteTrack`** [V]. Use `trackers.ByteTrackTracker`. 0.31.0 also removed the `supervision.keypoint` module (use `supervision.key_points`).
7. **rfdetr requires `transformers>=5.1,<6`** [V]. roboflow/sports' SigLIP code (`SiglipVisionModel`, `AutoProcessor`) should still work under transformers 5, but **test it Thursday night**.

---

## 1. RF-DETR (roboflow/rf-detr)

| | |
|---|---|
| Repo | https://github.com/roboflow/rf-detr. Apache-2.0, 9,871 stars, pushed 2026-10-22, default branch `develop` [V] |
| Install | `pip install "rfdetr[train]==1.11.2"`. Training needs the `train` extra. Add `rfdetr[onnx]` or `rfdetr[tensorrt]` for export. `rfdetr[plus]` adds the Atto/Femto/Pico/XL/2XL sizes, which use the **PML 1.0 license and require a Roboflow account** [V]. |
| Weights | Auto-download on first construction from `https://repo.roboflow.com/rfdetr` into `~/.roboflow/models`. Override with `RF_HOME` (or `ROBOFLOW_HOME`). To pre-seed the cache for offline use, copy the `.pth` files there (MD5-checked) [V, FAQ]. |

### Sizes

COCO val2017 accuracy. Latency is measured on a **T4 with TensorRT 10.4 FP16, batch 1** [V].

| Class | AP50:95 | T4 ms | Input | License |
|---|---|---|---|---|
| `RFDETRNano` | 48.4 | 2.3 | 384 | Apache |
| `RFDETRSmall` | 53.0 | 3.5 | 512 | Apache |
| `RFDETRMedium` | 54.7 | 4.4 | 576 | Apache |
| `RFDETRLarge` | 56.5 | 6.8 | 704 | Apache |
| `RFDETRXLarge` / `2XLarge` | 58.6 / 60.1 | 11.5 / 17.2 | 700 / 880 | PML 1.0 (plus) |
| `RFDETRSeg{Nano..2XLarge}` | 40.3 to 49.9 mask | 3.4 to 21.8 | | Apache |
| `RFDETRKeypointPreview` | 71.8 (COCO-17 kp) | 9.7 | 576 | Apache |

`RFDETRBase` is legacy; the FAQ says to use Small.

### COCO class IDs we need [V]

From `src/rfdetr/assets/coco_classes.py`. This is a dict keyed by the **original COCO category id**, not 0-79:

| id | class |
|---|---|
| 1 | person |
| 34 | frisbee |
| 37 | sports ball |
| 39 | baseball bat |
| 40 | baseball glove |

COCO has no cone, beanbag, pin or hoop class. Note that the detection.md FAQ text says "indexed 0-79", which contradicts the dict. **Print `detections.class_id` on a test image before hard-coding the IDs.** For fine-tuned models, use `detections.data["class_name"]`.

### Inference entry point [V, `detr.py` signature]

```python
model.predict(images, threshold=0.5, include_source_image=True, antialias=False)
```

- **`images`:** a path, URL, PIL image, **RGB** `np.ndarray`, or a `torch.Tensor` (C,H,W, values 0-1). A **list** gives a list of results, so 2-3 phones can be batched in one call.
- **Returns** `sv.Detections` with:
  - `xyxy` in source-image pixels
  - `confidence`
  - `class_id`
  - `data["class_name"]`
  - `metadata["source_image"]` (when `include_source_image=True`; pass `False` on the hot path to avoid copying)
- **Speed paths:**
  - `model.inference(compile_backend="cudagraph", batch_size=1, dtype="float16")`
  - `model.inference(compile_backend="inductor", ...)`
  - `model.export(format="tensorrt")` builds the TensorRT engine in-process.
- **OpenCV frames are BGR.** Call `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)` first; the docs examples do this.

### Measured speed (proven evidence only)

- **Official:** T4 TensorRT FP16, see the table above.
- **opendetect benchmarks** (https://opendetect.readthedocs.io/en/latest/guides/benchmarks.html; hardware named in rtmlib issue #71 as **RTX 4090 (Ti), Linux** [V]). End-to-end pipeline FPS:

  | Model | ONNX CUDA EP | TensorRT FP16 |
  |---|---|---|
  | RF-DETR-n | 128 | 349 |
  | RF-DETR-s | 81 | 225 |
  | RF-DETR-m | 63 | 190 |
  | RF-DETR-l | 37 | 127 |

  YOLOX-m on CUDA runs at 70 for comparison.
- **RF-DETR cookbook** `docs/cookbooks/export-cuda.ipynb`, NVIDIA L4: the RFDETRSmall CUDA-graph path takes **5.5-5.6 ms forward at batch 1** [V, from the results text; the notebook's output cells are not stored].
- **No laptop-GPU benchmark exists** (web search 2026-10-22). [E] A laptop RTX 4070/4080 is roughly 1/3 to 1/2 of a 4090. Expect about 25-40 FPS for RF-DETR-S through PyTorch or ONNX, and 70-110 FPS with TensorRT FP16. **Measure on Thursday.**

### Fine-tune API [V, `docs/learn/train/index.md` + training-parameters]

```python
from rfdetr import RFDETRSmall
m = RFDETRSmall()
m.train(dataset_dir=..., epochs=100, batch_size="auto", lr=1e-4, output_dir=...)
```

- **Defaults:** `epochs=100`, `batch_size=4`, `grad_accum_steps=1`, `use_ema=True`, `early_stopping=False`.
- **Dataset layout:** auto-detected. Either COCO (`train/ valid/ test/` folders, each with `_annotations.coco.json`) or YOLO (`data.yaml`).
- **Output:** `checkpoint_best_total.pth`. Load it with `RFDETRSmall(pretrain_weights=".../checkpoint_best_total.pth")` or `RFDETR.from_checkpoint(...)`.
- **Fine-tuning drops the COCO classes** (FAQ). To keep `person`, label persons in your set too, or **run two models**: COCO for persons plus a fine-tuned model for the ball and objects.

### Training time evidence [V]

From the cookbook `fine-tune_detection.ipynb`:
- About 1,500 images x 50 epochs takes about 10-25 min on an RTX 3090 / A10 / T4.
- Traffic set (~1,400 images): 15-20 min for 50 epochs. PPE set (~2,600 images): 20-30 min.
- Small sets (a few hundred images) improve over epochs 1-20 and plateau around epochs 30-50.
- FAQ: on an L4, `batch_size=16` ran about 27% faster than `4x4` accumulation.

[E] **About 300 images x 50 epochs is roughly 5-10 min on a laptop RTX 40-series.** Budget 15 min including validation.

### Gotchas (from issues)

- **#497:** input is **square only**; 1280x720 is letterboxed. Resolution must be a multiple of 32 for current detection checkpoints. Changing resolution away from the default can break position-embedding loading. For small balls, use SAHI-style tiling (`sv.InferenceSlicer`) or a higher `resolution`.
- **#170 / #650:**
  - README latencies are TensorRT FP16. Plain `predict()` in FP32 is much slower.
  - ONNX's CUDA EP "does not handle transformers well". Maintainers recommend TensorRT.
  - Many slow reports come from comparing at the wrong resolution. RF-DETR-N is meant to run at 384, not 640.
- **#879:** no fixed minimum object size. Maintainers suggest cropping/tiling for small objects.
- **Frames without a ball:** `sports ball` from COCO is weak on blurred or small balls. Plan to fine-tune a ball class on your own frames, or use the soccer/football Universe sets.

### Pipeline plug-in

One process holds two models:
- **`RFDETRSmall`** (COCO): person, sports ball, frisbee, bat, glove.
- **`RFDETRSmall`** fine-tuned per sport: ball, hoop, board, hole, bag, cones and pins.

Batch the phones per tick with `predict([f1, f2, f3])`. Output is `sv.Detections`, which goes to trackers (section 2), then rtmlib (section 4) on the person boxes.

---

## 2. roboflow/trackers + supervision

### trackers

| | |
|---|---|
| Repo | https://github.com/roboflow/trackers. Apache-2.0, 3,958 stars, pushed 2026-10-22; release 2.6.1 on 2026-09-25 [V] |
| Install | `pip install trackers==2.6.1`. This needs `numpy>=2.0.2`, `supervision>=0.26.1` and `opencv-python>=4.8`. The `[detection]` extra pulls `inference-models`, and `[tune]` adds Optuna. |
| Algorithms | SORT, ByteTrack, OC-SORT, BoT-SORT (camera-motion compensation), C-BIoU, and McByte (needs SAM/Cutie and torch) |

**Entry point:**

```python
ByteTrackTracker(lost_track_buffer=30, frame_rate=30.0, track_activation_threshold=0.7,
                 minimum_consecutive_frames=2, minimum_iou_threshold=0.1,
                 high_conf_det_threshold=0.6, iou=None)
```

These defaults are from source [V].
- `tracked = tracker.update(detections, timestamp=None)` returns `sv.Detections` with `tracker_id`. **Unconfirmed tracks come back as `-1`.**
- `tracker.reset()` between clips.

**Evidence** (HOTA, default parameters; README [V]):

| Tracker | SportsMOT | SoccerNet |
|---|---|---|
| ByteTrack | 73.0 | 84.0 |
| BoT-SORT | 73.8 | 84.5 |
| C-BIoU | 73.1 | 82.6 |
| McByte | 76.5 | 85.0 |

**Gotchas:**
1. **Variable frame rate is supported.** Pass the **capture** timestamp in seconds (`timestamp=`). Timestamps must be non-decreasing; a backwards timestamp **skips the whole step** and outputs `-1` IDs.
   - `lost_track_buffer` is in 30-fps units.
   - Set `frame_rate` to the true rate: 30 for iOS, 60 for Android.
   - WebRTC frames arrive with jitter, so use the RTP or capture timestamp, not the arrival time.
2. **ByteTrack ignores `class_id`.** Association is class-agnostic (source has no class handling [V]). **Run one tracker per class family**: one for persons, one for the ball or objects.
3. **Small, fast balls do not overlap frame to frame.** Plain IoU gives zero similarity. Either:
   - use `iou=BIoU(buffer_ratio=...)` or `DIoU` (docs: BIoU is "for very small or very fast objects where raw boxes rarely overlap"), or
   - skip MOT for the ball and use a single-object gate tracker (roboflow/sports `BallTracker`, or the aarnavshah12 motion-gate design in section 5).
4. **`track_activation_threshold=0.7` is too high for ball detections**, which often score 0.3-0.6. Lower it for the ball tracker, or the ball never gets an ID.
5. ByteTrack warns if you pass `frame=`, because it does not use pixels.

### supervision (pin 0.30.9)

**PolygonZone** [V, source]:

```python
sv.PolygonZone(polygon: (N,2) int array, triggering_anchors=(Position.BOTTOM_CENTER,), require_all_anchors=True)
```

- `.trigger(detections, coord_transform=None)` returns a bool array.
- **Requires at least 3 vertices.** Coordinates are image pixels.
- Use `BOTTOM_CENTER` for players' feet and `CENTER` for the ball.
- `require_all_anchors=False` gives "any anchor inside". That is the cornhole "any part on the board" rule when using corner anchors.

**LineZone** [V, source]:

```python
sv.LineZone(start: sv.Point, end: sv.Point, triggering_anchors=(TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT), minimum_crossing_threshold=1)
```

- `.trigger(detections)` returns `(crossed_in, crossed_out)` and keeps `in_count` / `out_count`.
- **Needs `tracker_id`.** Negative IDs are ignored.
- The default is all 4 box corners, so a crossing counts only when the **whole box** has crossed. That matches "whole ball over the line".
- Counting is **limited to the segment's perpendicular band**: only between `start` and `end` (`_calculate_region_of_interest_limits`). So a LineZone between two tapped cone bases is a cone goal.
- `minimum_crossing_threshold` debounces flicker (fixed in #2600).

**Annotators:** `BoxAnnotator`, `LabelAnnotator`, `TraceAnnotator`, `PolygonZoneAnnotator`, `LineZoneAnnotator`, `sv.KeyPoints` + `EdgeAnnotator` / `VertexAnnotator`.

**Homography:**
- supervision has **no public `ViewTransformer`**. It is in `roboflow/sports/sports/common/view.py` and in `supervision/examples/speed_estimation`.
- The class is about 30 lines: `cv2.findHomography(src, tgt)` + `cv2.perspectiveTransform`. Copy it, or call cv2 directly.
- New in 0.31: `coord_transform` on `trigger()` handles a moving camera. Not needed with tripods.

**Timers:** `FPSBasedTimer` (zone dwell time, as in the 3-second violation demo) is **example code** in `supervision/examples/time_in_zone/utils/timers.py`, not library API.

### Pipeline plug-in

- Each phone gets its own `ByteTrackTracker` for persons and its own ball tracker.
- Zones and lines are defined per phone in image space from the PWA taps.
- Metric decisions (out-of-bounds margin, line of scrimmage, rusher distance) use `cv2.perspectiveTransform` of the anchor points into field metres. Use **feet / box bottom-center** for people. For the ball, use the **bounce point**, not the airborne center.

---

## 3. roboflow/sports

| | |
|---|---|
| Repo | https://github.com/roboflow/sports. MIT, 5,436 stars, pushed 2026-08-28. Not on PyPI. |
| Install | `pip install git+https://github.com/roboflow/sports.git`. Dependencies: supervision, numpy, opencv-python, transformers, umap-learn, scikit-learn, tqdm, sentencepiece, protobuf. |
| Weights | `examples/soccer/setup.sh` uses gdown to fetch three YOLOv8 files (Ultralytics, **AGPL**): `football-ball-detection.pt`, `football-player-detection.pt` and `football-pitch-detection.pt`. Datasets are on Universe: `roboflow-jvuqo/football-players-detection-3zvbc`, `football-ball-detection-rejhg`, `football-field-detection-f07vi`, `basketball-court-detection-2`, `basketball-jersey-numbers-ocr`. |

### TeamClassifier [V, `sports/common/team.py`]

```python
TeamClassifier(device='cuda', batch_size=32)
```

- **Model:** `google/siglip-base-patch16-224` `SiglipVisionModel`. The embedding is the mean of `last_hidden_state`, then `umap.UMAP(n_components=3)`, then `KMeans(n_clusters=2)`.
- `.fit(crops: List[np.ndarray BGR])` and `.predict(crops)` returns an array of 0/1.
- **How main.py uses it:** it collects player crops every `STRIDE=60` frames over the clip, calls `fit`, then calls `predict` on each frame's player crops.
- `resolve_goalkeepers_team_id` assigns goalkeepers to the nearer team centroid.

**Gotchas:**
- `n_clusters=2` is hard-coded. Referees and bystanders have to be filtered first.
- Pickup players without matching shirts will **not** cluster. **Hand out pinnies, or two colors of tape armbands.**
- `fit` needs a warm-up batch of crops: about 10-20 s of play or a "line up by team" calibration screen.
- SigLIP on every crop every frame is too slow. Predict once per `tracker_id` and majority-vote over time.
- The labels are arbitrary 0/1. Map them to "home/away" with a calibration tap.

### Pitch keypoint model and radar [V]

- `SoccerPitchConfiguration` has 32 vertices in cm for a 120 x 70 m pitch.
- The keypoint YOLOv8 model is broadcast-trained on DFL Bundesliga footage.
- Radar = `ViewTransformer(source=frame_kps, target=pitch_vertices)`, then plot players on a drawn pitch.

**What transfers to non-soccer:**
- `ViewTransformer` (any 4+ points).
- The radar drawing idea. Swap the config for a court or field drawn from the tapped dimensions.
- `TeamClassifier`, for any sport with distinct colors.
- `BallTracker`: picks the detection nearest the centroid of recent positions. It is a decent single-ball filter.
- `BallAnnotator`.

The pitch keypoint weights do **not** transfer. Use the 4-tap homography. For basketball half-court keypoints, use the Universe `basketball-court-detection-2` set or Roboflow's RF-DETR keypoint court tutorial (https://blog.roboflow.com/train-rf-detr-keypoint/).

---

## 4. rtmlib (Tau-J/rtmlib): pose with feet

| | |
|---|---|
| Repo | https://github.com/Tau-J/rtmlib. Apache-2.0, 691 stars, release 0.0.16 on 2026-08-03 [V] |
| Install | `pip install rtmlib==0.0.16`, then swap `onnxruntime` for `onnxruntime-gpu` (see section 0). The `tensorrt` backend is discussed in issue #12 (open). |
| Weights | ONNX zips auto-download from `download.openmmlab.com`, with an automatic fallback mirror at https://huggingface.co/Tau-J/RTMPose [V]. |

### BodyWithFeet (Halpe-26) [V, `rtmlib/tools/solution/body_with_feet.py`]

Constructor: `BodyWithFeet(mode='balanced'|'performance'|'lightweight', backend='onnxruntime', device='cuda', to_openpose=False)`.

| Mode | Detector | Pose model | Pose AP (Body8) |
|---|---|---|---|
| lightweight | YOLOX-tiny 416 | RTMPose-s 256x192 | 72.0 |
| balanced | YOLOX-m 640 | RTMPose-m 256x192 | 76.7 |
| performance | YOLOX-x 640 | RTMPose-x 384x288 | 80.0 |

**Call:** `keypoints, scores = body_with_feet(bgr_frame)`.
- `keypoints` is `(N, 26, 2)` in image pixels. `scores` is `(N, 26)`.
- **Plug in our own boxes instead:** `bwf.pose_model(image, bboxes=[[x1,y1,x2,y2], ...])`, i.e. `RTMPose.__call__(image, bboxes)`. Feeding the RF-DETR + ByteTrack person boxes keeps our `tracker_id` aligned by index.
- Alternative: `Custom(det_class='RFDETR', ...)` with RF-DETR ONNX files on HF (`saifkhichi96/opendetect`), as in `custom_rfdetr_demo.py` [V].

### Halpe-26 indices [V, `visualization/skeleton/halpe26.py`]

| Index | Keypoint | Index | Keypoint |
|---|---|---|---|
| 0 | nose | 15 | left_ankle |
| 1 | left_eye | 16 | right_ankle |
| 2 | right_eye | 17 | head |
| 3 | left_ear | 18 | neck |
| 4 | right_ear | 19 | hip (mid) |
| 5 | left_shoulder | 20 | left_big_toe |
| 6 | right_shoulder | 21 | right_big_toe |
| 7 | left_elbow | 22 | left_small_toe |
| 8 | right_elbow | 23 | right_small_toe |
| 9 | **left_wrist** | 24 | **left_heel** |
| 10 | **right_wrist** | 25 | **right_heel** |
| 11 | left_hip | | |
| 12 | right_hip | | |
| 13 | left_knee | | |
| 14 | right_knee | | |

Indices 0-16 match COCO-17.

### Tracking mode [V, `pose_tracker.py`]

`PoseTracker(solution, det_frequency=1, tracking=True, tracking_thr=0.3)` runs the detector every N frames and tracks with greedy IoU in between.
- It **does not return IDs**; it only reorders arrays.
- It drops boxes smaller than `MIN_AREA=1000` px².

**Recommendation:** use our ByteTrack IDs and call `pose_model(image, bboxes)` directly.

### Speed (proven)

- **RTMPose paper (arXiv 2303.07399):** RTMPose-m reaches 75.8 COCO AP, over 90 fps on an i7 CPU and over 430 fps on a GTX 1660 Ti. That is model-only throughput.
- **rtmlib loops over boxes one at a time** (`for bbox in bboxes: preprocess -> inference`) [V]. The cost is **linear in the number of people**: 8 players x 3 phones x 30 fps = 720 crops/s.

  [E] At about 2-4 ms per crop on a laptop GPU through ORT, that does not fit. **Run pose only where needed:**
  - the ball handler and players within about 2 m of the ball (basketball);
  - the carrier and the nearest 2 defenders (touch football);
  - the thrower and the target (dodgeball);
  - or run at 10-15 Hz for the others.

### Gotchas

- rtmlib issue #4: low FPS with onnxruntime-gpu; the fix was warm-up.
- rtmlib issue #46: on Windows, the missing cuDNN 9 / `zlibwapi.dll` made `cuda` silently use the CPU (see section 0).
- The YOLOX detector sometimes emits duplicate boxes, causing ID swaps (issue #71). That is another reason to feed RF-DETR boxes.
- **Pose2Sim and Sports2D use rtmlib under the hood**, so their keypoint conventions match.

### Pipeline plug-in

Each tracked person gets 26 keypoints plus scores. Smooth them with a One-Euro filter per keypoint. Then emit:
- `wrist_xy[L,R]` for touch, possession and catch;
- `ankle`, `heel` and `big_toe` for steps and line or foot faults;
- `knee`, `hip` and `shoulder` for the strike zone.

---

## 5. Basketball

### 5a. avishah3/AI-Basketball-Shot-Detection-Tracker

| | |
|---|---|
| Repo | https://github.com/avishah3/AI-Basketball-Shot-Detection-Tracker. **No license**, 282 stars, pushed 2025-02-06 [V] |
| Weights | `best.pt` (6.3 MB, YOLOv8, ultralytics==8.0.26) is in the repo. Classes are `['Basketball', 'Basketball Hoop']` (config.yaml). Training sets: `universe.roboflow.com/034-ganesh-kumar-m-v-cs-r2lwe/basketball-lhqoe` (300 images) and `robocon-qchql/hoops-chrie-ivyrc` (1,300 images). |
| Claimed accuracy | "Score Detection Accuracy: 95%, Shot Detection Accuracy: 97%". This is self-reported with no eval set. It assumes **one ball and one hoop in frame**. |

**Make/miss logic** [V, `utils.py`, `shot_detector.py`]:
1. **Gating:** the ball is kept if `conf>0.3`, or if `conf>0.15` near the hoop. The hoop is kept if `conf>0.5`. Ball points are dropped if they jump more than 4 diameters within 5 frames or are non-square (aspect over 1.4). The ball buffer keeps 30 frames.
2. **`detect_up`:** the ball is inside a box 4 hoop-widths wide and 2 hoop-heights above the hoop center.
3. **`detect_down`:** the ball is below the hoop bottom (`y > hoop_cy + 0.5*h`).
4. **Every 10 frames:** if up and then down occurred in order, count an attempt.
5. **`score()`:** take the last point above the rim plus the next point. Fit a line with `np.polyfit`, find x at rim height, and call a **make if x is within `hoop_cx ± 0.4*w`**, plus a 10 px slack.

This is a 2-point linear extrapolation, so it is fragile on rim-outs.

### 5b. aarnavshah12/shot-tracker (RF-DETR)

| | |
|---|---|
| Repo | https://github.com/aarnavshah12/shot-tracker. No license, 7 stars, pushed 2026-08-12 [V] |
| Pins | `inference==1.3.10`, `rfdetr==1.9.2`, `supervision>=0.29,<0.32`, Python 3.12 |
| Models | Ball + rim: **RF-DETR Small** trained on Roboflow. The model ID `aarnavs-space/basketball-shooting-robot-kbsro-1-rfdetr-small-t1` is in **the author's private workspace, so expect it not to load with your key**. It was trained from the Universe dataset "Basketball Shooting Robot" (UArizona). Pose: zero-shot `RFDETRKeypointPreview` (COCO-17). |
| Results | Training: mAP50 88.8, P 75.7, R 84.9. Ball detected in flight on 98.1% of frames. **23/23 attempts segmented and judged correctly** on the author's own 30 fps clips. Caveat stated by the author: the tuning set equals the eval set, n=23. [V, PROGRESS.md] |

**Make rule** [V, `engine/state_machine.py` docstring]:
- **States:** `IDLE -> RISING` (release = 3 consecutive frames of upward velocity ≥ 2.0 m/s, scaled from the 18 in rim) `-> DESCENDING -> RESOLVED`.
- **Make:** the ball center **crosses the rim's top edge moving down, within the rim's horizontal span, on observed consecutive frames**, then is observed below the rim within ±25% of the rim width.
- **Occlusion:** a crossing may bridge a gap of 4 frames or fewer (net occlusion), stamped `occluded`.
- **Rattles:** a pop above the rim by less than 1 rim-width can still drop in (`rattled`). A higher pop counts as a miss.
- **Timeout:** a 10 s hard cap.
- **Calibration:** the median rim box over 100 frames gives the px/m scale.

Their config file is a good list of thresholds to copy.

**Verdict:** use 5b's **rule** (top-edge downward crossing + below-rim confirmation + occlusion bridge) with our own fine-tuned RF-DETR ball+rim model. Both repos have no license, so reimplement rather than copy. 5a's `best.pt` (AGPL YOLOv8, no license) works as a 15-minute fallback for a recorded demo.

### 5c. Dribble, travel and double dribble: what exists and how reliable it is

**ayushpai/AI-Basketball-Referee:** https://github.com/ayushpai/AI-Basketball-Referee. No license, 366 stars, last push 2024-04-14. Weights: `yolov8s-pose.pt` is in the repo; the ball model is on Google Drive [V].

| Detector | Exact rule in code [V] |
|---|---|
| Dribble | Ball center `delta_y` was more than +18 px (falling) and is now less than -18 px (rising). The reversal counts as one dribble. Pixels per frame, so it is **resolution- and distance-dependent**. |
| Step | Either ankle's y changes by more than `step_threshold` (5 px in `travel_detection.py`, 12 in `step_counting.py`) frame to frame. Then a 7-8 frame refractory period. Requires knee and ankle confidence above 0.5. Uses **person index 0 only**. |
| Travel | `ball_detected and step_count >= 2 and dribble_count == 0`. Steps reset on any dribble, or after 20 frames without a ball. **No gather step and no pivot-foot concept.** |
| Holding | min(wrist-to-ball distance) under 300 px for more than 0.85 s |
| Double dribble | `was_holding and dribble_count > 0` after the hold |

**Reliability:**
- No evaluation is published.
- The repo's own notes and our earlier research expect many false travels: the ankle-y threshold fires on jogging, and the pose keypoints jitter.
- Search snippets claim that early versions avoided camera step counting (phone-on-leg pedometer). That is **unverified**; the Hackster page returned 403.

**Better evidence-backed building blocks:**
- **Learned temporal model:** the UGM Mediapipe-YOLO-LSTM travelling classifier reports accuracy 0.869 at 10 fps or more (https://ir.lib.ugm.ac.id/id/eprint/6350/). No code.
- **Foot-contact timing from 2D pose is proven for walking in side view.** Stenum et al. 2021 (PLOS Comp Biol, https://pmc.ncbi.nlm.nih.gov/articles/PMC8099131/): OpenPose against motion capture gives **MAE 0.02 s for step and stance times**, and 0.049 m for step length.

  This was single-person, sagittal-view walking. Basketball (crossovers, occlusion, frontal views) is much harder; treat it as an upper bound.

**Recommended Trophy rules** [E]:

1. **Ground contact (per foot).**
   - Use heel (24/25) and big toe (20/21) y in the image. Better, project the foot points through the homography and require the foot point to be within about 5 cm of the floor plane.
   - Contact = the foot's vertical image velocity is near 0 for 2 or more frames, **and** its y is near the per-player running maximum (lowest point).
   - "Step" = contact onset on the foot that was not last in contact.
2. **Dribble.**
   - Ball bounce = the ball's y-velocity sign flips from down to up near the floor (the ball bottom at or below the player's ankle line), **plus the phone-mic audio onset** (a dribble "thump" is very distinct).
   - Ball-hand contact = the ball within about 1 ball diameter of a wrist (9/10).
3. **Possession.** The ball is within about 1.5 ball diameters of a wrist for at least 4 frames (about 130 ms at 30 fps).
4. **Travel (BETA).**
   - Count steps between "gather" (end of the last dribble, i.e. ball-hand contact sustained) and release or the next bounce.
   - **More than 2 steps** (plus the house gather step) = travel. Show the step timeline as evidence.
   - Require at least 2 visible heel/toe keypoints with confidence above 0.5, or the call becomes "players decide".
5. **Double dribble.** Bounce, then two-hand hold (both wrists within the ball radius for more than 300 ms), then bounce, with no shot or pass event in between. This is more reliable than travel because the hold is visible. Run it as AUTO-ish / BETA.
6. **"Off you" / last touch on out-of-bounds.**
   - Keep `last_touch = (player_id, team, t)` and update it whenever a wrist, or any keypoint, comes within contact radius of the ball **and** the ball's velocity changes direction or speed within ±2 frames.
   - On ball out-of-bounds (bounce point or ball-bottom outside the court polygon in the homography; or the holder's foot outside), award to the other team.
   - When the last two touches by different teams are within 150 ms, return BETA ("tip, players decide").
   - No open repo does this. It is new logic on top of sections 2 and 4.
7. **Make/miss:** section 5b rule. Audio: the rim clank or net swish helps with timing.

---

## 6. BaseballCV (BaseballCV/BaseballCV)

| | |
|---|---|
| Repo | https://github.com/BaseballCV/BaseballCV (moved from dylandru). Code MIT, MLB models AGPL-3.0 (`LICENSE-MLB-AGPL.txt`). 20 stars, pushed 2026-10-22. PyPI `baseballcv==0.1.28`, Python 3.11+ [V] |
| Install | `pip install baseballcv` (pulls ultralytics). `pip install "baseballcv[pose]"` adds MediaPipe for DistanceToZone. |
| Weights | `LoadTools().load_model(alias, model_type='YOLO'|'FLORENCE2'|'PALIGEMMA2'|'RFDETR')` resolves `https://balldatalab.com/api/models/<alias>`, which answered HTTP 302 on 2026-10-22, i.e. it is live. |

**YOLO aliases [V]:**
- `ball_tracking`, `ball_trackingv4`: the ball, pitcher's hand to the plate.
- `bat_tracking`
- `glove_tracking`: catcher's glove + ball + homeplate + rubber.
- `phc_detector`: pitcher, hitter, catcher.
- `base_detector`
- YOLOv9: `amateur_pitcher_hitter`, `homeplate_tracking`.

**RF-DETR aliases:** `glove_tracking_rfd` and `baseball_rubber_home_rfd`. Load them with:

```python
RFDETR(labels=["glove","ball","homeplate","rubber"], model_type="large", model_path=...)
```

All of these are **trained on MLB broadcast (center-field camera) footage**, so there will be a domain gap to a phone beside a wiffle game.

**Strike zone method** [V, `functions/utils/baseball_utils/distance_to_zone.py`]:
- **Pipeline:** Savant video plus Statcast `sz_top` / `sz_bot`, then catcher, glove, ball and homeplate detection. The pitch location is taken at the **frame where the ball reaches the glove**.
- **Width:** homeplate box width = **17 in**, which gives px/in.
- **Vertical bounds from hitter pose** (YOLO pose, COCO-17):
  - bottom = the higher knee (13/14);
  - top = the midpoint of mean shoulder (5/6) y and mean hip (11/12) y;
  - sanity check: top is at least 50 px above the knee.
- Output: distance to zone in inches, plus "In Zone".

The `analyze()` entry point is tied to the Savant scraper (date range). **For wiffle, reuse the geometry, not the class.**

**Trophy wiffle plan:**
1. Use COCO `sports ball` / `baseball bat` from RF-DETR, or fine-tune about 150 wiffle frames. The Universe `scratch-xkho6/wiffle-bat-and-ball` set has only 57 images.
2. Use rtmlib knees, hips and shoulders, which share the same indices.
3. Size the plate from a taped or known-width plate (17 in). The plate plane comes from the homography.
4. Find the plate-crossing frame from the ball trajectory, interpolating between frames. At 45 mph the ball moves about 0.7 m per frame at 30 fps, so this is always **BETA**.
5. **AUTO alternative:** a physical strike target, scored by ball-in-target-zone plus an audio thump.

---

## 7. Two-hand touch / flag football

### Datasets (opened in the browser, 2026-10-22)

| Set | URL | License | Images | Classes | Hosted model |
|---|---|---|---|---|---|
| NFL Detection 1500 | https://universe.roboflow.com/test-cm1hp/nfl-detection-1500 | CC BY 4.0 | 1,400 | **`0`, `1`, `2` (unnamed)** | `nfl-detection-1500/5`, RF-DETR (Base), mAP50 81.7% |
| Roboflow blog version | https://roboflow.com/blog/american-football-player-tracker | — | — | "labeled by team or role" | `nfl-detection-1500-jdrgz/4`, RF-DETR Small: mAP50 74.8, P 90.8, R 71.5. Augmentations: flip, ±25% saturation/brightness, 100 px motion blur. Then ByteTrack. **No snap or play detection.** |
| Flag Football (StatsLive) | https://universe.roboflow.com/statslive-ms3nd/flag-football-ashw8 | CC BY 4.0 | 192 | Ball, Player, Referee | `flag-football-ashw8/2`, Roboflow 3.0 Fast: mAP50 55.0, P 85.4, R 50.7 |

**Recommendation:**
- Persons come from COCO.
- For the football, fine-tune RF-DETR-S on StatsLive (192 images) **plus about 100-200 frames of your own Nerf or real football**. The NFL set's unnamed classes need inspection before use.

### Snap detection: proven method plus adaptation

**Atmosukarto et al., "Automatic Recognition of Offensive Team Formation in American Football Plays", CVPRW 2013** (https://openaccess.thecvf.com/content_cvpr_workshops_2013/W19/html/Atmosukarto_Automatic_Recognition_of_2013_CVPR_paper.html). Read in the PDF [V]:
- **Formation frame (just before the snap):** compute the **frame-to-frame MSE over all pixels** on registered frames, then apply a **5-tap median filter**. The formation frame is "the last frame after which the MSE values are substantial and monotonically increasing". An SVM on MSE differences ignores man-in-motion. **94.53% within 1 s (30 frames)** on 274 SD clips.
- **Line of scrimmage:** `argmax_y` of the **foreground (player) pixel density** along the field direction in the formation frame. **97.5% (SD) / 97.9% (HD) within 10 px.**
- Broadcast-camera patents (US 7474331, US 7639275) use camera zoom-then-hold as a start-of-play cue. Not relevant for tripods.

**Trophy snap detector** [E], built on that idea for a fixed tripod, so no registration is needed:
1. **Still gate.** Track players with ByteTrack and compute the mean player speed in field coordinates (m/s) from bottom-center points. Optionally add `cv2.calcOpticalFlowFarneback` magnitude inside the person boxes, or frame-difference MSE as in the paper. "Set" = mean speed below about 0.3 m/s for at least 1.0 s, with at least 4 players present.
2. **Snap onset.** The first frame after "set" where:
   - **the ball's displacement** exceeds about 0.3 m backward (away from the line of scrimmage) in under 0.3 s, **or**
   - the ball leaves the center's wrist/hand region, **and**
   - the collective speed rises monotonically over 3 or more frames (the paper's "monotonically increasing" criterion).

   Optional: an audio "hike" onset within ±300 ms raises confidence.
3. **Line of scrimmage** = the ball's field-x at the snap. Fallback: the paper's density-argmax of player feet along the field length during "set".
4. **Rush count.** A timer from the snap timestamp. Use the capture timestamp, not processing time. Announce "rush" at N s, matching the house rule (5 Mississippi ≈ 5 s). Rusher legality: rusher field-x at the snap is at least 7 yd from the line of scrimmage.

Validation data for timing logic only: NFL Big Data Bowl tracking has `ball_snap` event frames (https://github.com/nfl-football-ops/Big-Data-Bowl).

### Two-hand touch predicate [E]

- **Inputs:** the carrier (the person with possession at or after the snap) as a box or, better, an RF-DETR-Seg mask; each defender's wrists (9/10) with score above 0.4.
- **Rule:** a touch is "two hands" if **both** of one defender's wrists are inside the carrier's box (shrunk about 10% horizontally) or mask, **within the same 200 ms window** (6 frames at 30 fps, 12 at 60). Also require wrist speed toward the carrier, to exclude hands that were simply there.
- **Gotcha:** occlusion and depth ambiguity. A wrist in front of the carrier from the camera's view is not necessarily touching. This is a monocular depth gap, so the call stays **BETA**.
- **Multi-view (section 9):** require agreement from 2 phones, or use the phone with the best side view.
- **Output:** "1 hand / 2 hands, p=…".

---

## 8. Resting-object sports (cornhole, mini golf, bowling)

### Datasets (opened, 2026-10-22)

| Set | URL | License | Images | Classes | Trained model |
|---|---|---|---|---|---|
| **Cornhole Referee** | https://universe.roboflow.com/cornhole-referee/cornhole-referee | CC BY 4.0 | 394, 7 versions | hole, board, blue-bean-bag, **blue-bean-bag-in-hole**, red-bean-bag, **red-bean-bag-in-hole** | **0 models**. You must train it yourself. |
| cornhole-instanceseg | https://universe.roboflow.com/nonaugprj-0tyn3/cornhole-instanceseg-wyh9k | CC BY 4.0 | 440 | player, hole, beanbag_blue, beanbag_red, board_surface | 0 models; segmentation (useful for "any part on board") |
| minigolf-ball-detection | https://universe.roboflow.com/minigolf/minigolf-ball-detection | CC BY 4.0 | 1,583 | hole, golfball, golfhole | `minigolf-ball-detection/5` (Roboflow 3.0 Fast): mAP50 71.7, P 84.3, R 64.2 |
| Fallen bowling pins | https://universe.roboflow.com/industrial-robots/fallen-bowling-pins-detector | Public Domain | 98 | **Keypoint** task | Small |
| bowlingpin (kitirat) | https://universe.roboflow.com/kitirat/bowlingpin | CC BY 4.0 | 371 | pin, bowling | mAP50 58.6 (from earlier notes) |
| Dodgeball (Kandidat) | https://universe.roboflow.com/kandidat-pgnqx/dodgeball-f7dp5 | CC BY 4.0 | 1,005 | ball, person | `dodgeball-f7dp5/1` |
| Dodgeball (Simon Norin) | https://universe.roboflow.com/simon-norin-62w7g/dodgeball-detection-pcb7n | CC BY 4.0 | 2,231 | blueball, redball | `dodgeball-detection-pcb7n/1` |

### Two ways to run them locally

1. **Recommended: export the dataset and fine-tune RF-DETR locally.** Apache weights, fully offline after download.
   - `pip install roboflow`, then download with your own **free Roboflow API key**:

     ```python
     Roboflow(api_key=…).workspace("cornhole-referee").project("cornhole-referee").version(<n>).download("coco")
     ```

     That gives `train/valid/test/_annotations.coco.json`, which `RFDETRSmall().train(dataset_dir=…)` reads directly. Check the version number on the page; it shows 7 versions. Universe downloads need a signed-in account.
   - **Cornhole Referee (394 images) takes about 5-10 min to train** [E, from the cookbook rates]. Do it Thursday night or Friday morning.
2. **Run the hosted model with the `inference` package**:

   ```python
   from inference import get_model
   m = get_model("minigolf-ball-detection/5", api_key=KEY)
   m.infer(bgr)[0]
   sv.Detections.from_inference(...)
   ```

   - **Weights download once and are cached in `MODEL_CACHE_DIR`.** The default is `/tmp/cache`, which is cleared on reboot. **Set `MODEL_CACHE_DIR` to a persistent folder.** Source: https://docs.roboflow.com/reference/inference/inference-python/offline-weights
   - The docs examples pass `api_key` on every call. **The docs do not say whether a cached model loads with no network.** Test with Wi-Fi off before relying on it.
   - **Full air-gapped mode is an Enterprise feature:** Docker plus a 30-day weight lease (https://docs.roboflow.com/deploy/offline-mode).
   - **License:** Inference core is Apache-2.0. Models "follow the model's own license" when self-hosted. A commercial self-host license is an Enterprise add-on, and AGPL models stay AGPL (README [V]). "Roboflow 3.0 Fast" Universe models are YOLO-family. Check the selected model terms for the intended use.
   - Keep it in a separate venv (section 0, conflict 1).

### "Motion stopped" (settle) detector [E]

Standard method; no single canonical repo.

- **Per tracked object:** settled when the bottom-center speed in **board/field coordinates** stays below a threshold for N frames. The tracker is ByteTrack with `BIoU`, or a nearest-neighbor tracker, because bags and balls are big enough at rest.
  - **Cornhole:** < 2 cm/s for 15 frames (0.5 s).
  - **Mini golf:** < 1 cm/s for 20 frames.
  - **Bowling:** pins: no motion for about 1.5 s after the crash audio onset.
- **Frame-difference version** (no tracker needed for the "round is over" event):
  - Grayscale, Gaussian blur, then `absdiff` against the previous frame, inside the board/lane polygon mask.
  - Changed-pixel fraction below 0.2% for at least 0.7 s → `settled`.
  - Ignore pixels in the thrower's person boxes, so that someone walking up to the board does not reset the timer.
- **Score only at settle.** Re-score when a new bag lands (a bag can knock another one in or off), and keep the before and after frames as evidence.

### Homography to board coordinates

- **Tap 4 board corners** in the PWA. The regulation board is 24 x 48 in, the hole is 6 in in diameter, and the hole center is 9 in from the top edge. `cv2.findHomography(img_pts, board_in)` maps detections into board inches.
- **Classify each settled bag:**
  - "in hole" = the `*-in-hole` class, **or** the track disappeared inside the hole circle and does not reappear;
  - "on board" = any part of the bag box or mask inside the board polygon, and not touching the ground (the mask does not extend below the board's bottom edge);
  - otherwise "off".
- **Scoring:** 3 points in hole, 1 on board, per side. **Cancellation:** `round = |A − B|` to the higher team. Game to 21 (house bust rule optional).
- **Same template for:**
  - **mini golf:** a cup circle in the green's coordinates;
  - **bowling:** a 10-spot pin-deck template with a standing/fallen classifier per spot after settle. Use the US4827412 idea of sampling the pin base.

---

## 9. Multi-view possession (2-3 phones)

### Option A, recommended for 36 h: choose the best view per event

- **Per event,** take the view with the highest score from:
  - mean keypoint confidence of the involved players;
  - person box size;
  - lowest occlusion: IoU of the involved boxes with other people;
  - ball detection confidence;
  - viewing angle relative to the relevant line (side-on to the line for out-of-bounds or line of scrimmage).
- **Calls must agree:** require agreement in at least 2 views for AUTO. Disagreement → BETA.
- **Needs only:** per-phone homographies to the same field coordinates (4 shared taped points), plus time alignment.

### Option B: triangulate rtmlib keypoints with aniposelib

aniposelib: https://github.com/lambdaloop/aniposelib. BSD-2, 92 stars, 0.8.0 [V].

**API** [V, source + tutorial https://anipose.readthedocs.io/en/latest/aniposelib-tutorial.html]:
- **Calibration:** `cgroup = CameraGroup.from_names(names, fisheye=False)` and `cgroup.calibrate_videos(videos, board)` with `CharucoBoard(7, 10, square_length=25, marker_length=18.75, marker_bits=4, dict_size=50)`. Units are mm.
- **Save / load:** `cgroup.dump('calibration.toml')` and `CameraGroup.load(...)`.
- **Triangulation:**
  - `p3d = cgroup.triangulate(points, undistort=True)`, where `points` has shape `(n_cams, n_points, 2)` with NaN for low-score keypoints;
  - or `triangulate_ransac(points, min_cams=2)`;
  - or `triangulate_optim(...)` (smoothness).
- **Reprojection error:** `cgroup.reprojection_error(p3d, points, mean=True)`.

**Integration risks:**
- Needs intrinsics plus extrinsics. That means a printed ChArUco board waved in all views, or Pose2Sim's scene-point calibration.
- Needs **frame-level sync**.
- Needs **cross-view person association**: same `tracker_id` across phones. Do it by nearest field position via the homography feet points, then the Hungarian algorithm.
- [E] Several hours of work. Do it only if a teammate owns it.

### Pose2Sim synchronization method [V, README]

Pose2Sim: https://github.com/perfanalytics/pose2sim. BSD-3, `pose2sim==0.10.49`.

- **`Pose2Sim.synchronization()` method:** for each camera, it **computes the mean vertical speed of the chosen keypoints**. It then low-pass filters it (`filter_cutoff=6` Hz, 4th order) and **picks the time offset with the highest cross-correlation**.
- **Parameters:** `keypoints_to_consider`, `approx_time_maxspeed`, `time_range_around_maxspeed=2.0` s, `likelihood_threshold_synchronization=0.4`.
- **Works best with:**
  - a sharp vertical movement, such as a jump or arm raise;
  - at least 5 s of capture;
  - at most a few minutes, because of clock drift;
  - motion not toward or away from the camera.
- Pose2Sim notes that visual events beat audio, because sound travels slower than light.

### Trophy sync recipe [E]

1. **At game start,** everyone does one jump or arm raise while the phones flash their torches (a frame-brightness step gives sync within ±½ frame).
2. **Cross-correlate** the per-phone ball-speed or wrist-vertical-speed curves (Pose2Sim style) to refine.
3. **Re-check every few minutes** using bounce audio onsets, because of drift.

Over a 10 m indoor court, sound delay is about 30 ms, i.e. about 1 frame at 30 fps.

---

## 10. Running Roboflow Universe models offline: summary

- **API key:** a free Roboflow account and API key is needed to **download** Universe datasets or hosted weights. The README says inference on your own hardware uses no credits [V].
- **Weights cache:** `MODEL_CACHE_DIR`; default `/tmp/cache`.
- **Offline after caching:** not documented for the open-source pip package. **Verify with Wi-Fi off.**
- **Best practice for Trophy:** pull the Universe **datasets** when preparing training and fine-tune **RF-DETR locally**.
  - The checkpoint is a local `.pth`; no key or network is needed at runtime.
  - It is Apache-2.0, apart from each dataset's CC BY 4.0 attribution requirement.
  - It runs in the same venv and process as the rest of the pipeline.
- **Universe pages block scripted fetches (403)** but open in a normal browser.

---

## Blockers and risks (priority order)

1. **Windows CUDA stack.** torch (cu12x wheel), onnxruntime-gpu (CUDA 12 + cuDNN 9 DLLs) and `inference` (cu124, `onnxruntime-gpu<1.22`) can disagree. Build and verify the venv **before Friday**. Check `torch.cuda.is_available()`, the ORT providers list, and `nvidia-smi` during a run.
2. **No laptop-GPU throughput numbers exist.** Pose cost is linear per person in rtmlib. Measure RF-DETR-S at batch 3 plus RTMPose-m on 10 crops on the actual laptop, then decide on TensorRT and pose subsampling.
3. **The ball is the weakest detection.** COCO `sports ball` on blurred 720p WebRTC frames is weak. Plan to fine-tune a ball class per sport from your own phone footage (about 150-300 labeled frames, about 10 min of training). Also use the 1080p local recordings for replay or BETA re-analysis.
4. **Team colors need pinnies.** The SigLIP+KMeans k=2 classifier will not separate a pickup game in random shirts.
5. **Nothing open does "off you", snap, two-hand touch, or reliable travel.** These are new predicates on the event bus. Travel and two-hand touch should be **BETA with evidence clips**. Make/miss (5b rule), double dribble, snap timer, line of scrimmage, cone goal (LineZone between posts) and cornhole (after settle) can be AUTO.
6. **Licenses.** avishah3, aarnavshah12 and ayushpai have **no license**: reimplement, don't copy. roboflow/sports `.pt` files, BaseballCV and the Roboflow 3.0 Universe models are YOLO/AGPL-family. RF-DETR Nano-Large is Apache, but XL/2XL/Atto-Pico are PML and need an account.
7. **The aarnavshah12 RF-DETR ball+rim model ID is in a private workspace.** Train your own from the Universe basketball sets listed in section 5a/5b.

## Links verified on 2026-10-22

- **GitHub** (via the API): rf-detr, trackers, supervision, sports, rtmlib, AI-Basketball-Shot-Detection-Tracker, shot-tracker, AI-Basketball-Referee, BaseballCV, inference, pose2sim, aniposelib.
- **PyPI JSON:** all packages in section 0.
- **Opened in the browser:** Universe pages for cornhole-referee, cornhole-instanceseg, minigolf-ball-detection, nfl-detection-1500, flag-football-ashw8, fallen-bowling-pins-detector, both dodgeball sets.
- **WebFetch:** the Roboflow blog posts (american-football-player-tracker, automate-game-scorekeeping-vision-ai), the opendetect benchmarks page, the Roboflow offline-weights docs, and the anipose tutorial.
- **PDF downloaded and read:** Atmosukarto CVPRW 2013.
- **balldatalab model API:** HTTP 302, i.e. live.
