# Trophy: open-source tracking / calibration / event stack research

Researched 2026-10-22 for Trophy.
Setup assumed: 2-4 phones running a PWA stream video (WebRTC) to a local GPU laptop (RTX-class laptop GPU, 8-16 GB), plus AWS for post-game batch work.
Demo: live table tennis at the judging table, a recorded half-court basketball game, optional third sport from public footage.

Stars, licenses and last-push dates were pulled from the GitHub API on 2026-10-22 (all links below were verified to exist). Speeds marked "est." are my engineering estimates, not published numbers; measure on your laptop on Friday night.

License flags used below:
- **[NC]** non-commercial / research-only. Check whether the specific terms permit the intended use.
- **[AGPL]** Ultralytics family (YOLOv8/11/26, YOLOE, BoxMOT). Evaluate the applicable license obligations for the chosen code, weights and deployment.
- **[GPL]** copyleft (GPL-2/3). Use where the applicable copyleft obligations can be met.
- **[NoLic]** no license file found. Do not infer reuse permission from public availability; obtain permission for code reuse or implement the documented ideas independently.

---

## 0. TL;DR recommendations

| Sport | Ball | Field / table calibration | Events / rules | Effort |
|---|---|---|---|---|
| **Table tennis (live)** | **BlurBall** table tennis weights (or WASB/TrackNetV2 table tennis weights from the same repo), MIT | **TT3D `table_segmentation.ckpt`** (MIT) or SAM 3 "ping pong table" mask, then a 4-corner quad, then `cv2.solvePnP` with the known table size (2.74 x 1.525 m, top 0.76 m) | **Audio onset (phone mic, librosa/scipy) fused with a vertical-velocity sign flip** gives bounces. Table half comes from homography; net from a plane crossing. Port `ckjellson/tt_tracker` Analyzer logic (MIT) | Medium. Ball model is plug-in; rules engine and fusion are your work |
| **Basketball (recorded half-court)** | **avishah3 `best.pt`** YOLOv8 ball+hoop (AGPL weights, NoLic code) for day 1; **RF-DETR** fine-tune on Roboflow ball/rim data (Apache) if time | 4-click homography on half-court lines; optional RF-DETR keypoints on `basketball-court-detection-2` (33 pts) | Make/miss = ball enters the rim box from above, then exits below (avishah3 linear-fit logic, or the Roboflow shot-evaluator freefall rule). Players via RF-DETR/YOLO person + ByteTrack (supervision), teams via SigLIP+KMeans (`roboflow/sports`) | Low-medium |
| **3rd sport, pick tennis** (referee story: in/out) | yastrebksv **TrackNet** tennis weights or WASB tennis weights | yastrebksv **TennisCourtDetector** (14 kp + homography refine) | yastrebksv **CatBoost bounce model** plus a point-in-polygon in/out call | Low (turnkey `TennisProject`, all weights on Drive, NoLic) |
| 3rd sport alt: soccer | `roboflow/sports` soccer ball model (YOLOv8) | `roboflow/sports` pitch keypoints (32 pts) | RADAR mode (top-down), possession | Lowest. One `setup.sh`, sample video included |
| 3rd sport alt: pickleball | WASB tennis weights or Good-Pickleball (tennis-ball YOLO) | Good-Pickleball auto court corners plus a court template | rule-based bounce + kitchen-zone check | Low-medium |

**Universal fallback ("any sport, zero training"):**
1. **Setup frame:** an LLM picks the sport's ontology (ball name, court dims, rules). **SAM 3 / SAM 3.1** (text prompt "basketball hoop", "court lines", "ball") or **Grounding DINO / OWLv2 / Florence-2** finds the playing surface, goals and players on one keyframe. Fit a homography from a court-dims template, or fall back to "tap 4 corners" in the PWA.
2. **Players:** YOLOE / YOLO-World / RF-DETR "person" + ByteTrack (roboflow/trackers or supervision).
3. **Ball:** do not trust zero-shot detectors on tiny blurred balls. Use a **motion-candidate detector** (frame differencing + blob size + temporal consistency + Kalman/parabola fit) seeded with the WASB weight closest in size and speed (tennis, badminton, volleyball, soccer or basketball). On AWS post-game, use **SAM 2 / SAMURAI click-to-track** or SAM 3 text-prompt video tracking for higher-quality replays.
4. **Teach a new sport in 15 min (stretch):** auto-label about 300 frames on AWS with SAM 3 / Grounding DINO plus motion, then fine-tune RF-DETR-nano or a WASB/TrackNet head. This makes a strong demo moment.

---

## 1. Ball detection and tracking

### 1a. TrackNet family (heatmap, multi-frame, best for tiny fast balls)

