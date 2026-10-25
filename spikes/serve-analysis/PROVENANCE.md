# Source and model provenance

BlurBall is Thomas Gossard et al.'s HRNet and Squeeze-and-Excitation multi-frame detector. The unmodified upstream snapshot is in `vendor/blurball/` (MIT license included). `vendor/UPSTREAM.json` pins commit `2f0f5496f7ba4b5b1a36790749935121b2ce972d`, archive checksum, and individual file checksums. Adapter and workflow code lives separately in `trophy/`.

- Repository: https://github.com/cogsys-tuebingen/blurball
- Project and dataset: https://cogsys-tuebingen.github.io/blurball/
- Official weights share, linked by upstream README: https://cloud.cs.uni-tuebingen.de/index.php/s/6Z8TpM3sXRKHzGC
- Official dataset share, linked by upstream README: https://cloud.cs.uni-tuebingen.de/index.php/s/C3pJEPKWQAkono7
- Weight filename: `blurball_best`, 6,156,034 bytes.
- SHA-256: `3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`.
- Public WebDAV endpoints and checksums are recorded in `scripts/setup_assets.py`.
- Scene `00` is in upstream's training split. Scenes `22`–`25` are the configured test split. The initial smoke sample is `00/rallies_videos/001.mp4`; the held-out validation sample is `22/rallies_videos/003.mp4`.
- The videos and annotation CSVs are real author-released dataset material. Local downloads do not establish a separate redistribution license. Fetch them from the official share using the helper; retain attribution.

# Verified source contract and intentional adaptations

| Topic | Upstream source | Trophy adapter |
|---|---|---|
| Architecture | `src/models/blurball.py`, `src/configs/model/blurball.yaml` | Imports the original `BlurBall` directly by path. Strict state-dict loading. No architecture edits or training. |
| Checkpoint | `src/detectors/blurball_detector.py` | Official checkpoint dictionary, `model_state_dict`; CPU map location followed by explicit native device placement. SHA-256 checked before loading. |
| Color | `src/utils/utils.py:read_image`, `src/dataloaders/dataset_loader.py` | Training uses PIL RGB. Convert OpenCV BGR to RGB explicitly. Upstream's standalone video runner misses this conversion. |
| Normalization | `src/dataloaders/__init__.py` | float32 RGB / 255, mean `[.485,.456,.406]`, std `[.229,.224,.225]`. |
| Spatial input | `src/dataloaders/dataset_loader.py`, `src/utils/image.py` | 512×288, OpenCV bilinear affine transform as in training. Full-frame aspect-preserving letterbox matches training on 16:9; preserves the full image on portrait/other aspect ratios instead of cropping. Exact inverse affine maps detections and blur vectors back to display-oriented source pixels. |
| Temporal input/output | `src/runners/inference.py`, model config | Three chronological RGB CHW frames concatenate into 9 channels; outputs are three 288×512 logit maps in the same chronological order. Sigmoid, no softmax. Step=1. All complete real windows, strongest component mass across contexts. First and last real output heads are retained. |
| Decoding | `src/detectors/blurball_postprocessor.py` | Threshold strictly `> threshold`, connected components, heatmap-weighted centroid. Rank by sum of probabilities, matching upstream selection. Also export the component's peak as a bounded score and global heatmap peak for diagnostics. These are uncalibrated. No interpolation or extrapolation. |
| Blur | Same postprocessor | Estimate principal axis and full streak extent from thresholded component shape. Scale the vector with the inverse affine. Export full length; upstream stores half extent and leaves its length in heatmap pixels. PCA axis orientation has a 180° ambiguity. |
| Selection | `src/trackers/online_blur.py` | Strongest real component by upstream mass. Omits upstream's fixed 300-source-pixel displacement gate, whose behavior depends on resolution; therefore a distant false positive can still win. |
| Duplicates | `src/utils/preprocess.py` | Upstream offers SSIM>.99 filtering but calls it with `filter=False`. Trophy removes adjacent pixel-identical decoded frames from temporal windows and maps detections back to all original indices. Near duplicates stay. Broad SSIM filtering could incorrectly remove a moving tiny ball on a static background. |
| Boundaries | Standalone runner drops incomplete windows | Fewer than three unique frames: export frames with null coordinates and `insufficient_temporal_context`. No repeated-frame padding. Complete overlapping windows cover both ends otherwise. |
| Devices | Detector asserts CUDA, wraps DataParallel | Single-device CPU/MPS execution. No CUDA assumptions. Model-forward CPU fallback is prohibited. Preprocessing, connected components/PCA, video decoding and encoding remain explicitly on CPU. |
| Video export | Standalone runner hardcodes 25 FPS | Preserve source reported average FPS as a rational value. H.264, yuv420p, MP4 faststart, pad odd dimensions only on right/bottom. Original rotated display orientation is baked into output. Audio omitted. |

This prototype targets ordinary constant-frame-rate phone and broadcast clips. For variable-frame-rate sources, output preview cadence is normalized to source reported average FPS; CSV/JSON retain decoder timestamps. Portrait export and rotation handling are tested separately from model accuracy; the model's ability to track in portrait footage remains unvalidated.
