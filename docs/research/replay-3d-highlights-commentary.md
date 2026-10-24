# Trophy: open-source stack for replay and post-game features

Researched 2026-10-22. Every GitHub repo below was checked live through the GitHub API (license, stars, last push date). Hugging Face model IDs were checked through the HF API (200 = exists). "NOASSERTION" means this inventory does not establish the license; inspect the actual terms for the intended use. All SMPL/SMPL-X based tools also need the body model files, which require free registration at https://smpl.is.tue.mpg.de / https://smpl-x.is.tue.mpg.de (non-commercial). **Register on Day 0.**

Assumed hardware: one local laptop with an RTX 4080/4090-class GPU (12-24 GB VRAM), plus AWS (g5/g6e with 24-48 GB, or p4/p5 with 80 GB if credits allow). Phones: 2-4, not hardware-synced.

Adoptability scale: **A** = pip install plus a demo in under 2 hours. **B** = half a day with some environment pain. **C** = a stretch or risky in 36 h. **X** = don't.

---

## 0. Cross-cutting must-dos (they make or break everything else)

1. **Time sync across phones.** The phones aren't genlocked. Have everyone clap or air-horn at the start, then cross-correlate the audio tracks (numpy/scipy `correlate` on 16 kHz mono) to get offsets to about 1 frame. Pose2Sim also ships a keypoint-speed-based sync module.
2. **One world frame.** Ask the user to tap 4 court corners (or any known rectangle such as a key, a box, or cones at a measured distance) in each phone's first frame. `cv2.solvePnP` with known metric dimensions gives each phone's extrinsics in a shared metric frame, with ground plane z=0. That one step powers the auto-director geometry, triangulation, the 3D replay, and the first-person POV. Fallback or auto-calibration: VGGT / MapAnything / pi3 (below) on one frame per phone.
3. **Event log as the single source of truth.** Referee calls, scores, and detected actions go into `events.jsonl` (`t, type, player_id, cam_id, confidence`). Highlights, commentary, the score bug, and the director all read it.

---

## 1. 3D humans from video

### 1a. Monocular, world-grounded human mesh recovery (per phone)

| Repo | URL | License | Stars / last push | What it gives | Speed / HW | 36-h |
|---|---|---|---|---|---|---|
| **GVHMR** (SIGGRAPH Asia 24) | https://github.com/zju3dv/GVHMR | custom (NOASSERTION) | 2.2k / 2026-09 | World-grounded SMPL-X with gravity-aligned frame, from one moving or static video. `-s` flag = static camera (skips VO). Has a SimpleVO option (no DPVO build pain), a Colab, and an HF Space (https://huggingface.co/spaces/LittleFrog/GVHMR) | Paper claims SOTA accuracy *and* speed. The network itself is near-real-time; preprocessing (YOLO + ViTPose + ViT features) dominates. Expect roughly 1-2x real time on a 4090 per person-track | **A-** (best single pick). Caveat: the demo tracks the main person; for multiple players, loop over tracks |
| **PromptHMR** (CVPR 25) | https://github.com/yufu-wang/PromptHMR | custom | 500 / 2026-01 | **Multi-person, world-coordinate video pipeline** (`scripts/demo_video.py`, install with `--world-video=true`), uses SAM2 + DROID-SLAM + Metric3D + ViTPose. **Outputs GLB files directly** (human + camera motion) plus MCS (Meshcapade) and `results.pkl` | No numbers published; heavy stack (DROID-SLAM). Plan on minutes per 30 s clip | **B**. The GLB output is a big shortcut to Three.js |
| **WHAM** (CVPR 24) | https://github.com/yohanshin/WHAM | MIT | 1.2k / 2024-04 | World-grounded SMPL + foot contact; multi-person via tracking | Fast network; DPVO SLAM optional (skip it for static phones) | B (older deps) |
| **TRAM** (ECCV 24) | https://github.com/yufu-wang/tram | MIT | 645 / 2025-06 | Metric-scale world trajectory via masked DROID-SLAM + ZoeDepth | Slow (SLAM + depth) | B- |
| **4DHumans / HMR2.0** | https://github.com/shubham-goel/4D-Humans | MIT | 1.7k / 2026-02 | Per-frame SMPL + **PHALP** tracking (https://github.com/brjathu/PHALP, custom) in camera frame. Most robust multi-person tracker-of-meshes | Around 10+ fps on a 4090 | **A** for camera-frame meshes and tracking IDs |
| **CoMotion** (Apple) | https://github.com/apple-aiml-research/ml-comotion | Apple sample-code + model license | 303 / 2026-09 | Online multi-person 3D pose tracking from a single stream, robust to occlusion | Designed for streaming / online | B (good for a *live* referee) |
| **Human3R** (ICLR 26) | https://github.com/fanegg/Human3R | custom | 553 / 2025-12 | Joint 4D **human + scene** reconstruction (multi-person SMPL-X + point-cloud scene + camera) in one feed-forward pass from video (CUT3R-based) | Online / one stage; no FPS published | B. Interesting: gives the scene and the humans in the same frame |
| **NLF** (NeurIPS 24) | https://github.com/isarandi/nlf | MIT | 467 / 2026-10 | Fast multi-person SMPL/SMPL-X/any-skeleton from images (TorchScript model) | Very fast batched inference | A- (camera frame; pair with your PnP extrinsics) |
| **Multi-HMR** (ECCV 24) | https://github.com/naver/multi-hmr | custom (CC BY-NC-SA) | 423 / 2026-03 | Single-shot multi-person SMPL-X with camera-space depth | ~30 ms per frame (ViT-S) to a few hundred ms (ViT-L) | A- (per-frame; needs a tracker) |
| **CameraHMR** (3DV 25) | https://github.com/pixelite1201/CameraHMR | no license file | 262 / 2025-11 | Per-image SMPL with better camera/focal estimation | Fast | B (per-image only) |
| **SAM 3D Body** (Meta, 2025) | https://github.com/facebookresearch/sam-3d-body (HF `facebook/sam-3d-body-dinov3`) | SAM License | 3.6k / 2026-02 | Promptable single-image full-body mesh (body, hands, feet) on the **MHR** rig (https://github.com/facebookresearch/MHR, Apache-2.0), not SMPL | Per image, DINOv3 backbone, heavy | B- (no world trajectory; MHR adds conversion work) |
| **SMPLer-X** | https://github.com/MotrixLab/SMPLer-X (moved from caizhongang/) | custom | 1.2k / 2026-02 | Expressive SMPL-X per image | Per frame, ViT-H is heavy | C (superseded) |
| **Sapiens** (Meta) | https://github.com/facebookresearch/sapiens | custom (CC BY-NC) | 5.4k / 2026-05 | 2D pose (308 kp), segmentation, depth, normals; not a mesh | 0.3B-2B ViT; slow at high res | B (only for better 2D keypoints or masks) |
| **GENMO** (NVIDIA) | https://github.com/NVlabs/GENMO | custom | 534 / 2026-06 | Generalist motion model (estimation + generation) | Unknown | C |