| Project | URL | License | Stars / activity | What it gives | Speed / HW | Weights | 36 h adopt |
|---|---|---|---|---|---|---|---|
| TrackNetV2 (PyTorch port) | https://github.com/ChgygLin/TrackNetV2-pytorch | NoLic | 64, last push 2024-11 | Clean PyTorch V2 (3-in/3-out heatmaps, 512x288) | ~27 FPS reported for V2 in the V3 README (desktop GPU); est. 60+ FPS with FP16 | Badminton | Easy, but WASB already bundles V2 weights for 5 sports |
| **TrackNetV3** | https://github.com/qaz812345/TrackNetV3 | MIT per README (GitHub shows NOASSERTION) | 318, pushed 2026-09 | V2 + background estimation + **InpaintNet trajectory rectification** (fills occlusion gaps) | 25 FPS vs V2 27.7 FPS (README); F1 98.56% on shuttlecock | Badminton (Google Drive zip) | Easy to run `predict.py`; badminton-only weights. The InpaintNet idea is reusable for any ball |
| TrackNetV4 (official) | https://github.com/TrackNetV4/TrackNetV4 | MIT | 109, last push 2025-06 | Motion attention maps (frame-difference prompts), ICASSP 2025 | Similar to V2 (+small overhead) | Tennis + badminton `.keras` checkpoints (docs/RESULT.md) | **TensorFlow/Keras**, which is awkward next to a PyTorch stack. Skip unless tennis weights beat yastrebksv |
| TrackNetV5 SDK | https://github.com/thaonan/TrackNetV5-SDK | **Proprietary, academic only** | 38 | Code only; **no public weights** | n/a | No | **Avoid** |
| TrackNet tennis (yastrebksv) | https://github.com/yastrebksv/TrackNet | NoLic | 255, last push 2024-03 | PyTorch TrackNet trained on the tennis TrackNet dataset; used by TennisProject | est. 30-60 FPS at 640x360 | Tennis (Drive) | Easy |
| TrackNet-Pickleball | https://github.com/AndrewDettor/TrackNet-Pickleball | NoLic | 37, 2023 | TrackNet fine-tuned for pickleball | similar | Check repo | Medium (old, small) |
| fast-volleyball-tracking-inference | https://github.com/asigatchov/fast-volleyball-tracking-inference | MIT | 72, **pushed 2026-10-22** | TrackNet-style VballNet, 9 grayscale frames at 512x288, **ONNX/OpenVINO** | **CPU** 120-1140 FPS (model only, i5-10400F) | Volleyball ONNX | Very easy. A good template for a fast ONNX runtime path; volleyball-only accuracy |

### 1b. WASB and its descendants (recommended core for ball tracking)

| Project | URL | License | Stars / activity | What it gives | Speed / HW | Weights | 36 h adopt |
|---|---|---|---|---|---|---|---|
| **WASB-SBDT** (NTT, BMVC 2023) | https://github.com/nttcom/WASB-SBDT | MIT | 201, last push 2023-11 (stable) | HRNet-based multi-frame heatmap detector + online tracker; also re-implements DeepBall, DeepBall-Large, BallSeg, TrackNetV2, ResTrackNetV2, MonoTrack | Not stated; small HRNet at 512x288, est. 50-150 FPS on laptop RTX with FP16 | **Weights for all 7 models x 5 sports (soccer, tennis, badminton, volleyball, basketball)**, Google Drive (MODEL_ZOO.md) | Medium: Hydra configs; inference script exists. **Basketball weights are directly useful for the half-court game** |
| **BlurBall** (Tübingen, 2025-26) | https://github.com/cogsys-tuebingen/blurball | MIT | 56, pushed 2026-05 | WASB fork for **table tennis**: predicts ball position + motion-blur length/orientation (blur gives direction and speed from a single frame) | Not stated; WASB-class. A step parameter trades speed for accuracy | **Table tennis weights for BlurBall, WASB, TrackNetV2, ResTrackNetV2, BallSeg, DeepBall(-L), MonoTrack** (NextCloud) + 64k-frame TT dataset | **Best table tennis ball model available.** Note: sensitive to duplicated frames (re-encoded video), which matters if WebRTC drops or duplicates frames. Dedupe by timestamp |

### 1c. Table tennis specific

