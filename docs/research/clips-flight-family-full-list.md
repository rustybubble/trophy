# Trophy: public demo clips for the flight-family sports

Compiled 2026-10-23 for Cal Hacks 13. Nothing was downloaded except small thumbnails and auto-frames, which are in `ch13/thumbs/` (contact sheets `s_*.jpg`).

## How this was checked

- **YouTube:** I ran yt-dlp searches with the Creative Commons filter (`sp=EgIwAQ==`), about 45 queries. The machine's IP then hit Google's "sorry"/429 wall for watch pages; I did not try to bypass it. Instead I read each candidate's watch page in the in-app browser (normal same-origin fetch of `ytInitialPlayerResponse`) for these fields:
  - **license:** the exact string "Creative Commons Attribution license (reuse allowed)", or none, which I list as **STD**
  - **duration**
  - **max height and fps:** from adaptiveFormats, so "60/30" means a 60 fps stream exists
  - **audio stream present**
  - **description and chapters**
- **Camera angle:** checked for every clip from YouTube's three auto-frames (hq1/hq2/hq3, at about 25/50/75% of the video).
- **Wikimedia Commons:** API through the in-app browser. Direct curl was 429-limited.
- **Pexels:** WebFetch of search and detail pages.
- **Hugging Face, Zenodo, GitHub:** their APIs.
- **Audio caveat:** "audio = yes" means an audio stream exists. I could not listen without downloading. Where I say ball sounds are "likely audible", the reason is a courtside phone or GoPro and no music listed in the description. **Verify by ear before relying on the bounce/rim classifiers.**
- **License labels:**
  - **CC BY:** reuse allowed with attribution (credit the channel plus a link). OK for the Devpost video.
  - **STD:** standard YouTube license. Demo-only: ask the uploader or attribute, and do NOT put it in the Devpost video.
  - **NC / research-only datasets:** OK for a live judged demo with a credit, but avoid them in the public Devpost video.

Scoring rubric (1-10): static/tripod with corners visible (3), audio (1), full-body players (1), close calls or violations present (2), casual play (1), 1080p and at least 30 fps with long rallies (1), license cleanliness (1). Multi-view adds a bonus.

---

## 1. Table tennis

### HERO: Ping Pong Footwork & A Controversial Edge Shot (5-game battle vs Leanne)
- **URL:** https://www.youtube.com/watch?v=7maQFqJ3XQ0
- **Source and license:** YouTube, BenSucksAtPingPong. **CC BY (verified).**
- **Duration and format:** 9:35, up to 2160p, 60 fps.
- **Camera:** tripod at a table corner, low and wide. The whole table and all 4 corners are visible, and both players' full bodies are in frame. Single view.
- **Audio:** yes. Indoor club and phone near the table, so bounces are likely very audible.
- **Features and calls:** chaptered games (0:00, 2:04, 4:01, 5:34, 7:28), a **controversial edge point at 8:36** (edge vs side, good for the audio + trajectory edge classifier), long amateur club rallies, and serve and let opportunities.
- **Weaknesses:** stat-card text overlays at the start and end. Other tables are in the background. The corner angle foreshortens the far half of the table.
- **Score: 9**

### ALT 1: My Top Table Tennis Shots #3: Slams, Edges, & Lucky, Undeserved Blocks
- **URL:** https://www.youtube.com/watch?v=Xh7NxOMiQRo
- **Source and license:** YouTube, BenSucksAtPingPong. **CC BY.**
- **Duration and format:** 2:32, 2160p60.
- **Camera:** same club tripod setup, with a slightly varying corner per opponent.
- **Audio:** yes.
- **Features:** a compilation of **edge balls, net cords and lucky shots**: a ready-made "close call" reel and a Play of the Game source. Segments start at 0:00, 0:34, 0:43, 1:08 and 1:40.
- **Weaknesses:** it is a cut compilation, so there is no continuous match flow for scoring.
- **Score: 8**

### ALT 2: Rupesh vs Mykola, One Set Showdown to 7 (Thrilling, Unexpected Ending)
- **URL:** https://www.youtube.com/watch?v=YqrJZMJEDQ0
- **Source and license:** YouTube, Table Tennis Tube Canada. **CC BY.**
- **Duration and format:** 1:06, 1080p30.
- **Camera:** side-on tripod with the full table in view and full-body players.
- **Audio:** yes.
- **Features:** at 6-6 the server **misses his serve** and loses 7-6, a quick serve-fault and scoring demo.
- **Weaknesses:** the channel inserts PONGBOT ad cards in other uploads (this short one is fine). Only 30 fps.
- **Score: 7**

