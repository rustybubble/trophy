# Trophy: racket and net sports research (Cal Hacks 13.0)

Compiled 2026-10-22. Repo metadata comes from the GitHub API (authenticated `gh api repos/...`) on this date; "pushed" is the last push date. I checked Hugging Face entries through the HF API, Roboflow Universe entries through their page meta descriptions (the pages return 403 to fetchers, but the meta tags come through), PadelTracker100 through the Zenodo API, and footage counts through the Wikimedia Commons API. I did not download or run any weights. Speed figures are the authors' own numbers.

## 0. Points that apply to every sport here

- **30 fps fits.** The TrackNet-family training sets are 30 fps. The TrackNet tennis set is 1280x720 at 30 fps, and so is the TrackNetV2 shuttlecock set. That matches iPhone PWA capture, so the off-the-shelf weights fit Trophy's input without retraining for frame rate.
- **WASB-SBDT is the best single backbone for this whole group.** It ships one MIT-licensed architecture with weights for tennis, badminton and volleyball (plus soccer and basketball). It uses 3 frames at 288x512 and has 1.5 M params. Paper F1 at a 4 px threshold: tennis 94.0, badminton 91.6, volleyball 86.5. Paper FPS (Step=3, hardware unspecified): 58 / 70 / 18. For pickleball, padel and squash, start from the tennis weights.
- **New events the vocabulary needs** (everything else maps onto the existing bounce / contact / possession / step / in_zone / line_cross / net):
  - `wall_bounce`: padel, squash, racquetball. Use plane homography on a wall: tap the 4 corners of the front wall, the same code as court mapping.
  - `rim_hit`: roundnet. Best sensed by audio: rim "clack" vs net "thwack".
  - `contact_height`: badminton 1.15 m serve, pickleball and padel waist rule. The shuttle or ball at contact is assumed to lie in the vertical plane through the server's feet, which pose gives on the ground plane. With the solvePnP camera, that turns image y into metres.
  - `touch_count` per side: volleyball, roundnet. It falls out of contact events plus team assignment.
- **Audio carries a lot of weight in these sports.** Paddle and racket contacts, pickleball bounces, roundnet rim/net hits and volleyball touches are all loud, sharp onsets. Fusing them with the vision timeline fixes the 33 ms frame quantisation for "which came first" calls (two-bounce, double hit).

## 1. Pickleball

### Repos / data

| Asset | URL | License | Stars / last push | Weights? | Notes |
|---|---|---|---|---|---|
| Good-Pickleball (yo-WASSUP) | https://github.com/yo-WASSUP/Good-Pickleball | Apache-2.0 | 42 / 2026-07-03 | Yes, via Good-Tennis releases | Full pipeline: YOLO26s person, RTMPose/RTMO via **rtmlib**, homography to a 6.096 x 13.41 m court with a 2.1336 m kitchen, bounce detection, rally detection, minimap. **Caveat:** the README says the ball model is the *tennis* `tennis-ball.pt`, not trained on pickleballs. Bounce detection is marked experimental. It is a fork of Good-Tennis. |
| Good-Tennis releases (weights) | https://github.com/yo-WASSUP/Good-Tennis/releases | Apache-2.0 | 202 / 2026-07-03 | tennis-ball.pt (20 MB), yolo26s, yolo11s-pose, rtmo-s, rtmpose-s ONNX | Gives you the whole stack in one download. |
| TrackNet-Pickleball | https://github.com/AndrewDettor/TrackNet-Pickleball | none | 37 / 2023-12-22 | Yes (Google Drive) | TrackNetV2 3-in-3-out, fine-tuned on pickleball. No license file, so use it for the demo only. |
| PBLineCaller | https://github.com/clssmitty/PBLineCaller | MIT | 20 / 2025-02-03 | Roboflow-hosted | Colab notebook only. Shows the "multi-phone line caller" idea has been tried, not built. |
| smart-pickleball-assistant | https://github.com/arcotn/smart-pickleball-assistant | MIT | 13 / 2025-07-08 | ? | YOLO pose + DeepSORT and claims kitchen/foot-fault violation detection. Small, but worth a skim for its kitchen logic. |
| rally-lab | https://github.com/sebastianpaccetta-prog/rally-lab | Apache-2.0 | 0 / 2026-09-02 | Train-it-yourself | Clean commercial-license pickleball detector (2.9 M params, no ultralytics). Its results so far are from a 5-epoch sanity run only. |
| Roboflow BigAnnotationDS | https://universe.roboflow.com/pickleball-dataset/bigannotationds-rxifp | (page) | 3,542 images | dataset | Biggest pickleball image set I found. Use it to fine-tune WASB/YOLO overnight. |
| Roboflow Ball-tracker | https://universe.roboflow.com/ball-tracking-vcxpr/ball-tracker-pczbl | CC BY 4.0 | 651 images | dataset | |
| Roboflow PickleBall_V3 (court) | https://universe.roboflow.com/jeff-xqthf/pickleball_v3 | (page) | 610 court images | dataset | For court keypoints. Tapping 4 corners is still more reliable. |
| PB Vision / SwingVision | commercial | n/a | n/a | n/a | Commercial competitors. PB Vision needs a fixed camera with all 4 corners visible, which is the same constraint as Trophy. |

