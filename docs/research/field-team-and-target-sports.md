# Trophy: field, team and target sports research

Prepared 2026-10-22 for Cal Hacks 13.0 (Oct 23-25, 36 h, team of 4).

**Scope.** This covers field, team and target sports. Basketball, table tennis and spikeball are covered in other documents.

**Engine assumptions.** Phones run a PWA at about 30 fps on iPhone and up to 60 fps on Android. They stream to a local NVIDIA laptop. The perception stack is:
- RF-DETR detection
- ByteTrack tracking (roboflow/trackers)
- rtmlib pose with feet
- SigLIP + KMeans team colors
- Homography from 4 or more tapped field points
- Audio onsets from the phone mic

Rule packs map events to calls in three tiers: AUTO, BETA and PLAYERS DECIDE.

**How the links were checked**
- **GitHub stars, license and last push** come from the GitHub API (`gh api repos/OWNER/REPO`) on 2026-10-22/23.
- **Hugging Face (HF) entries** come from the HF API.
- **Roboflow Universe pages** block curl and WebFetch with a 403. They were checked in a real browser. Pages marked "(opened)" were loaded and their license, image count and classes read. Pages marked "(search)" appeared in the Universe search results on 2026-10-22, but their license was not read.
- **Repos with fewer than 20 stars** are hobby or student code. Use them to borrow ideas, not as dependencies.

---

## 0. Shared building blocks (used by many packs)

| Asset | URL | License | Stars | Last push | Weights | Notes |
|---|---|---|---|---|---|---|
| roboflow/sports | https://github.com/roboflow/sports | MIT | 5,436 | 2026-08-28 | Yes: `examples/soccer/setup.sh` downloads `football-ball-detection.pt`, `football-player-detection.pt` and `football-pitch-detection.pt` (YOLOv8, via gdown) | Soccer player/GK/ref/ball, 32-pt pitch keypoints, SigLIP+UMAP+KMeans teams. Trained on Bundesliga broadcast footage, so expect a domain gap on phone-on-tripod pickup video. |
| roboflow/rf-detr | https://github.com/roboflow/rf-detr | Apache-2.0 | 9,870 | 2026-10-22 | COCO checkpoints | **COCO already has `frisbee`, `sports ball`, `baseball bat`, `baseball glove`, `person`.** Zero-shot disc and bat detection comes for free. |
| roboflow/trackers | https://github.com/roboflow/trackers | Apache-2.0 | 3,958 | 2026-10-22 | n/a | ByteTrack/SORT/OC-SORT re-implementations. |
| roboflow/supervision | https://github.com/roboflow/supervision | MIT | 51,270 | 2026-10-22 | n/a | Zones, line-crossing counters, homography helpers (`PolygonZone`, `LineZone`), which map directly to `in_zone` and `line_cross`. |
| Tau-J/rtmlib | https://github.com/Tau-J/rtmlib | Apache-2.0 | 691 | 2026-08-03 | Yes (ONNX) | RTMPose/RTMW with feet keypoints. |
| nttcom/WASB-SBDT | https://github.com/nttcom/WASB-SBDT | MIT | 201 | 2023-11-23 | Yes, per sport (soccer, tennis, badminton, volleyball, basketball) | Heatmap small-ball detector. The best "universal fallback" for small, fast, blurred balls. |
| qaz812345/TrackNetV3 | https://github.com/qaz812345/TrackNetV3 | NOASSERTION | 318 | 2026-09-03 | Yes (shuttlecock) | Fine-tunable for any small object at 30 fps. |
| facebookresearch/sam2 | https://github.com/facebookresearch/sam2 | Apache-2.0 | 20,040 | 2026-05-30 | Yes | Click-to-track fallback for odd objects (bean bags, horseshoes, discs). Post-game on AWS. |
| yangchris11/samurai | https://github.com/yangchris11/samurai | Apache-2.0 | 7,119 | 2025-03-18 | Uses SAM2 | Zero-shot single-object tracking, robust to fast motion. |
| mguti97/PnLCalib | https://github.com/mguti97/PnLCalib | GPL-2.0 | 110 | 2026-03-17 | Yes | Automatic soccer field registration. Upgrade path beyond tapping 4 points. |
| jhong93/spot (E2E-Spot) | https://github.com/jhong93/spot | BSD-3 | 88 | 2023-02-15 | Code only | Temporally precise event spotting. A template if you train a "snap" or "throw" spotter. |
| lRomul/ball-action-spotting | https://github.com/lRomul/ball-action-spotting | MIT | 140 | 2023-07-02 | Yes | SoccerNet 2023 ball-action (pass/drive) winner. |
| AtomScott/TeamTrack | https://github.com/AtomScott/TeamTrack | MIT (code) | 79 | 2024-04-22 | Baselines | Full-pitch MOT for **soccer, basketball, handball**, with fixed and drone cameras. Data on Kaggle and Google Drive. |
| MCG-NJU/SportsMOT | https://github.com/MCG-NJU/SportsMOT | none listed | 233 | 2023-07-24 | Data | Soccer, basketball and volleyball MOT. |
| mikel-brostrom/boxmot | https://github.com/mikel-brostrom/boxmot | AGPL-3.0 | 8,319 | 2026-10-20 | ReID weights | Avoid unless you accept AGPL. roboflow/trackers is enough. |

**Licensing note.** Ultralytics YOLO (62.7k stars) is AGPL-3.0. Weights trained with it, including roboflow/sports `.pt` files, BaseballCV and most Roboflow Universe YOLO exports, carry AGPL implications if Trophy ever ships commercially. That is fine at a hackathon. Prefer RF-DETR (Apache-2.0) for anything you fine-tune yourself.

### The 30 fps budget
33 ms per frame decides the tiers more than model quality does:
- A wiffle or softball pitch at about 45 mph moves about 0.7 m per frame.
- A tape-ball cricket delivery at about 70 mph moves about 1 m per frame.
- A hockey slapshot is motion-blurred over 1-2 m.

Trophy's escape hatches:
1. **Judge resting state instead of flight.** Examples: puck in net, bag in hole, ball in cup, pins standing.
2. **Use audio onsets for sub-frame timing.** Mic onsets resolve to about 1 ms. Useful sounds include a ball popping into a glove, a bat crack, a bag thud, chains jingling, a pin crash and a stump hit.
3. **Interpolate trajectories with a physics fit,** as PocketDRS does, and report the uncertainty. That uncertainty is what decides BETA versus AUTO.

---

## 1. Two-hand touch / flag football