### Also considered
- **Table Tennis Tube Canada house-league matches.** Example: JhCxaWb7Dpg, 12:38, 1080p30, CC BY, a side-view tripod, but with ad interstitials.
- **Garage Ping Pong (I6aPCwP0OfY).** CC BY and very casual, but only 480p at 9 fps. Unusable.
- **Commons: "2 tekma finale državne ženske lige v namiznem tenisu Ravne 2015.webm".** https://commons.wikimedia.org/wiki/File:2_tekma_finale_dr%C5%BEavne_%C5%BEenske_lige_v_namiznem_tenisu_Ravne_2015.webm. 24:41, 1080p, **CC BY 3.0** (Televizija Uršlja). Broadcast-style camera, not casual.
- **Dataset: OpenTTGames.** https://lab.osai.ai/. **CC BY-NC-SA 4.0 [NC].**
  - 5 full games of 10-25 min plus 7 test clips, all 1080p at **120 fps** from a static side camera. Audio is not stated.
  - Labels: 4,271 **bounce, net and empty** events with ball coordinates, which makes it a ground-truth benchmark for the bounce/net-let detector.
  - Files are 0.2-10.8 GB; test_2.mp4 is 225 MB.
  - Demo-only because of NC. **Score: 7** (data value, not show value).
- **Multi-view:** no public synchronized multi-view TT video found. tt_tracker ships no videos, and "1000 Rallies" (arXiv 2606.25620) is event-camera data. Record your own 2-phone clip.

## 2. Pickleball

### HERO: Pickleball Doubles Challenge Court in Melbourne, FL 06/09/2023 Game 1
- **URL:** https://www.youtube.com/watch?v=QhLECLlXU3c
- **Source and license:** YouTube, BT Pickleball. **CC BY.**
- **Duration and format:** 8:26, **2160p, 60 fps.**
- **Camera:** tripod at the corner and side of the court. Both kitchens, the baselines and the sidelines are visible, and all 4 players are full-body (feet visible for kitchen faults). Single view.
- **Audio:** yes. Outdoor public courts, so paddle pops are likely audible, with neighbouring-court noise.
- **Features:** rec doubles; the channel's sister clips are labelled 3.5-4.5. Score overlay (for example "4-3"), so you can check Trophy's scorekeeping against it. Dinking at the kitchen line exercises the **kitchen volley foot fault** and two-bounce rule. Near-line in/out balls.
- **Weaknesses:** a burned-in score overlay (bottom right) and a date card at the start. Adjacent courts sit in the background.
- **Score: 9**

### ALT 1: Pickleball Doubles Mixed 3.5 to 4.5 in Melbourne, FL 06/04/2023, Games 2 and 4
- **URLs:** https://www.youtube.com/watch?v=0YAoUpbp37Y (11:58) and https://www.youtube.com/watch?v=cQq9A5RH3Ac (6:03)
- **Source and license:** YouTube, BT Pickleball. **CC BY.**
- **Format:** 2160p30.
- **Camera:** the same rig, behind the baseline corner.
- **Features:** full games with running score overlays; use them as a sequence. The same channel has a **1h24m session** (63HheyDLY3M, 2160p60) for long-form testing.
- **Score: 8**

### ALT 2 (top-down kitchen view): Phantom 3 Pickleball Pullman Berkman3
- **URL:** https://www.youtube.com/watch?v=0RKquBUivj8
- **Source and license:** YouTube, Bill Fulton. **CC BY.**
- **Duration and format:** 4:07, 1080p25.
- **Camera:** DJI Phantom 3 drone, **near-overhead hover over a casual singles game**.
- **Features:** the court lines are a perfect rectangle, ideal for showing the homography or minimap and **kitchen-line foot position** from above.
- **Weaknesses:** the drone drifts slightly and the players are small. Audio is probably drone noise.
- **Score: 6**