| Project | URL | License | Stars | Notes | Adopt |
|---|---|---|---|---|---|
| TTNet (maudzung, unofficial) | https://github.com/maudzung/TTNet-Real-time-Analysis-System-for-Table-Tennis-Pytorch | NoLic | 766, 2024-08 | Ball + bounce/net events + table/human segmentation; >120 FPS on 1080 Ti claimed. **No pretrained weights** (issue #10 open since 2020, 17 comments; several users could not reproduce ball detection) | **Avoid.** Training on OpenTTGames (33 GB) does not fit in 36 h |
| OpenTTGames dataset | https://lab.osai.ai/ (mirror listing: https://hyper.ai/en/datasets/21496) | **CC BY-NC-SA 4.0 [NC]** | n/a | 120 fps full-HD, ball coords + bounce/net events + masks | Use only for evaluation clips, if at all |
| **TT3D** (CVSport 2025) | https://github.com/cogsys-tuebingen/tt3d | MIT | 52, **pushed 2026-10-15** | Monocular 3D ball trajectory (physics fit anchored at bounces), **auto camera calibration from table segmentation** (`weights/table_segmentation.ckpt` is in the repo), Kalman + outlier rejection, RTMPose/MotionBERT player pose | Medium. Lift the table-segmentation + calibrate step; the physics rally fit is a great "Hawk-Eye replay" for post-game on AWS |
| **tt_tracker** | https://github.com/ckjellson/tt_tracker | MIT | 139, 2022 | **Two phones (iPhone 720p30) on opposite sides**, manual table-corner + net clicks, manual frame sync, 3D triangulation, Analyzer computes strokes/points/**bounces**, bounce heatmap, 3D animation | Easy to borrow: closest open analogue to Trophy TT. Old OpenCV ball detector; swap in BlurBall |
| TableTennisBallTrajectory | https://github.com/amad-person/TableTennisBallTrajectory | check | small | 3-camera triangulation only when all views see the ball | Reference only |
| table-tennis-detection | https://github.com/lukianchenko/table-tennis-detection | NoLic | 12 | YOLOv5 + CSRT + bg subtraction | Reference only |
| Roboflow Universe TT ball models | e.g. https://universe.roboflow.com/pingpong-av5si/ball_detection-itvgr/model/2 | varies | n/a | YOLO11 single-frame ball detectors | Backup single-frame detector; worse than BlurBall on blur |

### 1d. Basketball

| Project | URL | License | Stars | Notes | Adopt |
|---|---|---|---|---|---|
| **AI-Basketball-Shot-Detection-Tracker** | https://github.com/avishah3/AI-Basketball-Shot-Detection-Tracker | NoLic (YOLOv8 weights, so [AGPL]) | 282, 2025-02 | YOLOv8 **ball + hoop**, `best.pt` committed in the repo, make/miss via cleaned trajectory + linear fit through the hoop (claims 95% score accuracy). Breaks with multiple balls/hoops in frame | **Very easy, day-1 baseline** |
| Roboflow AI Basketball Shot Evaluator (Aug 2026) | https://roboflow.com/blog/how-to-build-an-ai-basketball-shot-evaluator, code https://github.com/aarnavshah12/shot-tracker | RF-DETR Apache; repo NoLic | 7 | RF-DETR-S ball+rim (98.1% in-flight frame recall), RF-DETR keypoint pose zero-shot, make/miss via **drop-speed-after-net-occlusion** rule, release speed/arc, runs on a laptop | Easy-medium; better make/miss logic than avishah3. Weights cached via Roboflow (needs API key) |
| Roboflow Basketball AI (player ID) | https://roboflow.com/blog/identify-basketball-players, notebook: https://colab.research.google.com/github/roboflow-ai/notebooks/blob/main/notebooks/basketball-ai-how-to-detect-track-and-identify-basketball-players.ipynb | Apache (RF-DETR) | n/a | RF-DETR-S, 10 classes (ball, **ball-in-basket**, rim, player, jump-shot, layup-dunk, block, ...), SAM2 tracking, SigLIP+UMAP+KMeans teams, SmolVLM2/ResNet jersey OCR. **1-2 FPS on T4**, so post-game/AWS only | Medium; dataset `roboflow-jvuqo/basketball-player-detection-3-ycjdo` |
| basketball_analysis (abdullahtarek) | https://github.com/abdullahtarek/basketball_analysis | NoLic | 195, 2025-05 | Players/ball tracking, team assignment, court keypoints, possession, passes/interceptions, speed | Good reference for the post-game report |
| AI-basketball-analysis (chonyy) | https://github.com/chonyy/AI-basketball-analysis | **OpenPose [NC]** | 1,297, 2024 | Shot + pose analysis (old TF + OpenPose) | Avoid (old, NC) |
| WASB basketball weights | see 1b | MIT | | Multi-frame ball heatmap, better under hands/occlusion than single-frame YOLO | Use as a second opinion when YOLO loses the ball |

### 1e. Tennis / pickleball / badminton

