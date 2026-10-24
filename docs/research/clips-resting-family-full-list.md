# Trophy demo clips: resting-object family (+ table goal/pocket games)

Researched 2026-10-23 for Cal Hacks 13 "Trophy". **No video files were downloaded.** I pulled only metadata, YouTube storyboard sprites (160x90 tiles) and stock/Commons poster thumbnails, saved in `ch13/thumbs/` (contact sheets: `sheet_*.jpg`), to check camera angles.

## License verification method
- **YouTube:** candidates came from YouTube's own Creative Commons filter (`sp=EgIwAQ==`). For each one I ran `yt-dlp --dump-json` and read the `license` field. "CC BY (verified)" means the field returned `Creative Commons Attribution license (reuse allowed)`. YouTube CC BY is CC BY 3.0, so the clip can go in the Devpost video, but **credit the channel and link the video**. In the first 260 hits from the CC filter, every one carried the flag.
  - Partway through, YouTube rate-limited this IP (HTTP 429 or a Google "sorry" bot page). I checked a handful of clips through an Invidious mirror instead: it gave resolution, duration and storyboards but no license field. Those clips are marked **"CC (filter hit, flag not re-read)"**. Before using one, open the watch page and confirm the "Creative Commons Attribution license (reuse allowed)" line under the description.
  - Excluded: CC-flagged channels that re-post broadcast footage they probably don't own (Jomboy Media breakdowns, "Top 5 PBA Moments" from FOX Sports, Oche180 / Xander PDC clips).
- **Wikimedia Commons:** license read from the API's `extmetadata.LicenseShortName`. CC BY-SA means you credit the author and any derivative must carry the same license, which is fine for a demo.
- **Pexels / Mixkit:** covered by the Pexels License and the Mixkit Free License. Both allow free commercial use with no attribution required. These are short (5-40 s) and **usually silent or music-only**, so they work as B-roll or for detector tests but not for audio features.
- **Datasets** (stills, not video): see the end of this file.

**Score** is a "showcase score" from 1 to 10. It reflects a static angle with the target visible, audio, scoring events, a highlight moment, license, and resolution. **HERO** marks the best pick for each sport.

---

## 1. Cornhole

**HERO: "Cornhole 4 bagger to win game | Daniel Lilley vs Josh Hiser UKCL"**: https://www.youtube.com/watch?v=by5-AKocoho
- UK Cornhole League channel. **CC BY (verified)**. 28 s, 1920x1080 at 30 fps, uploaded 2023-01-07.
- Camera: a broadcast split-screen. Left is a fixed **"Feature Board" cam** looking down the board from the foul-line side; right is a fixed **"Player Cam"**. That gives two static angles in one frame. There is also a scoreboard overlay (17-6 going in), which gives ground truth for score calls.
- Audio: indoor hall, so bag thuds and in-hole drops should be audible. Not verified by ear.
- Features: bags on board (1) and in hole (3). The 4-bagger is the "Play of the Game" highlight, roughly 0:05-0:25, with the celebration and handshake at about 0:24-0:27. The score jumps to the 21 win. Homography is easy on the board-cam panel.
- Weaknesses: you have to crop the board panel out of the split-screen, the overlay and sponsor logos cover part of the frame, it's pro play rather than backyard, and it's short.
- **Score 8**

**Alt 1: "Richardson vs Lilley | Semi Final | UK Cornhole League"**: https://www.youtube.com/watch?v=OmFqxrdGexk
- **CC BY (verified)**. 15:08, 720p30.
- Camera: the same fixed board-cam plus player-cam split with a running score overlay through a full match (scores 4 → 17 visible in the storyboard).
- Use it for cancellation scoring across many rounds, plus likely hangers and blocked bags. Good for regression-testing the round logic against the overlay score.
- Weakness: 720p.
- **Score 7**