### Also considered
- **OsnXfpuy1Lc.** 3.5 Mixed Doubles semifinal, All Things Pickleball TV, CC BY, 30:55, 1080p60, indoor, static behind the baseline. A strong long-form alternative.
- **ckY8h5k5f8Q.** Chasing Pickleballs, "Playing With A 4.5 DUPR in Open Rec", CC BY, 7:46, 2160p60, behind the baseline. Chapters: highlight point 0:00, game start 0:20, game-losing point 7:37.
- **Commons: "Pickleball game.webm".** https://commons.wikimedia.org/wiki/File:Pickleball_game.webm. **CC BY 3.0** (Victor Jehovskiy, from YouTube), 3:57, 1080p. Low courtside camera behind the net post on a tournament court.
- **Commons: DVIDS "Pro Pickleball Tour" clips.** Public domain, 60 s each, edited news footage.
- **Pexels (Pexels License, free, no attribution):**
  - 32041192, "Aerial Pickleball Match on Blue Court" (Frank Schrader): 29 s, 2160x3840 vertical, 24 fps, perfect top-down.
  - 37165624, "Aerial View of Outdoor Pickleball Matches": 51 s, 4K, oblique drone over multiple courts.
  - Both are silent and short. Use them for B-roll and the minimap shot.
- **Drone File Drop 3VeReQXwES8.** "JAPA Evening Pickleball", CC BY, 4:04, 1440p24, overhead drone.
- **Datasets:** none with video plus line-call labels. pickleball-thesis/pickleball-serve-dataset on Hugging Face is gated and CC BY-NC.

## 3. Badminton

### HERO: [GAMES] Tokyo Badcox International Badminton Club, Friday night, Raw
- **URL:** https://www.youtube.com/watch?v=ShrdcaZMdS0
- **Source and license:** YouTube, HeartFlow Badminton. **CC BY.**
- **Duration and format:** 44:39, 1440p, **24 fps** (DJI Action 2 at 2K24, per the description).
- **Camera:** static wide-angle at a back corner. The full court with its lines and service lines is visible, and the players are full-body.
- **Audio:** yes. Raw club footage, so shuttle smacks are likely audible.
- **Features:** chapters for highlight 0:00 and Games 1-5 at 0:14, 9:39, 17:27, 27:46 and 35:53. **"The LET" at 42:22**, a real let call. Casual club doubles with long rallies.
- **Weaknesses:** 24 fps blurs the shuttle, the green lighting cast is strong, and the GoPro-style fisheye bends the lines (undistort before the homography).
- **Score: 8**

### ALT 1: Best Moments from our Weekly Casual Doubles #7
- **URL:** https://www.youtube.com/watch?v=PerYpkiLXRE
- **Source and license:** YouTube, ShuttleRocks. **CC BY.**
- **Duration and format:** 19:50, **2160p60.**
- **Camera:** static, low at the court corner in a multi-court hall.
- **Audio:** yes.
- **Features:** **"POTD" (play of the day) at 0:00**, a ready "Play of the Game" analogue, then Games 1-9 chaptered (0:18, 3:56, 7:04, ...). Casual mixed and men's doubles.
- **Weaknesses:** other courts are in view, players sometimes walk in front of the lens, and it is an edited best-of.
- **Score: 8**

### ALT 2: Badminton Sesh #1 G1
- **URL:** https://www.youtube.com/watch?v=oSNKBSpQob8
- **Source and license:** YouTube, KPS Badminton Team ("just some buddies"). **CC BY.**
- **Duration and format:** 9:50, 1080p30.
- **Camera:** tripod behind the baseline at court level, with a clean wooden court and clear lines.
- **Audio:** yes.
- **Features:** pure pickup doubles, unedited. Good for **landing in/out** at the back line and the side lines.
- **Weaknesses:** low camera height compresses the far court, and only 30 fps.
- **Score: 7**

### Also considered
- **2012 US Badminton Adult National Championships (Roy Huang).** Several finals, CC BY, 1080p25. Static elevated behind-court camera, but spectators cross the frame. Example: eMfNpjUpx8k, Men's Singles Final, 32:55.
- **"Outdoor Stories" "No copyright" outdoor games.** Example: xiAEi677UGE, CC BY, 2160p30, 12:13. Faint chalk lines, so the homography is hard.
- **Commons: "Битва Корпораций ... Бадминтон" (2020).** Corporate amateur league, 1080p, CC BY 3.0, 7-14 min each.
- **Pexels 35087074, "Dynamic Indoor Badminton Match with Youths".** 22 s, 4K25.
- **Datasets:** ShuttleSet and TrackNet are broadcast and research-only, and the video comes from YouTube. No public multi-view badminton video found; BadmintonGRF (arXiv 2605.01876) is multi-view plus force plates, but release status is unknown.

## 4. Tennis

