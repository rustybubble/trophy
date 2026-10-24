# Trophy build flight: integration cards

Trophy integration research. Compiled 2026-10-22.

**How this was checked.** I shallow-cloned every repo (commits listed per card) and read the actual inference, postprocess and dataloader code, not only the READMEs. Paper numbers come from the arXiv HTML. Hugging Face file lists come from the HF API. The BlurBall weight and dataset listings come from the public Nextcloud WebDAV. Issue threads come from `gh api`. **Nothing was installed or run on a GPU**, so every speed marked "est." is a guess: measure on the laptop Friday night.

**Pin notation.** "Pinned by repo" means the repo's own requirements file. "Use" means what I recommend for one shared venv. As of today PyPI ships numpy 2.5, opencv-python 5.0, librosa 1.0 (needs Python 3.12 and numpy 2.1 or newer) and torch 2.14. A bare `pip install` of these repos will break them (see section 0).

---

## 0. Environment plan (read first)

### 0.1 One venv for the whole live pipeline: `trophy-cv` (Python 3.11)

```
py -3.11 -m venv trophy-cv && trophy-cv\Scripts\activate
# GPU torch. Pick the wheel by laptop GPU generation:
#   RTX 20/30/40 series:  torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
#   RTX 50 series (Blackwell, sm_120): needs CUDA 12.8 wheels, torch>=2.7, e.g.
#                          torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
pip install "numpy==1.26.4" "opencv-contrib-python==4.10.0.84" "scipy==1.13.1" \
    "hydra-core==1.3.2" "omegaconf==2.3.0" "timm==0.9.16" "einops==0.7.0" "scikit-image==0.23.1" \
    "scikit-learn==1.4.2" "pandas==2.2.2" "matplotlib==3.9.0" "imgaug==0.4.0" "shapely==2.0.4" \
    "lightning==2.3.3" "pytorch-lightning==2.4.0" "segmentation-models-pytorch==0.3.3" \
    "albumentations==1.4.18" "casadi==3.7.0" "tqdm" "pyyaml" "gdown" \
    "librosa==0.11.0" "soundfile" "panns-inference==0.1.1" "onnxruntime-gpu" \
    "jax==0.4.38" "jaxlib==0.4.38" "aniposelib==0.8.0" "toml" "numba==0.60.0"
pip uninstall -y opencv-python opencv-python-headless   # keep ONLY opencv-contrib-python
```

Why these pins:

| Constraint | Source |
|---|---|
| **numpy < 2** | BlurBall and WASB use `np.Inf` (16 hits in the BlurBall `src`), which NumPy 2.0 removed. BlurBall pins numpy 1.26.4. |
| **librosa 0.11.0, not 1.0.0** | librosa 1.0.0 (released 2026-08-11) needs `numpy>=2.1` and `python>=3.12`. 0.11.0 needs py>=3.8 and numpy>=1.22.3. |
| **jax 0.4.38** | aniposelib 0.8.0 depends on unpinned `jax` and `opencv-contrib-python`. Current jax 0.12 needs numpy>=2.2 and py>=3.12. jax is only imported inside `CameraGroup.triangulate()`. |
| **only one cv2 wheel** | aniposelib pulls `opencv-contrib-python`. If `opencv-python` is also installed, the two clobber each other's `cv2`. |
| **smp 0.3.3** | The TT3D checkpoint was saved with `arch=unetplusplus`, `encoder_name=timm-regnety_002`, `encoder_weights=imagenet`, Lightning 2.0.4 (read from the ckpt pickle without unpickling). Newer smp renamed the `timm-*` encoders. |
| **torch** | BlurBall pins torch 2.2.2 and TT3D pins 2.4.1. Neither uses anything version-specific, so 2.5.1 is fine. **torch >= 2.6 changed the `torch.load` default to `weights_only=True`.** If you must use torch 2.7+ (RTX 50), set `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`, or patch `torch.load(..., weights_only=False)` in BlurBall's `detectors/*.py`, TrackNetV3's `predict.py` and TT3D's Lightning load. |

### 0.2 Do not install these project environments; just borrow their weights and code

- **fast-volleyball-tracking-inference** pins `requires-python = ">=3.14"` (`.python-version` is 3.14) plus `pandas>=3`, `opencv>=4.13` and `openvino>=2026.2`. Do **not** `uv sync` it into the main venv. Its models are plain ONNX files committed to `models/`, so run them with `onnxruntime` from `trophy-cv` and copy the about 40-line decode function.
- **Good-Pickleball** pins CPU torch 2.5.1 and ultralytics (AGPL). Use only its classical `court/auto_detector.py` (numpy and OpenCV only).
- **TennisCourtDetector** pins torch 1.5.0+cu101 and numpy 1.19.3, which are uninstallable now. Its code runs fine on modern torch; skip its requirements.txt.
- **CourtKeyNet** contains an **obfuscated module** `courtkeynet/utils/_safetensors.py`, base64+zlib passed to `exec`, labelled "DO NOT EDIT". I decoded it without running it. At commit `2dd886a` it is a benign safetensors save/load helper that stamps author metadata. It still means you should load the HF `.safetensors` with `safetensors.torch.load_file` yourself rather than running the repo's GUI. Re-check the module if you pull a newer commit.

### 0.3 Downloads to do tonight (Drive throttles; plain `wget` on Drive `uc?id=` links breaks on large files, so use `gdown`)