**Alt 2 (casual / garage league): "Fountain City Cornhole Championship Matches"**: https://www.youtube.com/watch?v=sj7fi5KiAXw
- Wayward Waggs ("The Cornhole Couple"). **CC BY (verified)**. 30:46, 720p30.
- Camera: a static tripod at an oblique angle behind the throwers, with the board small but fully visible. A Scoreholio overlay shows per-round cancellation scores (18-17 late in the match). Real amateur league with live-stream audio.
- Weaknesses: small board in frame, PRISM Live watermark, 720p.
- **Score 6**

**Backyard B-roll:** "Bean Bag Toss Game" https://www.youtube.com/watch?v=X3U34lDhxuM
- **CC BY (verified)**, 32 s, 720p.
- A static camera on a small board on asphalt, with bags landing and coming to rest at about 0:10-0:22. Clean homography and rest-detection test.
- Weaknesses: a dog intro, a title card, then a slideshow after 0:25.
- **Score 5**

---

## 2. Mini golf / putting

**HERO: "MAROOCHY RIVER MINI GOLF - HOLE 08 - HOLE IN ONE ACE"**: https://www.youtube.com/watch?v=IBBQ_bgLVDQ
- JOSH MARS / Mini Golf Australia. **CC BY (verified)**. 19 s, **1080p at 50 fps**.
- Camera: a fixed tripod behind the tee looking down the whole hole. The green, the obstacles and the cup area are all in frame.
- Features: ball tracking from tee to cup, ball in hole, 1-stroke "ACE" call. It's the Play of the Game moment at about 0:03-0:11.
- Weaknesses: intro and outro logos, only one stroke (no multi-stroke count), and the cup is far from the camera.
- **Score 7**

**Alt: "a lot of Amazing mini golf holes in one. Team Billisa hole in one challenge"**: https://www.youtube.com/watch?v=Bq-4Z6pKyx0
- **CC BY (verified)**. 5:58, 720p30.
- Camera: placed on the ground near the cup or behind the tee, static for each shot. About 15 aces on different holes, with the ball rolling into the cup toward the camera. Good for testing a ball-in-hole detector across many layouts.
- Weaknesses: heavily oversaturated colour filter, 720p, a talking-head intro (0:00-0:05), and some handheld close-ups.
- **Score 6**

**Stock close-ups:** Pexels clips under the Pexels License, silent.
- "Person Putting Golf Ball into the Hole" https://www.pexels.com/video/person-putting-golf-ball-into-the-hole-6573522/ (1080p30, 9 s, low cup-level angle)
- "Golf Ball Rolling into the Hole" https://www.pexels.com/video/golf-ball-rolling-into-the-hole-6573525/ (1080p, 13 s)
- "Mini Golf Putting Challenge on Artificial Turf" https://www.pexels.com/video/mini-golf-putting-challenge-on-artificial-turf-30936718/ (1080p24, 10 s)
- "Jugando a golf - cenital hoyo pelota" https://www.pexels.com/video/jugando-a-golf-cenital-hoyo-pelota-19320486/ (4K, 8 s, **overhead of the cup**, which suits a homography/rest test)
- Score 4 each.

Dataset: Roboflow **minigolf-ball-detection** (CC BY 4.0, 3,616 images, classes hole/golfball/golfhole): https://universe.roboflow.com/minigolf/minigolf-ball-detection

---

## 3. Bowling (lane + toy)

**HERO: "Bowling a Full Game Up-Close(r) on an Old-School AMF 82-30 (259)"**: https://www.youtube.com/watch?v=GjE8aQdeJyI
- Joe the pro. **CC BY (verified)**. 8:04, 1080p30.
- Camera: **fixed on the lane just in front of the pin deck** (wide-angle). The full 10-pin rack is centred and static for every frame of a whole 10-frame game (259), including the pinsetter sweep and re-rack cycle.
- Features:
  - pin count after the ball (standing pins clearly countable)
  - strike vs. spare calls (259 means mostly strikes, so several in a row)
  - pins crashing at close range in the audio
  - running score you can check against the known 259 total
  - "Play of the Game" strike explosions
