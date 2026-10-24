# Trophy: a universal referee and post-game analyzer for casual sports (v3)

*2026-10-22, the day before Cal Hacks 13.0. Supersedes [v2](Cal%20Hacks%2013%20-%20Trophy%20(universal%20ref%20+%20post-game%20analyzer)%20v2.md). Changes:*
- *Chess is removed.*
- *Added pickleball, badminton, two-hand touch football and every popular casual sport we could find, now **28 sports**, organized into **three engine families**.*

*Everything else from v2 stays: PWA capture, the SubQ Snap decision layer and coach, honest call tiers, the house-rule compiler.*

*Research notes (licenses and links checked through the GitHub, HF and Roboflow APIs today) are in [Cal Hacks 13 research notes/](../research/). The two new ones are `Trophy - racket and net sports.md` and `Trophy - field, team and target sports.md`.*

> **One-liner:** *"Open a link on any phone, point it at any pickup game, and Trophy referees it. Live calls with honest confidence, challenges, replays, a commentator, and a coach that shows you the better move. 28 sports, one engine."*

---

## 1. The idea that makes "any sport" real: 3 engine families × 28 rule packs

Building 28 pipelines in 36 hours is impossible. But every casual sport falls into one of **three perception families**. Build the 3 families well, and each sport becomes a **rule pack** (rules, calls, tiers, coach options) plus, at most, a swap of detector weights.