| Project | URL | License | Stars | Notes | Adopt |
|---|---|---|---|---|---|
| **TennisProject** (yastrebksv) | https://github.com/yastrebksv/TennisProject | NoLic | 238, 2024-08 | TrackNet ball + 14-kp court detector + **CatBoost bounce regressor** + person detector + homography/minimap. All weights on Drive. Expects 1280x720 | **Easiest turnkey third sport** |
| tennis_analysis (abdullahtarek) | https://github.com/abdullahtarek/tennis_analysis | NoLic | 900, 2024-08 | YOLOv8 players + fine-tuned YOLO ball + ResNet court keypoints, shot speed, mini-court. Tutorial-grade | Easy; popular YouTube tutorial |
| tennis-tracking (ArtLabss) | https://github.com/ArtLabss/tennis-tracking | Unlicense | 718, 2024-02 | "Monocular Python HawkEye": TrackNet + classical court lines + bounce detection | Easy, older |
| **Good-Tennis / Good-Badminton / Good-Pickleball** (yo-WASSUP) | https://github.com/yo-WASSUP/Good-Tennis, https://github.com/yo-WASSUP/Good-Badminton (991 stars), https://github.com/yo-WASSUP/Good-Pickleball | Apache-2.0 code; YOLO weights (so [AGPL] in practice) | 202 / 991 / 42, pushed 2026-07 | Same pipeline per sport: YOLO11/26 ball, RTMPose/YOLO-pose, **auto 4-corner court detection with manual fallback**, court template mapping, rally segmentation, bounce points, heatmaps, Gradio WebUI. Release v0.1.0 ships `tennis-ball.pt`, `yolo11s-ball.pt` (shuttle), `yolo26s.pt`, pose ONNX. Pickleball reuses the tennis-ball model (README admits lower accuracy) | **Easy, modern, actively maintained.** Good for pickleball or tennis third-sport and as a code template for "court template + rules" |
| PBLineCaller | https://github.com/clssmitty/PBLineCaller | MIT | 20, 2025-02 | Pickleball in/out tool | Reference for in/out logic |
| CourtSide-Computer-Vision-v1 (HF) | https://huggingface.co/Davidsv/CourtSide-Computer-Vision-v1 | MIT | 13 likes | YOLO11n tennis ball | Backup single-frame tennis ball |

### 1f. Soccer: Roboflow Sports

| Project | URL | License | Stars | Notes | Adopt |
|---|---|---|---|---|---|
| **roboflow/sports** | https://github.com/roboflow/sports | MIT code; YOLOv8 weights [AGPL] | **5,436, pushed 2026-08** | `examples/soccer`: modes PITCH_DETECTION, PLAYER_DETECTION, BALL_DETECTION (with ball tracker + inference slicer), PLAYER_TRACKING, TEAM_CLASSIFICATION (SigLIP+UMAP+KMeans), **RADAR**. `setup.sh` downloads weights + sample videos. Datasets: soccer players / ball / pitch keypoints, **basketball court keypoints** (`roboflow-jvuqo/basketball-court-detection-2`, 33 pts), basketball jersey OCR | **Lowest-effort third sport** (RADAR view is a strong visual). Reuse its `TeamClassifier` and `ViewTransformer` for basketball |
| ball3d (CVPRW 2026) | https://github.com/lukaszgrad/ball3d | NOASSERTION | 10, 2026-06 | Physics-based 3D soccer ball from monocular video | Reference only |

---

## 2. Court / table / field keypoints and homography