- Weaknesses: fisheye distortion; the camera never shows the bowler or approach (no foul-line call); the ball enters fast at the bottom of the frame.
- **Score 8**

**Alt (split/spare): "20241018 4-5-7 spare conversion - ten-pin bowling.webm"**: https://commons.wikimedia.org/wiki/File:20241018_4-5-7_spare_conversion_-_ten-pin_bowling.webm
- Wikimedia Commons, by RCraig09. **CC BY-SA 4.0**. 18 s, 1080p.
- Camera: a static side-rear angle down the lane with the pins visible. It shows **successful and unsuccessful attempts at converting the 4-5-7 split**, which is exactly the "split" and "spare" call.
- Weaknesses: short, and the pins are smallish.
- **Score 6**

**Second angle (behind the bowler): "Bowling some stress away"**: https://www.youtube.com/watch?v=4Ku6dnbw3TA
- **CC BY (verified)**. 7:10, 1080p30.
- Camera: a static tripod behind the approach. The full lane is visible, with the pins at the far end. Casual solo bowling with real alley audio.
- Weakness: the pins are small at that distance.
- **Score 5**

**Toy bowling:**
- "My tiny bowling alley!" https://www.youtube.com/watch?v=p0zIkA2tC-8
  - **CC BY (verified)**. 6:45, 720p.
  - A cardboard alley with a static, pin-deck-focused camera.
  - Weakness: NCS background music over the audio.
  - **Score 4**
- "Toy Bowling (Sound design video)" https://www.youtube.com/watch?v=ehQ0FEXvwEs
  - **CC BY (verified)**. 28 s, 1080p60.
  - Toy pins with real sound and a low angle.
  - **Score 4**

Stock: Pexels "Bowling Ball Hitting Pins" https://www.pexels.com/video/bowling-ball-hitting-pins-7334251/ (Pavel Danilyuk, 1080p25, 38 s, a clean centred view of the pins). Silent, **score 4**.

Datasets:
- Roboflow kitirat/bowlingpin (CC BY 4.0, 891 images) https://universe.roboflow.com/kitirat/bowlingpin
- marvin-msmhr/bowling-ball-segment (classes ball/lane/pins)

---

## 4. Darts

**HERO: "501: INSANE Darts Match Highlights!"**: https://www.youtube.com/watch?v=5i7_m5eStl8
- Nick Sheppard / Project 501. **CC BY (verified)**. 5:14, 1080p60.
- Camera: a **perfectly frontal, fixed board cam** (Samurai board) with a **501 scoring-app overlay** (460/499, 417/379 and so on). That overlay is ground truth for segment scoring and checkout.
- Features: dart segment scoring (singles, trebles, bull), hand pulling darts (occlusion handling), 501 countdown, checkout highlight.
- Weaknesses: the vertical board video is pillarboxed inside a 16:9 frame with a CapCut watermark, audio is probably music or edited (check), and it's a highlights edit rather than continuous play.
- **Score 8**

**Alt (casual, two angles): "Throwing Darts For Fun 2 20 21"**: https://www.youtube.com/watch?v=FNuVp4ZOs6s
- mikieson. **CC BY (verified)**. 9:43, 1080p30.
- Camera: a fixed frontal board cam with a **picture-in-picture of the thrower** (the second angle), in a home setting with real dart "thunk" audio. Play runs from about 0:25 to about 8:30.
- Weaknesses: a flashy intro until about 0:25, an outro of graphics, a slightly off-axis board, and the PiP box covers the lower-left of the frame.
- **Score 7**

Stock: Pexels "A dart hitting a target in a dart board" https://www.pexels.com/video/a-dart-hitting-a-target-in-a-dart-board-26761291/ (4K, 19 s) and "Dartboard with Darts" https://www.pexels.com/video/dartboard-with-darts-7581338/ (1080p, 8 s). **Score 3-4**.