| What | Where | Size |
|---|---|---|
| `blurball_best` (+ `wasb_midpoint_best`, `tracknetv2_midpoint_best`, ...) | Nextcloud share `6Z8TpM3sXRKHzGC`: `https://cloud.cs.uni-tuebingen.de/index.php/s/6Z8TpM3sXRKHzGC/download?path=/&files=blurball_best` | 6,156,034 B (blurball_best); wasb_*: 6,108,890 B |
| BlurBall TT labels (fine-tune format reference) | Nextcloud share `C3pJEPKWQAkono7`: `all_csv_midpoint_annotations.zip`, `extract_csv.sh`, `extract_frames.sh`, 464 rally mp4s (1280x720, 25 fps nominal) | |
| WASB `wasb_{soccer,tennis,badminton,volleyball,basketball}_best.pth.tar` | Drive IDs `1pg0MpMtKZ6ziYEr4oyfKYPOO3hjLw94l`, `14AeyIOCQ2UaQmbZLNQJa1H_eSwxUXk7z`, `17Ac0pO5oryh1JwgwTFQTjOKHY3umbDQu`, `1M9y4wPJqLc0K-z-Bo5DP8Ft5XwJuLqIS`, `1nfECuSyJvPUmz3njZCdFERSQQbERt8FU` (`gdown <id> -O ...`) | ~6 MB each (est.) |
| TT3D `weights/table_segmentation.ckpt` | already in git (68,475,920 B) | |
| timm `regnety_002` ImageNet weights | fetched automatically the first time `TableSegmenter.load_from_checkpoint` builds the smp encoder (`encoder_weights="imagenet"`). **Load it once tonight with internet** so it is cached. | small |
| TrackNetV3 `TrackNetV3_ckpts.zip` (`TrackNet_best.pt`, `InpaintNet_best.pt`) | Drive `1CfzE87a0f6LhBp0kniSl1-89zaLCZ8cA`; HF mirror `rahulanantharama/TrackNetV3-badminton` has **only** `TrackNet_best.pt` (136,190,877 B), no InpaintNet, no model card | |
| TennisCourtDetector `model_tennis_court_det.pt` | Drive `1f-Co64ehgq4uddcQm1aFBDtbnyZhQvgG` | |
| CourtKeyNet | `hf download Cracked-ANJ/CourtKeyNet --local-dir ./courtkeynet-weights` → use `finetuned/courtkeynet_finetuned.safetensors` (4,977,840 B) | |
| PANNs `Cnn14_mAP=0.431.pth` | Zenodo record 3987831 (327,428,481 B) → `%USERPROFILE%\panns_data\`. Also `class_labels_indices.csv` from `http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv`. **panns_inference shells out to `wget`, which Windows lacks, so place both files manually.** | 327 MB |
| tt_sounds dataset (optional audio pretraining: 777 table, 290 floor, 1,239 "other", 3,396 racket clips) | Nextcloud `p3tw3EqE9csXoRn`. **CC BY-NC 4.0.** | |

---

## 1. BlurBall (table tennis ball + motion blur)

**Repo:** https://github.com/cogsys-tuebingen/blurball (commit `2f0f549`, 2026-05-14), MIT (`LICENSE.md` is NTT's WASB MIT). Paper: arXiv 2509.18387, CVPRW 2026 (CVSports). Project page: https://cogsys-tuebingen.github.io/blurball/. **Weights license is unstated**; open issue #2 asks whether `blurball_best` may be redistributed. Verify permission before using or redistributing those weights.

**Install**
```
git clone https://github.com/cogsys-tuebingen/blurball && cd blurball
# requirements.txt pins torch 2.2.2 / numpy 1.26.4 / hydra-core 1.3.2 / lightning 2.3.0; use trophy-cv instead
# edit src/configs/global.yaml: WASB_ROOT: <abs path to repo>   (it ships hard-coded /home/gossard/Git/blurball)
set HYDRA_FULL_ERROR=1
```
Device: **CUDA only.** `BlurBallDetector` asserts `device == "cuda"` and wraps the model in `nn.DataParallel`.

**Weights:** Nextcloud `blurball_best` (no extension; it is a torch checkpoint dict with key `"model_state_dict"`). The same share has `wasb_midpoint_best`, `tracknetv2_midpoint_best`, `monotrack_midpoint_best`, `restracknetv2_midpoint_best`, `ballseg_midpoint_best`, `deepball_midpoint_best` and `deepball_large_midpoint_best`, plus `*_endpoint_best` variants. "midpoint" means labels at the blur centre (the paper's convention); "endpoint" means the leading edge.

**Entry points**
- CLI (whole video): `python src/main.py --config-name=inference_blurball detector.model_path=<blurball_best> +input_vid=<video.mp4> detector.step=1 detector.postprocessor.score_threshold=0.7`
  - It writes PNG frames to `frames_<video>/` next to the video, then `traj.csv` with columns `Frame, X, Y, Visibility, L, Theta`. X and Y are **int pixels in the original resolution**, L is the blur half-length and Theta is degrees (both described below).
- Function-level (use this for streaming): `detectors.blurball_detector.BlurBallDetector(cfg).run_tensor(imgs, affine_mats)` followed by `trackers.online_blur.OnlineTrackerBlur(cfg).update(dets)`.

**Exact input**
- `frames_in = 3`, `frames_out = 3` (MIMO). The tensor is `[B, 9, 288, 512]`: three frames concatenated on the channel axis.
- Per frame: resize to **512x288 (W x H)**, `ToTensor()` (0-1), ImageNet `Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])`.
- **Colour order: train with RGB.** The training dataloader uses `PIL.Image.open(...).convert('RGB')`, but `runners/inference.py` reads frames with `cv2.imread` (BGR) and never converts. That looks like a channel-swap bug in the inference script. In our wrapper, feed **RGB**. A/B test both on 50 of our frames; a white ball is nearly colour-invariant, but the table and background are not.
- **Aspect ratio:** the training transform is an affine "letterbox" with `scale = max(h, w)`. For 16:9 input that equals a plain resize. **Send 16:9 landscape frames only.** A portrait 9:16 phone frame would be stretched at inference and mis-mapped back, because the inverse affine assumes max-side scaling. Lock the PWA to landscape 1280x720.
- `step`: with 3 (default), windows don't overlap: one forward pass covers 3 frames, giving lower latency per frame but 3 frames of buffering. With 1, the window slides by 1. That is more accurate, and each frame then gets three predictions from three windows (`det_results[path].extend` accumulates them; the tracker picks one).
- fps: the training set is 26 online recordings at about 25 fps (the sample rally I probed: 1280x720, `r_frame_rate 25/1`, avg 24.7 fps, so it has duplicates). Mean ball displacement is 18.7 ± 16.4 px/frame at train resolution. At our 30 fps that is about 0.83 of their per-frame motion, which is fine. 60 fps Android is even easier.
- **Ball colour:** TT3D's paper says BlurBall was **not trained on orange balls**. **Play with a white ball.**

**Exact output**
- Heatmap `[B, 3, 288, 512]` (logits; the postprocessor applies `sigmoid`). Position and blur both come from the same heatmap. There is no separate regression head: the model learns to paint a line-shaped blob (`binary_line_fixed_size` targets, sigma 2.5, min value 0.7).
- Postprocess (`BlurBallPostprocessor._detect_blob_concomp`): threshold at `score_threshold`, connected components, then per blob:
  - `xy` = heatmap-weighted centroid, mapped back to original pixels by the inverse affine.
  - `score` = **sum** of heatmap values in the blob (not 0-1). It grows with blob size, so normalise it yourself (e.g. `max(hm)`) to get a confidence.
  - `angle` = blob orientation from image moments, `0.5*atan2(2*mu11, mu20-mu02)`, **in degrees in [-90, 90]**, image axes (x right, y down). It is a direction **without sign**: you cannot tell travel direction from one frame.
  - `length` = **half** the PCA major-axis extent, **in heatmap pixels (512-wide space), not original pixels**. Multiply by `W_orig/512` (2.5 for 1280 wide).
- The tracker (`online_blur`) keeps the top-score candidate within `max_disp = 300` px (original pixels) of the last visible position. **Gotcha:** `xy_pred` is initialised to `None` and never set in `_select_best`, so the motion-model quality term is dead code (same in WASB's `online.py`). Effectively it is "highest score within 300 px". Add your own Kalman or parabola gate.

**Proven numbers** (BlurBall paper, TT test set, τ = 4 px, RTX 2080 Ti):
- Table 3: BlurBall 1-step F1 **96.52**, AP 98.23, blur half-length MAE **1.5 ± 1.2 px**, angle MAE **6.5 ± 18.9°** (computed only where l > 3 px), 1.49 M params, **79 FPS (3-step)**. With δ = 0.7 (the recommended threshold): F1 97.17 (1-step) / 96.12 (3-step), l MAE 1.2 ± 1.1 px, θ MAE 6.8°, 72 FPS.
- Table 2 baselines on the same data: WASB 3-step F1 95.77 at 95 FPS; WASB 1-step F1 96.00 at **42 FPS**; TrackNetV2 91.61 at 85 FPS; TrackNetV3 95.93 at 77 FPS.
- Trajectory prediction from 3 frames: position only, MAE 84.4 ± 136.6 px; with blur, 53.0 ± 87.1 px (median 28.4 → 19.9 px).
- est. on a laptop RTX 4070/4080 with FP16 and GPU-side peak picking: 100-200 frames/s per stream at step 3. The published FPS includes Python connected-components on CPU, which is the real bottleneck, so move threshold and argmax to the GPU.

**Known gotchas**
1. **Duplicate frames** break the 3-frame MIMO input (README). `utils/preprocess.process_video` has an SSIM dedupe, but it defaults to `filter=False`, so it does **not** dedupe despite the README. For WebRTC, dedupe by RTP timestamp or `captureTime`. Never feed a repeated frame into a window.
2. BGR/RGB mismatch in `runners/inference.py` (above).
3. The vis output path hard-codes `cv2.resize(vis_hm_pred, (1280, 720))`, which only matters for debug images.
4. Hydra needs `WASB_ROOT` set and writes an `outputs/` dir per run. For streaming, build the cfg once with `hydra.compose` (or a plain `OmegaConf.load` + merge) and keep the model resident.
5. `torch.load(model_path, map_location="cuda:0")` breaks on torch >= 2.6 because of the `weights_only` default.
6. Weights license is unstated (issue #2).

**Wrapper `track(frames) -> [(t, x, y, conf)]` (streaming design)**
- Keep a ring buffer of the last 3 deduped frames per camera, each with a capture timestamp `t_i` (sender clock, from WebRTC `captureTime`/RTP or a PWA-stamped `performance.timeOrigin + now`).
- Build the cfg dict from `inference_blurball.yaml` + `model/blurball.yaml` + `detector/blurball.yaml` (`step` is yours to manage).
- Each new frame (step = 1) or every 3rd frame (step = 3): `x = cat([norm(rgb(resize(f))) for f in buf], 0)[None]`, `trans = inverse affine` (`get_affine_transform(c=(w/2,h/2), s=max(h,w), rot=0, (512,288), inv=1)`, repeated 3x, shape `[1,3,2,3]`), then `run_tensor(x, trans)` → per-frame candidates.
- Batch cameras: stack the windows from 2-3 phones into `B = n_cams`. The model is fully convolutional, so the batch dimension is free.
- Emit `(t_i, x, y, conf, angle_deg, half_len_px_orig)`, where `conf = max(hm in blob)`. Keep blur in the record because the uncertainty model in section 9.5 uses it.
- Timestamp semantics: the blur centre is the ball position at **mid-exposure**, not at frame start. With rolling shutter, each row is exposed at a different time (about 10-30 ms top to bottom on phones). For sub-frame timing, use `t_frame + row/H * t_readout + t_exp/2`. If unknown, leave the offset as a constant and let the clap-sync absorb it.

**Fine-tune on ~200 of our frames**
- Label format (`datasets/tabletennis.py::load_csv`): one CSV per clip with columns `Frame, Visibility, X, Y, l, theta`, frames as `frames/<clip>/%05d.png`, directory layout `root/<match>/{frames,csv}/<clip>.csv`. Get the exact convention from `all_csv_midpoint_annotations.zip`: X, Y at the **blur midpoint**, l = half-length, theta in degrees.
- Labelling tool: any point tool. Click the two ends of the streak, then centre = midpoint, l = |p1 - p2|/2, theta = `atan2(dy, dx)`. About 5 s per frame, so 200 frames take about 20 min for one person.
- Command: `python src/main.py --config-name=train_blur dataset.root_dir=<ours> dataset.train.matches=[...] dataset.test.matches=[...] +model.init_weights_path=<blurball_best> runner.max_epochs=5 runner.find_fp1_epochs=[]` (`models/__init__.py` honours `init_weights_path`). The defaults are Adam lr 3e-4, batch 8 and 30 epochs with hard-sample mining from epoch 20 (`find_fp1_epochs`), so disable that for a quick run.
- 200 frames in about 67 three-frame windows is tiny. Use 3-5 epochs and keep a held-out rally. est. a few minutes on the laptop GPU.

---

## 2. TT3D (monocular table calibration and 3D trajectory)

**Repo:** https://github.com/cogsys-tuebingen/tt3d (commit `f079b79`, 2026-10-15), MIT. Paper: arXiv 2504.10035 (CVPRW 2025). Project page: https://cogsys-tuebingen.github.io/tt3d/.

**Install:** `pip install -r requirements.txt` (pins torch 2.4.1, numpy 1.24.4, scipy 1.10.1, opencv 4.8.1.78, smp 0.3.3, lightning 2.3.3, albumentations 1.4.18, casadi 3.7.0, wandb). Use `trophy-cv`; wandb is imported by `table_segmenter.py`, so `pip install wandb` or stub it out. **Run from the repo root.** `MODEL_PATH = Path("./weights/table_segmentation.ckpt")` is cwd-relative, and the modules use flat imports (`from table_segmenter import ...`), so for library use do `sys.path.insert(0, "tt3d/calibration")`.

**Weights:** `weights/table_segmentation.ckpt` (in git). A Lightning 2.0.4 checkpoint for smp **UnetPlusPlus** with encoder **timm-regnety_002**, about 2 M params. Paper: 0.92 mIoU on test, 70 fps, trained on 1,200 labelled images.

### 2a. Table segmentation → 4 corner suggestions (reuse this)
- `TableCalibrator(h, w)` → `.segment(img_bgr)` returns a uint8 mask at the original size.
  - Preprocess: BGR→RGB, `albumentations.Resize(height=320, width=640)` + `ToTensorV2()` with **no /255** (uint8 tensor). The model's `forward` then subtracts and divides by the encoder's mean and std. Copy `utils.preprocess()` exactly instead of re-implementing it.
  - Postprocess: `sigmoid > 0.8`, then resize back to the original size.
- `.process(img_bgr)` returns `(rvec, tvec, f, err, debug_img)`. Internally it runs mask clean → contours → `get_table_edges` (line fitting on the contour) → `extend_lines` → `filter_lines` → `HoughBundler` merge → choose the 4 lines. If 5-6 lines are found it tests all 4-line combinations by reprojection error. Then corner intersections go to `process_corners`.
  - `process_corners` tries 2 corner orderings. For each, `ReprojOpt.optimize_f` runs `scipy.optimize.least_squares` over **focal length f ∈ [500, 20000]** (init 1000) with an inner `cv2.solvePnP` on the 4 table corners. The principal point is fixed at the image centre and distortion is zero.
  - It rejects the result if mean reprojection error > 2 px (`er_thres`) or if the table depth `tvec_z` is outside [1, 20] m.
- **World frame:** origin at the **table-surface centre**, x across the width (±0.7625 m), y along the length (±1.37 m), z up. Corners `[-0.7625, 1.37, 0], [0.7625, 1.37, 0], [0.7625, -1.37, 0], [-0.7625, -1.37, 0]`; net top line `[±0.7625, 0, 0.1525]`.
- **What to reuse:** call `segment()` on the setup frame, get the corners from the line-intersection step (`self.fe.get_corners(lines)`), and **show them as draggable suggestions in the PWA**. Then run our own `solvePnP` with a better K: phone intrinsics from a one-time ChArUco session, or at least f from the TT3D search.
- **Gotchas:** open issue #1 reports "not enough lines" / "not enough corners" even on their own test videos, with no fix posted. The paper says player occlusion turns body contours into false table edges, and a **low camera elevation makes calibration unreliable**. So mount phones high (≥ 1.5 m, looking down) and run calibration on an empty-table frame. Calibrate once on the setup frame (cameras are static); do not run it per frame.

### 2b. 3D bounce / trajectory from one camera (post-game replay, or a 1-cam fallback)
- `tt3d/traj_seg/segmenter.py`:
  - `basic_segmenter(t, traj, deg=2, L=200, use_blur=True)` is dynamic-programming piecewise **quadratic** fitting of u(t) and v(t) (HOPS-style). The cost is fit residuals + 2·(blur-angle mismatch, used only where blur length ≥ 4) + L per segment. `traj` columns are `[u, v, visibility, l, theta]`.
  - `get_accurate_bouncing_pose(...)` gives the **sub-frame bounce time** and pixel position as the intersection of the neighbouring parabolas (needs ≥ 3 visible frames after the bounce).
  - `classify_q(...)` labels each breakpoint as racket hit (u-velocity sign flip) or table bounce (no flip). This assumes the camera's u axis roughly follows the table length (a side view).
- `tt3d/rally/geometry.py::intersect_ray_plane(rvec, tvec, img_pt, K, offset)` back-projects the bounce pixel onto the table plane. Use `offset=[0,0,0.02]` for the ball centre (radius 0.02 m). **This is the cheapest correct monocular bounce-to-table position: reuse it directly.**
- `rally/casadi_reconstruction.py::solve_trajectory` fits pre-bounce velocity and spin with a physics model (drag k_D = 3.8e-4, Magnus k_M = 4.86e-6, table COR 0.85, μ 0.3, m = 2.7 g, r = 0.02 m) by minimising reprojection error with IPOPT (CasADi). Velocity bounds: vx ±5, vy ±20, vz ∈ [-10, -0.5] m/s; spin ±900 rad/s. Use it for the AWS/post-game "Hawk-Eye replay".
- `rally/rally.py` hard-codes **`fps = 25  # HACK`** and reads `ball_traj_2D.csv` + `camera.yaml`. Change it to 30 (or, better, pass real timestamps).
- **Proven** (paper; simulated trajectories from 200 Hz ground truth, rendered at 25 fps, 2 px position noise): 3D MAE 12.4 cm side view (97.3% success), 17.1 cm oblique, 29.8 cm back view. Corner detection MAE 2.39 ± 1.47 px on 40 real images. The paper reports no real-footage 3D accuracy, and it estimates that 25 fps can cause up to ~40 cm error for a 10 m/s ball. **There is no measured bounce-position error in cm.**