### HERO (single view): Fall 2026 SGV Mens 3.5 SoCal Doubles 18 & Over Match #2
- **URL:** https://www.youtube.com/watch?v=JReOUveKesY
- **Source and license:** YouTube, Sammy Chang. **CC BY.**
- **Duration and format:** 26:08, 1080p, **60 fps.**
- **Camera:** tripod behind the baseline corner at fence height. The near and far baselines, sidelines and service boxes are visible, and the players are full-body.
- **Audio:** yes. Outdoor, so racquet hits are audible and bounces are fainter.
- **Features:** a full USTA 3.5 league doubles match (1st set 0:00, 2nd set 14:14). Many close **baseline and sideline calls**. Casual level.
- **Weaknesses:** the far court is small (as with every single-camera tennis clip), and neighbouring courts are visible.
- **Score: 8**

### HERO (multi-view gold): CalTennis dataset
- **URL:** https://huggingface.co/datasets/demalenk/caltennis (paper: arXiv 2606.20542)
- **License:** **CC BY-NC 4.0 [NC]**, ungated.
- **What it is:**
  - 51 h of practice and match play from 40 players.
  - **2-6 synchronized cameras at 60 Hz** on tripods at the net posts and corners, which is essentially Trophy's phone rig.
  - Per-video `timestamps.npy` and **`camera_calibration/<session>/<video>/calib.json`** with intrinsics and extrinsics.
  - Faces are blurred. 288 files; each mp4 is about 1.1-1.5 GB (for example, session `01_23_2026_17_00_court2` has E and W views).
- **Features:** this is the only found source that exercises **multi-view 3D, the auto-director, and challenge replay from several angles** with real calibration. It is also a UC Berkeley dataset, a nice Cal Hacks touch.
- **Weaknesses:** NC license, huge files (stream or download a single session), and pose-focused (no ball labels). Audio is unknown.
- **Score: 9** for the multi-view demo.

### ALT: 12 Mins Of Incredible Doubles Tennis (3.0 Men's USTA)
- **URL:** https://www.youtube.com/watch?v=bFuMpsuFK7Y
- **Source and license:** YouTube, knockitclose. **CC BY.**
- **Duration and format:** 12:58, 1080p30.
- **Camera:** elevated tripod centred behind the baseline (the best homography angle of all the tennis clips).
- **Audio:** yes.
- **Features:** a highlight reel of long 3.0 rallies, **SwingVision overlays** (score, "ACE" label) to compare against Trophy's calls, and hard serves.
- **Weaknesses:** burned-in SwingVision graphics, and the clip is an edited highlight cut.
- **Score: 7**

### Also considered
- **kA-Gj9n8eEA, "February 04 Tennis Racquet Club of Columbus 4.0".** CC BY, 17:23, 1080p24. Indoor, elevated behind-baseline view, unedited.
- **lUTREL5vsY8, "Weekend Tennis 2".** CC BY, 9:38, 1080p60, corner tripod.
- **rBo9EsdO8D8, Deo Diary.** CC BY, 4K30. Has a **"Controversial Call" chapter at 10:56**, but it is a handheld vlog.
- **IEEE DataPort "Multi-View Tennis Ball Dataset".** Drone plus court camera, with ball ground truth. https://ieee-dataport.org/documents/multi-view-tennis-ball-dataset-trajectory-estimation-drone-and-court-cameras-annotated. A DataPort login is likely needed; license unverified.
- **Avoid:** TK Tennis "double bounce" clips. They carry a CC tag but are re-uploaded ATP broadcasts, so the license is laundered.

## 5. Volleyball (indoor and beach)

### HERO, indoor: Handymen vs AZIAN Mixed, Mixed Moscow Volleyball League (1st set)
- **URL:** https://www.youtube.com/watch?v=kVpO4ypzPYU
- **Source and license:** YouTube, Almost Volleyball. **CC BY.**
- **Duration and format:** 15:19, 1080p, **60 fps.**
- **Camera:** static, elevated at a corner and side of the court. The whole court, the net and all 12 players are in view, full-body.
- **Audio:** yes, a gym. Hits are audible, with echo.
- **Features:** a **full set, "no highlights, first point to last"** (description). Amateur mixed league. Score overlay (HND/AZM). Good for **in/out, 4-touch counting and net touches**.
- **Weaknesses:** score overlay in the top left. Light at the far end of the gym washes out the far court.
- **Score: 9**
- **Twin:** uWO7pmyoC7o, "Drive New vs Skameyka Team", same channel, 12:57, 1080p60.