**Verdict:** Use **GVHMR** per player-track from the best static phone; the `-s` static-cam flag fits tripod phones perfectly. Use **4DHumans/PHALP** or **YOLO + ByteTrack** for the multi-person IDs. If you want GLB out of the box, try **PromptHMR's video demo** on AWS in parallel.

### 1b. Multi-view triangulated pose (2-4 phones)

| Repo | URL | License | Notes | 36-h |
|---|---|---|---|---|
| **Pose2Sim** | https://github.com/perfanalytics/pose2sim | BSD-3 | Full pipeline: calibration (checkerboard **or scene points with measured coordinates**), **synchronization** (keypoint-speed based), RTMPose 2D, person association, triangulation, filtering, OpenSim IK. Pip install. Very active (pushed 2026-10-20) | **A-**: best multi-view choice. Outputs TRC/C3D 3D keypoints, not meshes |
| **EasyMocap** (ZJU) | https://github.com/zju3dv/EasyMocap | custom | Multi-view SMPL/SMPL-X fitting, multi-person, needs calibrated *and* synced cameras | B- (env and calibration fussy) |
| **FreeMoCap** | https://github.com/freemocap/freemocap | AGPL-3.0 | GUI app, ChArUco calibration, MediaPipe/RTMPose, Blender export | B (built for webcams on one PC, not phone uploads; ChArUco board needed) |

**Reality check:** With only 2-4 phones at wide baselines, occlusion is heavy and calibration error at court scale is large. **Best-of-both:** run monocular GVHMR per phone to get per-player SMPL motion, then use multi-view only to fix each player's *root position* on the court (triangulate pelvis or ankles from 2D detections plus your PnP extrinsics, or just intersect the foot ray with the ground plane z=0 from one calibrated camera). Ground-plane foot projection from one calibrated camera is about 10 lines of code and is robust.

### 1c. Calibration / scene geometry helpers

- **VGGT** (CVPR 25 Best Paper): https://github.com/facebookresearch/vggt (custom license, 14.5k stars). Feed-forward camera poses + depth + points from a few images in under 1 s. Use one frame per phone for auto-extrinsics, up to scale.
- **MapAnything** (Meta): https://github.com/facebookresearch/map-anything (Apache-2.0). Metric-scale feed-forward reconstruction.
- **pi3**: https://github.com/yyfz/Pi3 (BSD-3).
- **MASt3R**: https://github.com/naver/mast3r (CC BY-NC-SA).
- Still recommended: 4-corner PnP with known court dimensions (deterministic, metric, zero ML).

### 1d. Rendering SMPL in the browser (Three.js)

No well-maintained "SMPL to glTF" library exists (GitHub search finds only toy repos). Proven routes, from easiest to hardest:

1. **Stick figures / capsules (2 h, zero risk).** Export the 24 SMPL joint positions per frame to JSON; render capsules and spheres in Three.js. Works for every view including POV. Good fallback.
2. **Rigged SMPL glTF + drive bones (recommended, ~half day).** Build *one* rigged SMPL-neutral `.glb` once:
   - **Meshcapade SMPL Blender add-on**: https://github.com/Meshcapade/SMPL_blender_addon (custom). Import SMPL-X, File > Export glTF. Also loads animation `.npz`.
   - or **SMPL-to-FBX**: https://github.com/softcat477/SMPL-to-FBX (MIT), then Blender to glb.
   - In Three.js, load with `GLTFLoader`. Each frame, set `bone.quaternion` from the SMPL axis-angle pose (`quat.setFromAxisAngle(axis.normalize(), angle)`) in SMPL joint order, and set root translation from `transl` / world trajectory. Or bake into a `THREE.AnimationClip` with `QuaternionKeyframeTrack`s and play it with `AnimationMixer` (gives scrubbing and slow-mo for free). Bone order mismatches are the classic bug, so map by name.