---

## 3. ckjellson/tt_tracker (two-phone TT, closest open analogue)

**Repo:** https://github.com/ckjellson/tt_tracker (commit `dcda159`, 2022-02-26), MIT. Tested only on **two iPhones at 720p30**, one on each side of the table. No requirements file: numpy, scipy, opencv, matplotlib. It uses `scipy.ndimage.filters`, a deprecated namespace that still imports in SciPy 1.13 with a warning.

**Pipeline**
1. `crop_video.py`: **manual sync**. Press 1/2 to step either video until the frames match, then Esc trims both to equal length. There is no audio or clock sync.
2. `balltracker.py`: double-click **6 points per camera**: 4 table corners clockwise from top-left, then the 2 net-post tops "from bottom to top". Ball detection (`process_video.find_ball`) is MOG2 background subtraction (history 15, varThreshold 50) + `SimpleBlobDetector` (area ≥ 30, circularity ≥ 0.75, convexity ≥ 0.9). Swap this for BlurBall.
3. `analysis_functions.analyzer(...)` does everything else.

**Calibration and triangulation (the reusable bit)**
- World frame: origin at a table corner, x along the length (0..2.74), y along the width (0..1.525), z up. Points: corners `(0,1.525,0), (2.74,1.525,0), (2.74,0,0), (0,0,0)`; **net-post tops `(1.37, -0.1525, 0.15)` and `(1.37, 1.6775, 0.15)`** (posts stand 15.25 cm outside the sidelines; the net is 15.25 cm high). Camera 2's points are re-ordered (p1↔p3, p2↔p4, p5↔p6) because it faces the other way.
- `calc_P` is a normalised **DLT from 6 points** (SVD, Hartley-normalised 2D, sign fixed so the points sit in front). Then `rq()` → K and [R|t]. Six points with only two off the plane is the bare minimum (11 DOF from 12 equations), so it is noisy. **Replace it with `cv2.solvePnP` using a known K** (ChArUco or EXIF FOV) and the same 6 world points (`SOLVEPNP_ITERATIVE` + `solvePnPRefineLM`).
- `calc_3d_point` is a linear two-view triangulation in normalised coordinates (a 6x6 SVD). That is equivalent to `cv2.triangulatePoints`.
- Filters: keep only points with `-1<x<3.74, -1<y<2.525, -1<z<3`. A point is an outlier if it is > 0.5 m from the mean of its 4 neighbours (a 5-frame window).