### HERO, beach: Who Wins This Beach Volleyball Battle?
- **URL:** https://www.youtube.com/watch?v=Jz9-F1OW_rQ
- **Source and license:** YouTube, John P. Vosnakis. **CC BY.**
- **Duration and format:** 9:23, **2160p60.**
- **Camera:** static behind the baseline. Full court, all four corner lines and the net are visible, and the players are full-body.
- **Audio:** yes. Outdoor with wind.
- **Features:** amateur doubles on a public beach court with a sand-line **in/out** focus.
- **Weaknesses:** a date stamp overlay, and wind noise is likely.
- **Score: 8**

### ALT, indoor: Week 1: Bumpin Uglies vs Sets On The Beach (Social)
- **URL:** https://www.youtube.com/watch?v=XfMTZRoAwdk
- **Source and license:** YouTube, Volleyball Austin. **CC BY.**
- **Duration and format:** 37:43, 1080p30.
- **Camera:** high end-line view of the whole court; the cleanest homography of any volleyball clip.
- **Features:** a true social rec league (casual).
- **Weaknesses:** 30 fps, and an intro card.
- **Score: 8**

### ALT, beach: Mens Doubles Sand Volleyball, Portland OR
- **URL:** https://www.youtube.com/watch?v=W7Xsb1Gufr8
- **Source and license:** YouTube, Tyler Gong. **CC BY.**
- **Duration and format:** 26:42, 1080p30.
- **Camera:** tripod behind the baseline, low.
- **Features:** 4 games chaptered (0:00, 5:59, 13:11, 19:51). Pickup doubles.
- **Weaknesses:** the low angle compresses the far court.
- **Score: 7**
- **Twin:** 7wagmNjzXVw, 12:48, games at 0:00 and 6:23.

### Also considered
- **Paul Sander "IVL Coed Rec League" (dozens of ~1h40m nights).** Example: RYJ7hqkZXrI, CC BY, 2160p30, **360° spherical "lifeguard" camera covering 2 courts**. You can reproject it to any virtual camera, a cheap "virtual multi-angle" demo. Matches are chaptered.
- **Commons: "Beach volleyball in Korea 2014.webm".** CC BY 3.0, 3:51, 720p, static wide shot of an amateur game.
- **Commons: "Beach volleyball in slow motion, 8 times slower.webm".** CC BY 4.0, 4K, 72 s, good for a slow-mo replay look.
- **fast-volleyball-tracking-inference repo (MIT).** Sample `examples/gtu_20250316_002.mp4` (20.5 MB) with a `_predict_ball.csv`, and `beach_st_lenina_20250622_g1_005.mp4` (6.7 MB) with a CSV. It is a ready "known good" tracker input.
- **Multi-view:** EPFL "Volley" 3-camera sequences give homographies and player positions only (research use). No open synchronized video found.

## 6. Roundnet / Spikeball

### HERO: Purdue vs MSU Pools, Central Fall Sectional 2026
- **URL:** https://www.youtube.com/watch?v=kgSM2WkQlek
- **Source and license:** YouTube, Cheung Roundnet. **CC BY.**
- **Duration and format:** 6:26, 1080p, **60 fps.**
- **Camera:** static tripod on grass, wide. The net is centred and all 4 players are full-body through 360° movement.
- **Audio:** yes. Outdoors, so net and rim hits are likely audible.
- **Features:** college sectional pool play with a score overlay (7-7 → 16-20). Fast rallies that exercise the **rim vs pocket** and **3-touch limit** calls, and diving saves for the Play of the Game.
- **Weaknesses:** "condensed" editing (dead time cut). The net is small in frame, so rim calls need a zoomed crop. Score and logo overlays.
- **Score: 8**
- **More from the channel:** UDKFf_M6lnE (7:16, 1080p60) and about 40 similar clips.

### ALT 1: Pick Up 23/03/2025 MIXED, Paulina/Cedric vs Vivien/Marek (Berlin)
- **URL:** https://www.youtube.com/watch?v=EXil8nprdXU
- **Source and license:** YouTube, Paulina_Roundnet. **CC BY.**
- **Duration and format:** 4:20, 2160p30.
- **Camera:** indoor gym tripod. The net is large in frame, so the **rim is clearly visible**.
- **Features:** a true **pickup** mixed game, one set to 15.
- **Weaknesses:** gym floor lines clutter the scene, and there is a timer overlay.
- **Score: 7**
- **Twins:** H9JKeVYB_HU (4:52, 2160p but 22 fps) and TuJqW5iOjDk (5:48, 2160p30).

### ALT 2: Spikeball 2018.08.12
- **URL:** https://www.youtube.com/watch?v=l5FVOzzP0_A
- **Source and license:** YouTube, Kyrylo Yakymenko. **CC BY.**
- **Duration and format:** 11:02, 1080p60.
- **Camera:** mixes a **drone overhead** shot with ground static shots, so it can serve as a pseudo multi-angle.
- **Weaknesses:** edited; the angles are not synchronized.
- **Score: 6**