### Repos, models and data
| Asset | URL | License | Stars / size | Activity | Weights | Notes |
|---|---|---|---|---|---|---|
| Roboflow "nfl-detection-1500" + RF-DETR-S tutorial | https://universe.roboflow.com/test-cm1hp/nfl-detection-1500 (search; blog: https://roboflow.com/blog/american-football-player-tracker) | Universe default (check) | ~1.5k images | Blog Apr 2026 | Hosted model `nfl-detection-1500-jdrgz/4` | RF-DETR Small + ByteTrack. mAP50 74.8%, P 90.8%, R 71.5%. **No snap or play detection.** |
| Flag Football by StatsLive | https://universe.roboflow.com/statslive-ms3nd/flag-football-ashw8 (search) | not read | 192 images, 2 models | — | Hosted | Classes: Ball, Player, Referee. This is actual flag-football footage. |
| Flag Football Model (smarticoachflagfootball) | https://universe.roboflow.com/smarticoachflagfootball/flag-football-model-3ltb0 (search) | not read | — | — | — | Alternative flag set. |
| American Football Player Detection (FH Technikum Wien) | via https://universe.roboflow.com/search?q=american%20football (search) | not read | 171 images, 1 model | — | Hosted | ball, referee, players. |
| RobMulla/helmet-assignment | https://github.com/RobMulla/helmet-assignment | Apache-2.0 | 13 | 2021-09-22 | No | Helper code for the Kaggle NFL Helmet Assignment. Competition data is **non-commercial, competition-use only**. Broadcast and endzone views with helmets, so it is not relevant to casual play. |
| NFL Big Data Bowl | https://github.com/nfl-football-ops/Big-Data-Bowl | none | 154 | 2019 (homepage) | — | 10 Hz *tracking* data (no video) with `ball_snap` event frames. Useful only to validate a snap-timing model or rush-count logic. |
| UnravelSports/unravelsports | https://github.com/UnravelSports/unravelsports | MPL-2.0 | 249 | 2026-01-16 | — | Loads BDB tracking, graph nets for play prediction. Use it for post-game analytics on AWS, not live calls. |

**Verdict.** No open repo detects the snap, the line of scrimmage or a "two-hand touch" from casual video. Use RF-DETR COCO `person` plus `sports ball`. COCO "sports ball" catches footballs only weakly, so fine-tune on the StatsLive/NFL-1500 sets, about 1 hour on the laptop GPU.

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Out of bounds (carrier steps on or over the sideline) | AUTO when the margin is over 0.3 m in the homography; BETA otherwise | Pose feet + field homography + `line_cross` |
| Line of scrimmage at snap (spot the ball) | AUTO | Ball position at `snap` projected to field coords. The LOS is drawn on the overlay. |
| Snap detection | AUTO (used as an event) | Center's ball leaves the ground/hands and moves backward, plus a collective motion onset (optical-flow burst across all players). Audio "hike!" onset as a second signal. |
| Rush count ("5 Mississippi") | AUTO | Timer from `snap`. Trophy announces "rush legal" at N s. Also check that the rusher started at least 7 yd back if house rules require it (homography at the snap frame). |
| Illegal forward pass (thrown from beyond the LOS) | AUTO when the passer's feet are clearly past the LOS; BETA near it | Release frame (wrist velocity peak + ball separation) + passer's feet vs the LOS |
| Second forward pass in the same play | AUTO | Possession/throw event count after the snap |
| Catch in bounds (one foot casual / two feet house rule) | BETA | `catch` (ball enters hands region and stops) + foot ground contacts (`step`) inside the polygon |
| Touchdown | AUTO when the ball carrier's ball or body clearly crosses the goal line in possession; BETA at the pylon | `possession` + `line_cross` of the end-zone line |
| First down / line to gain (if played) | AUTO | Homography: forward progress of the ball spot at the dead-ball frame |
| Two-hand touch | BETA | Both defender wrists (pose) inside the carrier's person mask/box within a ~200 ms window. Hand speed and audio don't help. Show "1 hand / 2 hands, 74%". Ambiguous cases go to SubQ Snap. |
| Flag pull (flag version) | BETA | Fine-tuned flag detector (colored belt flags), with the flag leaving the carrier's hip region and appearing in the defender's hand |
| Fumble = dead ball (flag rules) | AUTO | Ball `bounce` while not in possession |
| No-run zone (5 yd before the end zone / midfield, NFL FLAG rules) | AUTO | Play type (run vs pass via throw event) + ball spot in zone |
| Interception / pick-six | AUTO-ish (BETA for the catch) | Team color of the catcher differs from the offense |
| Pass interference, holding, illegal contact, "was that a block?" | PLAYERS DECIDE | — |
| Spot of a forward-progress dispute | PLAYERS DECIDE (Trophy shows the replay frame) | — |

### Demo
**Live at the venue:** weak. Indoors you can stage a 2v2 three-play walkthrough in a hallway with a Nerf football, but the field is small and play is slow. A park outside Moscone/Fort Mason is possible but risky.