| Project | URL | License | Stars | What it gives | Weights | Adopt |
|---|---|---|---|---|---|---|
| **TennisCourtDetector** | https://github.com/yastrebksv/TennisCourtDetector | NoLic | 280 | TrackNet-like single-image net, 14 kp (+center), refinement by white-line intersections, homography to a reference court. Precision 0.963, median error 1.83 px at 640x360 | Drive | Easy |
| **PnLCalib** | https://github.com/mguti97/PnLCalib | **GPL-2.0** | 110, pushed 2026-03 | Keypoint + line heatmaps then PnL refinement, full camera calibration (incl. lens distortion), single and multi-view; `inference.py --input_type video` | Release v1.0.0 (SV/MV, WC14, TSWC, WorldPose) | Medium (soccer only) |
| No Bells Just Whistles (NBJW) | https://github.com/mguti97/No-Bells-Just-Whistles | GPL-2.0 | 61 | Predecessor of PnLCalib (SoccerNet calibration challenge winner) | yes | Use PnLCalib instead |
| SoccerNet sn-calibration | https://github.com/SoccerNet/sn-calibration | NoLic | 111 | Dataset tools + baseline + eval for field calibration | baseline | Reference |
| TVCalib | https://github.com/MM4SPA/tvcalib | MIT | 54 | Differentiable segment-based calibration for soccer | yes | Medium |
| SoccerNet Game State (sn-gamestate) | https://github.com/SoccerNet/sn-gamestate | GPL-3.0 | 468, 2026-05 | End-to-end tracking + calibration + jersey + team, top-down minimap | yes | Heavy; reference |
| Basketball court keypoints | Dataset https://universe.roboflow.com/roboflow-jvuqo/basketball-court-detection-2 ; guide https://rfdetr.roboflow.com/latest/cookbooks/fine-tune_keypoints/ | dataset per Universe; RF-DETR Apache | n/a | 33 court landmarks; RF-DETR keypoint fine-tune cookbook covers basketball court + football pitch | Train yourself (~1 h on AWS GPU, est.) | Medium. **For a half-court phone video, 4-6 clicked points + `cv2.findHomography` is faster and more reliable** |
| Table tennis table | TT3D `weights/table_segmentation.ckpt` (https://github.com/cogsys-tuebingen/tt3d), or SAM 3 / Grounding DINO + SAM 2 mask | MIT / SAM License | | Mask, then `cv2.approxPolyDP` to a quad, then 4 corners | in repo | Easy |
| Good-* auto court corners | see 1e | Apache | | Auto-detect 4 outer corners with click fallback; court templates (pickleball 6.096 x 13.4112 m, NVZ 2.1336 m) | | Easy |

**Calibration recipe that works for every sport (do this, not a learned model, for the live demo):**
1. In the PWA, show the first frame; the user taps the 4 table/court corners (auto-suggest from SAM 3 / TT3D mask). For the table, also tap the two net-post tops.
2. On the laptop: `cv2.findHomography(img_pts, world_pts_on_plane)` for the 2D bird's-eye view, and `cv2.solvePnP(world_pts_3d, img_pts, K, dist)` for full camera pose. Approximate K from the phone FOV (fx about 0.8-1.0 x image width for main cameras), or run `cv2.calibrateCamera` once with a ChArUco board per phone model. Refine with `cv2.solvePnPRefineLM`.
3. Store per-camera `P = K[R|t]`; triangulate with `cv2.triangulatePoints` (2 cams) or aniposelib's RANSAC triangulation (3-4 cams).
Known dimensions: table tennis 2.74 x 1.525 m, height 0.76 m, net 15.25 cm. Basketball (NBA) 15.24 m wide, rim 3.05 m, FT line 4.57 m from backboard, 3-pt 7.24 m. Tennis 23.77 x 10.97 m. Pickleball 13.41 x 6.10 m.

---

## 3. Bounce / event spotting and in/out

| Approach / repo | URL | License | Notes | Adopt |
|---|---|---|---|---|
| TTNet events (bounce/net) | see 1c | NoLic | No weights. Avoid | No |
| **TennisProject CatBoost bounce** | https://github.com/yastrebksv/TennisProject (bounce model on Drive) | NoLic | Features from the ball trajectory (x, y, diffs) feed a CatBoost regressor that flags bounce frames | Easy; retrainable on your own TT clips in minutes |
| Good-Pickleball/Tennis rule-based bounce | see 1e | Apache | Score = direction change + speed drop; optional classifier | Easy |
| tt_tracker Analyzer | https://github.com/ckjellson/tt_tracker | MIT | 3D z-minimum near table height = bounce; stroke/point segmentation | Easy to port |
| TT3D rally physics | https://github.com/cogsys-tuebingen/tt3d | MIT | Chooses the bounce state that minimizes reprojection error; also spin | Post-game on AWS |
| BlurBall blur vectors | https://github.com/cogsys-tuebingen/blurball | MIT | Blur orientation gives the velocity direction per frame, which helps detect the vertical reversal at 30 fps | Free with BlurBall |
| **Audio onset** | librosa onset: https://librosa.org/doc/main/generated/librosa.onset.onset_detect.html | ISC | Ball-on-table and paddle "tock" are sharp transients (est. 2-6 kHz band). Band-pass, then spectral flux, then peak-pick with about 60 ms min gap. Classify table vs paddle vs floor with a tiny logistic/kNN on MFCCs from 20 labeled hits recorded Friday night. Gives **~1-2 ms timing vs 33 ms per video frame** | **Easy and a big accuracy win for TT. Highly recommended** |
| SoccerNet action spotting | https://github.com/SoccerNet/sn-spotting | NoLic | Soccer events (goal, card, ...) | Reference only |

**TT rules engine (custom, ~200 lines):** state machine over events {serve-toss, paddle-hit(side), table-bounce(side), net-touch, floor/out}. A point ends on double bounce, missed return, bounce on own side after hit, ball not hitting the table, or a net-crossing failure. Bounce side comes from homography x of the ball at the audio onset time; the net is the table midline. Let/serve rules can be simplified (announce "serve must bounce on both sides").

**Basketball make/miss:** ball center enters the rim box from above (y decreasing in world z), then appears below the rim within ~0.5 s, i.e. inside the net region. Fuse the avishah3 line-fit with the Roboflow freefall rule. Count 2 vs 3 points from the shooter's feet position (person bbox bottom-center through the homography) at release.

---

## 4. Multi-camera sync and triangulation

| Project | URL | License | Stars / activity | What it gives | Adopt |
|---|---|---|---|---|---|
| OpenCV (`solvePnP`, `triangulatePoints`, `findHomography`, ChArUco) | https://github.com/opencv/opencv | Apache-2.0 | 91k | Everything needed for 2-cam calibration + triangulation | Core |
| **aniposelib** | https://github.com/lambdaloop/aniposelib | BSD-2 | 92, pushed 2026-07 | Multi-camera ChArUco calibration, bundle adjustment, `triangulate_ransac`, `triangulate_optim` with smoothness, outlier rejection | **Easy, recommended for 3-4 phones** |
| **Pose2Sim** | https://github.com/perfanalytics/pose2sim | BSD-3 | 855, **pushed 2026-10-20** | Multi-cam calibration (incl. from scene points), **video synchronization by cross-correlating keypoint speeds**, person association, triangulation, filtering | Medium. Steal the sync-by-motion idea and apply it to the ball track |
| EasyMocap | https://github.com/zju3dv/EasyMocap | **Project Registration License [NC for free use]** | 4,936, pushed 2026-09 | Multi-view calibration + triangulation + SMPL | Overkill; NC |
| VoxelPose / learnable-triangulation | https://github.com/microsoft/voxelpose-pytorch, https://github.com/karfly/learnable-triangulation-pytorch | MIT | 554 / 1,135 | Multi-view 3D human pose | Not needed |
| tt_tracker (2-phone TT) | https://github.com/ckjellson/tt_tracker | MIT | 139 | 2-phone triangulation of TT ball | Borrow |
| montano96/tennis_trajectory3d_reconstruction | https://github.com/montano96/tennis_trajectory3d_reconstruction | NOASSERTION | 0 | Multi-view tennis ball 3D | Reference only |
| libsoftwaresync (Google) | https://github.com/google-research/libsoftwaresync | Apache-2.0 | 174, 2021 | Sub-ms wireless sync of Android camera capture (native app) | **Not usable from a PWA**; cite as the "real product" path |
| audio-offset-finder (BBC) | https://github.com/bbc/audio-offset-finder | Apache-2.0 | 234, pushed 2026-10 | MFCC cross-correlation to find the offset between two recordings | Easy for **post-game recorded** video sync |
| audalign | https://github.com/benfmiller/audalign | MIT | 151, 2026-05 | Fingerprint/correlation alignment of multiple audio files | Easy for post-game |

**Sync plan for the PWA (live):**
1. **Clock sync:** NTP-style ping over the WebSocket/data channel (10 round trips, take min-RTT sample) to get each phone's offset to the laptop clock, typically a few ms on local Wi-Fi.
2. **Per-frame timestamps:** on the laptop, `requestVideoFrameCallback` exposes `captureTime` (WebRTC, estimated from RTCP sender reports) and `rtpTimestamp`. If you ingest WebRTC in Python (aiortc, BSD-3, https://github.com/aiortc/aiortc), use the RTP timestamps + RTCP SR to map frames to the sender wall clock. Simpler alternative: the phone sends `performance.timeOrigin + performance.now()` with each JPEG frame over a WebSocket (worse latency, trivial sync).
3. **Event-based refinement (the robust bit):** at game start, do a **"clap sync"**: a sharp audio onset plus a visible flash (phone screen flash or a ball drop on the table). Find the onset in each phone's audio and the bounce frame in each video, then solve per-camera offsets. During play, keep refining by aligning ball-bounce audio onsets across phones (Pose2Sim-style cross-correlation on ball-speed curves also works).
4. **Unsynced-frame triangulation:** phone frames will not be simultaneous (30 fps gives up to 16 ms skew, ~15 cm at 10 m/s). Interpolate each camera's 2D ball track to a common timestamp (cubic spline between detections) before triangulating, or fit a 3D parabola segment to all rays between bounces (least squares). That is more robust than per-frame triangulation and gives smooth Hawk-Eye arcs.

---

## 5. Universal / zero-shot detection and tracking

| Model | URL | License | Stars / activity | What it gives | Speed (published or est.) | Weights | Fit for Trophy |
|---|---|---|---|---|---|---|---|
| **SAM 3** / **SAM 3.1** (Meta) | https://github.com/facebookresearch/sam3, HF https://huggingface.co/facebook/sam3, https://huggingface.co/facebook/sam3.1 | **SAM License** (custom; broad royalty-free use, redistribution must carry the license, no military/ITAR, no reverse engineering) | 12k, pushed 2026-10-14; SAM 3.1 Object Multiplex released 2026-03-27 | **Text-prompted concept segmentation + video tracking of all instances** ("ball", "hoop", "net", "court lines") | 848M params. Community reports: SAM 3 ~5-6 FPS at 1080p on H200; ~30 ms per image; SAM 3.1 up to ~2x (16 to 32 FPS) at medium object counts on H100. **Not real-time on a laptop** | **Gated** HF (manual approval). **Request access tonight** | Setup-frame understanding (find table/hoop/court) + post-game re-tracking on AWS (g6e/L40S or p5). Needs Python 3.12, PyTorch 2.7+, CUDA 12.6+ |
| SAM 2 / 2.1 | https://github.com/facebookresearch/sam2, HF https://huggingface.co/facebook/sam2.1-hiera-large | Apache-2.0 | 20k, 2026-05 | Click/box-prompted video object tracking | Hiera-tiny ~40+ FPS on A100 (paper); est. 10-25 FPS on laptop GPU | Open | Click-to-track ball/player in post-game; ungated fallback if SAM 3 access is slow |
| **SAMURAI** | https://github.com/yangchris11/samurai | Apache-2.0 | 7.1k, 2025-03 | Zero-shot single-object tracking on SAM 2.1 with motion-aware memory (Kalman), better for fast movers than vanilla SAM 2 | ~SAM 2 speed | Uses SAM 2.1 ckpts | Post-game "follow this ball" replays |
| Grounded-SAM-2 | https://github.com/IDEA-Research/Grounded-SAM-2 | Apache-2.0 | 3.8k, 2025-11 | Glue: Grounding DINO / Florence-2 / DINO-X then SAM 2 video tracking | as components | Open | Copy their video-tracking demo script |
| **Grounding DINO** | https://github.com/IDEA-Research/GroundingDINO, HF https://huggingface.co/IDEA-Research/grounding-dino-base | Apache-2.0 | 10.7k, 2024-08 | Open-vocab boxes from text | Slow: ~1.5 FPS for GDINO-T in YOLO-World's comparison (V100); est. 5-10 FPS with HF + FP16 | Open (HF transformers) | Setup frame + auto-labeling only |
| OWLv2 | HF https://huggingface.co/google/owlv2-base-patch16-ensemble (code: https://github.com/google-research/scenic) | Apache-2.0 | scenic 3.8k | Open-vocab + **image-exemplar** queries (show it one crop of the ball) | Slow (960x960 ViT); est. 2-5 FPS | Open | Auto-labeling; exemplar mode useful for odd balls |
| Florence-2 | HF https://huggingface.co/microsoft/Florence-2-large | MIT | 1.9k likes | Caption, OD, phrase grounding, OCR (scoreboards/jerseys) | 0.23B/0.77B; est. 5-15 images/s on a laptop GPU | Open | Scene understanding ("what sport is this?") + OCR |
| **YOLO-World** | https://github.com/AILab-CVC/YOLO-World (also in Ultralytics) | **GPL-3.0** (Ultralytics port AGPL) | 6.6k, 2025-02 | Real-time open-vocab detection; set classes by text, export with fixed vocab | 52 FPS (L) on V100 (paper) | Open | Real-time players/hoop/net with zero training. Tiny balls weak |
| **YOLOE / YOLOE-26** | https://github.com/THU-MIG/yoloe, Ultralytics docs https://docs.ultralytics.com/models/yoloe/ | **AGPL-3.0** | 2.3k | Text / visual-prompt / prompt-free (4,585 classes) detection **+ segmentation**; 1.4x faster than YOLO-Worldv2-S at +3.5 AP; `set_classes()` then TensorRT export | Real-time (YOLO-class) | Open (auto-downloads ~254 MB text encoder on first `set_classes`, so **pre-download before the venue**) | **Best real-time "any sport" detector** for people/hoops/nets/paddles |
| **RF-DETR** (Roboflow) | https://github.com/roboflow/rf-detr | Apache-2.0 | 9.9k, **pushed 2026-10-22** | Real-time DETR detector + seg + **keypoints**; very fast fine-tuning | Nano/S real-time on T4 (est. 100+ FPS on laptop RTX with TensorRT) | COCO-pretrained, open | **Recommended fine-tune target** (license-clean vs Ultralytics) for ball/rim/court keypoints |
| Ultralytics (YOLOv8/11/26/27) | https://github.com/ultralytics/ultralytics | **AGPL-3.0** | 62.7k, active | Detect/seg/pose, BoT-SORT/ByteTrack built-in, easiest training | real-time | Open | Fastest path; flag AGPL |
| DINO-X API | https://github.com/IDEA-Research/DINO-X-API | Apache (client) | 1.4k | Hosted open-world detector (cloud API, paid) | API | API | Optional |
| CoTracker / TAPNext (TAP point trackers) | https://github.com/facebookresearch/co-tracker (**CC-BY-NC [NC]**), https://github.com/google-deepmind/tapnet (Apache) | | 5.2k / 2.2k | Track arbitrary points | slow-ish | Open | Not suited to tiny blurred balls; skip |

**Multi-object trackers**

| Tracker | URL | License | Notes |
|---|---|---|---|
| ByteTrack | https://github.com/FoundationVision/ByteTrack (was ifzhang/ByteTrack) | MIT | 6.8k. Use via `supervision.ByteTrack` |
| **roboflow/trackers** | https://github.com/roboflow/trackers | Apache-2.0 | 4.0k, **active (2026-10-22)**. Clean re-implementations (SORT, ByteTrack, OC-SORT, ...) that plug into supervision. **Recommended** |
| supervision | https://github.com/roboflow/supervision | MIT | 51k, active. Annotators, zones (rim box, court polygon), `ViewTransformer`, `InferenceSlicer` for small objects |
| BoT-SORT | https://github.com/NirAharon/BoT-SORT | MIT | 1.6k. Camera-motion compensation + ReID; built into Ultralytics |
| OC-SORT | https://github.com/noahcao/OC_SORT | MIT | 1.2k. Better under non-linear motion |
| BoxMOT | https://github.com/mikel-brostrom/boxmot | **AGPL-3.0** | 8.3k. Many trackers + ReID in one package |

Note: for the **ball**, do not use a generic MOT tracker. Use a single-target Kalman / constant-acceleration filter with gating (or WASB's built-in online tracker) and a parabola fit between bounces.

---

## 6. Suggested 36 h build split (4 people)

- **P1 Ingest + sync:** PWA (getUserMedia 720p60 if the phone allows, else 30) streaming over WebRTC (aiortc on the laptop, or LiveKit https://github.com/livekit/livekit, Apache) + clock-offset ping + clap-sync + audio stream. Recorded-file mode for basketball.
- **P2 Table tennis CV:** BlurBall (TT weights) inference loop at 512x288 FP16, table calibration (tap corners, TT3D mask assist), audio onset bouncer, 2-camera triangulation, rules state machine. Kill-switch: if live 3D is flaky, run 2D homography from the single best camera + audio.
- **P3 Basketball + third sport:** avishah3 `best.pt` ball/hoop + make/miss; RF-DETR/YOLO person + roboflow/trackers + team KMeans; homography shot chart. Third sport: TennisProject (in/out calls) or roboflow/sports RADAR on public footage.
- **P4 Universal layer + post-game (AWS):** LLM sport ontology, SAM 3 / YOLOE setup-frame detection, SAM 2/SAMURAI replays, TT3D-style physics arcs, report/highlights UI.

**Suggested setup:** request SAM 3 HF access; download BlurBall, WASB (basketball/tennis), TennisProject, avishah3 `best.pt`, YOLOE text encoder, RF-DETR checkpoints; test CUDA/PyTorch versions (SAM 3 needs Py3.12 + Torch 2.7+, which may conflict with older repos, so use separate venvs or run SAM 3 on a separate suitable host).

## 7. Key risks

1. **Frame rate and blur:** at 30 fps a TT ball is a streak. Ask phones for 60 fps (`frameRate: {ideal: 60}`). iOS Safari WebRTC often caps at 30. BlurBall's blur estimate partly compensates, and audio onsets supply the bounce timing.
2. **WebRTC re-encoding** can drop or duplicate frames, and BlurBall/WASB multi-frame inputs are sensitive to duplicates. Dedupe by `rtpTimestamp`.
3. **Licenses:** TTNet/OpenTTGames [NC], EasyMocap [NC], CoTracker [NC], chonyy/OpenPose [NC]; Ultralytics/YOLOE/BoxMOT [AGPL]; YOLO-World, PnLCalib, NBJW, sn-gamestate [GPL]; SAM 3 custom license + gated; many tennis/basketball repos have no license [NoLic]. Check code, weight and dataset permissions separately for the intended use. A product path is RF-DETR + WASB/BlurBall/TrackNetV3 (MIT) + roboflow/trackers + OpenCV/aniposelib.
4. **Zero-shot models are too slow for live play and weak on tiny balls.** Keep them on the setup frame and in AWS post-game.
5. **TrackNetV5 SDK is proprietary with no weights, and TTNet has no weights.** Do not plan around either.

## Sources (verified 2026-10-22)
- GitHub API metadata for every repo listed (stars, license, pushed_at).
- WASB model zoo: https://github.com/nttcom/WASB-SBDT/blob/main/MODEL_ZOO.md
- TrackNetV4 paper: https://arxiv.org/abs/2409.14543 ; TrackNetV5 paper: https://arxiv.org/abs/2512.02789
- TT3D paper: https://arxiv.org/abs/2504.10035 ; project page https://cogsys-tuebingen.github.io/tt3d/
- OpenTTGames listing: https://hyper.ai/en/datasets/21496 ; Extended OpenTTGames (license note): https://arxiv.org/abs/2512.19327
- Roboflow basketball player ID: https://roboflow.com/blog/identify-basketball-players
- Roboflow shot evaluator: https://roboflow.com/blog/how-to-build-an-ai-basketball-shot-evaluator
- RF-DETR keypoints guide: https://roboflow.com/blog/train-rf-detr-keypoint
- SAM 3.1 speed comparisons (secondary): https://www.labellerr.com/blog/sam-3-vs-sam-3-1-performance-comparison/
- YOLOE docs: https://docs.ultralytics.com/models/yoloe/
- requestVideoFrameCallback: https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback
- librosa onset: https://librosa.org/doc/main/generated/librosa.onset.onset_detect.html