| Family | What it tracks | Sports | Core models (all checked) |
|---|---|---|---|
| **A. Flight** (a ball or shuttle flies and bounces on a mapped surface) | Ball/shuttle 2D → 3D, bounces (vision + **audio onsets**), the line or zone it lands in, contact height, touches per side, wall bounces | Table tennis, pickleball, badminton, tennis, volleyball, beach volleyball, roundnet/Spikeball, padel, squash/racquetball, four square, cup pong | [BlurBall](https://github.com/cogsys-tuebingen/blurball) (TT), [WASB-SBDT](https://github.com/nttcom/WASB-SBDT) (MIT; tennis, badminton, volleyball weights, F1 94.0 / 91.6 / 86.5), [TrackNetV3](https://github.com/qaz812345/TrackNetV3) (MIT, badminton F1 98.6), court keypoints, `solvePnP` |
| **B. Possession** (players move a ball or disc across a field) | People + teams + pose with feet, ball/disc carrier, field lines, snap/possession/timers, contact between players | Basketball, two-hand touch / flag football, soccer & futsal, ultimate frisbee, wiffle/softball/baseball, kickball, tape-ball cricket, dodgeball, street/floor hockey, touch rugby, team handball | [RF-DETR](https://github.com/roboflow/rf-detr) (COCO already has `sports ball`, `frisbee`, `baseball bat`, `baseball glove`), [roboflow/trackers](https://github.com/roboflow/trackers), [roboflow/sports](https://github.com/roboflow/sports) team classifier, [rtmlib](https://github.com/Tau-J/rtmlib) pose |
| **C. Resting object** (something is thrown and comes to rest; score by zone or distance) | A fixed phone + homography. Detect when motion stops, then score by zone or distance, with sound cues (bag in the hole, chains, pins) | **Cornhole**, mini golf/putting, bowling, bocce, darts, disc golf putting, horseshoes, Kan Jam, ladder toss | [Cornhole Referee](https://universe.roboflow.com/cornhole-referee/cornhole-referee) (CC BY 4.0, bag-in-hole classes), [minigolf-ball-detection](https://universe.roboflow.com/minigolf/minigolf-ball-detection) (CC BY 4.0), [deep-darts](https://github.com/wmcnally/deep-darts), Roboflow bowling-pin and bocce sets |

**Why 30 fps in the browser still works:**
- Flight sports get exact bounce timing from the phone mic, and their position from interpolation plus the error ellipse.
- Resting-object sports judge where things *stop*, which doesn't depend on frame rate.
- Fast pitches and shots (wiffle about 0.7 m per frame, cricket about 1 m) stay **BETA**.

### The sport wall (the "universal" proof judges see)
The dashboard shows a grid of **28 sport tiles**, each with an honest badge:
- 🟢 **LIVE**: demoed live at the table.
- 🔵 **VERIFIED**: runs end to end on footage we recorded at the event, with accuracy measured on labelled calls.
- ⚪ **PACK**: rule pack compiled and running on the generic family pipeline over a short clip, with no sport-specific tuning.

A judge taps any tile and watches its calls play over footage. The **house-rule compiler** (type a rule, and it's enforced on the next rally) makes the point that a 29th sport is just a rulebook away.

---

## 2. The sport catalog (calls by tier)

How it shows: **AUTO ≥ 90%** auto-call · **BETA** stands but challengeable, shows uncertainty · **PLAYERS DECIDE** never called. Demo plan: **L** = live at the venue, **R** = recorded at the event, **P** = pack + short clip.

### A. Flight family
| Sport | AUTO | BETA | PLAYERS DECIDE | Best existing code / weights | Demo |
|---|---|---|---|---|---|
| **Table tennis** ⭐ | Point scoring from the bounce sequence, double bounce, serve own side → opponent's side, net let on serve (audio + vision) | **Edge vs. side ball** (error ellipse), serve toss under 16 cm | Hand on the table, obstruction | BlurBall, [TT3D](https://github.com/cogsys-tuebingen/tt3d), [tt_tracker](https://github.com/ckjellson/tt_tracker) | **L** |
| **Pickleball** ⭐ | **Kitchen volley foot fault** (feet, not a fast ball, so it's reliable), **two-bounce rule**, clear in/out, double bounce | Near-line in/out, serve below waist / paddle below wrist, server foot fault, net touch | Score and server number disputes, hinders | [Good-Pickleball](https://github.com/yo-WASSUP/Good-Pickleball) (Apache; court corners, but its ball model is tennis weights), [TrackNet-Pickleball](https://github.com/AndrewDettor/TrackNet-Pickleball) (no license), WASB tennis weights | **L** (taped kitchen line + mini net) / **R** |
| **Badminton** ⭐ | **Landing in/out** (the shuttle falls almost vertically, so this is the easiest in/out of any sport), wrong service box, failing to clear the net | Serve height (casual "waist" or the 1.15 m rule), foot faults, double hit, net touch | Reaching over the net, obstruction | **TrackNetV3** ([HF weights](https://huggingface.co/rahulanantharama/TrackNetV3-badminton)), [Good-Badminton](https://github.com/yo-WASSUP/Good-Badminton) (Apache, ~1k★), [CourtKeyNet](https://github.com/adithyanraj03/CourtKeyNet) | **R** (L if the hall ceiling allows) |
| **Volleyball / beach** | Landing in/out | 4+ touches, the same player twice, antenna, serve foot fault, net touch | Lift / double contact, rotation | [fast-volleyball-tracking-inference](https://github.com/asigatchov/fast-volleyball-tracking-inference) (MIT, ~150 fps on CPU, detects touches), [RAVEL-VB](https://github.com/asigatchov/RAVEL-VB-beachvolleyball-tracking), WASB volleyball | **R** / P (the repo ships a sample match) |
| **Roundnet / Spikeball** | **Rim hit** (audio classifier), 3-touch limit, ball hits the ground before the net | Pocket/roll-up on serve, serve height, 7 ft serve line, toss height | Hinders, rim-or-pocket disputes | [Roboflow Roundnet Project](https://universe.roboflow.com/public-workspace-tpxwk/roundnet-project) (861 images + a model). **No open repo or paper exists**, so this is a novelty | **L** (one phone above the net) |
| Tennis | Clear in/out, double bounce, ball into the net | Close calls (about 1.4 m per frame at 30 fps), service box, foot fault, net-cord let | Hindrance, net touch | WASB tennis, [TennisCourtDetector](https://github.com/yastrebksv/TennisCourtDetector) (14 keypoints), TennisProject's bounce model (no license) | P |
| Padel | Floor bounce before the wall, double bounce | Serve rules, fence after the serve bounce | Out-of-court play, net touch | [Padex](https://github.com/rondo-labs/Padex) (GPL, ground vs. wall bounces), PadelTracker100 (CC BY) | P |
| Squash / racquetball | Tin or out line on the front wall, double bounce ("not up") | Serve zones, short serve | Let / stroke | [squash-vision](https://github.com/SpunkyMartian/squash-vision) (MIT, no weights), Roboflow squash ball set (4k images) | P |
| Four square | Ball out, bounce in the wrong square, double bounce | Carry/hold, "cherry bomb" house rules | Interference | Generic flight + floor homography (tape the squares) | **L** (tape it out at the venue) |
| Cup pong (water) | Ball in the cup (sound + vision), re-rack count | Bounce shot (counts double) | Elbow over the table | Reuses the table-tennis ball tracker; cups as resting zones | **L** (on the same table) |

### B. Possession family
| Sport | AUTO | BETA | PLAYERS DECIDE | Best existing code / weights | Demo |
|---|---|---|---|---|---|
| **Basketball** ⭐ | Make/miss + score, 3-second timer, shot clock, out of bounds (with an uncertainty band) | **Double dribble**, traveling | **Fouls, charges, and-ones** (shown to prove the tiers exist) | [AI-Basketball-Shot-Detection-Tracker](https://github.com/avishah3/AI-Basketball-Shot-Detection-Tracker) (weights in the repo, no license), [shot-tracker](https://github.com/aarnavshah12/shot-tracker) (RF-DETR), WASB basketball | **R** |
| **Two-hand touch / flag football** ⭐ | Out of bounds with a clear margin, **line of scrimmage at the snap**, **pass-rush "Mississippi" count** (a timer started by the snap), illegal forward pass beyond the line, touchdown, fumble = dead ball, no-run zone | **Two-hand touch** (both of the defender's wrists inside the carrier's box at the same moment), flag pull, catch in bounds, near-line out of bounds | Pass interference, holding, illegal blocks | **No open repo detects a snap or a two-hand touch, so this is a novelty.** Build it from a motion-onset snap, field homography and pose. Weights: [Roboflow nfl-detection-1500](https://universe.roboflow.com/test-cm1hp/nfl-detection-1500), [flag-football set](https://universe.roboflow.com/statslive-ms3nd/flag-football-ashw8) | **R** |
| Soccer / futsal | Goal (mini nets), clear ball out, restart type (corner, goal kick, throw-in), futsal 4-second rule | Near-line out, "goal" between cones (height), offside if played, handball | Fouls, tackles | [roboflow/sports](https://github.com/roboflow/sports) (MIT, 5.4k★, weights, top-down radar view) | **R** |
| Ultimate frisbee | **Stall count** (timer), drop = turnover, pull out of bounds | In/out on a catch, goal (catch in the end zone), travel, double team | Picks, fouls | COCO `frisbee` in RF-DETR + [Roboflow ultimate sets](https://universe.roboflow.com/ultimate-frisbee-analysis/ultimate-frisbee-game-hlwqv) | **R** |
| Wiffle / softball / baseball | Fair/foul (clear), cardboard strike-target hit, slowpitch mat strike, balls/strikes/outs bookkeeping | Strike zone, force outs (audio "pop" into the glove), catches, leaving the base early | Balk, infield fly | [BaseballCV](https://github.com/BaseballCV/BaseballCV) (MIT code + AGPL weights; ball, glove, bat, bases; 205 amateur game videos on HF), [roboump](https://huggingface.co/cvtechniques/roboump) | **L** (strike target) / R |
| Dodgeball | Center-line crossing, ball hold timer | **Hit = out, catch = thrower out**, head shot | Grazes, deflections | [Roboflow dodgeball sets](https://universe.roboflow.com/fetian/dodgeball-dataset) (1–2k images) | **L** (foam balls), the best live BETA demo |
| Tape-ball cricket | Bowled (audio + the wicket moves), boundary four, wide | Six, caught, no-ball, run out, **LBW with "umpire's call"** | Throwing (chucking) | [pocket-drs](https://github.com/kafle1/pocket-drs) (AGPL: single-phone LBW + physics fit, so reuse the idea), Roboflow cricket sets | P |
| Kickball | Kick behind the plate, clear fair/foul | Pegging (no head shots), bouncy pitch, force outs | Bunting, interference | Soccer weights + baseball pack | P |
| Street / floor hockey | Goal (puck/ball comes to rest in the net), ball out of play | High stick, crease, post vs. goal | Slashing | [HockeyAI](https://huggingface.co/SimulaMet-HOST/HockeyAI) (MIT), [HockeyBallDetector](https://universe.roboflow.com/detectorprendas/hockeyballdetector) | P |
| Touch rugby | 6-touch count | Touch, forward pass, try | Knock-on | The flag-football pack's touch logic | P |
| Team handball | Goal, 3-second hold | Goal-area violation, steps, double dribble | Fouls | Roboflow handball set (2.5k images) | P |

### C. Resting-object family
| Sport | AUTO | BETA | PLAYERS DECIDE | Best existing code / weights | Demo |
|---|---|---|---|---|---|
| **Cornhole** ⭐ | **Bag in the hole (3), on the board (1), cancellation scoring**, game to 21 | Foot fault, bag hit the ground first | "Bag was moved" disputes | [Cornhole Referee](https://universe.roboflow.com/cornhole-referee/cornhole-referee) (CC BY 4.0) + 6 more Universe sets, [davesarmoury/Cornhole](https://github.com/davesarmoury/Cornhole) | **L** (a **tabletop cornhole set** on the judging table: judges throw) |
| Mini golf / putting | In the hole, stroke count, out of bounds, max strokes | Double hit | Gimmes | [minigolf-ball-detection](https://universe.roboflow.com/minigolf/minigolf-ball-detection) (CC BY 4.0, 1.6k images) | **L** (putting mat + cup) |
| Bowling (toy or lane) | Pin count, strike/spare/split, gutter | Foul line, wobbling pin | Lane disputes | [bowlingpin](https://universe.roboflow.com/kitirat/bowlingpin), [fallen-pins](https://universe.roboflow.com/industrial-robots/fallen-bowling-pins-detector) | **L** (toy set) / P |
| Darts | Segment scoring (single, double, treble, bull), checkout | Bounce-outs | — | [deep-darts](https://github.com/wmcnally/deep-darts) (single-camera scorer with weights) | P (no sharp objects at the venue) |
| Bocce / horseshoes / Kan Jam / ladder toss | Closest-to-target ranking, ringer, slot/dinger, rung points | Measurement ties | — | [Roboflow bocce set](https://universe.roboflow.com/mod-vb96h/bocce-ball-multi-color-bocce-ball-vgatt) (4k images), generic | P |
| Disc golf putting | Made putt (chain audio + disc at rest in the basket) | Chain-out, circle-1 foot fault | Mandatory-route disputes | [disc-golf-basket](https://universe.roboflow.com/mrtzs-workspace/disc-golf-basket) | P |

**Skipped:** tetherball, tag and capture the flag (no meaningful calls). Foosball, air hockey and pool are possible PACK-only extras (goal or pocket detection only).

---

## 3. Demo lineup (3 minutes)

Before judges arrive, set up the judging table with the **table-tennis clamp net, a tabletop cornhole board, water cups for cup pong** and 3 phones on mounts. A Spikeball set sits on the floor beside the table.

| Time | Beat |
|---|---|
| 0:00–0:15 | "Every pickup game has *that* argument. Pros get Hawk-Eye. You get Trophy: open a link on any phone." A judge scans the QR code; their phone joins as a camera |
| 0:15–1:00 | **Table tennis, live.** A judge plays a rally. Phones beep and flash **"Double bounce, point to Sam."** An edge ball shows **"Edge, IN, 71%, challengeable."** The judge **challenges**: multi-angle replay → 3D ball mark with its error ellipse → verdict |
| 1:00–1:20 | **Switch sports in one tap.** The judge throws 3 bags at the tabletop cornhole board: "Bag in hole, 3. Cancels 1. Blue leads 4–1." The same phones, a different rule pack |
| 1:20–1:35 | **House rule.** The judge types "bags that hang over the hole count 2." Trophy shows the compiled rule and the next throw is scored with it |
| 1:35–1:55 | **Coach.** "On that rally you went cross-court; down-the-line was the better option (0.58 vs. 0.09)." The ghost trajectory plays and the commentator voices it |
| 1:55–2:30 | **Recorded at Cal Hacks:**<br>• Pickleball **kitchen foot fault**<br>• Badminton landing call<br>• Two-hand touch: **"5-Mississippi rush, early: penalty"** and a **two-hand touch at 82%**<br>• Basketball double dribble (beta) and a foul tagged "players decide" |
| 2:30–2:50 | **The sport wall:** 28 tiles with LIVE / VERIFIED / PACK badges and a measured accuracy number on each verified one. The **Play of the Game** trophy clip lands on the judge's phone |
| 2:50–3:00 | "Three engines, 28 rule packs, honest confidence. Any game, any phone." |

**If it's crowded:** skip table tennis rallies and lead with cornhole. It needs no rally and is almost impossible to get wrong.

---

## 4. Architecture

Same as v2: PWA phones, then the edge GPU laptop, then AWS after the game. The one change is that perception is split into the three families. The full repo map for capture, decisions, replay and broadcast is in [v2 §3](Cal%20Hacks%2013%20-%20Trophy%20(universal%20ref%20+%20post-game%20analyzer)%20v2.md#3-feature--existing-model-or-repo-what-to-download-not-build), minus chesscog and Stockfish.

- **Capture (PWA):**
  - Video: aiortc or FastRTC WebRTC at 720p, plus a 1080p MediaRecorder copy in OPFS.
  - Timing: phone-side audio-onset events, and NTP-style clock sync with a QR-clock calibration.
  - Feedback: a beep plus a full-screen flash. Android also vibrates; iOS can't vibrate from the web.
- **Event vocabulary** (expanded for 28 sports): `bounce`, `wall_bounce`, `contact`, `contact_height`, `touch_count`, `rim_hit`, `possession`, `snap`, `step`, `in_zone`, `line_cross`, `net`, `catch`, `player_touch`, `at_rest`, `score_zone`, `timer`. Each event carries an uncertainty.
- **Rule pack** (one YAML file per sport):
  - the family, detector weights and field template;
  - which rules run in code and which are Snap questions;
  - the tier of each call, and the coach's candidate-option generator;
  - the calibration temperature.
  Any rule that needs a signal we can't sense is tagged PLAYERS DECIDE automatically.
- **Decisions:**
  1. Geometry and timers in code.
  2. **SubQ Snap** (`subq-snap-1.1`) for ambiguous calls and the coach. Its per-option probabilities are temperature-calibrated on about 60 labelled calls.
  3. Claude writes the words: commentary, coach explanations, house-rule compilation.
  - Fallback chain: Snap → Qwen3-VL on the laptop → Claude voting → geometry only.
- **Coach per family:**
  - **Flight:** target zones on the opponent's side.
  - **Possession:** shoot / pass to the open teammate / drive, or in football the open receiver at release.
  - **Resting:** aim point and power for the next throw, from your miss pattern.
  - In every case Snap picks among the candidates, which always include the move actually made. The replay ghosts the better one.

---

## 5. Priorities (cut from the bottom)

- **P0:**
  - PWA join/record/stream, clock sync, beep/flash, challenge replay.
  - **Flight family on table tennis (live).**
  - **Resting family on cornhole (live).**
  - **Possession family on basketball (recorded).**
  - Rule-pack engine + those 3 packs.
  - Snap `decide()` with fallback.
  - Claude + Cartesia commentary.
- **P1:**
  - **Pickleball, badminton and two-hand touch** (recorded and VERIFIED).
  - Roundnet live.
  - House-rule compiler.
  - Coach + ghost.
  - Sport wall with all 28 tiles.
  - Trophy clip (RIFE + Remotion).
  - Calibration slide.
- **P2:**
  - More VERIFIED sports: soccer, volleyball, ultimate, dodgeball, wiffle, mini golf, cup pong.
  - 3D players (GVHMR/PromptHMR).
  - ReCamMaster re-shoot.
  - Privacy blur.

**Gates:**
- **Saturday noon:** each P0 family must produce at least one correct call, or fall back to "calls within 2 s after the point."
- **3 AM Sunday:** feature freeze.

**Recording trip (Saturday afternoon, about 2 h):** take 3 phones running the Trophy PWA itself to a park with courts and grass. In one trip, record basketball, pickleball, two-hand touch (3v3), soccer and ultimate, plus a few dodgeball and wiffle reps. Badminton goes indoors if the hall ceiling allows. Recording *during* the event with your own app also proves the PWA works. Don't pre-record footage before Friday; Cal Hacks requires all work to happen during the event.

---

## 6. Team split (4)

| Who | Owns |
|---|---|
| **A: PWA + resting family** | Device-test page (hour 1), camera/lens selection, recording to OPFS, WebRTC stream, clock sync, join by QR, beep/flash/challenge UI, router + HTTPS. Then **cornhole / mini golf / cup pong** (fixed phone, homography, detect objects once they stop moving) |
| **B: Flight family** | BlurBall + TT3D + triangulation + audio onsets (table tennis), then WASB/TrackNetV3 for **pickleball, badminton**, roundnet rim audio, volleyball |
| **C: Possession family** | RF-DETR + trackers + rtmlib + team colors, field homography; **basketball**, then **two-hand touch** (snap detector, rush count, touch from both wrists), soccer, ultimate, dodgeball |
| **D: Rules, decisions, story** | Rule-pack schema + 28 packs (Claude drafts, humans check the P0/P1 ones), house-rule compiler, Snap `decide()` + calibration, coach, Claude → Cartesia commentary, sport wall UI, trophy clip, **Devpost video** |

---

## 7. Do today (Thursday): accounts, downloads, gear, no code

- **Accounts:**
  - [ ] **SubQ console**: 1–2 people sign up now (100M free tokens, possible waitlist). Check that `subq-snap-1.1` is listed.
  - [ ] Cartesia ($5 Pro), Anthropic.
  - [ ] **AWS GPU quota** request.
  - [ ] SMPL registration (only if you'll do 3D players).
  - [ ] Roboflow account (needed to export the Universe datasets and models).
- **HTTPS:** [ ] a domain (also enters MLH's GoDaddy prize) + a Let's Encrypt wildcard via DNS challenge, pointed at the laptop's fixed LAN IP. iOS rejects self-signed certificates for `wss://`.
- **Download:**
  - Flight: BlurBall, TT3D, WASB (all sports), TrackNetV3 badminton, fast-volleyball-tracking.
  - Possession: RF-DETR, rtmlib models, basketball `best.pt`, roboflow/sports, BaseballCV weights.
  - Resting: the Cornhole Referee, minigolf, bowling and bocce exports from Roboflow.
  - Post-game: Practical-RIFE, PANNs, deface.
- **Gear:**
  - **Table:** clamp-on table-tennis net, paddles, **white** balls (BlurBall was trained on white, not orange); **tabletop cornhole set**; red cups.
  - **Bring to the venue:** **Spikeball set**; pickleball paddles + balls + **painter's tape** (kitchen line) + a portable net if you can carry one; badminton racquets + shuttles; a soft football; foam dodgeballs; cones.
  - **Rig and network:** 3–4 phone mounts, including one tall one; power banks; travel router; NVIDIA GPU laptop.

---

## 8. Risks

1. **Breadth vs. depth.** 28 sports invites "jack of all trades" skepticism. Defend it by being honest: the badges (LIVE / VERIFIED / PACK), a **measured accuracy on every VERIFIED sport**, and depth on the three family flagships.
2. **iPhone browser cameras:**
   - About 30 fps, and no focus or exposure lock.
   - The lens switches mid-game, so pick a physical lens by `deviceId`.
   - Use landscape only, because of sideways frames on iOS 26.6.
   - Settle it all in hour 1 with the device-test page.
3. **Calls near lines:** these stay BETA with a visible error ellipse.
4. **SubQ Snap:**
   - The model is new (1.1 launched today).
   - Its benchmarks are vendor-reported, and its capacity is limited.
   - The fallback chain must be wired by Saturday morning.
5. **Licenses:** many sport-specific weights are AGPL (Ultralytics, BaseballCV weights, pocket-drs), GPL (Padex), non-commercial, or unlicensed. That's fine for a hackathon. Keep the core on RF-DETR / rtmlib / WASB / BlurBall / roboflow (MIT/Apache) for a future startup.
6. **Venue Wi-Fi:** use your own router; nothing in the live loop touches the cloud.

**Competition for Q&A:**
- **SwingVision**: single-iPhone line calls, tennis and pickleball only, $15–40/month.
- Hawk-Eye: pro venues, 10+ cameras.
- **RefereeBench** (Apr 2026, 11 sports): the best video model scores about 60% and over-calls fouls. That's why Trophy uses geometry for measurable calls and a calibrated decision model only for judgment calls.
- **Novel per our search:** open computer vision for **roundnet** and for **flag-football snaps and two-hand touch**, and a **rulebook → referee compiler**.

---

## 9. Prize map (live Hive list, updated Oct 23 12:47 AM)

Source: [hive.hackberkeley.org/prizes](https://hive.hackberkeley.org/prizes), plus the MLH prizes listed only on Devpost. **Best Robotics has been removed** from both.

### Go for these (Trophy fits the judging criteria)
| Prize | What the judges ask for | How Trophy answers it | Built in |
|---|---|---|---|
| **1st / 2nd / 3rd Overall** | Application, Intentionality, Functionality, Creativity, Technical Complexity | Live input, judges play, honest confidence, 28 sports | Everything |
| **Most Technically Complex** | Technical depth | Several phones synced into 3D, calibrated decision probabilities, a rulebook compiled into a referee | Build plan F2–F11 |
| **Most Creative / Hacker's Choice** | Fresh idea; the crowd's favorite | People line up to play a point and get refereed; the sport wall | Demo |
| **Cartesia** (Meta glasses, TBD) | Voice must be **core, not a demo feature**. Scored 25% each on problem and originality, use of Cartesia, execution, and impact and responsibility (accessibility, privacy). They want a **2-minute demo-first video**, a README listing the Cartesia features used, and no keys in the repo | **Trophy is a voice referee.** Players mid-rally can't look at a phone, so **every call is spoken**. There are two commentator voices (play-by-play and colour), voice challenges ("Trophy, challenge!") and "ask the ref". **Audio-description mode** serves blind and low-vision players and spectators | F12, F19 |
| **Meta: Bringing People Closer Together with AI** (Round 2 trip to Menlo Park) | How meaningfully it strengthens human connection, how essential AI is, originality, the working demo | Pickup games with friends: it ends arguments fairly, makes casual games feel like a broadcast, and shares the Play of the Game and recap emails | Whole product |
| **SpacetimeDB** (prize "coming soon") | SpacetimeDB as the **core real-time backend**: live shared state, multiplayer, live dashboards, agents coordinating in one persistent world state. "Meaningfully used, not just added on the side" | **The game session lives in SpacetimeDB**: players, phones, rallies, score, calls, challenges, house rules. Phones, the dashboard, the engine and the Droid compiler all read and write the same live state through subscriptions and reducers | Build plan §0, F8 |
| **Anthropic** (prize "coming soon") | 1) **A named community** ("students" is too broad), 2) a real problem you've lived, 3) it works, and one thing done well beats a broad demo, 4) thoughtful use of Claude: you know where it could go wrong | **For this judge, frame Trophy around one community**, e.g. *"Berkeley rec pickleball regulars who call their own lines"*, and **lead with the pickleball line call plus the kitchen fault**. Claude: commentary grounded on the event log, coach explanations, rule answers. **Where it could go wrong:** wrong calls, which is why there are confidence tiers, "players decide", evidence mode, and Claude never making visual calls | F10–F12, F19 |
| **Factory: Best Use of the Droid SDK** ($2,000) | Droid does **real work in the running product** on **a trigger you designed**, with **controlled access and safety**, and its work **visible**: plans, steps, diffs, results. Scores poorly as a chatbot wrapper or a slides-only demo | **The house-rule compiler is a Droid.** A judge types a rule, a SpacetimeDB row triggers Droid, and Droid edits *only* the rule-pack file, replays the last 10 rallies as tests, repairs the rule until the tests pass, and streams its plan, diff and test results onto the dashboard. A human taps Approve to hot-load it | F10 |

### Cheap add-ons (only claim them if they're really used)
| Prize | Use |
|---|---|
| **Moss** (AirPods Max/Pro) | Example #1 is "voice agents that listen, respond, and act in real time." **Rulebook lookup:** official rules (scraped with Firecrawl), indexed in Moss for sub-10 ms search, answer "Trophy, what's the rule on…?", and cite the rule text in challenge verdicts (F19) |
| **MLH Best Use of Vultr** (M5Stack Tab5) | **Post-game GPU jobs on Vultr** (RIFE, GVHMR, ReCamMaster on an L40S). This also eases the $100 AWS limit |
| **MLH Best Use of Gemini API** | Gemini is the fallback decider and the highlight captioner |
| **MLH GoDaddy Registry domain** | The domain you need for HTTPS anyway |
| **Notability** | Keep ideation and architecture notes in it (they judge on process, detail, feature use and relevance) |
| **Figma** (brief TBD) | Only if the PWA is designed in Figma |

### Watch (recheck Saturday morning)
- **Annapurna Labs**, **Elastic**, **Convex**, **AfterQuery**, **Armadin**: all "coming soon". Convex is an alternative to SpacetimeDB, so pick one.
- **Microsoft "Built for the Real World"** is a long shot: it asks for high-impact domains (finance, productivity, healthcare), scored on customer understanding, measurable usefulness, path to production, responsible design and end-to-end function. You'd pitch rec-league referee shortages plus measured accuracy.
- **Best People-First Hack**, through the accessibility mode.

### Skip
Hyphenate, Visa, CRS, Capital One Nessie, Coinbase x402, Creao (you'd have to build in their platform), Fetch.ai, Apify, Bright Data, SpaceXAI (space data + Grok), Atlassian, Mana, Bitdeer, Planet-First, Hardware, Beginner, Solo.

**Opt-in list:**
- **Core:** Overall · Most Technically Complex · Most Creative · Hacker's Choice · Cartesia · Meta · SpacetimeDB · Anthropic · Factory Droid.
- **Extras:** Moss · MLH Vultr · MLH Gemini · MLH GoDaddy · Notability.

Don't add sponsors you only touch lightly; judges notice.

### Does adding Replay's features change the map? (Oct 23)
Replay's watch experience is rebuilt as the **Trophy Watch** post-game web app (build plan §5B). The opt-in list mostly holds; three prizes get stronger, and one new risk applies to all of them.

| Prize | Change |
|---|---|
| **Overall / Most Creative / Hacker's Choice** | ⬆ Trophy now covers **during** the game (the ref) *and* **after** it (a broadcast-style replay: follow a player, moments, condensed game, replay angles). That's a fuller story, as long as the demo stays tight |
| **Meta** | ⬆ Sharing reels, follow-a-friend, and a **watch party** where friends watch the replay together, synced through SpacetimeDB, are all "bringing people closer" |
| **SpacetimeDB** | ⬆ A second real-time use: **synced playback, cursors and reactions** across friends' browsers, on top of the live game state |
| **Moss** | ⬆ A second real use: **plain-English play search** over moments ("every kitchen fault by Sam"), on top of rulebook lookup |
| **Cartesia** | = Commentary was already core. Broadcast mode adds narrated highlight reels |
| **Anthropic** | = Still frame it around one named community. Claude parses search queries and paraphrases commentary, now behind Replay's **fact validator**, which is a good answer to "where could it go wrong" |
| **Factory Droid, Gemini, Vultr, GoDaddy, Notability** | No change |
| **Fire TV / Alexa** | Dropped: no Cal Hacks prize for them, and they carry device risk |
| **Elastic** (still "coming soon") | Watch: if its brief rewards search or agents over event data, play search could run on Elastic Agent Builder instead of Moss. Pick one |

> ⚠️ **New risk across every prize: eligibility.** Replay predates Cal Hacks and was submitted to the Amazon Developer Hackathon. Cal Hacks requires all implementation during the event. **Copying Replay's app code risks disqualification from every prize.** Safe path:
> 1. Use only the published MIT **courtcam** library as a disclosed dependency (confirm with organizers in #ask-directors).
> 2. Rebuild the watch app during the event.
> 3. Say on Devpost what existed before.