**Recorded:** good. Record your own 4v4 at a park before or after the event: one phone on a tripod at midfield, elevated if possible. That is the most reliable path. Stock clips are short (see the Pexels search for "flag football" videos at https://www.pexels.com/search/videos/flag%20football/, Pexels License: free use, no attribution). YouTube's search filter > Creative Commons has some youth flag games.

**Effort: LITE.** The generic engine covers it (snap timer, LOS, OOB and TD are all homography + events). Two-hand touch is the showcase BETA call. Fine-tune the ball class only.

---

## 2. Soccer and futsal (small-sided pickup)

### Repos, models and data
| Asset | URL | License | Stars | Last push | Weights | Notes |
|---|---|---|---|---|---|---|
| roboflow/sports (soccer) | https://github.com/roboflow/sports | MIT | 5,436 | 2026-08-28 | Yes (3 YOLOv8 .pt) | Player, ball and pitch keypoints, team clustering, radar view. **Best starting point.** Pitch keypoints assume a full FIFA pitch; for pickup, use the 4-tap homography instead. |
| SoccerNet/sn-gamestate | https://github.com/SoccerNet/sn-gamestate | GPL-3.0 | 468 | 2026-05-02 | Yes (TrackLab pipeline) | Full game-state reconstruction (minimap, jersey numbers, teams). Heavy, so use it as a reference only. |
| SoccerNet/sn-calibration | https://github.com/SoccerNet/sn-calibration | none | 111 | 2024-06-18 | Baseline | Line-based camera calibration. |
| SoccerNet/sn-spotting | https://github.com/SoccerNet/sn-spotting | none | 105 | 2024-02-07 | Baselines | Goal, card, throw-in, corner and out-of-play spotting. SoccerNet *videos* need an NDA. |
| lRomul/ball-action-spotting | https://github.com/lRomul/ball-action-spotting | MIT | 140 | 2023-07-02 | Yes | Pass/drive spotting. |
| mguti97/PnLCalib | https://github.com/mguti97/PnLCalib | GPL-2.0 | 110 | 2026-03-17 | Yes | Automatic field registration. |
| Neerajj9/Computer-Vision-based-Offside-Detection-in-Soccer | https://github.com/Neerajj9/Computer-Vision-based-Offside-Detection-in-Soccer | MIT | 44 | 2021-12-08 | — | Vanishing-point offside lines. A hobby-grade reference. |
| abdullahtarek/football_analysis | https://github.com/abdullahtarek/football_analysis | none | 1,020 | 2024-04-23 | Trained YOLO (linked) | Popular tutorial: possession %, speed, team assignment. |
| TeamTrack (soccer_side, soccer_top drone) | https://github.com/AtomScott/TeamTrack | MIT | 79 | 2024 | — | **Non-broadcast, fixed and drone cameras.** Closest to pickup framing. |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Goal (mini goals / pop-up nets) | AUTO | Ball `in_zone` of the goal-mouth polygon (homography) + ball disappears into the net + net motion. With cone goals, "below head height" decides it, so goal is AUTO laterally and BETA on height. |
| Goal with cone posts, ball over a "post" | BETA | Ball height above ground can't be measured from monocular video without a bounce. Use trajectory + nearest bounce. Ambiguous cases go to SubQ Snap. |
| Ball out (touchline / end line, whole ball over the line) | AUTO when the margin is clear; BETA within ~1 ball diameter | Ball bottom point vs the line in the homography; `line_cross` + settle |
| Restart type (kick-in/throw-in, corner, goal kick) | AUTO | Last `touch` team (team color of the nearest foot at the last ball direction change) + which line was crossed |
| Futsal 4-second restart / GK 4-second possession | AUTO | Timer from the restart-ready frame or GK `possession` |
| Futsal "ball over head height" (some indoor leagues) | BETA | Ball apex vs person height (pose) |
| Score and game-to-N | AUTO | Goal events |
| Offside (only if the group plays it) | BETA | Second-last defender line at the pass frame (pass = ball velocity change after a `touch`). 33 ms frame error ≈ 0.25 m at sprint, so always BETA with an uncertainty band. |
| Handball | BETA (shows a ball-near-arm frame) / PLAYERS DECIDE | Ball-wrist/elbow proximity (pose) + ball direction change |
| Fouls, advantage, "was that a dive" | PLAYERS DECIDE | — |
| Possession %, shots, pass map (post-game) | Analytics | AWS pipeline (sn-gamestate style) |

### Demo
**Live at the venue:** a 1v1 or 2v2 futsal-style game on a taped 6x10 m floor area with two shoe-box goals and a soft ball is feasible indoors. **Recorded:** many options:
- your own pickup game
- TeamTrack fixed/drone clips (MIT code; check the data terms on Kaggle)
- roboflow/sports sample clips (Bundesliga, Kaggle DFL competition terms)
- Pexels "soccer" stock clips

**Effort: LITE.** The roboflow/sports weights plus the generic engine cover it. Goal and ball-out are the AUTO showcase. The domain gap from broadcast footage means you should budget about 1 h to fine-tune the ball detector on your own frames.

---

## 3. Ultimate frisbee

### Repos, models and data
| Asset | URL | License | Stars / size | Activity | Weights | Notes |
|---|---|---|---|---|---|---|
| **RF-DETR / YOLO COCO `frisbee` class** | https://github.com/roboflow/rf-detr | Apache-2.0 | 9,870 | 2026-10-22 | Yes | The disc is a COCO class, so it works zero-shot. Weak when the disc is edge-on and small. |
| Ultimate Frisbee Game (ultimate-frisbee-analysis) | https://universe.roboflow.com/ultimate-frisbee-analysis/ultimate-frisbee-game-hlwqv (search) | not read | 662 images, 3 models | — | Hosted | Classes: Endzone Marker, Field Marker, Frisbee, Players, Viewers. Field-cone classes are useful for automatic homography. |
| Frisbee Ultimate PUJ | https://universe.roboflow.com/detection-xrovt/frisbee-ultimate-frisbee-puj (search) | not read | 1.39k images, 1 model | — | Hosted | Disc only. |
| ultimate frisbee disc detector (Eelke van Foeken) | via https://universe.roboflow.com/search?q=ultimate%20frisbee (search) | not read | 509 images, 5 models | — | Hosted | frisbee, hand, player. Hand + disc helps possession. |
| Ultimate Frisbee Homography (Wills Work Space) | https://universe.roboflow.com/wills-work-space/ultimate-frisbee-homography-uoe1p (search) | not read | 60 images | — | Keypoints | Field keypoints. |
| shunsuke-iwashita/VTCS (UltimateTrack dataset) | https://github.com/shunsuke-iwashita/VTCS ; paper https://arxiv.org/abs/2508.17611 | MIT | 2 | 2025-09-08 | — | 18k frames, 15 fps tracking of 7v7 + disc (disc from holder annotation). Analytics only. |
| Multi-sport space evaluation (ultimate/basketball/soccer) | https://arxiv.org/pdf/2603.06585 | paper | — | 2026 | — | Post-game "space" analytics idea. |
| hislopzach/disc-tracker | https://github.com/hislopzach/disc-tracker | none | 16 | 2021-03-01 | — | Tripod "follow flight" tracer (classical CV). |

### Calls
Ultimate is self-officiated (Spirit of the Game), so PLAYERS DECIDE is literally the rule. That is a pitch point.

| Call | Tier | Sensing |
|---|---|---|
| Stall count | AUTO | Timer from `catch`/`possession` start. Trophy counts audibly ("stalling one... ten") or listens to the marker's count via ASR and flags "fast count" as BETA. |
| Turnover: disc hits ground / drop | AUTO | Disc `bounce`/ground contact (disc stops near the ground plane) without possession |
| In/out on catch (first ground contact in bounds) | BETA | `catch` + first foot `step` after the catch in the field polygon |
| Goal (catch with feet in the end zone) | BETA → AUTO when clearly inside | `catch` + feet `in_zone` end zone |
| Pull out of bounds (brick) | AUTO | Disc landing point vs the field polygon |
| Travel (pivot foot moves) | BETA | Pose ankle displacement of the pivot foot during possession |
| Double team (second marker within 3 m) | BETA | Homography distances between defenders and thrower |
| Pick | PLAYERS DECIDE | — |
| Foul, strip, "up" contests | PLAYERS DECIDE | — |

### Demo
**Live at the venue:** good. Short-range "mini-ultimate" (3 people, a disc, a 10 m hallway or courtyard) shows stall count, drop turnover and in/out on a taped line. A soft "ultimate disc" is cheap. **Recorded:** Pexels stock clips are short and of mixed quality; filming your own is better.

**Effort: LITE.** It uses the COCO frisbee class plus timers. Stall count and drop are robust AUTO calls with minimal custom work.

---

## 4. Baseball / softball / wiffle ball

### Repos, models and data
| Asset | URL | License | Stars | Last push | Weights | Notes |
|---|---|---|---|---|---|---|
| **BaseballCV/BaseballCV** (formerly dylandru/BaseballCV) | https://github.com/BaseballCV/BaseballCV | MIT + AGPL-3.0 (`LICENSE-MLB-AGPL.txt`). Commercial use by teams needs a license. | 20 (repo moved; 1,080 commits) | 2026-10-22 (v0.1.28.0) | **Yes**, YOLOv11 `.pt` hosted at data.balldatalab.com (e.g. `ball_tracking_v4-YOLOv11.pt`) via `LoadTools.load_model()` | Models for ball, bat, glove (+ball, home plate, rubber), pitcher/hitter/catcher, bases, and amateur pitcher/hitter (YOLOv9), plus an RF-DETR glove model and Florence-2/PaliGemma2 ball models. Tools include `DistanceToZone` (MediaPipe pose → strike zone). |
| BaseballCV HF datasets | https://huggingface.co/datasets/dyland222/international_amateur_baseball_game_videos (+ `_bp_videos`, `_catcher_video_dataset`, photo sets) | per card | — | 2025-03 | — | **205 amateur game videos**: useful recorded footage. |
| cvtechniques/roboump (HF) | https://huggingface.co/cvtechniques/roboump | MIT | 0 likes | 2026-03-17 | Yes (YOLOv8m) | Ball, batter, pitcher, strike-zone box. Self-reported mAP50 0.92. Broadcast-trained. |
| COCO `baseball bat`, `baseball glove`, `sports ball` | RF-DETR COCO | Apache-2.0 | — | — | Yes | Zero-shot bat and glove. |
| pascalewalters/baseball-tracking | https://github.com/pascalewalters/baseball-tracking | none | 10 | 2020-04-09 | — | Pitch detection + release-point interpolation. |
| nickbild/tipper | https://github.com/nickbild/tipper | none | 14 | 2019-12-04 | — | Hobby-grade strike/ball prediction using a high-speed camera. |
| Wiffle bat and ball (scratch) | https://universe.roboflow.com/scratch-xkho6/wiffle-bat-and-ball (search) | not read | 57 images | — | — | Tiny set. |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Fair / foul (landing point vs foul lines) | AUTO when clear; BETA within ~0.5 m of the line | Ball first `bounce` (or catch point) in the homography vs the foul-line polygon. The bounce from a tripod at 1B/3B is reliable. |
| Home run (over a marked fence/line on the fly) | AUTO / BETA | Ball crosses the far line before any `bounce` |
| Out on catch (caught on the fly) | BETA → AUTO when the catch is clean | `catch` event with no prior `bounce`. Glove model + ball disappearance. |
| Strike zone (wiffle/baseball) | BETA | Pose-derived zone (knees to midpoint, BaseballCV DistanceToZone) + ball plate-crossing interpolated from 2-4 frames at 30 fps. 45 mph is ~0.7 m/frame, so always show the uncertainty. |
| Wiffle "strike target" house rule (a physical box or plywood target behind the batter) | AUTO | Ball hits the target: audio onset + ball in target zone. Recommended for the demo. |
| Slowpitch strike-mat rule (pitch landing on the mat/plate = strike) | AUTO | Ball `bounce` in the mat zone |
| Slowpitch arc height (6-12 ft legal) | BETA | Trajectory apex height via pitcher-height scale |
| Swing / check swing | BETA | Bat-angle crossing (bat model) / pose |
| Force out at base (bang-bang) | BETA | Foot-on-base frame (pose foot in base zone) vs ball-in-glove **audio pop** onset (sub-frame timing) |
| Tag out | BETA / PLAYERS DECIDE | Glove-to-runner contact |
| Leaving early / stealing (not allowed in slowpitch or wiffle) | BETA | Runner foot leaves the base zone before the `contact` (bat crack onset) or before the pitch crosses the plate |
| Count, outs, innings, runs bookkeeping | AUTO | Event accumulation |
| Balk, interference, obstruction, infield fly | PLAYERS DECIDE | — |

### Demo
**Live at the venue:** **wiffle ball is a great indoor demo.** Pitch underhand from 6 m to a cardboard strike target, bat with a plastic bat, and get AUTO strike-target calls plus BETA zone calls, fair/foul on a taped wedge, and catch outs. **Recorded:** BaseballCV's amateur game videos on HF, or your own wiffle footage.

**Effort: LITE** (plus BaseballCV weights). This is the one field sport with real pre-trained specialist weights, and the wiffle strike target turns the hardest call into an AUTO one.

---

## 5. Kickball

### Repos, models and data
There is no kickball-specific CV work. Kickball is a ball-detection problem using soccer weights, rubber-ball color, or COCO `sports ball`.
- **"KickBall"** (s Workspace) https://universe.roboflow.com/8521561-kookmin-ac-kr/kickball (search): 1.32k images, class KickBall. Unclear whether it is the US game.
- For the rest, reuse the soccer ball weights from roboflow/sports and the baseball pack's base/foul-line logic.

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Fair / foul | AUTO / BETA near the line | Ball first `bounce` or first touch in the homography vs foul lines |
| Bouncy pitch (WAKA: a pitch bouncing above ~1 ft at the plate is a ball) | BETA | Ball height at the plate vs the 1 ft reference (scale from plate size) |
| Caught fly = out | BETA / AUTO | `catch` with no prior `bounce` |
| "Pegging" a runner (hit below the shoulders = out; head shots don't count) | BETA | Ball-person contact (ball trajectory deflection + person box) + pose head/shoulder region |
| Force out at base | BETA | Foot-on-base vs ball possession (as in baseball) |
| Leaving the base before the kick | BETA | Foot leaves the base zone before the kick `contact` (audio onset) |
| Kicker kicks behind/at the plate | AUTO | Foot position at `contact` |
| Bunting ban, "too hard pitch", interference | PLAYERS DECIDE | — |

**Demo:** live indoors is feasible with a playground ball and taped bases (it is the same rig as wiffle). Recorded clips come from Pexels or YouTube CC.

**Effort: PACK-ONLY** (reuses the wiffle/baseball pack geometry + soccer ball weights).

---

## 6. Cricket (backyard / tape-ball)

### Repos, models and data
| Asset | URL | License | Stars | Last push | Weights | Notes |
|---|---|---|---|---|---|---|
| **kafle1/pocket-drs** | https://github.com/kafle1/pocket-drs | AGPL-3.0 (commercial license available) | 4 | 2026-10-20 | No trained model; colour/motion detector + RANSAC | **Single phone on tripod LBW review.** Details below. |
| Cricket (Mayur) | https://universe.roboflow.com/mayur-vfrav/cricket-3syfj (search) | CC BY 4.0 (per search snippet) | — | — | — | Classes: ball, bat, batsmen, stumps. |
| NEW BALL TRACKING | https://universe.roboflow.com/cricket-ball-tracking-dataset/new-ball-tracking (search) | CC BY 4.0 (per snippet) | — | — | — | Classes: ball, bat, batsman, stump. |
| cricket 2 (lbwdrs) | https://universe.roboflow.com/lbwdrs/cricket-2-7snzq (search) | not read | — | — | — | Classes: ball, bat, batsman, bowler, non-striker. |
| Kanav123/Cricket-ball-Tracking | https://github.com/Kanav123/Cricket-ball-Tracking | none | 6 | 2019-02-01 | — | Kalman/particle-filter ball tracking. |
| muaz-urwa/Cricket-Shot-Classification-using-Computer-Vision | https://github.com/muaz-urwa/Cricket-Shot-Classification-using-Computer-Vision | none | 15 | 2019-05-23 | — | Shot classification (post-game analytics). |
| KayanShah/Cricket_LBW_Review | https://github.com/KayanShah/Cricket_LBW_Review | MIT | 2 | 2026-06-27 | — | Browser-based LBW where the user marks points. |

PocketDRS in more detail:
- **Calibration:** PnP from 8 stump corners.
- **Physics:** a 10-parameter bounce/swing model with uncertainty propagated to the stump plane. It returns "umpire's call" when the 1σ miss exceeds the stumps. This is exactly Trophy's BETA philosophy.
- **Assumptions:** benchmarks assume 60 Hz.
- **Validation:** mostly synthetic, plus 3 real clips.
- **Stack:** Flutter + FastAPI.

Do not link the AGPL code into Trophy. Re-implement the idea.

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Bowled (stumps/wicket hit) | AUTO | Ball-stump contact: audio "clack" onset + stump/bail/bin displacement (backyard wickets are often a bin or crate) |
| Boundary 4 (ball crosses the boundary after bouncing) | AUTO | Ball `line_cross` of the boundary polygon after a `bounce` |
| Six (crosses on the full) | BETA | No `bounce` detected before the boundary. A missed bounce at 30 fps is the risk. |
| Caught | BETA | `catch` with no prior `bounce` since bat `contact` (bat-crack onset) |
| "One hand, one bounce" backyard catch | BETA | One wrist at the catch + exactly one `bounce` |
| Hit the fence/house on the full = out (house rule) | BETA | Ball-wall contact zone with no prior bounce |
| Run out | BETA | Bat or foot in the crease zone vs stumps-broken frame (audio) |
| Front-foot no-ball | BETA | Pose front foot vs popping-crease line (homography) at the release frame |
| Wide (outside the marked wide line) | AUTO when clear; BETA near the line | Ball crossing point at the batting crease vs the wide markers |
| LBW (rarely played in the backyard) | BETA | PocketDRS-style monocular physics fit. Needs 60 fps Android. |
| Throwing/chucking, "tip and run" disputes | PLAYERS DECIDE | — |
| Runs/overs/wickets scoring | AUTO | Event bookkeeping; runs from batter crossing count (crease `line_cross`) |

**Demo:** live is possible with a tennis/tape ball and a cardboard-box wicket in a hall: bowled (AUTO, audio + box moves), no-ball (BETA), wide (AUTO). Ball speed indoors is low, which helps. **Recorded:** YouTube CC tape-ball clips.

**Effort: LITE** (generic ball + pose + homography). An LBW module would make it FULL; skip it unless one teammate is a cricket fan.

---

## 7. Street / roller / floor hockey

### Repos, models and data
| Asset | URL | License | Stars / size | Activity | Weights | Notes |
|---|---|---|---|---|---|---|
| HockeyAI dataset + model (SimulaMet) | https://datasets.simula.no/hockeyai/ ; https://huggingface.co/SimulaMet-HOST/HockeyAI | MIT (HF) | 2,100 frames; HF 5 likes | HF 2025-12-07 | Yes (YOLOv8) | Classes: puck, player, goaltender, referee, faceoff dots, goal frame, center ice. Broadcast ice hockey. |
| SimulaMet-HOST/HockeyRink | https://huggingface.co/SimulaMet-HOST/HockeyRink | MIT | 1 like | 2025-12-07 | Yes | 56 rink keypoints (ice only). |
| HiteshG/ice | https://github.com/HiteshG/ice | none | 0 | 2026-01-15 | — | BoTSORT / SAM2+Cutie puck tracking modes. A good idea source. |
| grant81/hockeyTrackingDataset | https://github.com/grant81/hockeyTrackingDataset | GPL-3.0 | 25 | 2023-10-31 | — | MOT-format player tracking. |
| Hockey (Roboflow, 7.25k images) | https://universe.roboflow.com/project-prvhb/hockey-2mqk3 (search) | not read | 7.25k images, 2 models | — | Hosted | Instance segmentation: goalkeeper, player, referee, stick, lines, puck. |
| HockeyBallDetector (DetectorHockey) | https://universe.roboflow.com/detectorprendas/hockeyballdetector (search) | CC BY 4.0 (snippet) | — | — | — | Roller-hockey **ball**. Closest to street hockey. |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Goal | AUTO | Ball/puck enters the goal polygon and stops (resting state, robust at 30 fps) + net motion + audio |
| Post / "ping" vs goal | BETA | Audio onset + ball deflection |
| High sticking (stick blade above the shoulders) | BETA | Stick detection (Roboflow hockey "stick" class or SAM2) vs pose shoulders |
| Crease violation (attacker in the goalie crease) | BETA | Feet `in_zone` crease polygon |
| Ball out of play / over the boards | AUTO | Leaves the court polygon |
| Offside (rarely played in street hockey) | BETA | Blue-line `line_cross` order (ball vs attackers' feet) |
| Slashing, tripping, "car!" stoppages | PLAYERS DECIDE | — |

**Demo:** a live floor-hockey demo needs a hockey stick and a small net. With a broom and a tennis ball into a box, goal AUTO works well. **Recorded:** Pexels or YouTube CC street hockey.

**Effort: PACK-ONLY.** Goal-by-resting-state plus generic ball tracking. The puck/ball is tiny and blurred in flight, so don't promise in-flight calls.

---

## 8. Dodgeball

### Repos, models and data
| Asset | URL | License | Size | Notes |
|---|---|---|---|---|
| Dodgeball detection (Simon Norin) | https://universe.roboflow.com/simon-norin-62w7g/dodgeball-detection-pcb7n (search) | not read | 2.23k images, 1 model | blueball, redball |
| Dodgeball-detection (proyects) | https://universe.roboflow.com/proyects-vvb4r/dodgeball-detection-3aabw (search) | not read | 1.13k images, 4 models | arbitro, jugador, pelota, shagger (Spanish; game footage) |
| Dodgeball (Kandidat) | https://universe.roboflow.com/kandidat-pgnqx/dodgeball-f7dp5 (search) | not read | 1k images, 1 model | ball, person |
| Dodgeball Dataset (fetian) | https://universe.roboflow.com/fetian/dodgeball-dataset (search) | not read | 902 images | ball |

GitHub has no CV dodgeball repos; the results are games (Unity ML-Agents dodgeball env, TF2 mods).

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Hit = out | BETA | Ball-person contact: ball trajectory deflection or stop within the person mask + audio thump onset + no ground `bounce` before the contact |
| Ball hit the floor/wall first (not out) | AUTO / BETA | `bounce` before contact |
| Head shot doesn't count (house rule) | BETA | Contact point vs pose head keypoints |
| Catch = thrower out (+ teammate back in) | BETA → AUTO when clean | `catch` (ball stops in a person's hand region) + identity of the last thrower |
| Crossing the center line | AUTO | Pose feet `line_cross` of the center line (homography) |
| Hold-time limit (5-10 s) | AUTO | Timer from `possession` |
| Who's in/out roster, win condition | AUTO | Bookkeeping |
| Deflection off a held ball, "it grazed my shirt" | PLAYERS DECIDE | — |

**Demo:** **excellent live.** Foam balls in the hackathon hall, 2v2, a phone on a tripod or table, center line taped. Loud, fun and visual for judges.

**Effort: LITE.** Roboflow dodgeball weights + generic contact logic. It is the most entertaining BETA demo of the field set.

---

## 9. Touch rugby (FIT rules)

### Repos, models and data
GitHub has no touch-rugby CV. One real-rugby event set exists: "Rugby" (rugbymatchdetection), https://universe.roboflow.com/rugbymatchdetection/rugby-qhhcd (search). It has 26 images with classes ball, Team1/2 players, lineout, ruck, scrum, tackle event. Everything else is generic person/ball. The oval ball is detected weakly by COCO `sports ball`; the American-football ball sets transfer.

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Touch made | BETA | Defender wrist inside the carrier's box/mask (one-hand version of two-hand touch) |
| Touch count (6 per possession) | AUTO given touches | Counter. Announces "5th touch!". |
| Forward pass | BETA | Ball velocity component toward the opponent's goal (homography) at release |
| Defensive offside at the rollball (5 m / 7 m retreat) | AUTO-ish | Defender feet positions in field coords at the rollball event |
| Try (ball grounded on/over the try line) | BETA | Ball low point + carrier posture over the line |
| Knock-on, obstruction, "touch-and-pass" timing | PLAYERS DECIDE | — |

**Demo:** recorded only (it needs space). **Effort: PACK-ONLY** (a re-skin of the two-hand-touch pack).

---

## 10. Team handball

### Repos, models and data
| Asset | URL | License | Notes |
|---|---|---|---|
| TeamTrack (handball side view) | https://github.com/AtomScott/TeamTrack | MIT code | Fixed-camera full-court MOT data |
| handball (Hctors Workspace) | https://universe.roboflow.com/hctors-workspace-niy3k/handball-y6iy6 (search) | not read | 2.55k images, 5 models: Arbitro, Area, Jugador, Pelota, Porteria, Portero (includes the goal *area* class) |
| Handball (Handball) | https://universe.roboflow.com/handball-ty04w/handball-hcmgz (search) | not read | 216 images, 2 models: Ball, Spieler |
| HeshamHanafy14/handball-detection-showcase | https://github.com/HeshamHanafy14/handball-detection-showcase | NOASSERTION, 0 stars, 2026-10-01 | YOLO11 player/GK/ref/ball |

Academic work (Ivašić-Kos, Univ. Rijeka) covers YOLO ball/player detection and an I3D 9-class handball action dataset, with no public download found. See https://www.bib.irb.hr/999075.

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Goal | AUTO | Ball in goal polygon + net |
| Goal-area (6 m) violation by a court player | BETA | Feet `in_zone` before release (a jump from outside is legal, so check the takeoff foot) |
| Steps (more than 3 steps holding the ball) | BETA | `step` events from pose ankles during `possession` |
| 3-second hold | AUTO | Timer from `possession` |
| Double dribble | BETA | Possession → bounce → possession → bounce pattern |
| Passive play, charging, fouls | PLAYERS DECIDE | — |

**Demo:** recorded (rare in US casual play). **Effort: PACK-ONLY.**

---

## 11. Cornhole (bags)

### Repos, models and data
| Asset | URL | License | Size | Notes |
|---|---|---|---|---|
| **Cornhole Referee** | https://universe.roboflow.com/cornhole-referee/cornhole-referee (opened) | **CC BY 4.0** | 394 images, 7 versions, 0 trained models | Classes: hole, board, blue-bean-bag, **blue-bean-bag-in-hole**, red-bean-bag, **red-bean-bag-in-hole**. Best fit. |
| cornhole (Ryan McLean) | https://universe.roboflow.com/ryan-mclean/cornhole (search) | not read | 576 images | Instance segmentation: Bags |
| cornhole-instanceseg (nonaugprj) | https://universe.roboflow.com/nonaugprj-0tyn3/cornhole-instanceseg-wyh9k (search) | not read | 440 images | hole, player, beanbag_blue, beanbag_red, board_surface |
| qcaddy-cornhole-v2 (truepathventuress) | https://universe.roboflow.com/truepathventuress-workspace/qcaddy-cornhole-v2 (search) | not read | 195 images | Bags, Board, Hole (+ an OOD set of 310 images) |
| Cornhole Detection | https://universe.roboflow.com/cornhole-detection-ld3cw/cornhole-detection-amtpw (search) | not read | 153 images | bag, board, hole |
| cornhole-pose-detection | https://universe.roboflow.com/cornhole-robot-workspace/cornhole-pose-detection (search) | not read | 1.36k images | Board keypoints, giving automatic board homography |
| Roboflow cornhole scorekeeping blog | https://roboflow.com/blog/automate-game-scorekeeping-vision-ai | — | — | Overhead camera beats a behind-board view (no perspective). Zone logic: bag in hole vs on board. No public weights. |
| davesarmoury/Cornhole | https://github.com/davesarmoury/Cornhole | none, 10 stars, 2021-06-15 | — | KUKA robot cornhole demo (OpenCV). Not a scorer. |
| Academic "ASK" (Wentworth) | — | — | — | Hough-circle hole + HSV bag colors, ~90% color / 85% location accuracy |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Bag in the hole (3 pts), including "slide-in" and "airmail" | AUTO | Bag track disappears inside the hole polygon + `bag-in-hole` class + soft audio. Resting-state check after the round. |
| Bag on board (1 pt) | AUTO | Bag mask overlaps the board polygon at rest, including bags hanging off the edge (any part on the board counts). Check that it does not touch the ground. |
| Bag hit the ground first, then bounced onto the board (removed) | BETA | Bag trajectory `bounce` on the ground plane before landing on the board + audio onset pattern |
| Bag hanging over the edge touching the ground ("foul bag") | BETA | Bag mask extends below the board edge to the ground plane |
| Cancellation scoring, game to 21, house "bust" rule | AUTO | Bookkeeping per inning |
| Foot fault (foot past the front edge of the board/foul line) | BETA | Pose feet vs the foul line at release (release = wrist velocity peak) |
| Throwing out of turn / from the wrong side | AUTO | Team color of thrower + side zone |
| "Did it move the other bag?" disputes | PLAYERS DECIDE (Trophy shows before/after frames) | — |

**Demo:** **the best live demo in this list.** A tabletop or regulation board (or cardboard with a 6" hole) and a phone overhead or on a tall tripod behind the board. It works indoors, judges can throw bags themselves, and AUTO calls land in under 1 s. It is entirely at rest-state, so 30 fps doesn't matter. **Recorded:** Pexels cornhole clips (https://www.pexels.com/search/videos/cornhole/).

**Effort: FULL** (or, better, FULL for a shared **"target/resting-object" pipeline**: fixed camera → plane homography → detect resting objects → zone/distance scoring). The same pipeline then gives cornhole, mini-golf, bocce, horseshoes, cup pong and bowling almost for free.

---

## 12. Disc golf

### Repos, models and data
| Asset | URL | License | Size | Notes |
|---|---|---|---|---|
| disc-golf-basket (Mrtzs Workspace) | https://universe.roboflow.com/mrtzs-workspace/disc-golf-basket (search) | not read | 251 images | basket |
| disc-golf-disc-detection (Mrtzs) | https://universe.roboflow.com/mrtzs-workspace/disc-golf-disc-detection (search) | not read | 16.8k images | disc classes |
| Disc golf putting detection (vegalabs) | via https://universe.roboflow.com/search?q=disc%20golf%20basket (search) | not read | 143 images, 1 model | basket, hand, putter, putter_in_hand: putting-specific |
| Disc Golf Flight Tracker | https://universe.roboflow.com/disc-golf-tracer/disc-golf-flight-tracker (search) | not read | 423 images, 3 models | disc |
| hislopzach/disc-tracker | https://github.com/hislopzach/disc-tracker | none, 16 stars, 2021-03-01 | — | Follow-flight tracer |
| wanner-work/PuttLab | https://github.com/wanner-work/PuttLab | AGPL-3.0, 3 stars, 2026-01-10 | — | Putting stats app (manual entry) |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Made putt (disc comes to rest in the basket) | AUTO | Disc disappears into the basket region + **chain jingle audio onset** + disc not reappearing below |
| Chain-out / spit-out | BETA | Chain audio + disc reappears outside the basket |
| Circle-1 foot fault (within 10 m: must show balance behind the lie; "falling putt") | BETA | Pose feet vs the marker-disc lie line (homography) + feet stepping past the lie before balance (`step` timing after release) |
| Stroke count | AUTO with BETA throw detection | Throw event (arm swing + disc departure) |
| OB (lands outside a marked area) | BETA | Landing point in a large-scale homography (hard from one phone) |
| Mandos, relief, "is that casual water" | PLAYERS DECIDE | — |

**Demo:** live only with a portable basket; a laundry basket plus a mini disc stands in. **Effort: PACK-ONLY** (putting module on the target pipeline + chain audio).

---

## 13. Mini golf / golf putting

### Repos, models and data
| Asset | URL | License | Size/stars | Notes |
|---|---|---|---|---|
| **minigolf-ball-detection** | https://universe.roboflow.com/minigolf/minigolf-ball-detection (opened) | **CC BY 4.0** | 1,583 images, 4 models (YOLOv8s), mAP50 71.7%, P 84.3%, R 64.2% | Classes: hole, golfball, golfhole |
| Golf (learning-ut2sx) | https://universe.roboflow.com/learning-ut2sx/golf-t880f (search) | CC BY 4.0 (snippet) | — | players, holes, club heads, golf balls |
| Golf Ball Detection (ben-ohno) | https://universe.roboflow.com/ben-ohno/golf-ball-detection-yfjzh (search) | Public domain (snippet) | — | ball only |
| natterman12/Golf-Ball-Tracking-and-Speed-Detection | https://github.com/natterman12/Golf-Ball-Tracking-and-Speed-Detection | GPL-3.0 | 21 stars, 2023-10-26 | **Putt tracking + speed** (OpenCV HSV, webcam). A direct reference. |
| wmcnally/golfdb | https://github.com/wmcnally/golfdb | none | 321 stars, 2023-01-24 | Swing-event sequencing (8 events), giving a "stroke" event for post-game swing analysis |
| onkar-99/Golf-Ball-Tracking | https://github.com/onkar-99/Golf-Ball-Tracking | none | 9 stars | Trajectory curve drawing |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Ball in the hole | AUTO | Ball track ends inside the cup polygon + disappears (+ rattle audio) |
| Stroke count | AUTO | Ball transitions from rest to moving while the putter head (or the player's wrists) is adjacent |
| Out of bounds / off the course (1-stroke penalty, replace) | AUTO | Ball leaves the playable polygon |
| Max strokes (e.g. 6) | AUTO | Counter |
| Double hit / pushing the ball | BETA | Second velocity impulse while the club stays in contact |
| Lip-out "gimme", ball against the wall relief | PLAYERS DECIDE | — |
| Putt speed, break, start line (post-game) | Analytics | Homography track |

**Demo:** **excellent live.** Carpet + golf ball + a paper cup or putting mat, phone on a table or tripod. Slow ball, so 30 fps is plenty. **Effort: LITE** (on the target pipeline + the minigolf weights).

---

## 14. Bowling (ten-pin, duckpin, backyard/toy)

### Repos, models and data
| Asset | URL | License | Size | Notes |
|---|---|---|---|---|
| bowlingpin (kitirat) | https://universe.roboflow.com/kitirat/bowlingpin (opened) | CC BY 4.0 | 371 images, 1 model; mAP50 58.6%, P 45%, R 93% | Classes: pin, bowling. Weak. |
| bowling pins detection (New Workspace) | https://universe.roboflow.com/algoharymohamed47-gmail-com/bowling-pins-detection (search) | not read | 440 images | |
| Fallen bowling pins detector (Industrial Robots) | https://universe.roboflow.com/industrial-robots/fallen-bowling-pins-detector (search) | not read | — | Standing vs fallen: exactly the needed split |
| AntonioZZ841/Ten-Pin-Bowling-Imaging | https://github.com/AntonioZZ841/Ten-Pin-Bowling-Imaging | none, 1 star, 2020 | — | Pin-state image processing |
| Patents US4827412A (video pinfall detector) | https://patents.google.com/patent/US4827412 | — | — | The classic method: threshold white pins against a dark background at known pin spots, sampled at the pin base to avoid occlusion |

### Calls
| Call | Tier | Sensing |
|---|---|---|
| Pin count (standing pins after the ball) | AUTO | Fixed 10-spot template (homography of the pin deck) + per-spot standing classifier after `settle` (no motion for ~1.5 s after the crash audio onset) |
| Strike / spare / split / frame scoring | AUTO | Bookkeeping + standing-pin configuration |
| Gutter ball | AUTO | Ball track leaves the lane polygon |
| Foul line (foot over the line) | BETA | Pose foot vs the foul line at release |
| Wobbling pin ("did it fall after the sweep?") | BETA | Late motion after settle |
| Pinsetter/house disputes | PLAYERS DECIDE | — |

**Demo:** **live with a toy or duckpin set** on a hallway floor (phone at the pin end). At a real alley, the house scoring system already counts pins, so the value there is the foul line plus analytics (ball speed, board at the arrows, entry angle). **Effort: LITE** (target pipeline + a quick standing/fallen fine-tune).

---

## 15. Other popular casual games: do they fit?

| Game | Fit? | Best asset | AUTO | BETA | PLAYERS DECIDE | Effort |
|---|---|---|---|---|---|---|
| **Cup pong (water pong / beer pong)** | **Yes, strong.** It reuses the table-tennis ball tracker. | Roboflow "beer pong recognition" https://universe.roboflow.com/experiments-uz6cp/beer-pong-recognition (search, 1.66k images, ball/cup/person); "beerpong-labeling" https://universe.roboflow.com/beerpongtracker/beerpong-labeling (CC BY 4.0 per snippet) | Ball made in cup (ball disappears into a cup polygon + splash audio); cups remaining / re-rack; bounce shot (table `bounce` before the cup, worth 2 in house rules) | Elbow rule (pose elbow over the table edge at release); swatting a bounce shot | "Did it spin out", "redemption" disputes | LITE |
| **Four square** | **Yes.** Pure bounce + zone logic, the same engine as basketball/TT. Very demoable (tape four squares on the floor). | Generic ball (COCO sports ball / WASB) | Out (bounce outside all squares); double bounce in your square; serve rotation | Line ball (bounce near a line); "holding/carrying" via contact duration | Interference, "cherry bombs" house rules | PACK-ONLY → LITE |
| **Bocce** | **Yes**, on the target pipeline (distance-to-pallino). | Roboflow "Bocce ball + multi color bocce ball" (Mod) https://universe.roboflow.com/mod-vb96h/bocce-ball-multi-color-bocce-ball-vgatt (search, 4.15k images: jack_ball, play_ball, colors) | Closest ball / points when the margin is over ~5 cm | Close measurements (show distances with error bars) | Foot fault at the throwing line (could be BETA with pose) | LITE |
| **Horseshoes** | Yes (target pipeline). The stake is easy; the shoe needs SAM2 or a fine-tune. | Roboflow "horseshoe" (37 images, search) | Ringer (shoe encircles the stake: straight-edge test across the open end) | Within 6 inches (1 pt) measurement; leaner | Foul line | PACK-ONLY |
| **Darts** | **Yes, strong**, with a proven open model. | **wmcnally/deep-darts** https://github.com/wmcnally/deep-darts (172 stars, no license, 2021; weights + 16k images on IEEE DataPort). Single-camera keypoint scoring. Roboflow dartboard sets. | Dart score per throw (DeepDarts), 501 checkout logic | Bounce-out / dart falling (did it count?) | Oche foot fault | LITE (bar-friendly demo) |
| **Pool / billiards** | Yes (overhead phone). | Roboflow "Pool Balls" (Ben Gann) https://universe.roboflow.com/ben-gann-lscqy/pool-balls-qlnkb (search, 3.82k images, all 15 balls + cue); ekiefl/pooltool (Apache-2.0, 424 stars) for physics replay | Ball pocketed and which; scratch (cue ball pocketed); stripes/solids assignment; 8-ball early = loss | First ball contacted foul (contact at 30 fps); no rail after contact | Called pocket / "slop", jump-shot legality | LITE |
| **Foosball** | Partial. The ball reaches ~35 mph, but goals are resting-state. | Roboflow foosball sets (44-55 images) | Goal (ball exits into the goal slot) + score | "Spinning" (rod rotates more than 360°: rod-marker tracking) | Table bumping | PACK-ONLY |
| **Air hockey** | Partial (the same as foosball). | JJulio/AHRobot (GPL-2.0, 196 stars, 2014): puck tracking for a robot | Goal | Puck over the center line (palming) | — | PACK-ONLY |
| **Kan Jam** (disc into a can) | Yes (COCO frisbee + can zone). | COCO frisbee | Instant win (disc in the slot), 3-pt "bucket" (disc enters the top) | Dinger (deflection contact: audio onset) | Deflection legality | PACK-ONLY |
| **Ladder toss / ladder golf** | Yes (target pipeline: bola wrapped on rung 1/2/3). | none | Points per rung at rest | Bola hanging vs knocked off | — | PACK-ONLY |
| **Tetherball** | Weak (rule calls are about touching the rope/pole). | — | Win (rope fully wrapped) | Touching the rope/pole (pose) | Most | Skip |
| **Capture the flag / tag** | Poor fit (field too big, calls are all contact). | — | — | Tag (contact) | Most | Skip |
| **Pickleball / volleyball** | Probably covered with racket/net sports elsewhere. If not: WASB has volleyball weights. | nttcom/WASB-SBDT | — | — | — | (elsewhere) |

---

## 16. Footage sources (CC or freely usable)

| Source | URL | License | Good for | Caveat |
|---|---|---|---|---|
| Pexels videos | https://www.pexels.com/search/videos/cornhole/ (also `/flag%20football/`, `/ultimate%20frisbee/`, soccer, bowling...) | Pexels License (free, no attribution) | Short B-roll for cornhole, bowling, soccer, frisbee | Search is fuzzy (thousands of loosely related hits). Clips are 10-30 s with no full plays. |
| YouTube with Filters > Features > Creative Commons | https://www.youtube.com/results?search_query=pickup+soccer (then apply the CC filter) | CC BY | Full casual games (wiffle leagues, backyard cricket, flag) | Verify each clip's license badge |
| Wikimedia Commons video | https://commons.wikimedia.org | CC BY/BY-SA | Odd sports (handball, touch rugby) | Sparse |
| BaseballCV amateur game videos (HF) | https://huggingface.co/datasets/dyland222/international_amateur_baseball_game_videos | see the dataset card | 205 amateur baseball games | Baseball only |
| TeamTrack | https://www.kaggle.com/datasets/atomscott/teamtrack | see Kaggle | Fixed/drone soccer, handball, basketball | 4K-8K, large download |
| HockeyAI | https://datasets.simula.no/hockeyai/ | per site | Ice hockey frames | Broadcast, not street |
| DeepDarts dataset | IEEE DataPort DOI 10.21227/05e7-xs69 | per DataPort | Darts | Needs an IEEE account |
| SoccerNet | https://www.soccer-net.org | NDA for videos | Broadcast soccer | Not casual; NDA |
| **Your own footage (recommended)** | — | yours | Every sport. Record Friday night on campus/park: flag 4v4, ultimate 3v3, wiffle, cornhole. | 30 min of filming = all demo clips with the exact phone geometry Trophy uses |

---

## 17. Bottom line for a 36-hour build

1. **One FULL pipeline: the "target/resting-object" engine.**
   - **What it is:** a fixed phone, a plane homography (4 taps), resting-object detection after an audio/motion "settle" event, then zone and distance scoring.
   - **Lead sport:** cornhole. Its CC BY 4.0 dataset already has *in-hole* classes, and it demos live indoors with judges throwing.
   - **Sports it unlocks:** mini golf (LITE), bocce (LITE), bowling (LITE), cup pong (LITE, with the TT ball tracker), horseshoes, ladder toss, Kan Jam and disc-golf putting (PACK-ONLY).
   - **Why:** these are the sports where Trophy can honestly claim AUTO at 30 fps.
2. **Field sports stay LITE on the generic engine:**
   - Two-hand touch / flag: snap timer, LOS, OOB and TD as AUTO; two-hand touch as the BETA showcase.
   - Soccer: roboflow/sports weights.
   - Ultimate: COCO frisbee; stall count and drop as AUTO.
   - Wiffle: BaseballCV weights; the strike-target trick turns strikes into AUTO.
   - Dodgeball: Roboflow weights; the best live BETA demo.
   - Cricket: bowled and boundary 4 as AUTO; PocketDRS ideas for LBW. Skip LBW unless you have 60 fps.
3. **PACK-ONLY:** kickball, touch rugby, team handball, street hockey, disc golf, plus four square, horseshoes, foosball and air hockey.
4. **Licensing traps:**
   - Ultralytics/YOLO weights (AGPL), PocketDRS (AGPL), BaseballCV MLB models (AGPL dual) and SoccerNet sn-gamestate (GPL) are fine for the hackathon but not for a product.
   - Kaggle NFL/DFL data is competition-use only.
   - Prefer RF-DETR + roboflow/trackers + supervision (Apache/MIT) for the core.
