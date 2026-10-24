# Trophy: prior art for a universal AI referee (Cal Hacks 13.0, Oct 23-25 2026)

Research date: 2026-10-22. I checked each link marked **[verified]** by fetching it on that date. Star counts and licenses come from the GitHub page at fetch time. "36h" means how easily a team of 4 could adopt the item in a 36-hour hackathon: A = drop-in, B = a few hours of glue or fine-tuning, C = a reference only.

---

## 0. TL;DR

1. **Nobody has built a universal referee.** Each existing piece covers one rule in one sport, and most are demo-quality: ayushpai travel/double-dribble, Roboflow's 3-second violation notebook, Neerajj9 offside, TTNet bounce/net. The open space is the combination of a **sport-agnostic event layer**, an **LLM-compiled rule pack**, and **VLM adjudication of only the ambiguous clips**.
2. **Video-LLMs are not reliable referees.** RefereeBench (Apr 2026, 11 sports): Gemini-3-Pro and Doubao-Seed-1.8 score about 60%, and the best open model (Qwen3-VL) about 47%. They over-call fouls on clean clips and are weak at temporal grounding. Use them only to judge a clip whose event time the tracker already knows. SoccerNet 2025 MV-Foul supports this framing: a zero-shot video-LLM entry reached 49.3, close to the winning fine-tuned model's 52.2 and well above the 37.0 baseline.
3. **The best finds for table tennis are BlurBall and an audio bounce paper.** BlurBall (cogsys-tuebingen, MIT, pretrained table tennis weights plus a 64k-frame dataset) is a table tennis ball detector built on WASB. Sound-based bounce detection (Gossard et al., arXiv 2409.11760) reports millisecond-level timing and classifies the bounce surface (racket, table or floor) from audio alone. Phones have microphones. **Audio gives the timing and vision gives the location.**
4. **Correction to the design brief:** single-phone in/out, kitchen faults and table tennis edge balls are not "easy" near the line. They are easy only when the ball or foot is clearly away from the line. Make every geometric call return P(in) from a propagated error ellipse, and copy cricket DRS "umpire's call": when the call falls inside the uncertainty band, it goes to the players, a replay or the VLM. Hawk-Eye, with 10 or more synced high-speed cameras, claims a mean error of 2.2 to 3.6 mm. A 60 fps phone will be at centimetre scale.
5. **Licensing:** Ultralytics YOLO11/YOLO26 is AGPL-3.0. That is fine for an open-source hackathon repo, but if Trophy becomes a company, use RTMPose via rtmlib (Apache-2.0) and RF-DETR (Apache) instead. SoccerNet code is GPL-3.0 and data is behind an NDA. OpenTTGames is CC BY-NC-SA.

---

## 1. Rule-violation detectors (sport-specific)

### Basketball

| Item | URL | License / activity | What it gives | Speed / HW | Weights | 36h |
|---|---|---|---|---|---|---|
| **AI-Basketball-Referee** (ayushpai) [verified] | https://github.com/ayushpai/AI-Basketball-Referee | **No license**; 366 stars; last commit 2024-04-14 | `travel_detection.py`, `double_dribble.py`, plus `step_counting.py`, `dribble_counting.py`, `holding_basketball.py`, `blocking_foul.py`. Custom YOLOv8 ball model trained on 3k images, plus yolov8s-pose. Rules are hand-coded thresholds over ankle and wrist keypoints and ball position: steps without a dribble = travel; dribble, then hold, then dribble = double dribble. No numeric thresholds documented. | Real-time on a GPU laptop (YOLOv8s) | Yes (ball model on Google Drive, pose in repo) | **A**, as a reference for logic. Do not copy the code because it has no license; reimplement the logic. Expect many false travels from step counting. |
| **Roboflow 3-second violation** [verified] | https://roboflow.com/blog/detect-3-second-violation-ai-basketball ; Colab: https://colab.research.google.com/github/roboflow-ai/notebooks/blob/main/notebooks/basketball-ai-automatic-detection-of-3-second-violations.ipynb | Tutorial (Jul 2025) | Player detector, SAM2 zero-shot tracking, court-keypoint model, homography to the paint polygon, YOLO11-pose ankles, and a Supervision `PolygonZone` with `FPSBasedTimer`. The timer starts when one ankle enters the paint and resets only when both are out. The mask turns red after 3 s. Simplified: it ignores offense/defense and active guarding. | GPU; SAM2 is the slow part | Uses Roboflow-hosted models | **A**. This is the most demo-ready basketball violation and visually striking. The same zone-and-timer pattern covers out of bounds and backcourt. |
| **roboflow/sports** [verified] | https://github.com/roboflow/sports | MIT; 5.4k stars; active 2026 | Soccer pitch keypoints, ball and players, team classification utilities, basketball court-keypoint and jersey-OCR datasets | GPU | Roboflow Universe models and datasets | **A/B**. Court keypoints, homography and radar view |
| UGM Mediapipe-YOLO-LSTM travelling (2023) | https://ir.lib.ugm.ac.id/id/eprint/6350/ | Paper or thesis only | Classifies travelling with a stacked LSTM over MediaPipe pose and YOLO ball; reports 0.869 accuracy, at least 10 fps | CPU-friendly | No | C. Shows that a learned temporal model beats pure thresholds for travel |
| Roboflow shot evaluator | https://blog.roboflow.com/how-to-build-an-ai-basketball-shot-evaluator/ | Tutorial plus repo (2026) | RF-DETR ball and rim, RF-DETR keypoints; make/miss, release speed and arc. Runs locally on a laptop | Laptop | Yes | **A**. Scoring and shot clock for the post-game stats |
| UPF "ball tracking towards automatic detection of infractions" | https://repositori.upf.edu/handle/10230/25363 | Thesis | Goaltending and shots out of possession, using classical methods | - | - | C |