### Calls (casual rules, USA Pickleball 2026 text adds "clearly" to the volley-serve requirements)

| Tier | Call | Sensing |
|---|---|---|
| AUTO | **Kitchen volley fault**: a volley (contact with no bounce since the opponent's hit) while either foot is in the NVZ or on the line, *including momentum after the volley* | contact (audio + ball direction change), the no-bounce state from the ball track, pose ankle/heel keypoints projected by homography → `in_zone(NVZ)`. Feet are big and slow, so this is the most reliable call in the pack. |
| AUTO | **Two-bounce rule**: serve and return must each bounce before being hit | bounce + contact ordering per side. Audio onsets break ties. |
| AUTO | Serve lands in the wrong service box or short of the kitchen line (clear misses) | bounce position via homography, with a distance-to-line margin above about 10 cm |
| AUTO | Double bounce / ball not returned | bounce count per side |
| BETA | In/out within about 10 cm of a line | bounce localisation. At 30 fps a 15 m/s drive moves about 0.5 m per frame, so fit the parabola on both sides of the bounce and show an error ellipse |
| BETA | **Serve legality** (volley serve): underhand arc, contact below the waist, paddle head below the wrist | pose: wrist vs hip keypoints at contact. The paddle head needs a paddle detector or wrist-elbow vector, which is noisy |
| BETA | Server foot fault (stepping on or over the baseline at contact) | ankle keypoints vs baseline |
| BETA | Net touch by player or paddle | pose hands near the net plane. Weak |
| PLAYERS DECIDE | Score calling and server number, hinders, ball hits player (rarely visible), "wrong server" disputes | (Trophy can *track* the score but should not adjudicate it) |

### Live demo
**Good.** A taped kitchen line plus a short portable net (or a taped "net line" on a table edge) supports a dinking game in about a 3 x 4 m space. The kitchen-volley foot fault is the money shot: a player steps over the line and volleys, and Trophy calls it instantly with the foot highlighted. You do not need the full 20 x 44 ft court for that call.

**Recorded footage:** Wikimedia Commons has 4 pickleball videos, e.g. `File:Pickleball game.webm`, plus DVIDS-origin public-domain clips ("Pro Pickleball Tour AFN"). Best option: record your own tonight (Oct 22) at a local court with a phone on a raised tripod behind the baseline.

### Rating: **LITE** (strongest second sport after table tennis)
Generic engine, Good-Pickleball's court model, and WASB-tennis or TrackNet-Pickleball weights. Optionally fine-tune on BigAnnotationDS overnight on the GPU laptop.

## 2. Badminton

### Repos / data

| Asset | URL | License | Stars / last push | Weights? | Speed / notes |
|---|---|---|---|---|---|
| **TrackNetV3** (qaz812345) | https://github.com/qaz812345/TrackNetV3 | MIT (LICENSE file; GitHub shows "Other") | 318 / 2026-09-03 | Yes, `TrackNetV3_ckpts.zip` on Google Drive (TrackNet + InpaintNet) | F1 98.56%, 25.1 FPS (paper table). InpaintNet rectification needs future frames, so live use runs the TrackNet module and post-game uses both. |
| WASB badminton | https://github.com/nttcom/WASB-SBDT (MODEL_ZOO.md) | MIT | 201 / 2023-11-23 | Yes (Drive) | F1 91.6 / 70 FPS |
| Good-Badminton | https://github.com/yo-WASSUP/Good-Badminton | Apache-2.0 | 991 / 2026-07-03 | Yes, YOLO shuttle weights in releases | Most polished: auto court-line detection, RTMPose/RTMO, Gradio UI. About 0.02 s per frame for shuttle YOLO on GPU at 720p. |
| BadmintonTrackNet | https://github.com/ZSHYC/BadmintonTrackNet | MIT | 41 / 2026-08-09 | TrackNetV3-based | Adds hit/event analysis on top |
| badminton-pipeline-repro | https://github.com/ychenfen/badminton-pipeline-repro | none | 30 / 2026-08-01 | | TrackNet + YOLOv8s-pose reference pipeline |
| MonoTrack | https://github.com/jhwang7628/monotrack | Adobe Research License (non-commercial) | 58 / 2023-07-27 | Code; the weights are in WASB's zoo | 3D shuttle trajectory from monocular video, court detection, HitNet |
| FreeTrack | https://github.com/Alexanderyk6/FreeTrack | none | 0 / 2026-09-18 | ? | 3D shuttle via a planar-trajectory constraint. **6-point calibration: 4 court corners + 2 net posts**, a nice upgrade to the 4-tap flow |
| CourtKeyNet | https://github.com/adithyanraj03/CourtKeyNet ; weights https://huggingface.co/Cracked-ANJ/CourtKeyNet | MIT | 10 / 2026-09-12 | Yes (HF) | Badminton court quadrilateral keypoints |
| Hit-frame detection | https://github.com/arthur900530/Automated-Hit-frame-Detection-for-Badminton-Match-Analysis | MIT | 35 / 2026-06-26 | dataset on Drive | Transformer over pose sequences predicts hits |
| Shuttlecock hitting event | https://github.com/wish44165/A-New-Perspective-for-Shuttlecock-Hitting-Event-Detection | none | 32 / 2026-10-01 | | IJCAI'23 workshop |
| HF TrackNetV3-badminton mirror | https://huggingface.co/rahulanantharama/TrackNetV3-badminton | none stated | 2026-03-22 | TrackNet_best.pt | Convenient HF mirror if Drive is slow |
| ShuttleSet (CoachAI) | https://github.com/wywyWang/CoachAI-Projects/tree/main/ShuttleSet | MIT (repo) | 285 / 2026-07-17 | labels | 44 matches, 3,685 rallies, 36,492 strokes, stroke-level labels. Video is from YouTube, so it is not redistributable |
| Shuttlecock Trajectory Dataset (TrackNetV2) | https://hackmd.io/Nf8Rh1NrSrqNUzmO0sQKZw | research | | | 26 + 3 matches, 1280x720, 30 fps |

### Calls

| Tier | Call | Sensing |
|---|---|---|
| AUTO | **In/out of landing** (singles/doubles lines, long doubles service line on serve) | The shuttle *decelerates hard and falls nearly vertically*, so the landing point is easy to localise at 30 fps. This is the most reliable in/out of any sport here. bounce (shuttle stops) + homography |
| AUTO | Serve lands in the correct diagonal box | bounce + court zones + serve-side state from score parity |
| AUTO | Shuttle fails to clear the net / lands on own side | net-plane crossing from the trajectory |
| BETA | **Serve height**: 1.15 m (BWF Law 9.1.6) or the casual "below the waist" | `contact_height` trick (shuttle at contact, assumed in the server's vertical plane) or the waist rule from pose hip keypoints vs the shuttle. A good showcase of the 3D-from-solvePnP trick |
| BETA | Server/receiver foot faults (feet must stay stationary and in contact with the ground, inside the box) | ankle keypoints vs box lines and ankle velocity |
| BETA | **Double hit / carry** | two contacts within about 150 ms by the same player: audio onsets + direction changes |
| BETA | Net touch (racket or body) | pose wrist/racket near the net plane. A side camera is needed |
| PLAYERS DECIDE | Reaching over the net (follow-through is legal), obstruction, shuttle touching the player's body, lets | |

### Live demo
**Feasible in a hall with ceiling height.** A shuttle is slow and safe, a portable badminton net works, and in/out on taped lines works. The serve-height call is a good visual: draw a 1.15 m plane on the video. The main risk is HVAC drift and crowds.

**Recorded footage:** the TrackNetV2 dataset (research use), 20 Commons videos (e.g. "Badminton in school, 2009", EuroGames 2023), or your own recording.

### Rating: **LITE**
Best-in-class weights already exist (TrackNetV3, Good-Badminton). The generic engine plus a badminton pack covers it, and the serve-height `contact_height` event is the one new piece.

## 3. Tennis

### Repos / data

| Asset | URL | License | Stars / last push | Weights? | Notes |
|---|---|---|---|---|---|
| WASB tennis | nttcom/WASB-SBDT | MIT | 201 | Yes | F1 94.0 / 58 FPS (Step=3) |
| TennisCourtDetector | https://github.com/yastrebksv/TennisCourtDetector | none | 280 / 2024-03-15 | Yes (Drive) | 14 keypoints, 640x360, 8,841-image dataset; precision 0.963 with refinement + homography |
| TrackNet (unofficial PyTorch) | https://github.com/yastrebksv/TrackNet | none | 255 / 2024-03-17 | Yes | Trained on the TrackNet dataset (10 broadcast games, 19,835 frames, 1280x720, 30 fps) |
| TennisProject | https://github.com/yastrebksv/TennisProject | none | 238 / 2024-08-26 | Yes, incl. a **CatBoost bounce detector** | Ball + court + bounce. The bounce regressor is directly reusable for the `bounce` event |
| tennis_analysis (abdullahtarek) | https://github.com/abdullahtarek/tennis_analysis | none | 900 / 2024-08-12 | Yes (YOLO ball, court keypoints) | Popular tutorial code |
| tennis-tracking (ArtLabss) | https://github.com/ArtLabss/tennis-tracking | Unlicense | 718 / 2024-02-14 | Yes | "Monocular Python HawkEye" |
| Good-Tennis | https://github.com/yo-WASSUP/Good-Tennis | Apache-2.0 | 202 / 2026-07-03 | Yes (releases) | Same stack as Good-Pickleball |
| IN-OUT-Tennis-tracker | https://github.com/DanielWynter/IN-OUT-Tennis-tracker | none | 1 / 2025-12-18 | YOLOv8 | Amateur line-call assistant with tap-corners + homography, i.e. the Trophy flow for tennis |
| HF tennis ball YOLOv8n | https://huggingface.co/RJTPP/tennis-ball-detection | Apache-2.0 | 2025-07-03 | best.pt / best.onnx | Single-frame fallback |
| HaydenFaulkner/Tennis | https://github.com/HaydenFaulkner/Tennis | MIT | 145 / 2025-06-20 | | Event detection dataset |

### Calls

| Tier | Call | Sensing |
|---|---|---|
| AUTO | Clear in/out (more than about 15 cm from a line), double bounce ("not up"), ball into the net | bounce + homography, bounce count, net crossing |
| BETA | **Close line calls** | A 150 km/h serve moves about 1.4 m per frame at 30 fps, so the bounce point is interpolated. Show an uncertainty ellipse and route ties to SubQ Snap |
| BETA | Service fault (wrong box / long) | bounce + box zones |
| BETA | Foot fault (touching the baseline before contact) | ankle keypoints vs baseline at the contact time (audio onset). Needs a camera low and near the baseline |
| BETA | Net-cord let on serve | audio "tick" + small trajectory deflection at the net plane |
| PLAYERS DECIDE | Hindrance, touching the net during play, ball touching the player, score disputes | |

### Live demo
**Not feasible indoors.** Use recorded footage: your own court clip, the TrackNet dataset (research), or 261 Commons videos (mostly archival newsreels, poor for CV).

### Rating: **LITE** (recorded-only)
It has the most complete off-the-shelf stack of any sport here (WASB + TennisCourtDetector + TennisProject bounce). That makes it cheap to add as a "works on any court" proof point, but it is not a live demo.

## 4. Padel

### Repos / data

| Asset | URL | License | Stars / last push | Weights? | Notes |
|---|---|---|---|---|---|
| padel_analytics | https://github.com/Joao-M-Silva/padel_analytics | **CC BY-NC-SA 4.0** (LICENSE file) | 277 / 2024-10-21 | Yes (Drive) | Players, 13-pt pose, stroke classification, ball, hit prediction. **12-keypoint manual court selection**, fixed camera, 8 GB VRAM |
| Padex | https://github.com/rondo-labs/Padex (`pip install padex`) | GPL-3.0 | 21 / 2026-03-10 | ? | TrackNet + Kalman, **ground vs wall bounce classification**, shot/bounce events. Closest to Trophy's event model |
| ball_tracking_padel | https://github.com/michele98/ball_tracking_padel | MIT | 7 / 2023-10-18 | Training data "soon" | TrackNetV2 + parabolic trajectory fitting (Bologna MSc thesis) |
| PadelTracker100 | https://zenodo.org/records/14653706 | **CC BY 4.0** | 2025-01-15 | labels (7.1 GB zip) | About 100k frames from the WPT 2022 Finals: ball positions, player poses, shot events |
| PadelVic | https://github.com/UPC-ViRVIG/PadelVic | research-only | 27 / 2024-01-27 | | Includes **court-level phone video (Galaxy S22+ and iPhone 13 Pro Max, 1080p60)** of an amateur match. This is the exact analog of Trophy's phone setup |
| Roboflow padel-tracking | https://universe.roboflow.com/padelytixs-workspace/padel-tracking | CC BY 4.0 | 508 images | dataset | |

### Calls

| Tier | Call | Sensing |
|---|---|---|
| AUTO | Ball must bounce on the floor before touching the opponent's wall/fence (a direct hit on glass is a fault) | `wall_bounce` vs `bounce` ordering. Needs wall-plane homographies (tap the corners of the back glass) |
| AUTO | Double bounce on the floor | bounce count |
| BETA | Serve: underhand, contact at or below the waist, ball bounced first, behind the service line, lands in the diagonal box and **not touching the fence after the bounce** (side glass is OK) | pose (waist vs ball), bounce before the serve, box zones, wall_bounce type |
| BETA | Ball hits the metal fence after the bounce on the serve | wall-type segmentation (glass vs mesh) |
| PLAYERS DECIDE | Playing the ball outside the court (exit-door play), touching the net, ball hitting the player | |

### Live demo
**Not feasible** because you need walls. Recorded only: PadelTracker100 (CC BY, broadcast) or PadelVic phone clips (research-only, but ideal for showing phone-angle robustness in a judged demo).

### Rating: **PACK-ONLY**
Use WASB-tennis weights (the ball is identical) plus a wall-bounce rule pack on one short PadelVic/PadelTracker100 clip.

## 5. Squash / racquetball

### Repos / data

| Asset | URL | License | Stars / last push | Weights? | Notes |
|---|---|---|---|---|---|
| squash-vision | https://github.com/SpunkyMartian/squash-vision | MIT | 1 / 2026-03-08 | No weights published | TrackNetV3 + Kalman, YOLO11 + BoT-SORT, manual-corner homography, T-dominance, score OCR. Good architecture reference |
| OpenCV_SquashTracking | https://github.com/JoneOA/OpenCV_SquashTracking | none | 5 / 2026-02-17 | n/a (classical) | Frame differencing + parabola-fit tracker |
| Roboflow Squash_Ball detection | https://universe.roboflow.com/grad-6qy6l/squash_ball-detection | CC BY 4.0 (search snippet) | 4,082 images | dataset | Largest squash-ball set found |
| Roboflow squash final complete | https://universe.roboflow.com/ruwins-workspace/squash-final-complete | (page) | 1,935 images + hosted model | API | classes ball / player / **tin** |
| Roboflow squash ai | https://universe.roboflow.com/weone/squash-ai-wpfdx | (page) | 635 images + hosted model | API | |
| Racquetball | none found | | | | No CV repos at all; it is a pack variant of squash |

### Calls

| Tier | Call | Sensing |
|---|---|---|
| AUTO | Ball hits the tin or goes above the out line on the front wall | `wall_bounce` position on a front-wall homography (tap the 4 wall corners) vs the tin/out-line heights |
| AUTO | Double bounce ("not up") | floor bounce count between front-wall hits |
| BETA | Serve lands in the correct back quarter / above the service line | front-wall hit height + floor bounce zone |
| BETA | Racquetball: serve must land past the short line (short serve), "three-wall serve", "ceiling serve" | wall/floor bounce sequence |
| PLAYERS DECIDE | **Let / stroke / no let**: interference is the core casual dispute and is unjudgeable by CV in 36 h | |

### Live demo
**Not feasible** (needs a court). Recorded only: 41 Commons squash videos (e.g. "02016 0029 World Junior Squash Championships"), or your own clip from a campus court. A dark ball on a white wall at 30 fps blurs badly, so use 60 fps Android.

### Rating: **PACK-ONLY**
There are no usable pretrained ball weights. Fine-tune YOLO on Roboflow if you want, but the wall-plane mapping is the interesting part.

## 6. Volleyball (indoor, beach, backyard)

### Repos / data

| Asset | URL | License | Stars / last push | Weights? | Speed / notes |
|---|---|---|---|---|---|
| **fast-volleyball-tracking-inference** | https://github.com/asigatchov/fast-volleyball-tracking-inference | MIT | 72 / **2026-10-22** (active) | Yes, ONNX/OpenVINO in repo | VballNetV4c F1 0.902 at **150 FPS CPU** (inference only); FastV1 1,140 FPS. **`track_calculator_with_court.py` + PLAYER_CONTACTS.md: player-aware touch detection labelled by technique, rally vs. ball-handover segmentation.** Directly feeds touch-count rules. HF demo: https://huggingface.co/spaces/asigatchov/volleyball-tracking |
| vball-net | https://github.com/asigatchov/vball-net | MIT | 13 / 2026-06-08 | Yes (Drive/Yandex) | TrackNetV4-based (motion prompt layer) |
| RAVEL-VB | https://github.com/asigatchov/RAVEL-VB-beachvolleyball-tracking | MIT | 14 / 2026-08-07 | Yes (.pt + OpenVINO, YOLO26n-vb beach-trained) | Players + ball in one temporal detector |
| WASB volleyball | nttcom/WASB-SBDT | MIT | 201 | Yes | F1 86.5 / 18 FPS (paper) |
| HF beach-volley TrackNetV3 | https://huggingface.co/deadfast/beach-volley-vision-models | MIT | 2026-08-31 | tracknet_best.pt | Beach-volleyball fine-tune of TrackNetV3 |
| HF volleyball person+ball D-FINE-S | https://huggingface.co/grdesignbuild/volleyball-person-ball-detector | Apache-2.0 | 2026-09-08 | safetensors + **CoreML** | 10 M params. Ref-stand wide-angle, beach and grass footage, so it suits casual play |
| volleyball_analytics | https://github.com/masouduut94/volleyball_analytics | GPL-2.0 | 137 / 2026-10-08 | Yes (Drive, auto-download) | Game state (SERVICE/PLAY/NO-PLAY via VideoMAE), 6-class action detection (serve/receive/set/spike/block), court segmentation |
| VolleyVision (shukkkur) | https://github.com/shukkkur/VolleyVision | AGPL-3.0 (README badge says CC BY-NC-ND) | 331 / 2025-06-20 | Yes (YOLOv7-tiny, RoboFlow volleyball_v2 with 18,980 images) | Ball, actions, court |
| VREN | arXiv 2209.13846 | CC BY-NC-ND 4.0 | | dataset only | Rally notation, pro/NCAA |

### Calls

| Tier | Call | Sensing |
|---|---|---|
| AUTO | In/out of ball landing (clear margin; the ball is large and easy to track) | bounce + homography. Beach/backyard lines are ropes or cones, so tap them |
| AUTO | Ball lands / rally ends; side that let it drop | bounce + side |
| BETA | **4+ touches per side** (3 max; in indoor play the block does not count, in beach it does) | contact events (ball direction change + audio thump + player proximity, as in PLAYER_CONTACTS.md), team assignment by court side |
| BETA | Same player touches twice in a row (outside the block/first-ball exception) | contact → player-ID association. The person tracker is the weak link |
| BETA | Ball crosses outside the antenna / under the net | net-plane crossing position vs antenna x-coordinates (tap the antenna tops) |
| BETA | Foot fault on serve (on the end line) | ankle keypoints |
| BETA | Net touch | pose hands/body near the net plane plus net-motion pixels. Weak |
| PLAYERS DECIDE | **Double contact / lift / carry** (handling), rotation/overlap (indoor; tedious but possible later), reaching over, centre-line interference, beach "open-hand tip" | |

### Live demo
**Partial.** A real game in a hall is unsafe, but a two-player pepper/passing drill with a soft ball is safe. Trophy counts touches live and calls "4 touches" when a third person joins in. You can also tap out a mini-court on the floor and use it for in/out on drops.

**Recorded footage:** 398 Commons videos (e.g. "Beach volleyball in slow motion, 8 times slower.webm", "Volleyball serve.ogv"), the sample clip `examples/gtu_20250316_002.mp4` in fast-volleyball-tracking-inference, and the WASB volleyball set (Ibrahim et al. YouTube matches).

### Rating: **LITE**
It has the richest *casual-relevant* assets: MIT weights, CPU-fast models, and existing touch detection. The engine plus the closest weights should yield a credible touch-count demo.

## 7. Roundnet / Spikeball

### Repos / data

| Asset | URL | License | Size | Weights? | Notes |
|---|---|---|---|---|---|
| Roboflow "Roundnet Project" | https://universe.roboflow.com/public-workspace-tpxwk/roundnet-project | CC BY 4.0 (search snippet) | **861 images + pre-trained model & hosted API** | Yes (Roboflow) | classes: net, person-with-ball, spikeball |
| Roboflow "RoundenetVision" | https://universe.roboflow.com/jonass-workspace-d1mry/roundenetvision | MIT (search snippet) | 70 images + model | Yes | player, frame, net, white ball |
| roundnet-ai-showcase | https://github.com/austinulfers/roundnet-ai-showcase | none | 4 stars / 2024-08-23 | No (private repo) | Proves someone tried. The code is closed |
| Papers / datasets | none found | | | | **White space**: no published roundnet CV work |

### Calls (IRF rules, summarised via Wikipedia)

| Tier | Call | Sensing |
|---|---|---|
| AUTO | **Rim hit** → point to the other team | **audio** classifier (hard plastic rim click vs trampoline thump) + ball near the rim ellipse (tap 4 points on the rim, which gives an ellipse homography) |
| AUTO | Ball fails to hit the net within 3 touches | contact count (audio + direction changes) → net bounce |
| AUTO | Ball hits the ground before the net / after a touch | bounce on ground vs net-bounce classification (the net bounce is in the rim ellipse with a trampoline audio signature) |
| BETA | Pocket / roll-up on serve (receiving team *may* call a fault; in a rally it is legal) | ball contact location near the rim edge + abnormal rebound angle. Route to SubQ Snap |
| BETA | Serve too high (IRF: above the receiver's shoulder; casual groups vary, so make it a pack parameter) | ball apex vs receiver shoulder keypoint (pose) |
| BETA | Server behind the 7 ft (2.13 m) line | ankle keypoints vs a circle of radius rim + 2.13 m on the ground plane |
| BETA | Toss too short (under 4 in / about 10 cm) | ball rise after release |
| PLAYERS DECIDE | Hinders, possession/defensive interference, "soft touch" double-touch exceptions, rim-vs-pocket "can't tell" → replay (this matches PLAYERS DECIDE semantics exactly) | |

### Live demo
**Best live demo in this group.** A Spikeball set fits on any patch of floor or lawn about 6 m across, the action is concentrated around a 0.9 m net, and one phone on a tall tripod looking down at the net captures everything. The rim-vs-net audio call is instant, novel, and lands with judges. Play outside the venue or in an open hallway corner.

**Recorded footage:** none on Commons (0 hits). Record your own; it is trivial.

### Rating: **LITE** (demo-driven)
Generic engine + Roboflow Roundnet Project weights (or COCO "sports ball" + yellow colour gating) + a tiny audio rim/net classifier. Collect about 50 labelled hits of each class with your own set in 30 minutes; MFCC + logistic regression is fine. No competitor or open repo exists.

## 8. Summary table

| Sport | Best repo / weights | AUTO | BETA | PLAYERS DECIDE | Live demo | Rating |
|---|---|---|---|---|---|---|
| Pickleball | Good-Pickleball (Apache) + WASB-tennis / TrackNet-Pickleball; Roboflow BigAnnotationDS 3.5k | kitchen-volley foot fault, two-bounce, clear in/out, double bounce | near-line in/out, serve waist/wrist/arc, server foot fault, net touch | score/server #, hinders | Yes (taped kitchen + mini net) | **LITE** |
| Badminton | TrackNetV3 (MIT, F1 98.6) / Good-Badminton (Apache, 991★) / CourtKeyNet | landing in/out, service box, net fail | 1.15 m / waist serve height, foot faults, double hit, net touch | over-net reach, obstruction | Yes (needs ceiling) | **LITE** |
| Tennis | WASB-tennis + TennisCourtDetector + TennisProject bounce CatBoost | clear in/out, double bounce, net | close calls, service box, foot fault, net-cord let | hindrance, net touch | No (recorded) | **LITE** |
| Padel | Padex (GPL) / padel_analytics (NC) + PadelTracker100 (CC BY) | floor-before-wall, double bounce | serve rules, fence-after-bounce | out-of-court play, net touch | No | **PACK-ONLY** |
| Squash / racquetball | squash-vision (MIT, no weights) + Roboflow 4k squash set | tin/out line, not up | serve zones, racquetball short serve | let/stroke | No | **PACK-ONLY** |
| Volleyball | fast-volleyball-tracking-inference / VballNet / RAVEL-VB (all MIT) + WASB-volleyball | landing in/out | 4+ touches, consecutive touch, antenna, serve foot fault, net touch | lift/double contact, rotation, reach-over | Partial (pepper drill) | **LITE** |
| Roundnet | Roboflow Roundnet Project (861 imgs, model) + own audio classifier | rim hit, 3-touch, ground before net | pocket/roll-up on serve, serve height, 7 ft line, toss | hinders, possession, can't-tell replays | **Best** | **LITE** |

**Recommendation.** If the team adds one sport beyond table tennis and basketball, add **pickleball**. It is hot right now, the kitchen foot fault is a perfect AUTO call that needs feet rather than a fast ball, and its weights overlap tennis. For a second live crowd-pleaser, add **roundnet**, which is open white space and has an audio-first rim call. Badminton and volleyball are cheap LITE packs on strong existing weights. Tennis, padel and squash should appear only as recorded-clip "the engine generalises" slides.

## 9. Licence cautions
- Non-commercial or copyleft: padel_analytics (CC BY-NC-SA), MonoTrack (Adobe Research), VolleyVision (AGPL / CC BY-NC-ND), volleyball_analytics (GPL-2.0), Padex (GPL-3.0), PadelVic (research-only), VREN (CC BY-NC-ND).
- No license file (demo-only): TrackNet-Pickleball, the yastrebksv tennis repos, abdullahtarek/tennis_analysis.
- Clean (MIT / Apache / Unlicense): WASB, TrackNetV3, the Good-* family, the asigatchov volleyball stack, CourtKeyNet, rtmlib, the HF D-FINE volleyball model, ArtLabss.
