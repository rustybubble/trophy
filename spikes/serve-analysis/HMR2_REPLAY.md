# 4D Humans + two-camera ball replay on your footage

Executed locally on 2026-10-24. Open **http://127.0.0.1:8505/** while the local
server is running. The interactive replay supports orbiting, recording-camera
views, overhead view, seeking, slow motion, synchronized source playback and
video downloads.

This first reconstruction covers **original 8.00–10.87 seconds**, exported as
87 frames at 30 fps. It does not process the complete 107/113-second recordings.
The meshes come from actual official HMR2 checkpoint inference on both cameras,
followed by a two-view body fit. The ball comes from independent BlurBall model
detections and two-view triangulation. It is a reconstruction estimate; no
independent metric 3D ground truth is available for these recordings.

## Results

| Measurement | Executed result |
| --- | --- |
| Official HMR2 inference | 180 person frames per camera, native Apple MPS |
| Per-camera model run including load, processing and export | 21.2 / 20.6 seconds |
| Refined image time offset | camera 2 = camera 1 + **79.7 ms** |
| Separate moving-arm timing estimate | **83.3 ms** |
| Visible-joint image agreement before / after fitting | **37.6 / 5.2 px median** |
| Visible-joint image agreement after fitting, 95th percentile | **16.1 px** |
| Per-view median body fit | **4.2 / 6.6 px** |
| Accepted ball positions in the exported replay | **60 / 87 frames** |
| SMPL buffer adapter versus official SMPLLayer | **0.0 m** maximum vertex difference |
| MPS body calculation versus CPU | **2.38e-7 m** maximum vertex difference |
| Main project tests | **48 passed** |

The image measurements above use pretrained MediaPipe image landmarks as the
body fitting targets. They are not manually annotated ground truth, and the
fit residual is not a 3D accuracy measurement. The ball disappears in missing or
rejected frames; no physics path supplies the gaps.

Source videos are 4K/60 fps. The test used 1920 × 1080 exports of original seconds
8–14 and analyzed their first 180 frames. HMR2 runs every second source frame,
with both people in both views. The last few source frames are outside the
usable cross-view human interpolation interval and are excluded from export.

## What was actually run

1. Official [4D Humans](https://github.com/shubham-goel/4D-Humans) source, pinned
   to `efe18deff163b29dff87ddbd575fa29b716a356c`, remains unmodified under
   `vendor/4D-Humans`, including its MIT notice.
2. The official university-hosted `hmr2_data.tar.gz` was downloaded in verified
   HTTP byte ranges after repeated slow/disconnected transfers. The extracted
   checkpoint SHA256 is
   `c9ea09c834161468638c9de7a782c614e300c622709bf52967274c543ec72fcf`.
3. The checkpoint itself contains the SMPL template, shape and pose bases, joint
   regressor, parent hierarchy, skinning weights and faces. The adapter uses
   those exact published tensors with `smplx.lbs`. A separate registration-gated
   body-model file was therefore unnecessary for this checkpoint. The result was
   checked against `smplx.SMPLLayer` instantiated from the same buffers.
4. The official ViT-H backbone and SMPL transformer head load every inference
   weight with strict key/shape matching. RGB, normalization, antialiasing and
   crop geometry match upstream preprocessing, with a maximum normalized-input
   difference of 4.77e-7 in the executed comparison.
5. Known player crop IDs and pretrained MediaPipe image landmarks provide person
   boxes. The PHALP tracker and ViTDet detector are not used in this controlled
   two-player experiment. This is the HMR2 human reconstruction core from
   4D Humans, not a claim that the complete PHALP tracking pipeline was run.
6. Both cameras' actual HMR2 rotations and shapes initialize a shared SMPL body
   per player. Root position, joint rotations and a fixed per-player shape are
   fitted to visible landmarks in both views with temporal and weak floor
   priors. HMR2 does not estimate the ball or camera synchronization.
7. Native macOS OpenGL renders the recovered mesh surfaces to MP4, and Three.js
   displays the same vertex sequence interactively. The source comparison
   reprojects those meshes onto both real videos.

Exact inference reports, device execution, package versions, checksum provenance
and the SMPL parity check are under `artifacts/user-two-camera/hmr2/`. The
isolated `.venv-hmr2` reuses the existing core Torch installation; its added
top-level dependencies are pinned in `requirements-hmr2.in`.

## Calibration, synchronization and limitations

The recordings do not have measured intrinsics, distortion or external camera
poses. Explicitly inspected table image points initialize square-pixel pinhole
cameras with a centered principal point and no distortion. Camera 2 hides part
of the table, so its near half-table and net/table intersections initialize its
geometry. Static-background image matching transfers the initial geometry, and
per-frame homographies compensate dominant camera rotation. Camera translation,
parallax and rolling shutter are not fully modeled.

`configs/user-two-camera-calibration.json` records those image measurements and
their assumptions. The first half of the rally's ball correspondences refines
camera geometry and timing. The second half is held out from that fit. Its
all-correspondence epipolar error has a **3.6 px median and 224.3 px 95th
percentile**, showing severe outliers/occlusions that the reconstruction must
reject. Low residual on accepted samples alone would hide these failures.

The earlier audio alignment estimated 40 ms. Ball consistency refines this to
79.7 ms, and a separate moving-arm check estimates 83.3 ms. These are effective
image offsets, not verified hardware synchronization or proof of acoustic/video
latency sources.

Body silhouettes, visible limbs and movement can be compared directly in the
overlay video. Clothing, hair, exact anatomy, hidden joints and detailed hand
pose remain estimates. Rackets, racket-face angles, exact impact times and spin
are not recovered. A claimed centimeter-level 3D accuracy would require an
independent calibrated reference or motion-capture recording.

## Outputs and reproduction

- `artifacts/user-two-camera/reconstruction/orbit.mp4`: 1280 × 720 / 30 fps.
- `artifacts/user-two-camera/reconstruction/comparison.mp4`: two source mesh
  overlays and the 3D view, 1920 × 360 / 30 fps.
- `artifacts/user-two-camera/reconstruction/contact-sheet.jpg`: inspected frames.
- `artifacts/user-two-camera/reconstruction/fitted-bodies.npz`: fitted vertices,
  joints, rotations, shape and root positions in table coordinates.
- `artifacts/user-two-camera/reconstruction/scene.json`: ball positions, timing,
  geometry assumptions and fitting report.
- `vertices.f32` and `faces.u32`: the same meshes used in the interactive viewer.

The prepared local pipeline can be rerun using cached model assets:

```bash
bash scripts/run_user_hmr2_pipeline.sh
.venv/bin/python scripts/serve_replay.py \
  --directory artifacts/user-two-camera/reconstruction --port 8505
```

The script reuses existing inference outputs. It requires the prepared per-view
ball detections, pose estimates and geometry files from this experiment. To
update the estimated camera geometry after changing the recorded table points:

```bash
.venv/bin/python scripts/prepare_user_multiview.py
.venv-hmr2/bin/python scripts/fit_hmr2_multiview.py
.venv-hmr2/bin/python scripts/render_hmr2_replay.py
```

GPU inference and native graphics rendering need local device access. Verified
execution used MPS for the neural model and body fitting, native CPU for image
decode/preprocessing, and native OpenGL for video rendering. Model CPU fallback
is not enabled. The replay remains offline and local; the footage was not
uploaded to a remote inference service.