Shot clock and out of bounds: I found **no dedicated repo**. Both are straightforward once you have possession events (ball near a player's wrist), rim-touch events and a court homography. The shot clock is a timer in the state machine. Out of bounds is a test of ball or foot against the court polygon with an uncertainty band.

### Tennis / pickleball line calling and foot faults

| Item | URL | License / activity | What it gives | Speed | Weights | 36h |
|---|---|---|---|---|---|---|
| **TennisProject** (yastrebksv) [verified] | https://github.com/yastrebksv/TennisProject | **No license**; 238 stars | Complete pipeline: TrackNet ball, a 14-keypoint court detector, homography, and a CatBoost bounce regressor, so in/out on a minimap. 1280x720 input | GPU; not stated | Yes (Drive, all 3 parts) | **A** for the third sport from public tennis footage. Recommended. |
| **TennisCourtDetector** [verified] | https://github.com/yastrebksv/TennisCourtDetector | No license shown; 280 stars | Court keypoints at 0.961 accuracy and a 1.83 px median error after refinement plus homography | - | Yes | A |
| kjfk/tennis-bounce-detector (HF) | https://huggingface.co/kjfk/tennis-bounce-detector | HF model | Gradient boosting over 16 trajectory features, trained on the TrackNet dataset; PR-AUC about 0.95 on unseen matches. The author notes that a fixed height threshold failed and proposes candidates from upward kinks in the image trajectory. | CPU | Yes | A. A cheap bounce classifier |
| Monocular electronic line calling (arXiv 2107.09255) | https://arxiv.org/abs/2107.09255 | Paper | Fits curves to the descending and ascending trajectory segments and takes their intersection as the bounce point, with sub-frame precision | - | No | C. The method to copy for the bounce point and its uncertainty |
| PlayReplay / Owl AI / PB Vision | (commercial) | Closed | PlayReplay has a "Review" mode (players challenge, animated replay) and a "Live" mode. Automated line calls arrive on the PPA Tour and MLP in 2026. PB Vision requires all 4 court corners visible from a fixed camera. | - | - | Product framing: copy the challenge/review UX |
| Pickleball kitchen faults | Roboflow Universe only (e.g., https://universe.roboflow.com/meesoc/pickleball-detection-crqer) | CC BY 4.0 datasets | **No OSS kitchen-fault detector exists.** Building one needs (a) volley detection (paddle contact with no bounce since the last hit), (b) foot keypoints vs. the NVZ polygon including the line, and (c) a momentum window after contact. Rochester students adapted TrackNetV2 (badminton) to pickleball with transfer learning (https://www.hajim.rochester.edu/senior-design-day/pickleball-analytics/). | - | Ball detectors only | B. More a "moderate" call than an "easy" one |
| Foot faults | CalTennis (arXiv 2606.20542); race-walking fault detection (arXiv 2208.12646) | Papers | CalTennis reports that *all* pose models struggle with depth and foot contact. The race-walking paper does contact-based fault detection from HigherHRNet keypoints on a smartphone. | - | - | C. Foot-to-line contact is weak from a single phone; mark it beta |

### Table tennis

| Item | URL | License / activity | What it gives | Speed | Weights | 36h |
|---|---|---|---|---|---|---|
| **BlurBall** (Tübingen cogsys) [verified] | https://github.com/cogsys-tuebingen/blurball | **MIT**; 56 stars | Table tennis ball detection **plus blur length and orientation** (motion blur becomes velocity information). Built on WASB, multi-frame. Includes about 64k annotated real-game frames. Also ships weights for WASB, TrackNetV2, ResTrackNetV2, BallSeg, DeepBall and Monotrack | Not stated; GPU | **Yes** (Nextcloud) | **A**. Recommended table tennis ball tracker |
| **Sound-based bounce and spin** (Gossard et al., arXiv 2409.11760) [verified abstract] | https://arxiv.org/abs/2409.11760 | Paper says dataset and code are released (repo URL not on the abstract page; check the PDF) | Energy peak detection plus a CNN over 3,396 bounce samples: **millisecond-level bounce timing**, contact surface (racket, table or floor), spin yes/no. Contact lasts only 1.3 to 1.8 ms, so frame-based video misses it. | Real-time capable | Claimed | **A/B**. Even plain onset detection with the Web Audio API in the PWA gives "a bounce happened at t". Vision only has to say where. |
| TT3D (Tübingen) [verified] | https://github.com/cogsys-tuebingen/tt3d ; https://cogsys-tuebingen.github.io/tt3d/ | MIT; 52 stars | Monocular 3D trajectory from match video. Auto-calibrates the camera from the table edges and corners, fits the bounce state to reprojection error, infers spin | Offline | - | B. Post-game AWS 3D replay of an edge-ball or double-bounce call |
| spindoe | https://github.com/cogsys-tuebingen/spindoe | Apache-2.0 | Spin from the dot pattern on the ball | Needs printed balls | - | C |
| TTNet (OSAI, CVPRW 2020) | https://arxiv.org/abs/2004.09927 | Paper | Ball detection, bounce/net-hit event spotting (97.0% event accuracy), segmentation; under 6 ms per tensor on a consumer GPU | Real-time | - | C |
| TTNet PyTorch reimplementation (maudzung) [verified] | https://github.com/maudzung/TTNet-Real-time-Analysis-System-for-Table-Tennis-Pytorch | No license shown; 766 stars | Bounce and net events, ball, segmentation; over 120 fps on a 1080Ti | Fast | **No pretrained weights**, so you train it yourself | C in 36h |
| **OpenTTGames dataset** [verified] | https://lab.osai.ai/ | CC BY-NC-SA 4.0 | 5 training plus 7 test full-HD videos at **120 fps**, 4,271 bounce/net/empty events, ball coordinates, masks; about 35 GB | - | - | B. Use test clips for the "public footage" demo and calibration |
| Serve-foul detection (Yang et al., *Electronics* 2024) | https://openrepository.aut.ac.nz/items/5b4770cd-d1b8-4efd-b367-2f9d386b38f5 | Paper | Multi-camera YOLO ball plus a Transformer for trajectory keypoints (F1 0.93). Checks toss height and toss verticality | - | No | C. Confirms the toss rule is computable |
| Hung 2018 fault serve (*Sports*) | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6316619/ | Open access | High-speed camera toss trajectory with classical CV | - | - | C |
| Uplifting Table Tennis (arXiv 2511.20250), TT4D (arXiv 2605.01234) | https://arxiv.org/abs/2511.20250 ; https://arxiv.org/abs/2605.01234 | Papers; no code found | 2D to 3D uplift robust to missed detections and varying fps; 4D reconstruction from broadcast video | - | - | C |

Table tennis rule facts relevant to the design. On the serve, the ball rests on an open palm, is tossed near-vertically at least 16 cm, is struck behind the end line and above the playing surface, and is not hidden. A serve that touches the net and then lands correctly is a let. Edge vs. side is notoriously hard even for human umpires, so make it **beta**, not automatic.

### Soccer offside / VAR-style tools

| Item | URL | License | What it gives | 36h |
|---|---|---|---|---|
| Neerajj9 offside [verified] | https://github.com/Neerajj9/Computer-Vision-based-Offside-Detection-in-Soccer | MIT; 44 stars | Vanishing-point geometry from pitch lines, projection of the farthest body part, jersey-colour team clustering; F1 0.85. Pose weights on Drive | B. A third-sport option on still frames |
| Roboflow 3D offside (Jul 2026) | https://blog.roboflow.com/build-a-3d-soccer-offside-var-system/ | Tutorial | RF-DETR players, SAM3D Body for 3D reconstruction, HSV pitch lines; monocular | B |
| Single-camera real-time offside (arXiv 2502.16030) | https://arxiv.org/abs/2502.16030 | Paper | - | C |
| FIFA SAOT (context) | - | Commercial | 12 tracking cameras, 29 points per player at 50 Hz, ball IMU at 500 Hz to time the pass. The kick moment is the hard part, which is the same problem as table tennis bounce timing. | Framing |

---

## 2. SoccerNet and refereeing benchmarks

| Item | URL | License / activity | Notes | 36h |
|---|---|---|---|---|
| **SoccerNet-MVFoul / VARS** [verified] | https://github.com/SoccerNet/sn-mvfoul ; paper https://arxiv.org/abs/2304.04617 | GPL-3.0; 64 stars | 3,901 multi-view foul actions from 500 games, annotated by a pro referee with 10 properties: foul type (tackling, standing tackling, holding, pushing, elbowing, high leg, challenge, dive) and severity (no card / yellow / red). Splits are 2,916 / 411 / 301 / 273. Weights `14_model.pth.tar` on Drive, plus a GUI "VARS interface". **The data requires an NDA password.** | C for the demo (NDA latency). Use it as evidence in the pitch. |
| HF mirror (OpenSportsLab) [verified] | https://huggingface.co/datasets/OpenSportsLab/soccernetpro-classification-vars | AGPL-3.0, gated with click-through conditions | Branches `mvfoul` and `svfoul` in OSL JSON | B. Possibly faster access than the NDA; check the conditions |
| X-VARS (CVPRW 2024) | https://arxiv.org/abs/2404.06332 | Paper | Multimodal LLM referee with explanations. SoccerNet-XFoul has 22k video-question-answer triplets from more than 70 referees. Human study: explanations comparable to referees' | C. Supports the "explain the call" UX |
| SoccerNet 2024 results | https://arxiv.org/abs/2409.10587 | - | MV-Foul combined balanced accuracy: WJB 44.76, baseline 36.99 | - |
| **SoccerNet 2025 results** [verified] | https://arxiv.org/abs/2508.19182 | - | MV-Foul winner TAdaFormer-L/14 scored **52.22**. **A zero-shot video-LLM team with a composite rules prompt scored 49.32** (3rd). A GPT-4o RAG-over-keyframes entry scored 31.7, *below* baseline. So prompting with rule context and priors works on whole clips, but keyframe-only LLMs do not. | Key evidence for the VLM-adjudicator layer |
| sn-spotting (action and ball-action spotting) | https://github.com/SoccerNet/sn-spotting | - | Dev kit plus baselines (E2E-Spot, ball-action fork https://github.com/recokick/ball-action-spotting) | C |
| E2E-Spot (ECCV 2022) | https://github.com/jhong93/spot | BSD-3 | Precise frame-level event spotting (tennis, figure skating, FineDiving, FineGym) | B |
| **T-DEED** [verified] | https://github.com/arturxe2/T-DEED | GPL-3.0; 39 stars | Precise event spotting; configs and checkpoints for FigureSkating, FineDiving, FineGym, **Tennis**, SoccerNet, SoccerNetBall. 1st place in the 2024 ball-action-spotting challenge | B. Post-game on AWS for tennis event spotting |
| **RefereeBench** (Apr 2026) [verified] | https://arxiv.org/abs/2604.15736 | Paper (work in progress; no code link yet) | 11 sports, 925 videos, 6,475 QA pairs. Tasks: foul existence, foul/penalty classification and reasoning, entity perception, temporal grounding. **Best about 60% (Doubao-Seed-1.8, Gemini-3-Pro); best open model Qwen3-VL about 47%.** Models over-call fouls on normal clips and are weak at rule application and timing. Suggests RAG over rulebooks and a decomposition into detect, generate candidates, verify. | Cite in the pitch: "VLMs alone get 60%; we gate them" |
| Beyond the Single Camera (arXiv 2607.11844) | https://arxiv.org/abs/2607.11844 | Paper | Multi-view benchmark with an "Adjudicative Decision Reasoning" task (sanction from multiple angles, ground truth from referee reports) | Multi-phone argument |
| **SPORTU** (ICLR 2025) [verified repo] | https://github.com/chili-lab/SPORTU ; https://arxiv.org/abs/2410.08474 | No license shown | 900 rules/strategy text multiple-choice questions plus 1,701 slow-motion clips over 7 sports with 12,048 QA pairs, including foul detection and rule application. GPT-4o 71% on text; best on the hard video tasks only about 52.6 to 57.8% depending on the version | B. Pull a few clips as a sanity eval for the VLM prompt |
| DeepSport (arXiv 2511.12908) | https://arxiv.org/abs/2511.12908 | Paper; no code found | Agentic RL multi-sport MLLM with a frame-extraction tool (the model asks for frames); 12 sports | C. Design pattern: the VLM requests frames or zooms |
| Sports-QA | https://arxiv.org/abs/2401.01505 ; https://github.com/HopLee6/Sports-QA | - | VideoQA over MultiSports and FineGym | C |
| F³Set (ICLR 2025) | https://mlanthology.org/iclr/2025/liu2025iclr-3set/ | - | Fast, frequent, fine-grained events (tennis shots). Existing methods struggle with motion blur and subtle differences | C |
| FAVOR-Bench (NeurIPS 2025) | https://arxiv.org/abs/2503.14935 | - | 21 MLLMs show significant limits on fine-grained motion | C. Supports "don't trust VLMs for timing" |

---

## 3. Pose and action models for rule checks

| Model | URL | License | Speed / notes | Weights | 36h |
|---|---|---|---|---|---|
| **rtmlib** (RTMPose / RTMO / RTMW / DWPose / ViTPose, no mmcv) [verified] | https://github.com/Tau-J/rtmlib | **Apache-2.0**; 691 stars | `pip install rtmlib`; ONNX Runtime, OpenVINO or TensorRT. RTMPose paper (arXiv 2303.07399): RTMPose-m reaches 75.8 COCO AP, over 90 fps on an i7 CPU and over 430 fps on a GTX 1660 Ti. RTMO (arXiv 2312.07526) is one-stage multi-person, about 141 fps on a V100. Includes Halpe-26 with **foot keypoints (heel, big toe, small toe)**, which matters for line and foot calls. | Auto-download | **A**. Recommended |
| MMPose [verified] | https://github.com/open-mmlab/mmpose | Apache-2.0; 8.0k stars | Last release v1.3.0 (Jan 2024); maintenance has slowed, and mmcv install pain is common on Windows | Yes | B. Use rtmlib instead |
| Ultralytics YOLO11-pose / YOLO26-pose | https://docs.ultralytics.com/ ; https://www.ultralytics.com/license | **AGPL-3.0** or enterprise | Easiest API; detection, pose and ByteTrack in one call; TensorRT export | Yes | **A** for speed of building. Mind the license |
| ViTPose | https://github.com/ViTAE-Transformer/ViTPose (also in HF transformers) | Apache-2.0 | Higher accuracy, slower; good for post-game | Yes | B |
| MMAction2 (PoseC3D, ST-GCN, VideoMAE) | https://github.com/open-mmlab/mmaction2 | Apache-2.0 | Skeleton action recognition, e.g. "gather step", "pivot", "carry" | Kinetics / NTU weights | C. No sport-specific weights |
| SAM 3 / SAM 3.1 | https://github.com/facebookresearch/sam3 ; https://ai.meta.com/blog/segment-anything-model-3 | SAM license (custom; check it) | 848M parameters, text-prompted detect plus track. SAM 3.1 multiplexes 16 objects per pass, 16 to 32 fps on an **H100**. Too heavy for a laptop live; fine on AWS post-game | Yes (HF, gated) | B. Post-game masks and highlight overlays |
| WASB-SBDT [verified] | https://github.com/nttcom/WASB-SBDT | MIT; 201 stars | BMVC 2023 ball detection baseline over 5 sports (soccer, tennis, badminton, volleyball, basketball); 7.8 to 16.8 AP above prior methods; over 30 fps on 4 of 5 | MODEL_ZOO.md | **A/B** for basketball and tennis balls |
| TrackNetV3 [verified] | https://github.com/qaz812345/TrackNetV3 | MIT; 318 stars | Shuttlecock tracking plus InpaintNet trajectory repair; about 25 fps | Yes (Drive) | B. Badminton as a fourth sport, or fine-tune for pickleball |
| TrackNetV4 | https://time.griffith.edu.au/paper-sites/tracknet-v4 | - | Motion attention maps | Project site | C |
| Beach-volley TrackNetV3 fine-tune | https://huggingface.co/deadfast/beach-volley-vision-models | MIT | Volleyball ball | Yes | B |

**How people combine pose and ball to call a violation (common pattern):**
1. Ball detection gives a trajectory. A Kalman filter, or curve fitting on segments, gives a bounce or contact time and position with covariance.
2. Pose gives wrist and ankle keypoints. Possession is ball-to-wrist distance below a threshold. A step is a local minimum of ankle height, or a velocity drop of the ankle keypoint. Contact is a wrist-ball proximity spike plus an audio onset.
3. A court or table homography from detected keypoints, or from 4 corners the user taps in the PWA, maps everything to world coordinates.
4. A hand-written state machine turns predicates into calls: ayushpai counts steps since the last dribble; Roboflow uses a zone timer.

The weak links are step detection (keypoint jitter), foot-ground contact (no depth) and occlusion. Smooth with a One-Euro filter. Use a hysteresis "debounce" (N consecutive frames). Report confidence rather than a binary call.

---

## 4. Video-LLMs as a "universal ref"

| Model | URL | License | Video facts | Fit |
|---|---|---|---|---|
| **Gemini API (2.5 / 3 Pro / 3 Flash)** [verified docs] | https://ai.google.dev/gemini-api/docs/video-understanding | Paid API | **Default sampling is 1 fps.** The current docs set a custom fps and clipping in a `processing` object (`{"type":"static","fps":..., "start_offset":..., "end_offset":...}`); older SDKs used `videoMetadata {fps, startOffset, endOffset}`. Timestamps are in MM:SS. Tokens: 66 per frame at low `media_resolution`, 258 otherwise. Inline requests must be under 20 MB. The docs warn 1 fps "may miss details" in fast motion. Gemini 3 Pro launch blog (https://blog.google/technology/developers/gemini-3-pro-vision/): tuned for sampling above 1 fps, with a golf swing analysed at **10 fps**. **Live API takes about 1 fps JPEG frames** (Vertex docs), so it is useless for live officiating and fine for chatty commentary. | **Primary adjudicator**: send 2 to 4 s clips at 10 to 15 fps with overlays, plus the rule text. Pick Flash for latency and 3 Pro for hard calls |
| **Qwen3-VL** (2B/4B/8B/32B, 30B-A3B, 235B-A22B) [verified] | https://github.com/QwenLM/Qwen3-VL | Apache-2.0 | Default 2 fps (set `fps=4` and up); text-timestamp alignment for grounding; vLLM 0.11 or later | Local fallback on the GPU laptop (8B at 4-bit about 8 to 10 GB). RefereeBench best open model, about 47% |
| Qwen3.5 (Feb 2026, natively multimodal, Apache-2.0) | https://www.alibabagroup.com/document-1960233590314762240 | Apache-2.0 | 397B-A17B flagship; smaller 9B and 2B variants take video | Newer alternative; not benchmarked on refereeing |
| NVIDIA Cosmos-Reason2 (2B / 8B / 32B) | https://huggingface.co/nvidia/Cosmos-Reason2-2B ; https://huggingface.co/nvidia/Cosmos-Reason2-32B | NVIDIA Open Model License (commercial OK); gated on HF | Physical-AI reasoning VLM; 256K context. One guide lists at least 24 GB VRAM for 2B and 32 GB for 8B | C/B. Physics-plausibility checks ("did the ball bounce twice?") but heavy |
| Molmo2 (Ai2, Dec 2025) | https://playground.allenai.org ; arXiv 2601.10611 | Apache-2.0 (MolmoPoint-8B card) | **Video pointing and tracking**: outputs spatio-temporal points and tracks. Press reports it beats Gemini 3 on video tracking | B. Zero-shot "point to the ball at the bounce" for a new sport with no trained detector |
| VideoLLaMA3 | https://github.com/DAMO-NLP-SG/VideoLLaMA3 | Check the card | Temporal grounding demos (Charades-STA) | C |
| InternVL3.5 / LLaVA-Video / VideoChat3 | HF | Various | General video QA; no sports-ref evidence | C |
| TimeLens2-2B / TimePLE (Qwen3-VL-based temporal grounding) | https://huggingface.co/MCG-NJU/TimeLens2-2B ; https://huggingface.co/KlingTeam/TimePLE | BSD-3 / Apache-2.0 | Return time intervals for a text query | C. Post-game "find every carry" search |

**Evidence on fine-grained accuracy:** RefereeBench reports 60% at best, weak temporal grounding and over-calling. SPORTU hard tasks top out around 58%. FAVOR-Bench and F³Set show MLLMs and event detectors struggle with fast, fine-grained motion. In SoccerNet 2025 MV-Foul, a zero-shot video LLM with a rules prompt came close to the best fine-tuned model **for classifying a pre-cut foul clip**. Conclusion: **the VLM classifies; the tracker localizes in time.**

### "Rules as code": LLM to rule engine

| Item | URL | What it shows |
|---|---|---|
| **Code World Models for General Game Playing** (DeepMind, ICLR 2026) | https://arxiv.org/abs/2510.04542 | The LLM writes Python state transitions, legal moves and termination from natural-language rules plus trajectories, then refines against unit tests from observed traces. Matches or beats Gemini 2.5 Pro in 9 of 10 games. **This is the closest template for the Trophy rule compiler**: generate code, test it on recorded event traces, repair. |
| Distilling Game CWM generation (arXiv 2605.24375) | https://arxiv.org/abs/2605.24375 | Small models can do it; frontier models still best |
| Autoformalizing game scenarios (arXiv 2412.08805) | https://arxiv.org/abs/2412.08805 | 96% syntactic and 87% semantic correctness, natural language to logic programs |
| Boardwalk (SBGames 2025) | https://arxiv.org/abs/2508.16447 | Claude 3.7, GPT-4o and DeepSeek-V3 implement 12 board games against a fixed API. Using a constrained API improved correctness, which supports the "fixed predicate vocabulary" idea |
| Ludii grammar-based generation / GAVEL | https://arxiv.org/abs/2407.17404 ; https://arxiv.org/abs/2407.09388 | A context-free game DSL that LLMs can emit; grammar-constrained decoding improves validity |
| nl2spec (CAV 2023) | https://finkbeiner.groups.cispa.de/publications/CHMST23.html | Natural language to temporal logic, with **interactive editing of sub-formulas mapped back to sentence fragments**. A UX idea: click a rule clause and see its predicate |
| Lang2LTL / NL2TL | https://arxiv.org/abs/2302.11649 | Natural language to LTL. Rules like "a player may not hold the ball for more than 3 s in the paint" are metric temporal logic over an event stream |
| Robot-soccer FSM referee (Dadios & Park) | https://animorepository.dlsu.edu.ph/faculty_research/3672 | Hand-built FSM plus fuzzy evaluators for event detection; prior art for the "state machine plus fuzzy confidence" referee |
| RoboCup neuro-symbolic sportscasting (arXiv 2607.14809) | https://arxiv.org/abs/2607.14809 | A symbolic event extractor feeds an LLM. Notes that prompting on raw coordinates is unreliable, which supports emitting typed events, not raw tracks |

**No paper compiles a physical-sports rulebook into a referee FSM.** That is Trophy's novelty claim.

---

## 5. Uncertainty and confidence for calls

- **Hawk-Eye**: claims a mean error of 3.6 mm, later 2.2 mm, and publishes no maximum error (https://theconversation.com/out-goal-the-ball-was-in-but-could-hawk-eye-get-it-wrong-20741). Its displayed call is binary. Critics note that balls "out by 1 to 3 mm" may be in. Academic critique: Collins & Evans, "You cannot be serious! Public understanding of technology with special reference to Hawk-Eye" (*Public Understanding of Science*, 2008). **Trophy's differentiator is showing the ellipse.**
- **Cricket DRS "umpire's call"**: if the projected ball-tracking result falls within a marginal zone, the on-field decision stands. This maps directly to Trophy's tiers: when P(in) is between about 0.2 and 0.8, the call is "players decide / replay"; otherwise it is automatic.
- **Error ellipse recipe for in/out from one phone**:
  1. Each ball detection carries pixel noise σ_px, which grows with blur (BlurBall predicts blur length, so use it as σ).
  2. Fit the pre- and post-bounce trajectory segments with weighted least squares, or a Kalman smoother. Intersecting them gives the bounce pixel and its 2x2 covariance.
  3. Propagate through the homography Jacobian to court metres: Σ_world = J Σ_px Jᵀ. Add homography uncertainty from keypoint reprojection residuals.
  4. Compute the signed distance d to the line along its normal and σ_d = sqrt(nᵀ Σ_world n), then P(in) = Φ(d/σ_d).
  5. Render the 95% ellipse on the replay.
  6. Timing: at 60 fps a 25 m/s ball moves about 42 cm per frame, so sub-frame interpolation and **audio onset timing** (mic-video sync) matter more than detector accuracy.
- **Classifier calibration** for the travel, carry and double-dribble beta models and for VLM verdicts:
  - Temperature scaling (Guo et al. 2017, https://arxiv.org/abs/1706.04599) on a small labeled set you record at the venue (about 50 clips per call type).
  - Conformal prediction (Angelopoulos & Bates, https://arxiv.org/abs/2107.07511) gives a calibrated set, for example {travel, legal}. If the set has 2 items, the call is "challengeable". Note that TS can enlarge conformal sets (https://arxiv.org/abs/2402.04344).
  - VLMs have no usable logits through the API. Use self-consistency instead: run k=3 to 5 samples with varied frame offsets or prompts and take the vote share. Require the VLM to cite the frame timestamp and rule clause, and reject an answer if the cited time disagrees with the tracker event by more than 0.5 s.
- **Detector-level confidence**: combine detection score, track continuity (missing frames), keypoint confidence and multi-phone agreement. If two phones see the bounce, triangulate and shrink the ellipse; this is the multi-phone story.

---

## 6. Recommended architecture for "any game"

```
Phones (PWA: getUserMedia 60fps + Web Audio onset detector, WebRTC to laptop; user taps court/table corners once)
   |
[L1 Perception - sport-agnostic primitives, GPU laptop, real-time]
   ball: BlurBall (TT) / WASB (basketball, tennis) / YOLO fine-tune ; people: YOLO/RF-DETR + ByteTrack
   pose: rtmlib RTMPose Halpe-26 (feet) ; geometry: homography from taps or court-keypoint model
   audio: onset + surface classifier (racket / table / floor / dribble-on-floor)
   |
[L2 Event bus - typed events with uncertainty]
   bounce(t, xy, Σ, surface) | contact(player, t) | possession(player, start, end) | step(player, foot, t)
   in_zone(entity, zone, P) | crossing(entity, line, t, P) | net_hit(t) | rim_touch(t) | score(team)
   |
[L3 Rule pack = state machine compiled by LLM from rulebook text]
   Claude/GPT: rulebook -> YAML/Python over the FIXED predicate vocabulary above
   each rule: tier {auto | beta | players}, confidence formula, evidence clip window
   validation: LLM-generated unit traces (CWM-style) + replay on recorded games; human approves diff
   rules referencing predicates we can't sense -> auto-tagged "players decide" (fouls/intent)
   |
[L4 Adjudicator - only for beta calls or P in grey band]
   cut +/-1.5 s clip around tracker event, burn in overlays (ball trail, zone, ellipse)
   Gemini 3 Flash/Pro @10-15 fps (or Qwen3-VL-8B local) + rule clause -> {verdict, cited_ts, reason}, k-vote
   |
[L5 Call UI + challenge]  speaker/phone announces; challenge -> replay with ellipse + VLM rationale
[Post-game, AWS] SAM 3.1 masks, TT3D 3D replay, T-DEED/TimeLens event search, Gemini 3 Pro commentary + stats
```

Key design choices:
- **The fixed predicate vocabulary is the "universal" part.** Every racket or ball sport reduces to bounce, contact, possession, zone, crossing, timer and score. A new sport is a new rule pack plus a court template, with no new models. When the LLM compiler meets a rule that needs an unavailable predicate, it says so: "contact/intent: players decide".
- **The VLM is never on the hot path for easy calls** and never decides *when* something happened.
- **Audio is a first-class sensor** for racket sports and dribbles. It is cheap, works on phones and gives millisecond timing.

---

## 7. Which violations to demo

**Table tennis, live at the judging table** (fixed phone side-on at net height, plus an optional second phone end-on):
- AUTO: point scoring from the bounce sequence (bounce on the opponent's side, then no return, means a point); **double bounce**; ball not hitting the opponent's side; **serve must bounce on own side, then the opponent's**; **let on serve** (net-hit event from audio and vision plus a correct bounce).
- AUTO when clear, otherwise BETA: **serve toss under 16 cm** (wrist and ball height against the table plane from the side phone).
- BETA with ellipse: **edge vs. side ball** (show P(edge) and the replay; this is the strongest Hawk-Eye-style wow).
- PLAYERS: hidden serve, obstruction.

**Half-court basketball (recorded):**
- AUTO: **3-second-in-the-paint timer** (Roboflow pattern; red mask), **out of bounds** with a band, **shot clock** from possession and rim-touch, make/miss scoring.
- BETA, challengeable: **double dribble** (more reliable than travel: hold events are clear), **traveling** (step counter after the gather, high false-positive rate, so show the confidence).
- PLAYERS: blocking/charging and shooting fouls (show "players decide" explicitly to prove the tiering).

**Third sport from public footage. Recommended: tennis broadcast clips** through TennisProject (weights for ball, court and bounce all available) for **in/out with an error ellipse**.
- Alternative: show pickleball by **swapping the court template and having the LLM compile the USA Pickleball kitchen rule live**. The volley-in-NVZ rule then runs on the same primitives. This is the most convincing "universal" moment.
- Best judging moment: let a judge type a house rule ("no serves faster than X" / "make-it-take-it" / "bounce must land in the back half") and watch the rule pack recompile and call it on the next rally.

---

## 8. 36-hour adoption shortlist

| Need | Use | Why |
|---|---|---|
| Table tennis ball | BlurBall weights (MIT) | Purpose-built for table tennis, blur gives σ |
| Basketball / tennis ball | WASB (MIT) or YOLO11 fine-tuned on Roboflow Universe | Pretrained |
| Pose with feet | rtmlib RTMPose Halpe-26 (Apache) | Fast, no mmcv |
| Players + tracking | Ultralytics YOLO11 + ByteTrack (AGPL), or RF-DETR + supervision | Fastest to build |
| Court geometry | 4-corner tap in the PWA, then `cv2.findHomography`; TennisCourtDetector for public tennis footage | Robust and quick |
| Bounce timing | Web Audio onset in the PWA; optional Gossard CNN | ms timing |
| Rule compile | Claude/GPT, rulebook to YAML FSM over the predicate list, plus generated test traces | CWM pattern |
| Adjudicator | Gemini 3 Flash/Pro with a `processing` fps of 10 to 15 on 3 s clips; Qwen3-VL-8B local fallback | RefereeBench: best available, gated by the tracker |
| Confidence | Gaussian ellipse to P(in); temperature scaling or k-vote for classifiers; DRS-style grey band | Honest calls |
| Post-game | AWS GPU: SAM 3.1, TT3D, Gemini 3 Pro summaries | Heavy models off the laptop |

Risks:
1. Phone-to-laptop latency. Use WebRTC rather than WebSocket JPEG streaming, and give the phone a fixed mount.
2. 60 fps limits for table tennis. Some phones expose 120 fps through getUserMedia; test this on Thursday.
3. No-license repos (ayushpai, TennisProject, TTNet reimplementation). Use them as references or demo code, and keep them out of the shipped product.
4. AGPL Ultralytics if the project is commercialized.
5. VLM API latency of about 3 to 10 s per adjudication. That is acceptable for challengeable beta calls but not for auto calls.