### Datasets and stock
- **Roboflow "Roundnet Project".** 861 images, CC BY 4.0. Images only.
- No Commons or Pexels roundnet video.

## 7. Padel

### HERO: Intermediate Level 3.5+, Padel Match (Mariano Sports Arena)
- **URL:** https://www.youtube.com/watch?v=GKWNVYeEAlE
- **Source and license:** YouTube, Padel Match Point. **CC BY.**
- **Duration and format:** 44:36, 1080p, **60 fps.**
- **Camera:** static, behind the back glass at about head height. The full court, the side and back glass, and the net are visible, and the players are full-body.
- **Audio:** yes. Indoor, so ball-on-glass and ball-on-floor thuds are likely audible, which is great for **wall-bounce sequencing**.
- **Features:** a full amateur match (3.5). Exercises floor-before-wall, double bounce and serve rules.
- **Weaknesses:** the near-side players occlude the view, and the far service lines are small.
- **Score: 8**
- **Channel:** dozens of full amateur matches. Examples: 8BbUDdm1cCs (39:29, 1080p60) and 632k3fKraeA (47:02, 1080p60).

### ALT 1 (high overhead): THE RALLIES KEEP GETTING BETTER! FULL PADEL MATCH 1H30
- **URL:** https://www.youtube.com/watch?v=Kbghpf089I4
- **Source and license:** YouTube, PADEL PRO CASABLANCA. **CC BY.**
- **Duration and format:** 1:29:48, 1080p30.
- **Camera:** a **high corner camera looking down over the whole court**, the best homography view.
- **Features:** a full match.
- **Weaknesses:** 30 fps, and the fisheye is visible.
- **Score: 7**

### ALT 2 (multi-view gold): PadelVic dataset
- **URL:** https://github.com/UPC-ViRVIG/PadelVic
- **License:** **research-only** ("CC-BY-like license coming soon").
- **What it is:** one amateur match filmed by 4 cameras, plus Xsens motion capture of one player:
  - main camera at 6 m: 4K50
  - GoPro at 7.5 m: 4K60
  - **two court-level phones at 1.45 m:** Galaxy S22+ and iPhone 13 Pro Max, 1080p60
  - Each file is 3.2-5.2 GB on Dropbox. Synchronization is implied (paper: Padel Scientific Journal 2024); verify it.
- **Features:** the exact phone-rig analogue, a multi-view auto-director, and challenge replay.
- **Score: 8** (judged demo only)

### Also considered
- **PadelTracker100.** https://zenodo.org/records/14653706, **CC BY 4.0**. About 100k frames from the WPT 2022 Finals, single broadcast angle. Labels only (7.1 GB zip): ball positions, poses and shot events.
- **nptZ7bnXJmo, "Padel in Barcelona 2.0-2.5".** CC BY, 1080p30. Has burned-in "Just in" / "Oops" call banners, but the description lists **music**, so its audio is unusable.
- **Pexels (free, silent):**
  - 32210388, "Aerial View of Padel Court Match in Play": 25 s, 2720x1530, 24 fps, top-down.
  - 33444758: 12 s, 4K30, oblique.

## 8. Squash / Racquetball

### HERO: Woodruff Nee Squash Tournament 2018, Peter Boal vs. Benjamin Smith
- **URL:** https://www.youtube.com/watch?v=uDzznrSM5tY
- **Source and license:** YouTube, Craig Lebowitz. **CC BY.**
- **Duration and format:** 15:14, 1080p, **60 fps.**
- **Camera:** static, **high above the back wall**. The whole floor, short line, service boxes, front wall and side-wall out lines are in view, and the players are full-body.
- **Audio:** yes. In a squash court the ball-on-wall cracks are loud.
- **Features:** amateur club tournament play. Exercises **front-wall out and tin** (the tin line is at the far end of the view) and side-wall out lines.
- **Weaknesses:** the tin is far and thin in frame. Two players overlapping from above.
- **Score: 8**