**Bounce / "point" logic (what it actually does)**
- "Points" means rallies, segmented by a ±30-frame moving average of ball presence (threshold 0.5). There is **no scoring logic** (who won).
- Strokes: split where the x-velocity along the table length changes sign (`find_turns`).
- Bounces: per stroke longer than 10 frames, the local minima of z (`argrelextrema`). The first stroke of a point is treated as the serve and takes the 2 lowest minima; every other stroke takes the lowest minimum. z is then clamped to 0.
- Gaps are filled with cubic interpolation through 4 neighbouring 3D points.
- Real-time: the author says "possible on a good computer" but it would need restructuring (issue #2). It is batch code over whole arrays.

**What to port:** the 6-point world model, the stroke split by x-velocity sign, and the bounce as a z-minimum near the table. Replace the DLT with solvePnP and the z-minimum with audio-onset time + parabola intersection (section 9).

---

## 4. WASB-SBDT (multi-sport ball heatmaps)

**Repo:** https://github.com/nttcom/WASB-SBDT (commit `923462c`, 2023-11-23), MIT. Paper: arXiv 2311.05237 (BMVC 2023). Tested with Python 3.8, CUDA 11.3, torch 1.11 (Dockerfile: `nvcr.io/nvidia/tensorrt:21.06-py3`, numpy 1.22.4, hydra-core 1.2.0, opencv 4.6.0.66, timm 0.6.5).

**The repo has eval code only.** There is no video inference script (issues #2, #3, #5) and no training code ("Training: TBA", issue #6). **Use the BlurBall repo instead.** It is a WASB fork that adds `inference_wasb.yaml`, a video runner and training. Run `python src/main.py --config-name=inference_wasb detector.model_path=<wasb_tennis_best.pth.tar> +input_vid=<mp4>`; the `dataset:` entry is irrelevant at inference. A community wrapper also exists: https://github.com/indicium15/wasb-sbdt-inference (no license, 25 stars, 2026-01).

**Model zoo** (MODEL_ZOO.md; `setup_scripts/setup_weights.sh` names them):

| Sport | WASB file | Drive ID |
|---|---|---|
| Soccer | `wasb_soccer_best.pth.tar` | 1pg0MpMtKZ6ziYEr4oyfKYPOO3hjLw94l |
| Tennis | `wasb_tennis_best.pth.tar` | 14AeyIOCQ2UaQmbZLNQJa1H_eSwxUXk7z |
| Badminton | `wasb_badminton_best.pth.tar` | 17Ac0pO5oryh1JwgwTFQTjOKHY3umbDQu |
| Volleyball | `wasb_volleyball_best.pth.tar` | 1M9y4wPJqLc0K-z-Bo5DP8Ft5XwJuLqIS |
| Basketball | `wasb_basketball_best.pth.tar` | 1nfECuSyJvPUmz3njZCdFERSQQbERt8FU |

The same naming applies to `{deepball,deepball-large,ballseg,tracknetv2,restracknetv2,monotrack}_{sport}_best.pth.tar`. All the links resolved (HTTP 200) today.

**Input / output:** identical to BlurBall. 3 consecutive RGB frames, 512x288, ImageNet-normalised, `[B, 9, 288, 512]` → 3 heatmaps (HRNet with the stem strides removed, so the output is at full input resolution). Model name `hrnet` in `configs/model/wasb.yaml`, 1.5 M params. Detector `tracknetv2` postprocessor: threshold 0.5, connected components, weighted centroid, score = blob sum. Online tracker with `max_disp = 300` px; the motion term is dead code (see BlurBall). There is no blur output for the non-BlurBall weights.

**Proven** (paper Table 2, τ = 4 px; timing hardware not stated, the server had 4x V100):

| Sport | Step 3 F1 / FPS | Step 1 F1 / FPS | Dataset (res, fps) |
|---|---|---|---|
| Soccer | 88.3 / 55.7 | 88.2 / 23.6 | 1920x1080, 25 |
| Tennis | 94.0 / 58.2 | 95.6 / 35.2 | 1280x720, 30 |
| Badminton | 91.6 / 70.4 | 93.1 / 34.3 | 1280x720, 30 |
| Volleyball | 86.5 / 18.0 | 88.0 / 15.8 | 1280x720, n/a |
| Basketball | 80.6 / 30.2 | 82.6 / 22.3 | 1920x1080, n/a (NBA broadcast) |

Training: 30 epochs from scratch, Adam, batch 8, quality focal loss, binary GT (radius 2.5, min 0.7) with real-valued maps for hard samples, HLSM from epoch 20.

**Gotchas**
- **Broadcast-only training data.** Tennis comes from the TrackNet broadcast set and basketball from NBA broadcast (the largest per-frame motion, 33.7 px). Expect a domain drop on a low, sideline phone view. Issue #5 users report the tennis weights work on pickleball, sometimes better than on tennis, but they fire on the tennis centre mark.
- Commercial license for the weights is unclear (issue #12, open).
- `np.Inf` means numpy < 2.

**Wrapper / fine-tune:** the same as BlurBall (section 1), with cfg `model=wasb`, `detector=tracknetv2`, `tracker=online`. For fine-tuning, the BlurBall training runner accepts any `dataset/*.yaml`. Write a dataset class mirroring `datasets/tabletennis.py` with CSV `Frame, Visibility, X, Y` (the WASB/TrackNet format; drop l/theta and use `dataloader=default` with `binary_fixed_size` heatmaps), then `+model.init_weights_path=<wasb_<sport>_best.pth.tar>`. **Check the checkpoint key:** BlurBall's loader expects `["model_state_dict"]`, the same key the WASB detector reads.

---

## 5. TrackNetV3 (badminton) + HF mirror

**Repo:** https://github.com/qaz812345/TrackNetV3 (commit `6eda442`, 2026-09-03). The README states **MIT for both code and checkpoints** (commercial OK). Paper: ACM MM Asia 2023, https://dl.acm.org/doi/10.1145/3595916.3626370 (ACM blocks bots; link exists). Developed on Python 3.8.7, torch 1.10.0. requirements: numpy 1.22.4, opencv 4.4.0.46, pandas 2.0.0, Pillow 10.0.0, dash 2.5.1, plotly 5.8.2. Works in `trophy-cv` (est.). Recent commits added MPS/CPU device selection to `predict.py`.

**Weights:** Drive `TrackNetV3_ckpts.zip` → `ckpts/TrackNet_best.pt` + `ckpts/InpaintNet_best.pt`. The HF mirror `rahulanantharama/TrackNetV3-badminton` contains only `TrackNet_best.pt` (136 MB; no InpaintNet, no card, no license). Each checkpoint stores `param_dict` (`seq_len`, `bg_mode`) and `model`.

**Entry point:** `python predict.py --video_file x.mp4 --tracknet_file ckpts/TrackNet_best.pt --inpaintnet_file ckpts/InpaintNet_best.pt --save_dir out [--eval_mode weight|average|nonoverlap] [--large_video --max_sample_num 1800 --video_range s,e] [--output_video]` → `out/<name>_ball.csv` with columns `Frame, Visibility, X, Y` (original pixels).

**Exact input**
- `HEIGHT=288, WIDTH=512` (`utils/general.py`). The released model was trained with `--seq_len 8 --bg_mode concat`. Input channels = **(8+1)x3 = 27**: a **background median image** prepended to 8 RGB frames, all /255, no mean/std. Frames are read with cv2 and flipped to **RGB** (`frame_arr[..., ::-1]`).
- Background: `np.median` over the whole video's frames (capped by `--max_sample_num 1800`), computed on full-resolution frames and then resized. **For live use, compute it once on a few seconds of empty court before play, and recompute if the camera is bumped.**
- `bg_mode` options: `''` (Lx3), `subtract` (L), `subtract_concat` (Lx4), `concat` ((L+1)x3).
- Output: 8 heatmaps → threshold **0.5** → `cv2.findContours` → bounding box of the largest-area contour → centre. **There is no confidence value**: the paper's AP is "N.A." for this reason. In a wrapper, take `max(heatmap)` inside that contour as conf.
- `eval_mode=weight` (default) runs sliding windows with stride 1 and blends overlapping predictions with a temporal ensemble weight. That costs 8x the compute of `nonoverlap`.
- **InpaintNet** (rectification): `seq_len = 16`. Its input is normalised coordinates + an inpaint mask built by `generate_inpaint_mask` (gaps where visibility = 0, height threshold `h*0.05`). It **needs future frames**, so it is **post-game only**.

**Proven:** README / paper table on the Shuttlecock Trajectory Dataset test split: TrackNetV3 accuracy 97.51%, precision 97.79%, recall 99.33%, **F1 98.56%, 25.11 FPS** (TrackNetV2 F1 97.03%, 27.70 FPS; GPU not stated). On BlurBall's TT data: F1 95.93, 77 FPS (BlurBall Table 2, 2080 Ti).

**Gotchas**
- Issue #9: users measured **3 FPS on a T4** and 0.3 FPS on another GPU running `predict.py` end to end. The bottlenecks are the median background, the 8x-overlap ensemble and the CPU dataloader. For live use: `nonoverlap`, batch, and a precomputed median.
- Issue #22: **InpaintNet invents a fixed 16-point pattern** whenever a whole window has no detections, and marks those points `Visibility=1`. The CSV has no column to filter them out. Only inpaint gaps shorter than about 16 frames, and keep our own mask.
- Issue #15: the last ~6 frames' coordinates come out of order at the end of the video. Sort by `Frame`.
- Issue #23: Drive download blocked for some users. The HF mirror has the TrackNet half only.

**Wrapper:** keep a ring of 8 RGB frames at 512x288 + a cached median image; tensor `[1, 27, 288, 512]`; slide by 8 (nonoverlap) or by 1 with the ensemble. Emit `(t, x*w/512, y*h/288, conf)`.

**Fine-tune:** `train.py --model_name TrackNet --seq_len 8 --bg_mode concat --epochs N --batch_size 10 --alpha 0.5 --save_dir exp`. Data layout is `data/train/matchX/{csv/<rally>_ball.csv, video/<rally>.mp4}`, then `preprocess.py`, which extracts frames and medians. There is **no init-from-checkpoint flag**. `--resume_training` resumes from `exp/` (so copy `TrackNet_best.pt` there as the last checkpoint), or add `model.load_state_dict(torch.load(ckpt)['model'])` in `train.py`. Issue #14 ("Train from scratch", 10 comments) and #8 cover reproduction problems. With 200 frames, fine-tune only. Training from scratch took one user 4 days for 2 epochs on a 4090 (issue #9 comment).

---

## 6. asigatchov/fast-volleyball-tracking-inference

**Repo:** https://github.com/asigatchov/fast-volleyball-tracking-inference (commit `3aad1b9`, 2026-10-04), MIT LICENSE file. HF demo: https://huggingface.co/spaces/asigatchov/volleyball-tracking.

**Models (ONNX committed in `models/`, OpenVINO IR in `ov/`):** `VballNetV4c_seq9_grayscale_20260908_213829.onnx` (best), `VballNetGridV2b_seq9_grayscale_20260909_001145.onnx`, `VballNetGridV3_seq9_grayscale_20260908_225156.onnx`, `VballNetFastV1_seq9_grayscale_233_h288_w512.onnx`, plus `RAVEL-VB-011-9f.onnx` / `RAVEL-VB-012-9f.onnx` (players + ball + heads; sidecar `.json` gives input size and channels).

**Input/output (heatmap family; from `inference_onnx_seq_gray_v2.py` and the V4c sidecar JSON)**
- Input name `clip`, shape **`[1, 9, 288, 512]` float32**: **9 grayscale frames** (`cv2.COLOR_BGR2GRAY`, resize to 512x288, /255), stacked on the channel axis. The first call pads the buffer by repeating the first frame. The window slides by `batch_size` (= 9) new frames.
- V4c output `heatmaps` `[1, 18, 288, 512]`: 9 heatmaps then 9 radius maps (radius as a fraction of frame width). **The script infers model params from the filename** (`seq9`, `vballnetgrid`, ...) and sets `planes=1` for V4c, so the radius planes are ignored and the radius comes from a motion-contour heuristic. **Do not rename the files.**
- Decode: threshold (`--confidence_threshold`), largest contour, moment centroid → `(vis, x, y)` in 512x288 → scaled to the source resolution. CSV columns: `Frame, Visibility, X, Y, Radius`. No confidence is written; add `max(heatmap)` yourself.
- Grid family (`VballNetGrid*`): input 768x432, 48x27 grid, planes = (conf, x-offset, y-offset[, radius]), argmax cell.
- Some variants carry a GRU state (`h0`) between calls (`has_gru`). V4c is a pure heatmap model.

**Proven** (README; beach-test-raw, 3 clips, 886 labelled frames; hit = within 9 px at 1920 width; CPU OpenVINO on an i5-10400F, model call only): V4c **F1 0.902**, 149.6 FPS; GridV2b 0.892 / 122.9; GridV3 0.867 / 229.3; FastV1 0.799 / 1,140 FPS. Expect a full pipeline about 10% slower or more (decode shares the cores).

**Touch detection:** `src/track_calculator_with_court.py` with `PLAYER_CONTACTS.md`.
- Inputs: ball CSV + `--court_json_path` + `--players_json_path` (`ravel-vb-predictions-v1`: `predictions[]` with `class_id, score, track_id, frame_index, bbox_xyxy`), `--fps`, `--beach`.
- Contact = a break in the flight path after **subtracting gravity** (velocity fitted before and after each sample), with a player inside a reach ellipse around their box. NMS over a 0.3 s window. Confidence is raised by the player's approach speed.
- Technique comes from ball height relative to standing box height: `attack/block/serve` (above the head), `overhead_pass` (0-0.25), `dig` (0.25-0.95), `low_touch`.
- Output per `track_*.json`: a `player_interaction` block with `ball_start`/`ball_end` (`origin`: serve_zone / in_court / off_court / unattached), `contacts[]` (`frame, player_track_id, contact_type, depth_ratio, side, in_serve_zone, ball_above_net, confidence`) and `summary` (`contact_count, side_switch_count, serve_side`, ...). Possessions carry `max_touches_in_possession` and `over_three_touch_possessions`, which the author calls a *diagnostic* (it usually signals mis-attribution), so it is not a reliable "4 touches" call.

**Gotchas:** `requires-python >= 3.14`; a hard-coded Linux `LD_LIBRARY_PATH` for cuBLAS (harmless on Windows); `ort.preload_dlls()` needs onnxruntime >= 1.21. The models are volleyball/beach specific.

**Wrapper:** `ort.InferenceSession(path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])`. Ring of 9 gray frames → one call every 9 frames (300 ms latency at 30 fps), or slide by 1 to get the newest-frame output at 9x the cost (still about 150 calls/s on CPU for V4c). **Fine-tune:** there is no training code in this repo (training lives in the author's `vball-net-pytorch`, not public; the `asigatchov/vball-net` repo has Keras/TrackNetV4 code). Treat these as fixed weights.

---

## 7. Court keypoints → 4 corners → `cv2.solvePnP`

### 7a. yo-WASSUP/Good-Pickleball, `court/auto_detector.py` (commit `952fb47`), Apache-2.0
- **Classical, not learned.** Grayscale → Gaussian 5x5 → `bright = threshold(165)` OR `Canny(50,150)` → close → `HoughLinesP(threshold=80, minLineLength=max(40, 0.16·min(W,H)), maxLineGap)` → split into horizontal and vertical segments → fit a court model scored against a reference court template (`CourtReference.score_line_support`).
- Returns `{"corners": [(x,y)x4 int px, order TL, TR, BR, BL], "roi_corners", "mid_height", "confidence"}`, or `None` with a `last_diagnostics["reason"]` such as `no_hough_lines`, `not_enough_horizontal_or_vertical_lines`, `no_consistent_court_model`, `low_confidence` (< 0.72) or `low_reference_score` (< 0.85).
- Assumes a **behind-the-baseline view** with near-horizontal baselines and white lines brighter than 165. It falls back to a manual 4-click UI (`mapper.annotate_court`), and the result is cached in `outputs/<video>/court_annotations.txt`.
- Court model: 6.096 x 13.4112 m, NVZ 2.1336 m from the net; image-to-court mapping uses `cv2.getPerspectiveTransform`.
- **For solvePnP:** world points `(0,0,0), (6.096,0,0), (6.096,13.4112,0), (0,13.4112,0)` in TL, TR, BR, BL order (check that the order matches your camera side). Four coplanar points work with `SOLVEPNP_IPPE`, which is best for planar targets. Add the two net-post tops (0.9144 m at the posts) for a non-planar constraint.
- The ball model `weights/tennis-ball.pt` is the tennis YOLO weight, not trained on pickleballs (README). Bounce detection is marked experimental.

### 7b. yastrebksv/TennisCourtDetector (commit `e5cd4f1`, 2024-03), **no license file**
- Model: `BallTrackerNet(out_channels=15)` (TrackNet-style, **one image in**), input **640x360, BGR** (`cv2.imread`, no conversion, which matches training: `dataset.py` also uses `cv2.imread`), /255, no mean/std. Output: 15 sigmoid heatmaps (14 keypoints + court centre).
- `postprocess(heatmap*255, low_thresh=170, max_radius=25)` uses a Hough circle on the heatmap, with `scale=2` back to 1280x720. That means **the predicted coordinates are in 1280x720 space; resize the input from a 720p frame.** Optional `refine_kps` (white-line intersection in a 40 px crop; skipped for keypoints 8, 12 and 9) and `get_trans_matrix` (best-of-configurations homography to the reference court, which also fills occluded points).
- Keypoint order (`court_reference.py`, units ≈ cm including 10 cm line widths): 0-1 top baseline ends (286,561), (1379,561); 2-3 bottom baseline ends (286,2935), (1379,2935); 4-5 left singles line; 6-7 right singles line; 8-9 top service line; 10-11 bottom service line; 12-13 centre service line. **The 4 outer doubles corners are keypoints 0, 1, 2, 3**; world metres ≈ (ref − (286,561))/100 (10.93 x 23.74 m).
- Proven (README, 1280x720 val set, 7 px threshold): precision 0.963, accuracy 0.961, median distance 1.83 px with refine + homography (base model 0.936 / 2.83 px).
- Gotchas: **broadcast-only training** (issue #10: no support for non-broadcast views yet, so expect failures from a low phone angle). `np.Inf` in `homography.py` (fixed in the PR in issue #15). Memory leak on long videos (issue #3). Pinned torch 1.5.

### 7c. adithyanraj03/CourtKeyNet (commit `2dd886a`), MIT; weights on HF `Cracked-ANJ/CourtKeyNet`
- Weights: `finetuned/courtkeynet_finetuned.safetensors` (recommended, 4.98 MB) and `pretrained/courtkeynet_base.safetensors`. 1,238,856 params (from the embedded metadata). The model class is `courtkeynet/models/courtkeynet.py`; read `config.yaml` from HF for the constructor args.
- Input: **640x640 stretched (no letterbox), RGB, /255** (`inference.py::process_frame`).
- Output dict: `heatmaps [B,4,160,160]`, `kpts_init [B,4,2]`, `kpts_refined [B,4,2]` **normalised 0-1** (multiply by W and H), `features`. Exactly the **4 outer court corners** (a quadrilateral constraint module enforces convexity). No court-type output (issue #2), and it assumes every image *is* a court. The repo adds three ad-hoc confidence measures: heatmap peak, entropy and geometric validity.
- Proven (HF card): fine-tuned PCK 99.99%, IoU 99.67%; base PCK 99.09%, IoU 94.33%. **The PCK threshold and the test split are not stated**, so treat these as self-reported. Trained on badminton + tennis broadcast-style images (140k pretrain, 7k fine-tune).
- Gotchas: the obfuscated `_safetensors.py` (section 0.2); the GUI-only inference (tkinter); its `inference.py` originally loaded `.pt` only (issue #1). Load the model with `safetensors.torch.load_file` → `model.load_state_dict`.

**Bottom line for corners:** all three can produce 4 image corners for `solvePnP(world4x3, img4x2, K, dist, flags=SOLVEPNP_IPPE)`, then `solvePnPRefineLM`. Good-Pickleball and TennisCourtDetector give pixel corners directly. CourtKeyNet gives normalised corners. **For the demo, show the auto corners as draggable suggestions and let a human confirm.** Any of these failing on a phone angle costs 5 seconds, not the demo.

---

## 8. Roboflow Universe "Roundnet Project" (`public-workspace-tpxwk/roundnet-project`)

- Universe pages sit behind a Cloudflare challenge (HTTP 403 to curl and WebFetch); I did not bypass it. A search-engine snapshot of the page confirms: "Roundnet Project Object Detection Dataset and Pre-Trained Model", **861 images, CC BY 4.0**, labels **Net, Person with Ball, Spikeball**, published about 5 years ago (~2021). **The model version number and its mAP are unverified**: open the page in a browser to read `/<version>`.
- How to run:
  - **Hosted (simplest):** `pip install inference-sdk`, then
    `InferenceHTTPClient(api_url="https://serverless.roboflow.com", api_key=KEY).configure(InferenceConfiguration(api_key_transport="header")).infer(img, model_id="roundnet-project/<ver>")`. That is a network round-trip per frame, so it is not usable live at 30 fps.
  - **Local:** `pip install inference-gpu` (Roboflow docs use `--extra-index-url https://download.pytorch.org/whl/cu124`; `inference` 1.8.1 needs **Python >= 3.10, < 3.14**). Then `from inference import get_model; m = get_model(model_id="roundnet-project/<ver>", api_key=KEY); m.infer(img)`. Weights are downloaded and cached on first call. "Fine-tuned models and Universe models require an API key." Self-hosted inference uses no credits. A 2021 model is likely an old Roboflow-Train or YOLOv5-era export, so local download may or may not be offered for it. **Test tonight.**
  - **Recommended:** download the **dataset** (CC BY 4.0, with attribution) in YOLO or COCO format and fine-tune RF-DETR-nano (Apache) or YOLO (AGPL) ourselves for about 30 min. Then nothing at runtime depends on Roboflow.
- Rim-hit calls should come from **audio** (section 9.2), not this detector. "Spikeball" here is the ball class.

---

## 9. Methods

### 9.1 Audio onset detection for bounces
- **Sound physics (arXiv 2409.11760, Gossard et al., IEEE STAR 2025; code https://github.com/cogsys-tuebingen/tt_sounds, no license file; data CC BY-NC 4.0):** TT bounce energy sits around **11 kHz**. Their detector is a **5th-order Butterworth high-pass at 10 kHz (zero-phase)** + 1 ms frame energy compared against an exponential moving average × a multiplier (`MovingAverageDetect`; the repo also has `AdjacentFrameDetect` with abs threshold 0.005 and a 20 ms refractory period). Results: **precision 0.98, recall 1.00 (quiet) / 0.95 (speech noise), onset error 0.09 ms / 0.2 ms**. Recording: Zoom H4n Pro at 44.1 kHz, 0.5-2 m.
- **Classifier (same paper):** 15 ms clips (661 samples at 44.1 kHz), mono, 64-band Mel, n_fft 256 → 6-layer 2D CNN (Conv-ReLU-BN; k5 s2 first, then k3 s(2,1)) → GAP → Linear. Surface classes (10 rackets + table + floor + other): **F1 0.97**. Spin: F1 0.96 (topspin and backspin nearly indistinguishable). SVM baseline F1 0.94 (surface). CPU inference 4.2 ms (i7-1165G7). Mel beat raw spectrogram, MFCC and LFCC.
- **librosa route** (pin 0.11.0; doc URL that works: https://librosa.org/doc/0.11.0/generated/librosa.onset.onset_detect.html, the `/doc/main/` and `/doc/latest/` paths now 404):
  `env = librosa.onset.onset_strength(y=hp_filtered, sr=48000, hop_length=128, n_fft=512, fmin=6000, aggregate=np.median)` (spectral flux on a mel spectrogram; `onset_strength` takes `lag` and `max_size`), then
  `librosa.onset.onset_detect(onset_envelope=env, sr=48000, hop_length=128, units="time", backtrack=False, pre_max=..., post_max=..., pre_avg=..., post_avg=..., delta=..., wait=...)`.
  The defaults (from source) are pre_max 30 ms, post_max 0 ms+1 frame, pre_avg 100 ms, post_avg 100 ms+1 frame, **wait 30 ms**, delta 0.07, all in frames (`sr//hop_length` scaling). hop 128 at 48 kHz gives 2.7 ms resolution. Refine each onset to the sample with the energy peak in ±3 ms of the HPF signal.
- **Phone capture gotchas (engineering):** `getUserMedia({audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false, sampleRate: 48000, channelCount: 1}})`. AEC, NS and AGC smear or gate transients, and iOS may ignore some flags. Opus in WebRTC may band-limit or pre-echo an 11 kHz click at low bitrates. The safest path is an `AudioWorklet` sending raw 48 kHz PCM chunks with `currentTime`→wall-clock stamps over the data channel (96 kB/s per phone). At minimum, verify on the received stream that the 10-14 kHz band survives.

### 9.2 Light rim / net / ground (or table / paddle / floor) audio classifier
- **PANNs embeddings:** `pip install panns-inference==0.1.1` (MIT; https://github.com/qiuqiangkong/panns_inference). `from panns_inference import AudioTagging; at = AudioTagging(checkpoint_path=r"%USERPROFILE%\panns_data\Cnn14_mAP=0.431.pth", device="cuda"); clipwise, emb = at.inference(audio[None, :])`.
  - Audio must be **32 kHz mono float**, shape (batch, samples). `emb` is a **2048-d** vector. The model is Cnn14 (window 1024, hop 320, 64 mel, **fmax 14 kHz**, so an 11 kHz click is still in band).
  - Clip length: use about 0.5-1.0 s centred on the onset, zero-padded. Cnn14 pools globally, so very short clips are fine but noisier. est. 5-15 ms per clip on the GPU.
  - The import fetches the label CSV via `wget`, and construction downloads the 327 MB checkpoint via `wget`. **Both fail on Windows: pre-place the files.**
- **Classifier:** `sklearn.linear_model.LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")` on L2-normalised embeddings, 5-fold CV. With ~50 clips per class (rim / net / ground / player-touch / other), expect CV accuracy in the high 80s to 90s. That is my estimate: no published number exists for roundnet. Cheaper alternative that matches the TT paper's SVM baseline: 64-mel log spectrogram of a 15-30 ms window around the onset, flattened, then PCA(32) and SVM-RBF. Train on 20-50 claps per class recorded on-site Friday night (the room acoustics matter more than the model).
- **Fuse with vision:** accept a "rim" label only if the ball track is within about 15 cm of the rim ellipse at the onset time (±1 frame). Accept "table bounce" only if the ball's homography position is on the table and the vertical image velocity flips within ±2 frames.

### 9.3 Multi-view triangulation (2-3 phones)
- **Per camera:** K from `cv2.calibrateCamera` / ChArUco (once per phone model; phones lock focus poorly, so set the focus in the PWA if possible), or fx ≈ fy ≈ W/(2·tan(HFOV/2)) with the principal point at the centre. `solvePnP` on the table/court points → R, t; `P = K[R|t]`. Store the reprojection RMSE per camera as `σ_cal` (px).
- **2 cameras:** undistort first (`cv2.undistortPoints(pts, K, dist, P=K)`), then `X_h = cv2.triangulatePoints(P1, P2, x1.T, x2.T)` (inputs 2xN float64; output 4xN homogeneous; divide by the last row). This is linear DLT, not optimal, so refine with 2-3 Gauss-Newton steps on reprojection error, or use `cv2.correctMatches` with the fundamental matrix first.
- **3+ cameras / missing views:** aniposelib. `Camera(matrix=K, dist=d, size=(w,h), rvec=r, tvec=t, name=...)` → `CameraGroup([...])`, then `cg.triangulate(points_CxNx2, undistort=True)` (imports jax; NaN marks missing) or `cg.triangulate_ransac(points, min_cams=2)` (an outlier-robust subset search), plus `cg.reprojection_error(p3d, p2d)`. Writing your own N-view DLT is about 15 lines of numpy SVD and avoids jax entirely.
- **Asynchronous phones** (the main error source): with 30 fps unsynchronised capture, the frames are up to 16.7 ms apart, which is 17 cm at 10 m/s. Do **not** pair "nearest frames". Either (a) fit each camera's 2D track with a per-segment quadratic in time and evaluate every camera at common timestamps before triangulating, or (b) better, the parabola-to-rays fit below, which uses each observation at its own timestamp. Clock offset comes from NTP-style pings + clap sync (audio onset), refined by aligning bounce onsets across phones.

### 9.4 Parabola fitting between bounces (3D, multi-view, asynchronous)
- Model per flight segment k (between events): `X(t) = X0 + V0·(t−t0) + ½·g·(t−t0)²`, with `g = (0,0,−9.81)`. That is 6 unknowns. Drag for a TT ball (k_D/m ≈ 0.14 /m) bends a 0.5 s, 10 m/s flight by tens of cm, so either add a quadratic-drag term (as TT3D does) or keep segments short (TT flights are only 0.3-0.6 s).
- Residuals: for every detection (camera c, time t_i, pixel u_i), `r_i = (π_c(X(t_i + δ_c)) − u_i) / σ_i`, with δ_c the camera clock offset and σ_i the per-detection uncertainty (9.5). Solve with `scipy.optimize.least_squares(..., loss="huber", f_scale=2.0)`, initialised from linear triangulation of the 2-3 closest pairs. One camera also works (monocular + gravity is well-posed if the segment has ≥ 4-5 points and enough parallax; this is TT3D's approach).
- Bounce: intersect the segment-k and segment-(k+1) curves at `z = z_table + r_ball` (0.76 + 0.02 m for TT). Solve `X_k,z(t) = z_plane` for the root nearest the audio onset; the audio onset time `t_a` (±0.2 ms) **pins the bounce time**, so evaluate `X_k(t_a)` directly. In-plane bounce position = `(X_k,x(t_a), X_k,y(t_a))`.
- Covariance: `Σ_θ ≈ (JᵀJ)⁻¹·s²` from `least_squares` (`res.jac`, `s² = 2·res.cost/(m−6)`). Bounce covariance `Σ_b = G Σ_θ Gᵀ`, where G = ∂X(t_a)/∂θ (a 2x6 Jacobian of the x and y components).

### 9.5 P(in) = Φ(d/σ)
- `d`: signed distance from the bounce point to the boundary line along its inward normal n̂, positive inside. Apply the rule convention: in TT any touch of the table edge counts, so add r_ball (contact patch) at the edge; in tennis and pickleball the line is in, so measure to the line's outer edge.
- `σ² = n̂ᵀ Σ_b n̂ + σ_cal,world² + σ_sync²`, where:
  - `Σ_b` comes from the fit (9.4). If you instead project a single 2D bounce pixel through the homography: `Σ_world = J_H Σ_img J_Hᵀ`, where J_H is the 2x2 Jacobian of the homography at that pixel.
  - Per-detection image covariance from BlurBall: `Σ_img = R(θ)·diag(σ_∥², σ_⊥²)·R(θ)ᵀ`, with `σ_⊥ ≈ 1-1.5 px` (BlurBall position accuracy; F1 is at a 4 px threshold) and `σ_∥ = sqrt(σ_⊥² + (2l/√12)²)` (along-streak ambiguity, treating the full streak 2l as uniform; l in original px). For non-blur models use `σ = 2-4 px` isotropic, inflated by 1/conf.
  - `σ_cal,world`: the camera's PnP reprojection RMSE (px) times the local metres-per-pixel at the bounce point (|J_H|).
  - `σ_sync`: `|v_ball| · σ_Δt`. Audio-pinned bounces: σ_Δt ≈ 1 ms; video-only bounce time: about `frame_period/√12` ≈ 9.6 ms at 30 fps, which is about 10 cm at 10 m/s. **This term dominates at 30 fps unless the audio onset pins the time.**
- `P(in) = scipy.stats.norm.cdf(d / σ)`. Policy: call IN if P > 0.95, OUT if P < 0.05, otherwise "too close: replay / players decide". Show the 1σ and 2σ ellipse on the replay.

---

## 10. Blockers and risks (ranked)

1. **Dependency drift:** numpy 2, OpenCV 5, librosa 1.0, torch 2.6+ `weights_only`. Pin exactly as in section 0. If the GPU laptop is **RTX 50-series**, you need torch >= 2.7 with cu128, and must then handle `weights_only` (env var `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`).
2. **BlurBall is CUDA-only, takes 16:9 RGB frames only, and must not see duplicate frames.** Its inference script feeds BGR (likely a bug), and the README's "automatic unique frames" is actually disabled (`filter=False`). It was not trained on orange balls (TT3D paper), so use **white balls**.
3. **WASB has no inference or training code in its own repo.** Use the BlurBall repo's runners. All WASB weights come from broadcast footage. Expect degradation on phone angles (basketball F1 is only 80.6 even in-domain).
4. **TrackNetV3 live speed:** users report 0.3-3 FPS with the stock `predict.py` (issue #9). Use nonoverlap windows, a precomputed median, and no InpaintNet live. InpaintNet hallucinates on long gaps (#22).
5. **TT3D auto-calibration is fragile** (issue #1, unresolved; occlusion; low camera elevation). Use it only as a corner *suggestion* on an empty-table frame. Its smp encoder downloads ImageNet weights on first load, so cache them tonight.
6. **Court detectors are broadcast-trained** (TennisCourtDetector #10, CourtKeyNet). Good-Pickleball's is classical and needs bright lines and a baseline view. Keep human-confirmed 4-tap corners as the primary path.
7. **Roundnet Roboflow model:** about 5 years old, version and mAP unverified (Cloudflare blocks fetchers), needs an API key, and may not be locally exportable. Plan to fine-tune on its CC BY 4.0 dataset instead.
8. **Audio over WebRTC:** browser AEC, NS and AGC plus Opus can erase the 10-14 kHz transient the TT detector relies on. Send raw PCM through an AudioWorklet and verify the band on Friday.
9. **Licenses:** the BlurBall and WASB weights have unstated licenses (open issues #2 and #12), TennisCourtDetector has no license, tt_sounds data is CC BY-NC, and Good-* YOLO weights are AGPL. Verify each component's permissions for the intended use; a demo setting does not waive its terms.
10. **CourtKeyNet ships obfuscated `exec` code.** It decoded as benign at `2dd886a`, but bypass it anyway.

## Sources (all fetched or verified 2026-10-22)
- Repos (cloned): cogsys-tuebingen/blurball `2f0f549`, cogsys-tuebingen/tt3d `f079b79`, ckjellson/tt_tracker `dcda159`, nttcom/WASB-SBDT `923462c`, qaz812345/TrackNetV3 `6eda442`, asigatchov/fast-volleyball-tracking-inference `3aad1b9`, yo-WASSUP/Good-Pickleball `952fb47`, yastrebksv/TennisCourtDetector `e5cd4f1`, adithyanraj03/CourtKeyNet `2dd886a`; also cogsys-tuebingen/tt_sounds, qiuqiangkong/panns_inference, lambdaloop/aniposelib, indicium15/wasb-sbdt-inference (via `gh api`).
- Papers: BlurBall https://arxiv.org/abs/2509.18387 (Tables 2 and 3); TT3D https://arxiv.org/abs/2504.10035; WASB https://arxiv.org/abs/2311.05237 (Table 2); TT audio https://arxiv.org/abs/2409.11760; TrackNetV3 https://dl.acm.org/doi/10.1145/3595916.3626370 (403 to bots; numbers from the repo README).
- HF API: rahulanantharama/TrackNetV3-badminton, Cracked-ANJ/CourtKeyNet (+ README card). Zenodo API record 3987831 (PANNs).
- Nextcloud WebDAV listings: shares 6Z8TpM3sXRKHzGC (weights), C3pJEPKWQAkono7 (TT dataset), p3tw3EqE9csXoRn (tt_sounds).
- Roboflow: https://docs.roboflow.com/deployment/self-hosted/self-hosted ; the Universe page is Cloudflare-blocked, and the facts above come from a search snapshot.
- librosa onset defaults: librosa/librosa `librosa/onset.py` (main branch); docs at https://librosa.org/doc/0.11.0/.
- PyPI JSON for every version and Python constraint quoted in section 0.