Dataset: **DeepDarts** (McNally et al., 16k images with keypoint labels, IEEE DataPort DOI 10.21227/05e7-xs69, code at https://github.com/wmcnally/deep-darts). The license field is blank on DataPort, so **treat it as research-only** until confirmed. Roboflow "Darts" (CC BY 4.0) https://universe.roboflow.com/dartsdataset/darts-i7eg8

---

## 5. Bocce / pétanque / lawn bowls (closest-ball calls)

**HERO: "Bocce being played"**: https://commons.wikimedia.org/wiki/File:Bocce_being_played.theora.ogv
- Wikimedia Commons, by Victorgrigas. **CC BY-SA 3.0**. 11 s, 1920x1088.
- Camera: down the court from the throwing end. The pallino and 4-5 balls are at rest at the far end and clearly separated, which is the classic "who's closest" frame for a distance measurement.
- Weaknesses: very short, audio unknown, no measurement-tie moment.
- **Score 6**

**Alt (full club play, pétanque): "Playing petanque"**: https://www.youtube.com/watch?v=u1jHCDW_8eo
- Sandy Austin. **CC BY (verified)**. 2:25, 1080p25.
- Herne Bay Petanque Club, Auckland. Camera sits near the jack end, so boules land and roll to rest beside the jack (closest-boule calls). There are several static stretches and the audio includes boule clacks.
- Weaknesses: some panning or handheld moments, and players walk into frame.
- **Score 6**

**Static-terrain alt: "Petanque Wallingford - Thames Valley Regional Shooting Competition"**: https://www.youtube.com/watch?v=ubrDLGLlFcA
- **CC BY (verified)**. 7:14, 720p30.
- Camera: a **locked-off tripod** down a gravel lane with target circles. Boules fly in and come to rest, which makes a perfect rest-detection test. The winner's run is at 3:28-4:49 per the description.
- Weakness: it's a shooting drill, not a closest-to-jack game.
- **Score 5**

Measurement-tie reference: "09 - Measuring Eng" (Learn With A Champion) https://www.youtube.com/watch?v=IrSUn743edM
- **CC BY (verified)**, 1:27, 1080p.
- A world champion explains measuring. It's mostly talking head, so it's useful only as a reference for the "measurement tie" rule.
- **Score 3**

Stock: Pexels "Four People Playing Boule in Park" https://www.pexels.com/video/four-people-playing-boule-in-park-10071083/ and "Petanque" https://www.pexels.com/video/petanque-17658629/

---

## 6. Horseshoes

**HERO: "ONTV News Break: MHPA Doubles Tournament (08/03/24)"**: https://www.youtube.com/watch?v=b5hwtNIxi9U
- Orion Neighborhood Television. **CC BY (verified)**. 3:18, 720p60.
- Content: Michigan Horseshoe Pitchers Association state doubles. There is a **close-up of a pit with shoes around the stake at about 0:06-0:10**, then rows of courts with pitchers throwing, including wide static shots down the courts. Clay-pit clank audio sits under the narration.
- Features: shoe at rest relative to the stake (ringer vs. shoe-in-count), plus a pitching motion.
- Weaknesses: a news edit with interviews and lower-thirds, short static stretches, no single pit filmed through a full inning.
- **Score 5**

**Alt: "ONTV News Break: LO Horseshoe Club (07/02/24)"**: https://www.youtube.com/watch?v=YGY7J6E0buU
- **CC BY (verified)**. 1:31, 720p60.
- Similar news-style footage with lane-long shots of pits and pitchers.
- **Score 4**

**Casual backyard: "Horse shoes 1999"**: https://www.youtube.com/watch?v=pIMryxrEBoA
- ESPONET. **CC BY (verified)**. 10:31 (VHS upscaled to 1080p).
- A backyard sand pit with a shoe landing near the stake (around 4:30-5:00) and red-cup party vibe.
- Weaknesses: handheld VHS, poor quality.
- **Score 3**

Gap: there is **no good static, single-pit CC clip with a clear ringer**. The tournament live streams by "Go Live Sports Cast" (NHPA Worlds) appeared in the CC filter, but the one I checked returned "video not available", so I couldn't confirm them. **Recommend filming horseshoes yourselves**, or using a toy or rubber horseshoe set at the venue.

---

## 7. Kan Jam

**HERO: "09.25.2021 - Can Jam Final Tourney at Sly Fox Brewery-Pottstown, PA"**: https://www.youtube.com/watch?v=s3l_Uo74q4Y
- Chris Cafiero. **CC (filter hit, flag not re-read)**. 12:57, **2160p30**.
- Camera: a **static tripod** at one goal end with the throwers and a big festival crowd behind them. There's a long continuous sequence of throws and deflections into the can, with real crowd audio.
- Weaknesses: the near can is at or below the bottom edge of the frame, and a spectator's head sits in the right foreground. Instant-win slot shots (through the front slot) might not be clearly visible. Re-read the license on the watch page before use.
- **Score 5**

**Alt: "Kan Jam At LOG"**: https://www.youtube.com/watch?v=KmlQ_9L8jRA
- GOhioCasts. **CC (filter hit, flag not re-read)**. 4:49, **480p only**.
- Casual outdoor game; the cans are visible.
- **Score 3**

Gap: Kan Jam is thin. **Film it yourselves.** It's easy at the venue with a phone on a tripod by the can, plus a second phone at the thrower.

---

## 8. Ladder toss / ladder golf / ladder ball

**HERO (weak): "1v1 Outdoor Minigame Battle | Ladder Ball | Freezing Cold Punishment"**: https://www.youtube.com/watch?v=cEMp2g-lI14
- savage gamer 68. **CC (filter hit, flag not re-read)**. 33:49, 1080p30.
- A backyard YouTuber challenge with an on-screen "Game 1: LadderBall, first to 15" score overlay, which is usable as ground truth. Bolas wrapping the rungs: the top rung scores 3, the middle 2, the bottom 1.
- Weaknesses: a vlog edit with face-cams and graphics, and the ladder isn't always in a static frame. Find the ladder-ball segment early in the video; the storyboard shows it after about 1:30.
- **Score 4**

Other leads not verified because of time and the rate limit: "Stige golf" https://www.youtube.com/watch?v=F7SbRl3SRRY (Danish ladder golf, 2:25) and "Redneck Golf" https://www.youtube.com/watch?v=SzY8PwGmz9I (3:53). No useful Pexels, Mixkit or Commons hits.

Gap: **film it yourselves.** Ladder toss is cheap, the static framing is trivial, and the bola "clack and wrap" is good audio.

---

## 9. Disc golf putting

**HERO: "BDGC / Halo Putting League - Season 2 Finale"**: https://www.youtube.com/watch?v=2Q9PDDK6f3Q
- Baysinger's Disc Golf Channel. **CC (filter hit, flag not re-read)**. 30:27, **1080p60**.
- An indoor putting league in a gym. The basket is in frame, putters stand at distance, and there's **chain rattle audio** indoors. Many makes and misses (chain-outs or spit-outs) across rounds. Putting runs from about 1:40 onward; the opening is graphics and an outdoor intro.
- Weaknesses: the camera moves between putters (not one locked angle all the way through), there's an end card, and some shots are close-ups of the putter rather than the basket.
- **Score 6**

**Alt (outdoor): "The British Putting Game | Disc Golf Putting Challenge"**: https://www.youtube.com/watch?v=iDvasVtMFE0
- Disc Golf Shenanigans. **CC (filter hit, flag not re-read)**. 19:49, **2160p30**.
- A putting-game challenge with an on-screen score ("First to 15 wins"), outdoors among trees, with the basket and chains visible.
- Weaknesses: an edited YouTube format with graphics and multiple angles.
- **Score 5**

Fallback: Commons "Eric Wu and Scott Schiller playing disc golf at DeLaveaga" https://commons.wikimedia.org/wiki/File:Eric_Wu_and_Scott_Schiller_playing_disc_golf_at_DeLaveaga.webm (CC BY-SA 2.0, 82 s, 720p; a course round, little putting). **Score 2**

---

## 10. Table games (goal / pocket detection only)

**Pool, HERO: "Awesome Break Shot!"**: https://www.youtube.com/watch?v=3oDeMi2bjLg
- Pool Table Friends. **CC (filter hit, flag not re-read)**. 51 s, 1080p30.
- Camera: **a static, near-overhead full-table view** with all six pockets visible. It shows a break with balls dropping, with a timer overlay. Ideal for homography plus pocket events.
- **Score 7**

Alts:
- Commons "Video Aktivitas Bermain Biliar di Bedugul" https://commons.wikimedia.org/wiki/File:Video_Aktivitas_Bermain_Biliar_di_Bedugul.webm (**CC BY-SA 4.0**, 12 s, 1080p, a casual angled table)
- Pexels "A Cue Ball Hitting a Rack of Billiard Balls" https://www.pexels.com/video/a-cue-ball-hitting-a-rack-of-billiard-balls-6503646/ (cottonbro, 4K25, 8 s)
- Commons "Carom billiards" (CC BY 3.0, 80 s, 1080p, static full-table view with a scoreboard, but **no pockets**)

**Air hockey, HERO: "Intense Air Hockey Battle!"**: https://www.youtube.com/watch?v=zGbfL9Njt3o
- J. Wolf. **CC (filter hit, flag not re-read)**. 10:42, 1080p30.
- Camera: a static side view of a home air-hockey table, with both goals in frame, a long rally game and real puck-clack audio.
- Weakness: oblique angle.
- **Score 6**

Alt: Pexels "Friends Playing Air Hockey" https://www.pexels.com/video/friends-playing-air-hockey-7233523/ (2560x1080, 15 s).

**Foosball, HERO: "Table football.ogv"**: https://commons.wikimedia.org/wiki/File:Table_football.ogv
- Wikimedia Commons, by אבנר. **CC BY-SA 4.0**. 11 s, 1080p. It was filmed **at a hackathon** (2017), which is a fun fit for the Devpost story.
- Weaknesses: an angled view with people in frame, and short.
- **Score 4**

Alts:
- Commons "Foosball.ogv" https://commons.wikimedia.org/wiki/File:Foosball.ogv (**Public domain**, 29 s, 720p, high angle over the table)
- Pexels "Friends Playing Foosball" https://www.pexels.com/video/friends-playing-foosball-7986560/ (1080p, 36 s)
- Chase Pennell's CC tournament uploads, e.g. https://www.youtube.com/watch?v=e0xz66FtDjU (37:50, not checked, rate-limited), which are worth a look for a full overhead match.

---

## Datasets (stills, for detector training)
- Roboflow **Cornhole Referee** workspace (394 images): https://universe.roboflow.com/cornhole-referee. Also Roboflow's cornhole scorekeeping tutorial: https://blog.roboflow.com/automate-game-scorekeeping-vision-ai/
- Roboflow **minigolf-ball-detection** (CC BY 4.0, 3,616 images)
- Roboflow **kitirat/bowlingpin** (CC BY 4.0, 891 images)
- **DeepDarts** (16k images; license unconfirmed) and Roboflow Darts (CC BY 4.0)
- Disc golf: Roboflow "Disc Golf Throw Detection" (CC BY 4.0) and DiscDetector. There are none for chains or baskets.
- I found **no datasets for horseshoes, Kan Jam, ladder toss or bocce.**

## Bottom line
- **Strong public footage** exists for cornhole (UKCL), bowling (pin-deck cam, 259 game), darts (board cam with 501 overlay), pool (overhead break) and mini golf (MGA ace).
- **Weak public footage**: horseshoes, Kan Jam, ladder toss and disc-golf putting (no clean static single-target CC clip). **Film these four at the venue** with phone tripods: one camera locked on the target, one on the thrower.
- Before the Devpost video, re-open each "filter hit, flag not re-read" watch page and confirm the CC BY line. Put credits for every CC BY / CC BY-SA clip in the video description.