3. **PromptHMR GLB output**: load directly with GLTFLoader (it already contains the motion).
4. **Server-side vertex baking** (`smplx` https://github.com/vchoutas/smplx forward pass, then per-frame vertices into glTF morph targets or a vertex buffer). Heavy files (6890 verts x frames); OK for a 5 s highlight only.
- Python preview: **viser** https://github.com/viser-project/viser (Apache-2.0, web-based; GVHMR, PromptHMR and Human3R demos use it) and **aitviewer** https://github.com/eth-ait/aitviewer (MIT, desktop).
- **Meshcapade smplcodec**: https://github.com/Meshcapade/smplcodec, a small SMPL motion file codec (MCS/SMPL files).
- Scene backdrop in the browser: **Spark** https://github.com/sparkjsdev/spark (MIT, Three.js Gaussian splat renderer, very active) or **GaussianSplats3D** https://github.com/mkkellogg/GaussianSplats3D (MIT). Capture the empty court as a static splat *before the game* with a phone app (Scaniverse / Polycam / Luma, export .ply/.spz), or train one with **gsplat** https://github.com/nerfstudio-project/gsplat (Apache-2.0, ~10-20 min on a 4090). Clean or align it in **SuperSplat** https://github.com/playcanvas/supersplat (MIT). Align splat and court frame by clicking the same 4 corners.

---

## 2. Novel-view / generative replays

| Model | URL | License | GPU / time per ~5 s clip | Fit for Trophy | 36-h |
|---|---|---|---|---|---|
| **ReCamMaster** (ICCV 25 best paper finalist, Kuaishou/Kling) | https://github.com/KlingAIResearch/ReCamMaster (old KwaiVGI path redirects); ckpt HF `KwaiVGI/ReCamMaster-Wan2.1` (redirects) | MIT code; Wan2.1 Apache-2.0 | Built on **Wan2.1-T2V-1.3B**, 81 frames at 832x480, via DiffSynth-Studio. Base Wan 1.3B is ~4 min per 5 s 480p on a 4090 (8.2 GB). ReCamMaster concatenates source + target tokens, so expect **~6-12 min on a 4090, ~3-5 min on an A100/H100** (estimate). 10 preset trajectories (pan, tilt, zoom, arc L/R, translate) or custom extrinsics | "Re-shoot this play with an arc-around": best-looking generative option. README warns the open Wan2.1 port is weaker than the paper's internal model; fast sports motion and small players will hallucinate | **B**. Run on AWS, pre-render the trophy clip only |
| **TrajectoryCrafter** (ICCV 25 oral) | https://github.com/TrajectoryCrafter/TrajectoryCrafter ; HF `TrajectoryCrafter/TrajectoryCrafter` | custom | **VRAM >= 28 GB** recommended (so an A100/L40S/H100 or g6e). Depth-warp (DepthCrafter) + CogVideoX-Fun diffusion; several minutes per clip | Arbitrary trajectories from monocular video, more geometrically faithful than ReCamMaster | B- |
| **GEN3C** (NVIDIA, CVPR 25 highlight) | https://github.com/nv-tlabs/GEN3C ; HF `nvidia/GEN3C-Cosmos-7B` | Apache-2.0 code (NVIDIA open model license for weights) | Cosmos-7B; tested only on H100/A100; **~43 GB even with full offload**; 8-GPU option; many minutes per clip | Best 3D consistency (3D cache), supports dynamic video | C (H100 only) |
| **CameraCtrl / CameraCtrl II** | https://github.com/hehao13/CameraCtrl | Apache-2.0 | AnimateDiff/SVD-based, 16-25 frames, low res | T2V/I2V camera control, not video re-render | X (outdated for this) |
| **Wan2.1/2.2-Fun Control-Camera** (Alibaba PAI) | https://github.com/aigc-apps/VideoX-Fun ; HF `alibaba-pai/Wan2.2-Fun-5B-Control-Camera`, `alibaba-pai/Wan2.2-Fun-A14B-Control-Camera`, `alibaba-pai/Wan2.1-Fun-V1.1-1.3B-Control-Camera` (all verified) | Apache-2.0 | 5B: 24 GB-class (4090) with offload, roughly 5-10 min per 5 s 720p; A14B: 80 GB or offload | **Image-to-video** with a camera path: animates *a still frame*, so the players' actual motion isn't preserved. OK for a stylized "intro" shot, wrong for replays | C |
| **Wan2.2-TI2V-5B** base | https://github.com/Wan-Video/Wan2.2 ; HF `Wan-AI/Wan2.2-TI2V-5B` | Apache-2.0 | README: 720p@24fps, runs on a 4090 (24 GB) with offload; "one of the fastest 720P models" (several minutes per 5 s) | Generic generation | C |
| **Stable Virtual Camera** | https://github.com/Stability-AI/stable-virtual-camera | custom (NC) | Static scenes only | Could make a fly-through of the empty-court splat | X for players |
| **SynCamMaster** | https://github.com/KlingAIResearch/SynCamMaster | none listed | Multi-view generation from text | Not a re-render tool | X |
| **ComfyUI-WanVideoWrapper** | https://github.com/kijai/ComfyUI-WanVideoWrapper | Apache-2.0 | Fastest way to run Wan + Fun-Camera + ReCamMaster-style workflows with fp8, block-swap and TeaCache speedups | B+ if someone on the team knows ComfyUI |
| **LightX2V** (Wan accelerator, linked from the Wan README) | https://github.com/ModelTC/LightX2V | Apache-2.0 (2.9k stars, pushed 2026-10-22) | Step-distilled Wan, runs on 8 GB to 5090; large speedups | Use it if generative replay is on the critical path |

### 4D Gaussian splatting from few cameras
- Methods: **4DGaussians** https://github.com/hustvl/4DGaussians (Apache-2.0), **4D-GS (Fudan)** https://github.com/fudan-zvg/4d-gaussian-splatting (MIT), **SpacetimeGaussians** https://github.com/oppo-us-research/SpacetimeGaussians (custom), **Shape of Motion** (monocular 4D) https://github.com/vye16/shape-of-motion (MIT).
- These assume **dense, synchronized, calibrated rigs** (the sports benchmarks are CMU Panoptic and the ST-NeRF basketball set with 32 cameras). With 2-4 unsynced phones at wide baselines, quality falls apart; per-scene training also takes 30-90 min. 2026 work on sparse-camera sports splats (e.g. a Lund thesis that splits human avatars from a static background) confirms that **decomposition** is the way to go.
- **Verdict: X for 36 h.** Do the decomposed version instead: **static court splat (pre-captured) + animated SMPL meshes (from §1)**. That *is* a 3D replay you can orbit, and it renders at 60 fps in the browser.

### Is first-person POV feasible?
- **Yes, via geometry, and it's cheap.** From the SMPL head joint (index 15) or the neck-to-head direction plus global orientation, place a Three.js `PerspectiveCamera` at head + 0.1 m forward. Orient it with the head joint's world rotation, smoothed with slerp and a ~5-frame low-pass (raw head rotation jitters and causes nausea). FOV around 90°. You see the court splat and the *other players' meshes* from that player's eyes, so it reads clearly as "POV". Hide the POV player's own head and body (or show the hands and forearms only). Add a little camera bob from the pelvis vertical velocity for game-feel.
- **Generative ego video: not feasible in 36 h.** **EgoX** (CVPR 26) https://github.com/DAVIAN-Robotics/EgoX (761 stars, no license file): exo-to-ego video from a single third-person video, LoRA on **Wan2.1-I2V-14B**, **>= 80 GB VRAM inference**. **Exo2Ego-V** https://github.com/showlab/Exo2Ego-V (Apache-2.0) needs 4 exo views and is trained on Ego-Exo4D. **WorldWander** https://github.com/showlab/WorldWander (ECCV 26). All are research-grade, slow, and trained on manipulation scenes rather than sports. You *could* run EgoX once on an 80 GB AWS GPU (p4d/p5) for one pre-rendered "wow" clip, but treat it as an optional stretch.
- Courtside / top-down / broadcast-high views are just preset Three.js camera poses in the same scene: courtside = eye height 1.6 m on the sideline; top-down = orthographic from z=15 m; broadcast-high = 8 m up and 12 m back, 30° down, tracking the ball or play centroid.

---

## 3. Frame interpolation (slow-mo)

| Tool | URL | License | Speed | Notes | 36-h |
|---|---|---|---|---|---|
| **Practical-RIFE** (v4.25/4.26) | https://github.com/hzwer/Practical-RIFE | MIT | RIFE paper: 30+ fps for 2x 720p on a 2080Ti; v4.x is faster. A 4090 does 1080p 4x roughly in real time | `python inference_video.py --multi=4 --video=in.mp4`. v4.25 is the recommended default. Weights are Google Drive links; download early | **A** |
| RIFE (ECCV22 original) | https://github.com/hzwer/ECCV2022-RIFE | MIT | same | Reference | A |
| **rife-ncnn-vulkan** | https://github.com/nihui/rife-ncnn-vulkan | MIT | Real time on most GPUs, any vendor; single binary | Best "it just works" CLI, including on AMD/Intel or a Mac | **A** |
| **FILM** (Google) | https://github.com/google-research/frame-interpolation | Apache-2.0 | Much slower (around 0.5-1 s per 1080p frame on a modern GPU); best on large motion | Use only for the 1-2 s hero moment if RIFE ghosts on a fast arm swing | B |
| **GIMM-VFI** (NeurIPS 24) | https://github.com/GSeanCDAT/GIMM-VFI | custom | Slow, arbitrary-timestep | Quality option | C |
| **EMA-VFI** (CVPR 23) | https://github.com/MCG-NJU/EMA-VFI | Apache-2.0 | Moderate | Alternative | B |
| **Framegen** (browser) | https://github.com/MONZikWasTaken/Framegen | MIT | Hand-written WGSL; **~2 ms per frame at 720p on an RTX 4060 Ti**; Chrome 121+ with shader-f16 | Real-time interpolation in the browser. Could power a live "slow-mo scrub" in the PWA viewer | B (integration) |
| **slow-motion-reality** (browser demo) | https://github.com/baditaflorin/slow-motion-reality | MIT | RIFE ONNX in a Web Worker via onnxruntime-web WebGPU | Reference for RIFE-ONNX in the browser; needs COOP/COEP headers | C (experimental, tiny repo) |
| vs-mlrt (RIFE ONNX/TensorRT) | https://github.com/AmusementClub/vs-mlrt | GPL-3.0 | TensorRT-fast | Source of RIFE ONNX exports | B |
| ffmpeg `minterpolate` | built in | LGPL/GPL | Slow, artifacts | Zero-install fallback: `-vf minterpolate=fps=120:mi_mode=mci` | A |

**Tip:** Ask players to record at 60 fps (or 120/240 on iPhone slo-mo) on at least one phone. Native high-fps beats any interpolation. Then RIFE 2-4x on top for 240-480 effective, played back at 30 fps for 8-16x slow-mo. Speed-ramp with ffmpeg `setpts` per segment.

---

## 4. Highlight detection and auto-editing

### Detection
- **SoccerNet action spotting** (https://github.com/SoccerNet/sn-spotting, no license file), **T-DEED** (https://github.com/arturxe2/T-DEED, GPL-3.0, precise event spotting at CVsports 24), **ball-action-spotting 1st place** (https://github.com/recokick/ball-action-spotting, MIT), **OSL-ActionSpotting** (https://github.com/OpenSportsLab/OSL-ActionSpotting, GPL-3.0). All are **trained on broadcast soccer**, so they won't transfer to phone footage of pickup basketball or spikeball without fine-tuning. **Don't use them in 36 h**; cite them as prior art.
- **Lighthouse** (https://github.com/line/lighthouse, Apache-2.0, active): pip library for *moment retrieval + highlight detection* (QD-DETR, UniVTG, etc.) with text queries ("player shoots the ball", "people celebrating"). It produces saliency scores per 2 s clip. **B+**, a useful generic scorer.
- **UniVTG** https://github.com/showlab/UniVTG (MIT), **TimeChat** https://github.com/RenShuhuai-Andy/TimeChat (BSD-3): older video-LLM temporal grounding.
- **Video-LLM scoring (recommended).** Cut candidate windows (5-8 s) around triggers, then ask a VLM: "Rate 0-10 how highlight-worthy; name the action; who (jersey color)". Options: a hosted multimodal API (fastest to build, natively takes video), or self-hosted **Qwen3-VL-8B** (https://github.com/QwenLM/Qwen3-VL, Apache-2.0, HF `Qwen/Qwen3-VL-8B-Instruct` verified) on a 24 GB GPU with vLLM. Qwen3-VL does timestamp grounding natively.
- **Audio excitement (cheap, strong signal).** **PANNs** (https://github.com/qiuqiangkong/panns_inference, MIT; `pip install panns-inference`) gives AudioSet class probabilities per 1 s frame, including *Cheering, Applause, Crowd, Shout, Whoop, Yell*. Combine with RMS-energy z-score and onset spikes (librosa), which is how the IBM golf work did it (cheer classifier + commentator tone). YAMNet (TF Hub / MediaPipe audio classifier) is the same idea in a lighter model. Research note: a Sept 2026 arXiv study ("Audio for Sports Highlight Detection: A Comparative Empirical Study", arXiv 2609.17923) shows audio-only baselines are surprisingly competitive.
- **Fusion heuristic (what to actually build):** `score(t) = 0.35*audio_cheer + 0.25*referee_event(score/foul/block) + 0.2*motion_energy (optical-flow magnitude in court ROI) + 0.2*VLM_rating`. Use peak picking with 8 s non-max suppression, then take the top-N. The "Play of the Game" is the argmax, with a tie-breaker from the VLM.
- **Shot boundaries:** PySceneDetect https://github.com/Breakthrough/PySceneDetect (BSD-3). Rarely needed for static phones, but useful for clip hygiene.

### Auto-reframe to 9:16
- **MediaPipe AutoFlip** is still in-tree at `mediapipe/examples/desktop/autoflip` in https://github.com/google-ai-edge/mediapipe (Apache-2.0), but it's a C++/Bazel build. **C**: skip it.
- **pyautoflip** https://github.com/AhmedHisham1/pyautoflip (MIT, pushed 2026-10-21): Python AutoFlip re-implementation with UNISAL saliency + faces, ONNX CPU. **A-**.
- **auto-vertical-reframe** https://github.com/KazKozDev/auto-vertical-reframe (MIT, 2026-10): CLI, PySceneDetect + YOLO11-seg + ByteTrack + MediaPipe faces + pose to a smooth 9:16 crop, with a debug preview. **A-**, closest to sports.
- **ClipsAI** https://github.com/ClipsAI/clipsai (MIT, stale 2024): resize module that tracks the speaker.
- **Roll your own (recommended, ~2 h):** You already have player tracks and the ball. Crop center x = EMA of the weighted centroid of (ball, ball-handler, active players), clamped and smoothed with a critically damped spring. 1080x1920 from 4K landscape (or 608x1080 from 1080p, then upscale). This beats saliency on sports.

### Programmatic editing / score bug
- **Remotion** https://github.com/remotion-dev/remotion (custom "Remotion License": **free for individuals and companies with 3 or fewer employees**, verify eligibility for the actual user or organization; 66k stars). React compositions: `<OffthreadVideo>` + `<Sequence>` + an animated score-bug component + `<Audio>` for the Cartesia commentary. `@remotion/renderer` / `npx remotion render` locally, or Remotion Lambda on AWS. Speed-ramp with `playbackRate`. The TikTok caption template https://github.com/remotion-dev/template-tiktok gives word-timed captions (feed it Cartesia word timestamps). **A** if anyone knows React. This is the best trophy-clip renderer.
- **ffmpeg** (via ffmpeg-python https://github.com/kkroening/ffmpeg-python, Apache-2.0): crop, `setpts` slow-mo, `overlay` PNG score bug, `drawtext`, `amix` commentary over a ducked game audio (`sidechaincompress`). **A**. Fast fallback.
- **MoviePy** https://github.com/Zulko/moviepy (MIT), **editly** https://github.com/mifi/editly (MIT, declarative JSON edits): alternatives.
- Prior-art "Opus Clip" open clones: https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator (MIT, 5.5k stars), https://github.com/fralapo/clippyme (MIT).

---

## 5. Multi-camera auto-director

**There's no maintained open-source sports virtual director.** Prior art to cite:
- Chen et al., *Learning Sports Camera Selection from Internet Videos* (WACV 19), arXiv 1809.02854: https://arxiv.org/abs/1809.02854 (soccer; learns the director's choice per frame).
- Chen, Wang, Heinzle, Carr, Smolic, Gross, *Computational Sports Broadcasting: Automated Director Assistance for Live Sports* (ICME 13, Disney Research): ranks views with cinematographic rules plus learned director style.
- JOANNEUM *Virtual Director* (Kaiser & Weiss 2013): rule-based shot selection and cutting for soccer and dance.
- *Automatic Camera Control and Directing with an UHD Collaborative Recording System*, arXiv 2208.05213: detection-driven, online and offline.
- **LangView**, *Which Viewpoint Shows it Best?* (CVPR 25 highlight), code https://github.com/SAGNIKMJR/lang-view (MIT): weakly supervised best-view selection on Ego-Exo4D, which includes basketball. Pretrained, but not plug-and-play for phones. Cite it.
- A 2026 Lund MSc thesis does zero-shot best-camera selection for basketball highlights with VLMs. This validates "ask a VLM which of these 4 thumbnails shows the play best" as a tie-breaker.

**Heuristic to implement (works, explainable, ~4 h).** Per camera c, per 0.5 s window:
- `vis_ball` = ball detected (YOLO "sports ball" class, or the ball track) and not near a frame edge
- `vis_actor` = bbox area of the ball-handler / event player (from the event log), with a penalty if occluded (IoU with other boxes)
- `facing` = the actor's torso normal (from SMPL global orientation) dotted with the camera's view direction. Favor cameras that see the player's front for shots and celebrations
- `quality` = sharpness (variance of the Laplacian) - motion blur - shake (phone gyro if you log it in the PWA, or global optical-flow magnitude)
- `geometry` = the camera is on the side of the court where the play is (distance to the play centroid in the world frame)
- `score_c = 0.3 vis_actor + 0.25 vis_ball + 0.2 facing + 0.15 quality + 0.1 geometry`
- Then **Viterbi/HMM smoothing**: switching cost lambda, minimum shot length 2 s, max 8 s, and cut *on action boundaries* (pass release, shot release) taken from the event log. For the slow-mo replay, use "replay from a different angle than the live cut" (the classic broadcast rule).
- Optional VLM tie-breaker: send the top-2 camera thumbnails and ask "which shows the [event] best?"

---

## 6. AI sports commentary

### Papers / code (prior art, soccer-centric)
- **SoccerNet-Caption** (dense video captioning of commentary): https://github.com/SoccerNet/sn-caption (no license)
- **MatchTime / MatchVoice** (EMNLP 24 oral): https://github.com/jyrao/MatchTime (no license). It realigns timestamps of 500+ games of commentary and trains a video-LLM commentator.
- **UniSoccer / MatchVision** (CVPR 25): https://github.com/jyrao/UniSoccer (MIT). Unified soccer understanding, commentary included.
- **LiveCC** (CVPR 25, Show Lab): https://github.com/showlab/livecc (no license file); HF `chenjoya/LiveCC-7B-Instruct` (verified; GGUF builds exist). Qwen2-VL-7B trained on streaming ASR transcripts and produces **real-time play-by-play commentary from video frames**. The only open model that truly does live video-to-commentary. 24 GB GPU. **B**: a fun "AI watches the game" mode, but it hallucinates names and scores.
- **SoccerNet-Echoes**: https://github.com/SoccerNet/sn-echoes (ASR commentary dataset).

### Recommended pipeline (grounded on the event log)
1. The event log (referee + detectors) gives structured JSON per event: `{t, event:"made_shot", player:"Jay", points:2, score:"11-9", streak:3, cam:2, speed_kmh, jump_height_cm}`. The 3D pipeline gives fun stats (jump height from the pelvis trajectory, sprint speed from the root trajectory).
2. **Live mode:** a small LLM (fast hosted model) with a system prompt for a persona (play-by-play vs. color commentator, 1-2 sentences, <= 15 words, never invent facts not in JSON). Stream tokens into the Cartesia WebSocket.
3. **Post-game mode:** a stronger LLM writes a 20-40 s script for the Play of the Game. Include build-up, call, reaction, and `[laughter]` / emotion tags. Then synthesize with word timestamps for captions, and duck game audio in Remotion/ffmpeg.
4. Two voices (play-by-play + color) = two Cartesia contexts on the same WebSocket.

### Cartesia (sponsor): verified from docs.cartesia.ai today
- **Current model:** `sonic-3.6` (alias to the latest stable; snapshot `sonic-3.6-2026-08-27`), backward compatible with `sonic-3.5`. `sonic-preview` = beta. 44 languages. Instant voice cloning (cloning a friend as the "announcer" is a great demo moment).
- **Latency:** Cartesia markets ~40-90 ms model latency; independent measurements put P50 time-to-first-audio around **~170-190 ms** over the network (Coval-style benchmarks, mid-2026). Fine for live calls.
- **WebSocket** (`wss://api.cartesia.ai/tts/websocket`, `Cartesia-Version` header or query param): send `{model_id, transcript, voice:{mode:"id", id}, output_format:{container:"raw", encoding:"pcm_f32le"|"pcm_s16le", sample_rate:44100}, context_id, continue:true}` per LLM chunk, then a final `continue:false` (or an empty transcript to close). Same `context_id` = continuous prosody across chunks. Set `max_buffer_delay_ms` when streaming LLM tokens. `{"context_id":..., "cancel":true}` cancels not-yet-started generation (use it to interrupt stale commentary when a new event happens). Contexts expire 1 s after the last audio. Multiple concurrent contexts per socket. Billing is ~1 credit per character.
- **Expressiveness:** `generation_config.emotion` (English): neutral, calm, angry, content, sad, scared are the best; the full list includes **excited, enthusiastic, elated, euphoric, triumphant, amazed, surprised**. `generation_config.speed` 0.6-1.5, `volume` 0.5-2.0. Inline SSML-style tags: `<emotion value="excited"/>`, `<speed ratio="1.3"/>`, `<volume ratio="1.5"/>`, plus `[laughter]`. Emotion must match the text. Sonic 3.6 infers pacing from the text and handles fillers ("uhm").
- **Timestamps:** word and phoneme timestamps are available (docs show them with SSE; WebSocket supports `add_timestamps`). Use them for burned-in captions.
- **Suggested voices** (docs): Daniel (en-US male) `47c38ca4-5f35-497b-b1a3-415245fb35e1`, Archie (en-GB male) `ef191366-f52f-447a-a398-ed8c0f2943a1`. Browse the library for a "sports announcer" style, or clone one.
- SDKs: Python https://github.com/cartesia-ai/cartesia-python (Apache-2.0), JS https://github.com/cartesia-ai/cartesia-js (Apache-2.0). Both updated 2026-10-16.
- **Cartesia Line** (https://github.com/cartesia-ai/line, Apache-2.0; docs https://docs.cartesia.ai/line): a Python voice-agent framework (STT "Ink" + Sonic + any LLM, turn-taking, interruptions). **Heads-up: Cartesia now says it stops *hosting* Line SDK agents on Dec 1, 2026, migrating to "Managed Agents" (`/v1/agents` REST API, config-only, no deploy)**; self-hosted Line code keeps working. Line/Managed Agents fit a **"talk to the ref / ask the commentator" voice feature** (e.g. "Hey Trophy, was that a foul?", answered from the event log and the clip). For one-way commentary, use the raw TTS WebSocket; Line is overkill. A small Line or Managed-Agents "ask the ref" interaction can complement Sonic commentary if it serves the product.
- Offline fallback TTS: Piper https://github.com/rhasspy/piper (MIT).

---

## 7. Privacy blur of non-players

| Tool | URL | License | Notes | 36-h |
|---|---|---|---|---|
| **deface** (ORB-HD) | https://github.com/ORB-HD/deface | MIT (CenterFace model MIT) | `pip install deface`, `deface in.mp4 --thresh 0.2 --mask-scale 1.3 --replacewith blur`. onnxruntime-gpu auto-offloads to CUDA; DirectML on Windows. Blurs **all** faces with no identity | **A**, but blurs players too |
| **supervision** (Roboflow) | https://github.com/roboflow/supervision | MIT | `BlurAnnotator` / `PixelateAnnotator`, ByteTrack wrapper, polygon zones (court ROI), video sink | **A** (glue layer) |
| **trackers** (Roboflow) | https://github.com/roboflow/trackers | Apache-2.0 | Clean SORT/ByteTrack/OC-SORT implementations | A |
| **ByteTrack** | https://github.com/FoundationVision/ByteTrack | MIT | Reference tracker | A |
| **BoxMOT** | https://github.com/mikel-brostrom/boxmot | AGPL-3.0 | BoT-SORT/StrongSORT/DeepOCSORT **with ReID** built in (OSNet weights auto-download) | A- |
| **Ultralytics YOLO11/26** | https://github.com/ultralytics/ultralytics | AGPL-3.0 | person/ball detection, pose, seg, `model.track()` | A (evaluate applicable AGPL obligations) |
| **InsightFace** (SCRFD detector + ArcFace) | https://github.com/deepinsight/insightface | code MIT-ish; **models non-commercial** | Face detection + 512-d embeddings for enrollment matching | A- |
| **Torchreid / OSNet** | https://github.com/KaiyangZhou/deep-person-reid | MIT | Body ReID embeddings (clothing) | B+ |
| **FastReID** | https://github.com/JDAI-CV/fast-reid | Apache-2.0 | Alternative ReID | B |
| **YOLOv5-Face** | https://github.com/deepcam-cn/yolov5-face | GPL-3.0 | Face detection + landmarks | B |
| **SAM 2 / SAM 3** | https://github.com/facebookresearch/sam2 (Apache-2.0), https://github.com/facebookresearch/sam3 (SAM license) | | Full-body masks for "blur the whole bystander" mode; SAM 3 takes text prompts ("person") with video tracking | B |
| **Grounded-SAM-2** | https://github.com/IDEA-Research/Grounded-SAM-2 | Apache-2.0 | Text prompt + track | B |

**Recommended "keep enrolled players, blur everyone else" pipeline:**
1. **Enrollment in the PWA:** each player takes a 3 s selfie video plus one full-body shot. Store ArcFace face embeddings (InsightFace `buffalo_l`) and an OSNet body embedding (it captures jersey and shirt color, which is more reliable than faces at court distance).
2. Per camera: YOLO person detection, then ByteTrack/BoT-SORT track IDs.
3. Per **track** (not per frame): aggregate face-embedding matches (cosine > 0.4, majority vote) **or** body ReID match **or** "track spent > 60% of its time inside the court polygon during play" → `player`. Everything else → `bystander`.
4. For bystanders: blur the face box (deface/CenterFace or SCRFD, expanded 1.3x) or the full body (bbox ellipse or SAM2 mask). Default to **blur unless confidently a player** (privacy-safe failure mode). Apply track-level hysteresis so a blur doesn't flicker on and off.
5. Render the blur in the same ffmpeg/Remotion export, and keep the raw footage only on the local laptop. Good privacy talking point: "faces of non-players never leave the laptop."

---

## Recommended stack per post-game feature (summary)

| Feature | Stack | Where it runs | Risk |
|---|---|---|---|
| Sync + calibration | Audio cross-correlation + 4-corner solvePnP (VGGT as auto fallback) | Laptop | Low |
| Tracking | YOLO11 + ByteTrack via supervision; jersey color / OSNet for player IDs | Laptop GPU | Low |
| Auto highlights | PANNs cheer/crowd + RMS energy + referee events + optical-flow energy, then VLM rerank (hosted or Qwen3-VL-8B); Lighthouse optional | Laptop + API | Low |
| Play of the Game clip | Top-ranked event → auto-director picks the angle → Practical-RIFE 4x (or native 120/240 fps) → own tracker-driven 9:16 crop (pyautoflip / auto-vertical-reframe as backup) → **Remotion** (score bug, captions from Cartesia timestamps, commentary audio, speed ramp) | Laptop (Remotion render) | Low-Med |
| Multi-angle auto-director | Heuristic per-camera score + HMM/Viterbi smoothing with min shot length; VLM tie-breaker; cite LangView / Chen & Carr | Laptop | Low |
| Cinematic slow-mo | Practical-RIFE v4.25 (or rife-ncnn-vulkan), FILM for the hero 1 s; Framegen-style WebGPU for in-browser scrub (stretch) | Laptop / browser | Low |
| 3D replay (courtside / top / broadcast / POV) | GVHMR (`-s` static cam) per player-track → root anchored by ground-plane foot projection → rigged SMPL glb (Meshcapade Blender add-on, once) driven by bone quaternions in **Three.js** → pre-captured court splat via **Spark** → 4 camera presets + POV from the head joint (smoothed). PromptHMR GLB output as a parallel try | AWS/laptop for HMR; browser for viewing | Med |
| Generative "re-shoot" (stretch) | ReCamMaster (Wan2.1-1.3B) arc-around on the single trophy clip, pre-rendered on AWS A100/H100 (~3-12 min); TrajectoryCrafter if >= 28 GB VRAM. Skip GEN3C, EgoX, 4DGS | AWS | High |
| AI commentary | Event-log-grounded LLM → Cartesia `sonic-3.6` WebSocket streaming (contexts, emotion=excited, `[laughter]`, 2 voices, cloned announcer), word timestamps → captions; LiveCC-7B as an "AI watches the raw video" experiment; Line / Managed Agents for "ask the ref" voice Q&A | API + laptop | Low |
| Privacy blur | Enrollment (ArcFace face + OSNet body) → per-track player vote → deface/SCRFD face blur or SAM2 body blur for non-players, via supervision BlurAnnotator | Authorized compute with private media access | Low-Med |

### Suggested team split (4 people, 36 h)
1. **Capture + sync + calibration + tracking + privacy blur** (Python, laptop).
2. **Highlights + auto-director + slow-mo + Remotion trophy clip.**
3. **3D: GVHMR → SMPL glb → Three.js viewer with splat + camera presets + POV.**
4. **PWA + referee events + LLM commentary + Cartesia (live and post-game) + an "ask the ref" Line agent.**

Hour-0 downloads (large / gated): SMPL & SMPL-X registration, GVHMR checkpoints (incl. ViTPose, HMR2), Practical-RIFE v4.25 weights (Google Drive), the PANNs CNN14 checkpoint, InsightFace buffalo_l, YOLO11 weights, and (if attempting) Wan2.1-T2V-1.3B + the ReCamMaster ckpt on the AWS box. Capture the court splat on Friday night.