### ALT 1: Court 1 / Winter League Championship (Maine Squash)
- **URL:** https://www.youtube.com/watch?v=c4ekhzAYKvo
- **Source and license:** YouTube, Maine Squash. **CC BY.**
- **Duration and format:** 2:09:50, 1080p30.
- **Camera:** fixed **high camera behind the back glass**, fisheye, showing the full court with the front wall and tin.
- **Features:** an amateur league night with chaptered matches (00:11:25 position 7 match, 00:47:33 position 1 match, 01:34:07 women's match) and a score bug.
- **Weaknesses:** heavy fisheye.
- **Score: 7**
- **Channel:** dozens of 2-3 h league streams.

### ALT 2: W3.5 Amy Busey vs Lin Zhao (2017 Rothenberg)
- **URL:** https://www.youtube.com/watch?v=xUAd_tZfSh4
- **Source and license:** YouTube, Squash Worldwide. **CC BY.**
- **Duration and format:** 30:07, **480p only**, 30 fps.
- **Camera:** static behind the back glass at eye level, showing the **tin and front-wall lines clearly**.
- **Features:** rated amateur (3.5 women).
- **Weaknesses:** low resolution.
- **Score: 6**
- **Twins:** 3j5N8bvtn-4 (M5.0 Final, 35:30) and SulAR9b68N8 (M4.0 Final, 31:26).

### Racquetball
- **URL:** https://www.youtube.com/watch?v=EckAW5V1wv0
- **Title:** "Racquetball Singles - Barry vs Cajetan (Match 1 of 4)", New Brunswick Racquetball Association. **CC BY.**
- **Duration and format:** 8:16, 1080p60.
- **Camera:** high on the back wall, showing the whole court.
- **Features:** casual Monday-night play. The channel has 30+ similar videos.
- **Score: 7**

## 9. Four square

This sport has the weakest supply. No good CC footage exists, so the hero is standard-license.

### HERO (STD license, demo-only): PRBC 4-Square Champions League
- **URL:** https://www.youtube.com/watch?v=lzlcWsl4Voc
- **Source and license:** YouTube, ColeParker12. **Standard license.** Ask or attribute; not for the Devpost video.
- **Duration and format:** 22:27, 1080p30.
- **Camera:** static, elevated corner over a **taped 4-square court on carpet**. All 4 squares and their corners are visible, and the players are full-body.
- **Audio:** yes. Indoor, so ball bounces are likely audible.
- **Features:** adult or teen competitive play (top 8 of a youth group). Exercises **line balls, double bounces and out calls**, and has many highlight plays.
- **Weaknesses:** the license, and some players stand outside the frame while waiting.
- **Score: 7**

### ALT (STD): 2012 Four Square World Championships Men's Final and Women's Final
- **URLs:** https://www.youtube.com/watch?v=OgF8rzssd0c (5:15) and https://www.youtube.com/watch?v=MaqrHuNF6ks (4:26)
- **Source and license:** YouTube, peterredshoes. **STD.**
- **Format:** 480p30.
- **Camera:** a gym floor court. The men's final is semi-handheld; the women's final is static and elevated.
- **Score: 5**

### Best CC option: Game of Four Square
- **URL:** https://www.youtube.com/watch?v=GYOKq-MLQa0
- **Source and license:** YouTube, Marc Graham. **CC BY.**
- **Duration and format:** 1:14, 480p30.
- **Camera:** a chalk court in a driveway, with a roughly static camera at a corner.
- **Features:** truly casual neighbourhood play.
- **Weaknesses:** low resolution, short, and faint chalk lines.
- **Score: 5**

### Also considered
- **jYWi4PyGJCM, Dave Briccetti.** "Detecting a Foursquare line fault, using a laser beam and micro:bit", CC BY. A hardware demo, not gameplay, but on-theme for line faults.
- **Commons and Pexels:** nothing.
- **Recommendation:** **film four square yourselves.** Chalk plus a phone on a tripod takes 15 minutes, and it is the cheapest sport to record.

## 10. Cup pong / beer pong / water pong

### HERO: ASOBP Kick Off Semifinale, Lucky Strike vs Twin Towers
- **URL:** https://www.youtube.com/watch?v=1Mc6mAcON5c
- **Source and license:** YouTube, bpong.at. **CC BY.**
- **Duration and format:** 4:43, 1080p, 25 fps.
- **Camera:** static, side-on to the table at table height. Both cup racks and both throwers are full-body.
- **Audio:** yes, but it is a noisy event hall. Ball-on-table bounces are probably partly masked.
- **Features:** a full tournament game. Exercises bounce shots, **cup hits (sinks) and re-racks**, and elbow-line throws. Throwers' feet are visible for "elbow over table" style faults.
- **Weaknesses:** 25 fps, so the ball blurs. Spectators sometimes block the view. Beer, not water.
- **Score: 7**

### ALT 1: ELITE Beerpong 2019-2020, Round 15: STEEL CITY vs. LeVerEgyBlant
- **URL:** https://www.youtube.com/watch?v=fcgK3Pz79lc
- **Source and license:** YouTube, sorpingponghu (Hungarian Beer Pong Association). **CC BY.**
- **Duration and format:** 23:57, 1080p25.
- **Camera:** static, elevated, **end-on along the table's long axis**, so both racks are in view. Good for cup localization.
- **Features:** a league match.
- **Weaknesses:** a dim bar and a crowd.
- **Score: 6**
- **Channel:** 30+ similar league finals. Examples: rlfcK3qzP8M and YK1UbBPRL_4, which uses a fisheye.

### ALT 2 (STD, demo-only): WSOBP IX Championship Game
- **URL:** https://www.youtube.com/watch?v=jcvp_T8K2h8
- **Source and license:** YouTube, bpong.at. **STD.**
- **Duration and format:** 15:02, 1080p25.
- **Camera:** static side-on view of the full table with referees, at the World Series of Beer Pong.
- **Features:** a "Play of the Game" source.
- **Score: 6**
- **Also:** RUpnVDumA7w, the uncut Game 3.

### Stock
- Pexels "friends playing beer pong" clips by cottonbro. Example: 6806109, 39 s, 4096x2160, 25 fps, free license, party B-roll with a moving camera.
- **Water pong:** nothing usable. **Recommend filming it**, which is trivial: a phone over a folding table, water cups and a cheap ball.

---

## Cross-sport notes for the build team

1. **Multi-view gold:**
   - **CalTennis** (tennis, CC BY-NC, calibrated 2-6 views at 60 Hz) and **PadelVic** (padel, research-only, 4 views including two court-level phones at 1080p60) are the only real synchronized multi-view sources found.
   - **Paul Sander's 360° IVL rec-league volleyball videos** (CC BY) can fake multi-angle by reprojection.
   - For table tennis, pickleball, badminton, roundnet, four square and cup pong, **record your own 2-3 phone clips** at the venue.
2. **Highest-frame-rate CC clips** (better for bounce timing and tracking): QhLECLlXU3c (pickleball 4K60), 7maQFqJ3XQ0 (table tennis 4K60), PerYpkiLXRE (badminton 4K60), kVpO4ypzPYU (volleyball 1080p60), Jz9-F1OW_rQ (beach 4K60), kgSM2WkQlek (roundnet 1080p60), GKWNVYeEAlE (padel 1080p60), uDzznrSM5tY (squash 1080p60), JReOUveKesY (tennis 1080p60).
3. **Burned-in overlays:**
   - Scores: BT Pickleball, Almost Volleyball, Cheung Roundnet, Maine Squash.
   - SwingVision graphics: the tennis clips that use SwingVision.
   - Mask them before OCR or the detector, or use them as ground truth for Trophy's scoreboard.
4. **Attribution string template:** "<Title>" by <Channel> (YouTube), licensed CC BY 3.0 (YouTube's CC license is CC BY 3.0). Commons: per the file page. Pexels: no attribution needed, but credit is nice.
5. **Licenses to avoid:** re-uploads of pro broadcasts that carry a CC tag (VolleyHub VNL, TK Tennis ATP clips, "BadmintonLegends: Free Use Vids"). The uploader does not own those rights.
6. **Timestamps of real calls worth cueing in the demo:**

| Clip | Timestamp | Call |
|---|---|---|
| Table tennis, 7maQFqJ3XQ0 | 8:36 | Edge-ball dispute |
| Badminton, ShrdcaZMdS0 | 42:22 | Let |
| Tennis, rBo9EsdO8D8 | 10:56 | Controversial umpire call (vlog) |
| Pickleball, ckY8h5k5f8Q | 7:37 | Game-losing point |
| Badminton, PerYpkiLXRE | 0:00 | POTD |
| Table tennis, YqrJZMJEDQ0 | Final rally, near the end of the 66 s clip (exact time not checked) | Missed serve at 6-6 |

Sources: YouTube watch pages (license field read 2026-10-23); Wikimedia Commons API; Pexels pages; https://huggingface.co/datasets/demalenk/caltennis; https://github.com/UPC-ViRVIG/PadelVic; https://zenodo.org/records/14653706; https://lab.osai.ai/; https://github.com/asigatchov/fast-volleyball-tracking-inference; https://ieee-dataport.org/documents/multi-view-tennis-ball-dataset-trajectory-estimation-drone-and-court-cameras-annotated.
