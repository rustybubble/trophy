# Trophy - public demo clips, possession-family sports

Researched 2026-10-23 for Cal Hacks 13. No video files were downloaded; only YouTube auto-frame thumbnails (hq1/hq2/hq3 = frames at ~25/50/75% of the video) and Commons poster frames were pulled to check camera angle. Contact sheets: `C:\Users\Joseph\AppData\Local\Temp\claude\C--Users-Joseph-Code-TreeHacks-IDeas\c155ce4e-327e-4c15-95c5-3a10044b5441\scratchpad\ch13\thumbs\poss\sheet_<sport>.jpg` (+ `sheet_commons.jpg`).

## How this was searched and verified

- **YouTube**: ~60 queries run through YouTube search with the Creative Commons filter (`sp=EgIwAQ%3D%3D`) via yt-dlp flat search (about 1,300 unique results). The shortlisted videos were then fetched individually with `yt-dlp --dump-json --skip-download`. Clips marked **"CC BY (verified)"** returned `license == "Creative Commons Attribution license (reuse allowed)"` from that per-video fetch, along with max listed resolution and fps. YouTube rate-limited and bot-checked the IP mid-run (other agents were also scraping), so some clips are marked **"CC filter; re-check"**: they came back from the Creative-Commons-filtered search, but the per-video confirmation was blocked. Open the watch page and confirm the "License: Creative Commons Attribution" line under the description before using them. yt-dlp ran without a JS runtime, so a higher format could be missing; treat resolution as a floor.
- **CC BY caveat**: a CC BY tag on YouTube is the uploader's claim. That is fine for amateur channels filming their own games (most picks below). Channels re-uploading pro broadcasts with a CC tag (e.g. "Handball World") were excluded as likely license-washing.
- **Attribution**: CC BY requires a credit line ("Video: <channel>, YouTube, CC BY 3.0"). Several pickup-soccer uploads include "if you are in this video and don't want it public, tell me"; be respectful: crop or blur faces in the Devpost video if in doubt.
- **Wikimedia Commons**: MediaWiki API, File namespace, `filetype:video`, licenses read from `extmetadata`.
- **Pexels / Mixkit**: search pages (stock clips are 8-30 s, mostly drone/handheld; they serve as B-roll only).
- **Datasets**: Kaggle/HF/GitHub license fields checked directly.

Scoring (1-10) weighs: static/elevated camera with visible lines (homography) > visible Trophy calls > casual/pickup story > audio > resolution/fps > license cleanliness.

**Legend**: Static = tripod / fixed mount, no pan. "Devpost-OK" = license allows use in the public Devpost video with attribution.

---
## Hero clip per sport (at a glance)

| Sport | Hero clip | License | Len / res | Camera | Key Trophy calls | Score |
|---|---|---|---|---|---|---|
| Basketball | JaiArtHub "Fun Moderate to Intense 10 games Saturday run" https://www.youtube.com/watch?v=2NxcgKW7xFM | CC BY (verified) | 32:10, 4K60 | static tripod, outdoor half-court, score overlay | make/miss, OOB, travel, 10 game chapters | 9 |
| Flag football | "Flag Football Coaching" rule clips, e.g. Illegal Snap https://www.youtube.com/watch?v=V6nJyuKNstQ (+ 7 more) | CC BY (verified) | 15-35 s each, 1080p30 | static elevated wide sideline | snap, LOS, flag pull legal/illegal, flag guarding, PI: each clip pre-labelled | 9 |
| Soccer / futsal | Rob Alexander "Chantilly Co-Ed Pickup Soccer FULL GAME" https://www.youtube.com/watch?v=1vZ7AToa2qY | CC BY (verified) | 1:41:46, 4K60 | static wide-angle sideline, pop-up goals | goal between pop-up goals, ball out, restarts | 9 |
| Ultimate | AFDA "Marlow Street vs Pie Wagon, AMUC 2024 div 2" https://www.youtube.com/watch?v=gFwXenra7kI | CC BY (verified) | 39:17, 1080p30 | elevated wide, near-static, score overlay | end-zone catch, drop turnover, OOB | 8 |
| Wiffle / softball / baseball | Logan Hawkins "Militia vs Carolina OutKast, Slowpitch" https://www.youtube.com/watch?v=8i6MPqrGIGg | CC BY (verified) | 33:55 condensed, 4K30 | static wide behind backstop | fair/foul, catches, balls/strikes, bat crack | 8 |
| Kickball | "Kickball Game 10/19/2016" https://www.youtube.com/watch?v=jdsPIY_QU2w | CC BY (verified) | 45:39, 1080p30 | static action-cam on backstop, whole diamond | fair/foul, catches, outs at bases | 8 |
| Cricket | NCA Cricket AU "So many Wickets!! Backyard Cricket" https://www.youtube.com/watch?v=y8POhHKjGlU | CC BY (verified) | 4:32, 1080p30 | static behind bowler, real stumps | bowled, caught, FOUR overlays | 8 |
| Dodgeball | "NUS IFG Dodgeball 2019 UTSH" https://www.youtube.com/watch?v=SJP8ke6de2s | CC BY (verified) | 4:49:32, 1080p30 | locked-off elevated, full court | hit vs catch, OOB, final at 4:15:00 | 8 |
| Hockey | Beauty Roll Media "Tuesday Night Ball Hockey Pickup" https://www.youtube.com/watch?v=narcxP96V6o | CC (search filter; re-check, see note) | 7:03 | fixed high cam behind the net, GOAL overlays | goal / no-goal, crease | 8 |
| Touch rugby | Dallas Touch "Houston Tournament Game09 - Dallas vs HARC" https://www.youtube.com/watch?v=_vfK4y6bDpg | CC (search filter; re-check) | 18:19 | sideline tripod, pans | touch count, try, rollball | 6 |
| Team handball | NSW Handball "Round 4 NSWHA League 2026 - Sydney Uni vs UNSW" https://www.youtube.com/watch?v=vo8hQfV9PAY | CC (search filter; re-check) | 1:09:03 | fixed elevated corner, 6 m line visible | goal-area violation, goals, steps | 8 |

**Multi-view (synchronized) footage**: none of the CC YouTube finds are true synchronized multi-angle recordings (Roses Live ultimate is a switched multi-camera broadcast). For the multi-view / auto-director / challenge-replay demo use datasets: **SoccerTrack** (fisheye + drone, time-synced, LGPL-3.0) or **TeamTrack basketball** (2 side views + drone top view, MIT). Otherwise film it yourselves with 2 phones.

**Best "license-clean for the Devpost video" picks** (CC BY / CC BY-SA / CC0 / Pexels, no doubts about the uploader's rights): Rob Alexander pickup soccer (own footage, CC BY), Flag Football Coaching clips (own footage), Commons HCTV baseball/basketball (CC BY 4.0), Commons Alberta dodgeball (CC BY-SA 4.0), Commons Old Markonians cricket (CC BY-SA 4.0), Commons roller hockey (CC0), TeamTrack handball (MIT). A Devpost video that edits in a CC BY-SA clip is arguably an adaptation that must itself be released CC BY-SA, so prefer CC BY / CC0 clips where possible.

**Sports where you should film your own**: touch rugby (weak public footage) and two-hand touch football (no CC game footage). Kickball and wiffle are thin but usable.

---

## 1. Basketball (half-court pickup / streetball)

### HERO: "Fun Moderate to Intense 10 games Saturday run" - JaiArtHub
- URL: https://www.youtube.com/watch?v=2NxcgKW7xFM
- Source / license: YouTube, **CC BY (verified)**. Devpost-OK with credit.
- Duration 32:10 (1930 s); **2160p, 60 fps**; uploaded 2026-03-24.
- Camera: **static tripod at about head height facing one hoop**, single view, outdoor **half-court** run at Hogben Park; sideline, key paint and hoop visible; full bodies. Running score overlay ("Team A 4 - Team B 0", "Session 4") burned in.
- Audio: raw recording (ball bounces, rim, calls) - not checked for added music.
- Calls showcased: make/miss (10 short games), out of bounds / last touch, travel / double-dribble opportunities, fouls (evidence only). The score overlay doubles as ground truth for make/miss.
- Chapters (from description): 0:00 G1, 2:12 G2, 5:08 G3, 8:07 G4, 12:06 "Fun Intense Game 5", 16:47 G6, **19:16 "Intense Game 7"**, 24:18 G8, 26:34 G9, 29:23 G10. Play-of-the-Game candidates in G5/G7.
- Weaknesses: burned-in score overlay (mask before CV); low camera, so a waiting player in the foreground sometimes blocks part of the frame; one view only.
- **Showcase score: 9/10**

### Alt: Basketball613 "Casual Basketball 613" / "social basketball" / "Pickup Basketball 613"
- URLs: https://www.youtube.com/watch?v=z47hgGOI5cM (2:41), https://www.youtube.com/watch?v=U80wtWpum7E (2:29), https://www.youtube.com/watch?v=MbMDqimmE00 (0:36)
- YouTube, **CC BY (verified)**; 1080p, 30 fps; 2014-2015 (Melbourne social league / meetup).
- Camera: **fixed camera at chest height from a court corner** of an indoor gym (edited, a few camera positions): wide view with most court lines and the hoops visible, full-body players. Good homography input apart from the low angle.
- Audio: not checked (short edits may carry music).
- Calls: make/miss, out of bounds, travel, double dribble. The "social basketball" framing fits the casual-play story.
- Weaknesses: older 1080p30, short, players small in a wide frame, indoor full court.
- **Showcase score: 7/10** (cleanest indoor court lines of the basketball finds)

### Alt: "3 on 3 blacktop Basketball Game 2020" - M'ster Lewis
- https://www.youtube.com/watch?v=YmFqdAfnEE8 - CC BY (verified), 8:26, 1080p, **24 fps**.
- Static tripod, outdoor blacktop half-court, three-point line + key visible, 3v3, so this is true streetball.
- Weakness: description links a Spotify album, so the soundtrack is probably music, not court audio; 24 fps.
- **Showcase score: 7/10**

Also seen: "RAW FOOTAGE | GAME OF 21" (https://www.youtube.com/watch?v=kEQSSfgiB8U, CC BY, 1080p60, 9:12, outdoor park, mostly static); Roundball BC rec league (CC BY, handheld close-ups, skip); Wikimedia Commons "Boys Varsity Basketball v. Stowe - MARCH 4, 2026" (https://commons.wikimedia.org/wiki/File:Boys_Varsity_Basketball_v._Stowe_-_MARCH_4,_2026.webm, Hardwick Community TV, **CC BY 4.0**, 1080p, 88 min, high school) as a license-clean full-game fallback. Datasets: **TeamTrack** basketball (MIT) = 2 side views + drone top view, the only multi-view option found.

---

## 2. Flag football / two-hand touch

### HERO: "Flag Football Coaching" rule-clip series (flag-coaching.info)
- Clips (all YouTube **CC BY verified**, 1080p 30 fps unless noted, uploaded 2017-2018):
  - Illegal Snap - https://www.youtube.com/watch?v=V6nJyuKNstQ (0:16)
  - Flag Guarding - https://www.youtube.com/watch?v=Q4Bc-_4Menk (0:26)
  - Illegal Flag Pull - https://www.youtube.com/watch?v=ia4vDkeKfG8 (0:29)
  - False Start - https://www.youtube.com/watch?v=0oy3ZeCtAvo (0:26)
  - Pass Interference Defense - https://www.youtube.com/watch?v=U5-Zpli85MY (0:27)
  - illegal Forward Pass - https://www.youtube.com/watch?v=1KHE6Te6JLA (0:32)
  - illegal Motion - https://www.youtube.com/watch?v=KoEpbHSChIg (0:23)
  - Blocking - https://www.youtube.com/watch?v=cdzbER-7PHI (0:23, 720p)
  - (about 25 more on the channel: roughing the passer, illegal contact, illegal shift...)
- Camera: **static, elevated, wide sideline view** of adult amateur flag games on a grass pitch. The full field width, the line-of-scrimmage area and full-body players are in frame. The coach circles the offending player and titles the foul, so each clip is **labelled ground truth** for a Trophy flag call.
- Calls: snap, line of scrimmage / false start / motion, flag pull (legal vs illegal), flag guarding, forward-pass legality, pass interference; some show catches.
- Weaknesses: short (15-35 s); burned-in circle + title overlay; field lines faint (reused soccer pitch); hike-call audio unverified.
- **Showcase score: 9/10** (unique: every clip is a pre-labelled referee call)

### Alt: "SMW @ BVN Varsity Girl's Flag Football" - BVN Broadcast
- https://www.youtube.com/watch?v=8Dxx8tV_v0I - CC BY (verified), **85:50 full game**, 720p30, 2026-09-18.
- Fixed sideline student-broadcast camera under lights (light pan/zoom), yard lines and referees visible, score bug overlay (score changes = touchdown ground truth).
- Calls: snap, line of scrimmage, flag pulls, catches in bounds, touchdowns, rush.
- Weakness: high school, 720p, some panning.
- **Showcase score: 7/10**

### Alt: "We Started A New Season! 5v5 Men's Flag Football" - House to World
- https://www.youtube.com/watch?v=lkL3x55AaIY - CC BY (verified), 13:07, **2160p60**, 2026-03-27. Adult rec league under lights, a vlog mix of handheld + game footage. Strong pickup story and audio, weak geometry. **5/10**

Also: "12u 7v7 Unity Thunder vs Laurel Stallions Scrimmage" (https://www.youtube.com/watch?v=LLNlE3QnCcs, CC BY, 4K60, 9:13, handheld youth 7v7); "2013 Intramural Flag Football" (https://www.youtube.com/watch?v=GBpny9O9wWg, CC BY, 1080p, 1:10, US Air Force base intramural). Pexels has no true flag-football game clips (only soccer/drone B-roll). No usable CC two-hand-touch footage found beyond a gym PE lesson (4c38mt-Vnu0).

---

## 3. Soccer & futsal (small-sided pickup, cone / pop-up goals)

### HERO: "Chantilly Co-Ed Pickup Soccer | FULL GAME March 5, 2023" - Rob Alexander (@novasoccer)
- https://www.youtube.com/watch?v=1vZ7AToa2qY - **CC BY (verified)**, **1:41:46 (6106 s)**, **2160p, 60 fps**.
- Camera: **static tripod, wide-angle (GoPro-style fisheye) at the sideline**. Turf field with painted lines; small-sided co-ed pickup with **pop-up goals**, matching the cone-goal story.
- Audio: raw field audio (shouts, ball strikes) - not checked for music.
- Calls: goal between pop-up goals / cones, ball out over the touchline, restarts (kick-in), handball evidence.
- Weaknesses: fisheye distortion (undistort before homography); the far goal is small; long, so cut 2-3 min.
- Same uploader and setup, highlight cuts that are easier to demo:
  - "Soccer Highlights 2023-01-29 | 'Intentional hands!'" https://www.youtube.com/watch?v=_R3HcUCSKNI (18:41, 4K60, CC BY) - camera right behind a pop-up goal; the title names a handball call.
  - "Highlights - Chantilly Co-Ed Pickup Soccer 4/20/2023" https://www.youtube.com/watch?v=vY3udgpzmpk (12:20, 4K60, CC BY) - burned-in score + game clock ("WHITE 1 - DARK 5").
  - "Fairfax County Pickup Soccer Game Summary Feb 5, 2023" https://www.youtube.com/watch?v=s3IxEpyKi7A (20:50, 4K60, CC BY).
- Uploader note: "If you are in this video and do not want it made public please let me know." Be considerate (crop/blur faces) in the Devpost video.
- **Showcase score: 9/10**

### Alt (5v5 with goal timestamps): "sweat, sweat | 5 v 5 | sns football 4k" - sns interviews
- https://www.youtube.com/watch?v=s6EMb1PXuHI - CC BY (verified), 36:01, **2160p30**, 2024-11-20.
- Static camera **behind one goal** of a floodlit 5v5 cage pitch, score overlay ("sns vs tc 5-1").
- **Goal chapters**: 2:12 1-0, 3:26 1-1, 8:00 2-1, 12:36 3-1, 13:03 4-1, 13:25 5-1, 19:00 half time, 19:39 6-1, 19:59 7-1, 22:15 8-1, 23:42 9-1, 24:23 9-2, 25:03 9-3. These are ready-made ground truth for the goal detector.
- Weakness: behind-goal angle (poor homography for the far half), net in the foreground.
- **Showcase score: 8/10**

### Alt: "Charisturf Futsal Corner Cam Vlog Full Vid" - Cmon jB
- https://www.youtube.com/watch?v=TX6ncGlSBKo - CC BY (verified), 21:43, 1080p30, 2025-08-30. **Static corner camera** on a roofed futsal turf; centre circle + lines visible; the uploader says he films "one side of the pitch" for positioning. **7/10**

Also: "This match was so one-sided we had to change the teams. 2x 5v5s" - Wednesday Warriors (https://www.youtube.com/watch?v=uxVrsA7JVAM, 26:14; surfaced under a floorball query but it is indoor 5-a-side football) - **elevated static corner camera** in a sports hall, all court lines, score overlay ("DUVAL 0-3 ALEX"), weekly pickup group: a strong futsal alternate (CC filter; per-video re-check pending). "AFC Yorkies 4-0 AFC Wyke | Full Match unedited | VEO 2 Camera" (https://www.youtube.com/watch?v=Ryt6tidyYaI, CC BY, 1:55:22) uses a Veo AI-panning virtual camera (11v11, worse for homography); Life of Arth / SamsterGK pickup matches are handheld or behind-goal. Dataset: **SoccerTrack** (synchronized fisheye + drone; LGPL-3.0) for the multi-view / auto-director demo.

---

## 4. Ultimate frisbee

### HERO: "Marlow Street vs Pie Wagon | AMUC 2024 division 2" - Australian Flying Disc Association (AFDA)
- https://www.youtube.com/watch?v=gFwXenra7kI - **CC BY (verified)**, 39:17, 1080p30, uploaded 2025-04-04 (game played 19 Oct 2024, Nelson Bay).
- Camera: **elevated, wide, near-static** view from the sideline corner (pole/tower or drone-height), most of the field in frame, faint painted lines; running score overlay (e.g. "Marlow St 7 - Pie Wagon 1").
- Division-2 club ultimate, so amateur play, not elite.
- Calls: catch in end zone (score overlay = ground truth for each point), drop turnovers, out-of-bounds, pulls.
- Weaknesses: lines faint on brown grass; stall count only audible if near the mic; players small at the far end.
- **Showcase score: 8/10**

### Alt: "Ultimate Frisbee: Outdoor Open | Roses 2025" - Roses Live (York vs Lancaster student TV)
- https://www.youtube.com/watch?v=4XwVUHIPkHY - CC BY (verified), 1:34:25, **1080p60**, 2025-05-04.
- Student-broadcast, **multi-camera switched production** (wide sideline + closer angles), score bug, commentary. That makes it a reference for the "auto-director" look, but not raw synced multi-view.
- Chapters: 5:16 match intro, 7:29 opening points, 13:56, 20:11, 26:58, 33:49 "York takes the lead", 39:43, 48:15, 56:30, 1:07:02 match conclusion, 1:21:23 interviews.
- University sport; commentary audio covers stall counts. **7/10**
- Companion: "Ultimate Frisbee: Indoor Mixed | Roses 2025" (https://www.youtube.com/watch?v=I8AWmy3masE, CC BY, 19:31) - sports-hall lines visible.

### Alt: "Montpelier Youth Sports - Ultimate Frisbee vs Champlain Valley Union 5/2/2025" - ORCA Media
- https://www.youtube.com/watch?v=0rmKpobOrpI - CC BY (verified), 1:31:19, 1080p30. Community-TV sideline camera, mostly static, with the physical scoreboard in frame. High-school ultimate. **6/10**

Also: "2021 Club Ultimate Frisbee Cooler Classic: Elevate vs Liquid Hustle" (https://www.youtube.com/watch?v=Vt9gu5KuMqA, 49:49, found via the CC filter but the per-video fetch was bot-blocked, so recheck the license tag) - static sideline tripod, rec club, strong pickup feel. Wikimedia Commons: "Ucniss ultimate-frizbee staff-vs-students.ogv" (CC BY 3.0, 480p, 4:55, very casual) and "Colombia vs USA Disco Volador - World Games Cali 2013" (CC BY-SA 3.0, 720p, 2:17). Pexels "Ultimate frisbee game on a sunny field" (pexels.com/video/32514516, 8 s, 4K60, Pexels License) as B-roll.

---

## 5. Wiffle ball / softball / sandlot baseball

### HERO: "Turn Back The Clocks | Militia vs Carolina OutKast | Slowpitch Softball" - Logan Hawkins
- https://www.youtube.com/watch?v=8i6MPqrGIGg - **CC BY (verified)**, 33:55 (condensed game), **2160p30**, 2026-04-20.
- Camera: **static wide-angle behind the backstop / home plate**: both foul lines, the infield, the batter and the catcher in frame. Adult lower-division (E/Rec) slowpitch tournament, a casual-league story.
- Calls: fair/foul (foul lines visible), catches/fly-outs, strikes and balls (slowpitch arc is easy to track; zone approximate), bat-crack audio for contact detection.
- Condensed = high event density. Same uploader has 5+ more games (Carolina OutKast vs Hellhounds, Bad Intentions, Upstate Jays, all CC BY).
- Weaknesses: fisheye; outfield players small; no wiffle.
- **Showcase score: 8/10**

### Alt (best geometry): "Tallmadge Little League vs Wolfpack 8u travel ball game" - Fastpitch Softball Games
- https://www.youtube.com/watch?v=vdU_pFTLjSE - CC BY (verified), 57:57, 1080p30, 2018-06-06.
- **Elevated static camera directly behind home plate**: batter's boxes, plate, both foul lines and the whole infield visible. The cleanest homography of any bat sport found. 8U girls fastpitch (kids, not adults).
- Calls: strikes/balls (strike zone over the plate is in view), fair/foul, catches, plays at first.
- **8/10**

### Alt (actual wiffle ball): "Season 3 Game 2: Ding Dong Ditchers VS. Slamming Sigmas" - Backyard Wiffleball League
- https://www.youtube.com/watch?v=bWAk4At9ESE - CC BY (verified), 5:06, **1440p60**, 2024-08-05.
- Static camera behind the backyard strike-zone net; edited overlays name events ("Walk", "Two Run Homer!!!", "Solo Homer!!!", outs/innings), which can serve as labels. True backyard casual story.
- Weaknesses: heavy edit overlays, likely music, short. **7/10**
- Other wiffle: "Lugnuts vs Grizzlies | Midwest Wiffle Ball [6-21-17]" (https://www.youtube.com/watch?v=1E0Kee_Zxck, CC BY, 8:31, 1080p60) - static backyard cam with a strike-zone target, but the description lists background music.

Also: "Sandlot Softball - Gerard's Game-Ending Foul Out to the Catcher" (https://www.youtube.com/watch?v=pjKIOkk5dNQ, CC BY, 0:53, 4K30) - a ready-made "foul-ball catch" highlight from a Friday-night rec league; same channel has "Game 2 condensed footage" (1dJTBnkB55g, 18:32). "2021-05-26 Minor Angels at Yankees" (4V5u28PfRJk, CC BY, 2:23:49, Little League, static side cam). License-clean Commons fallback: "Boys Varsity Baseball v. U-32 - MAY 19, 2026" (https://commons.wikimedia.org/wiki/File:Boys_Varsity_Baseball_v._U-32_-_MAY_19,_2026.webm, **CC BY 4.0**, 1080p, 2:04:31, elevated static behind the backstop, HCTV high school). Dataset: BaseballCV amateur game videos (no declared license; see dataset table).

---

## 6. Kickball

### HERO: "Kickball Game 10/19/2016" - channel "C"
- https://www.youtube.com/watch?v=jdsPIY_QU2w - **CC BY (verified)**, 45:39, 1080p30, uploaded 2016-10-31.
- Camera: **static wide-angle (action-cam) mounted on the backstop fence behind home plate** under floodlights; whole diamond, both foul lines and all bases visible. Adult rec-league night game: perfect casual story.
- Calls: fair/foul kicks, catches (fly outs), force outs at bases, pegging (hit-by-ball) and the pitch.
- Weaknesses: night lens flare, small players in the outfield, no description/timestamps; audio unknown.
- **Showcase score: 8/10**

### Alt: Kickball365 "O.P.P. vs Brawndo - Semi Finals - Big Easy Kickball Open" / "Flying V-Jays vs 100 Proof - Finals - Women's BEKO"
- https://www.youtube.com/watch?v=tODBPUgsCT8 (10:22) and https://www.youtube.com/watch?v=4VFZpjoWaRo (12:48) - CC BY (verified), 1080p30, 2017.
- Low camera behind home plate, mostly static, score/inning overlays ("Bottom 3", team scores); competitive adult kickball tournament (New Orleans). **7/10**

Also: "Kick Ball Game Bell Elementary April, 2022" (d887FFj6RQw, CC BY, 43:38, Veo AI camera, kids); "Adult Kickball Alliance Video Highlights - May 20 2016" (V0UM0YEONag, CC BY, 1:38, handheld + music). No Commons/Pexels kickball game footage found.

---

## 7. Tape-ball / backyard cricket

### HERO: "So many Wickets!! | Backyard Cricket" - NCA Cricket AU
- https://www.youtube.com/watch?v=y8POhHKjGlU - **CC BY (verified)**, 4:32, 1080p30, 2024-03-08.
- Camera: **static, from behind the bowler's end looking down a dirt-track "pitch" to real stumps**; batter, bowler and stumps all full-frame. Backyard family game. Edited overlays ("Power Surge", score, "FOUR FOUR FOUR FOUR") act as labels for boundaries and wickets.
- Calls: **bowled** (stumps clearly visible), boundary/four, caught, possibly LBW evidence; "so many wickets" means many dismissal events in under 5 minutes.
- Weaknesses: edited (cuts + overlays), probably music in places; trees partly occlude; no boundary rope (backyard rules).
- Series: Games 1-4 linked in the description (rtVpgUKvzqA, 4u0UP47gOuQ, E7aGA4ZZ5PE, KmjXHvVoEKY; license not individually checked).
- **Showcase score: 8/10**

### Alt (literal tape-ball, real drama): "12 balls need 24 runs = tape ball cricket match" - MCDA Sport
- https://www.youtube.com/watch?v=NdysRz0ywFc - CC BY (verified), 8:18, **720p30**, 2021-03-27.
- Camera roughly fixed behind the bowler's end (slight offset), night floodlit dirt ground, matting strip, stumps visible; burned-in chase graphic ("Runs 14 Balls 6"). Tape-ball run chase in Pakistan with crowd noise: a built-in Play-of-the-Game arc.
- Calls: bowled, run out at the striker's end, boundaries (crowd reaction), last-over chase.
- Weaknesses: 720p, night noise, some camera drift. **7/10**

### Alt (backyard, very static): "Back yard cricket match 2 ..." / "Backyard cricket in OVERCAST conditions" - Cricket at dB's
- https://www.youtube.com/watch?v=30DYzg21VSw (4:16) and https://www.youtube.com/watch?v=reDRND0234Y (1:18) - CC BY (verified), 1080p30, 2025-04.
- Locked-off tripod behind the bowler on a driveway pitch, score overlay ("RONAN 3 - DB 13*"). Father-and-son backyard cricket. Small far-end target; stumps are improvised. **6/10**

### License-clean (Devpost-OK, share-alike): Wikimedia Commons "Old Markonians CC v Bucks Cricket select XI at Bayford, Herts, England 199/356"
- https://commons.wikimedia.org/wiki/File:Old_Markonians_CC_v_Bucks_Cricket_select_XI_at_Bayford,_Herts,_England_199.webm (2:22) and ..._356.webm (1:57) - **CC BY-SA 4.0** (Acabashi), 1080p, filmed 7 May 2026, mid-week 40-over club match.
- Close static side-on view of the striker's end: batter, keeper, stumps, slip and umpire all in frame. Good for bowled/LBW evidence and bat-on-ball audio. Not a pickup game, and the field of view is too narrow for boundaries. **6/10**

Also: "Exciting Cricket Match - Rushton Cricket Club" (https://www.youtube.com/watch?v=3EK2WIQm0ZU, CC BY, 23:06, 1080p **24 fps**, static boundary camera of a 45-over club match with "4" graphics); Pexels has 24+ cricket match clips (e.g. 30172302 "Casual cricket match in lush green park", 33907672 aerial) as Pexels-licensed B-roll. No CC LBW-review style footage found; LBW will need our own clip or a staged one.

---

## 8. Dodgeball

### HERO: "NUS IFG Dodgeball 2019 UTSH (1240hrs onwards)" - Roman G.
- https://www.youtube.com/watch?v=SJP8ke6de2s - **CC BY (verified)**, 4:49:32, 1080p30, 2019-09-16.
- Camera: **locked-off tripod, elevated in the stands**, whole court with lines and the centre line visible (identical framing in all sampled frames). National University of Singapore inter-faculty games: casual student teams, real tournament stakes.
- Chapters: 22:00 Arts v Law, 52:00 Eng v Med, 1:22:00 SoC v Law, 1:54:00 Arts v Med, 2:34:00 Biz v SoC (semi), 3:03:00 Arts v Sci (semi), 3:40:00 Biz v Sci (3rd/4th), **4:15:00 Arts v SoC (final)** - use the final for the Play of the Game.
- Calls: hit vs catch (catch = thrower out), out-of-bounds dodging, ball count; head shots are visible but small at this distance.
- Audio: gym audio (ball smacks, cheering); uploader notes audio drifts ~+2 s after the 2.5 h mark.
- Weaknesses: players fairly small in frame; spectators along one side.
- **Showcase score: 8/10**

### Alt (catch vs hit labels): "CATCHES OF THE YEAR" - College Dodgeball (NCDA)
- https://www.youtube.com/watch?v=KA9uDJnjwKs - 3:35, 2019-20 season. Low end-court tournament cameras with score bug; every clip is a catch, so it is a labelled set for the hit-vs-catch classifier. **7/10**
- Same channel: full matches with static end-court cams, e.g. "BGSU vs. Maryland | Dodgeball Full Match | 2025 Pink Out" (https://www.youtube.com/watch?v=kEDhakH7RUA, 1:11:25) and "HIGHLIGHTS: Dodgeball National Title: Miami vs. Cincinnati" (https://www.youtube.com/watch?v=JvUUoAwBELI, 13:48, elevated wide arena view).
- Note: these College Dodgeball / WDF videos came from the CC-filtered search, but the per-video license re-check was bot-blocked. Confirm the "Creative Commons" line on the watch page before use.

### License-clean (Devpost-OK): Wikimedia Commons "Dodgeball game at the University of Alberta"
- https://commons.wikimedia.org/wiki/File:Dodgeball_game_at_the_University_of_Alberta.webm - **CC BY-SA 4.0** (Sdkb), 0:41, 1920x1080. Lister residence rec-league game; elevated corner view of a gym court with all lines; a real casual game. Short. **6/10**
- Also on Commons: "8th Annual International Dodgeball Tournament of CHAMPIONS! Hamline 2014 8" (CC BY 3.0, 3:08, 1080p) and "2013 GitHub Dodgeball Tournament for Charity" (CC BY 3.0, 1:50, recap edit with music).
- "World Dodgeball Federation - 2015 Women's Semi - Canada vs Australia" (https://www.youtube.com/watch?v=uxDs-Br61AQ, 44:52) - static wide-angle cam behind the side net (CC filter; re-check pending).

---

## 9. Street / floor / roller / ball hockey

> License status for every YouTube link in this section: **CC filter; re-check** (it came from the Creative-Commons-filtered search, but the per-video confirmation was bot-blocked). Resolution/fps not confirmed.

### HERO: "TUESDAY NIGHT BALL HOCKEY PICKUP: BGC - Saint John, NB | April 14, 2026" - Beauty Roll Media
- https://www.youtube.com/watch?v=narcxP96V6o - 7:03, 2026. Found via the CC-filtered search; per-video license re-check bot-blocked (confirm the CC line on the watch page).
- Camera: **fixed high-angle camera above and behind one net**: the goal mouth, crease paint, goalie and shooters in full view, with "GOAL" pop-up overlays and a score bug. Literally a pickup game in a gym.
- Calls: **hockey goal** (ball crosses the goal line, with the overlay as ground truth), crease violations, saves.
- Weakness: only one end visible; overlays to mask; resolution not confirmed.
- **Showcase score: 8/10**

### Alt: JayChirps "McNabb Ball Hockey" weekly pickup highlights
- e.g. "2025, Nov 15 | McNabb Ball Hockey | GM1 Dark | Dave" https://www.youtube.com/watch?v=bry9zEoGBLw (7:35) and "Non Stop Action | Pickup Ball Hockey Highlights" https://www.youtube.com/watch?v=zbNg-fke_M4 (4:12). Same behind-net elevated goal-cam style, gym floor lines visible, weekly drop-in game; dozens of episodes on the channel (CC filter; re-check pending). **7/10**

### Alt (whole rink): "Outdoor Roller Hockey" - Dustin
- https://www.youtube.com/watch?v=cvDju-D2t4s - 1:42:08. **Static camera over the boards** of a covered outdoor roller rink, centre circle and lines visible, inline skaters ("just some buds ripping it up"). The full-length raw game suits homography and long-form analysis; goals at the far end are small. (CC filter; re-check pending.) **7/10**

License-clean: Wikimedia Commons "Women European League Roller Hockey 2017 - Ris Orangis vs Rubi" clips (**CC0**, 1080p, e.g. ..._61.ogv 5:04 = penalty-shot sequence; others 14-41 s) - elevated arena view, rink-hockey (quad skates), semi-pro. "Breda in Beeld - Urban Hockey Tour" (CC BY 3.0, 2:06, street hockey with kids, edited). Floorball: no strong CC amateur static footage found (FISU uploads are broadcast highlights).

---

## 10. Touch rugby / tag rugby

> License status for every YouTube link in this section: **CC filter; re-check** (it came from the Creative-Commons-filtered search, but the per-video confirmation was bot-blocked). Resolution/fps not confirmed.

### HERO: "20140510 HoustonTournament Game09 - Dallas vs. HARC" - Dallas Touch
- https://www.youtube.com/watch?v=_vfK4y6bDpg - 18:19, 2014. Found via the CC-filtered search; per-video re-check bot-blocked.
- Camera: sideline tripod (follows play with pans/zooms), grass park pitch, full-body players. US amateur touch-rugby tournament game, so the touch count is visible on every phase.
- Calls: touch count (1-6), touchdown over the line, rollball restarts; offside distance is hard without lines.
- Weaknesses: older (likely 720p or lower), panning, field lines barely visible. The best of a thin category.
- Same channel: "20140510 HoustonTournament Game08" (nJxWtTuB0KU, 14:26) and "DallasTouch20141102 - Sunday pickup game. Everyone is welcome." (x-N76MvSdZw, 4:15) for the pickup story.
- **Showcase score: 6/10**

### Alt (casual story): "Tag Rugby, Hackney, LONDON, GB" - LONDON WALKS 4K
- https://www.youtube.com/watch?v=eZ8dZxSzUJ0 - 6:56, 4K. Mixed social tag-rugby session in a London park with tags on shorts and cone markers; a walking-tour camera that is handheld/ground level. Strong "pickup" vibe, weak geometry. **5/10**

### License-clean: Wikimedia Commons "2017-Interfaculty-Touch-Rugby-Tournament 1080p-Nueva Zelanda"
- https://commons.wikimedia.org/wiki/File:2017-Interfaculty-Touch-Rugby-Tournament_1080p-Nueva_Zelanda.webm - **CC BY 2.5** (University of Auckland), 0:29, 1080p; also on YouTube as CXWyq9hcZTg. Low, close, edited promo of a casual student touch tournament; good B-roll, not refereeable. **5/10**

Also: "NZ Touch Counties vs Canterbury Open Mens 2010" (dia1ejtYAe0, 8:15, elite final, sideline tripod, SD .VOB rip). The MĀORI+ NZ secondary-schools touch highlights are broadcast edits. **Recommendation: film touch rugby yourselves**; public footage is the weakest of all 11 sports.

---

## 11. Team handball

> License status for every YouTube link in this section: **CC filter; re-check** (it came from the Creative-Commons-filtered search, but the per-video confirmation was bot-blocked). Resolution/fps not confirmed.

### HERO: "Round 4 NSWHA League 2026 - Sydney Uni vs UNSW" - NSW Handball Live Stream
- https://www.youtube.com/watch?v=vo8hQfV9PAY - 1:09:03, 2026. Found via the CC-filtered search; per-video re-check bot-blocked.
- Camera: **fixed, elevated corner camera** in a multi-sport hall; goal, **6 m goal-area line**, 9 m line and most of the court visible; referee visible. University men's club league (amateur).
- Calls: **goal-area (crease) violation** (feet vs 6 m line), goals, steps (travel), restarts.
- Weaknesses: multi-sport floor has many overlapping lines (handball lines must be chosen at tap time); far goal small.
- **Showcase score: 8/10**

### Alt: USATH College Nationals 2026 (USA Team Handball, college club teams)
- "North Carolina vs West Point Black" https://www.youtube.com/watch?v=oFaezxqGAa0 (52:51, women) and "Case Western vs Olin CoE" https://www.youtube.com/watch?v=_HeH6kA97Jo (1:02:17, men's D2 semifinal).
- Elevated end/corner camera covering a whole basketball-gym court with taped handball lines and portable goals; score + game-clock overlay (goal ground truth). Beginners-to-club level play: very "casual". **8/10** (tie with the hero; pick by which camera shows the 6 m line more clearly)

### Alt: "5th Place match | 2025 Men's Australian Handball Championship" - NSW Handball Live Stream
- https://www.youtube.com/watch?v=oY--X7ZylLA - 1:27:41; static wide hall camera with the venue scoreboard in frame. **7/10**

License-clean: **TeamTrack handball** (MIT, Kaggle) - static 6K fisheye side view of handball (30 min) with player boxes. The best fully-licensed handball source. Commons: "Handball match between home team Bosna and Lokomotiva from Brcko in Mladost hall in Visoko" (CC BY-SA 4.0, 0:24, 1080p, elevated arena view, Bosnian league). Excluded: "Handball World" channel (pro EHF/LNH broadcasts re-uploaded with a CC tag, likely not the rights holder).

---

## Datasets and stock libraries (cross-sport)

| Source | Sports | What it gives Trophy | License (verified) | Size / access | Verdict |
|---|---|---|---|---|---|
| **TeamTrack** (Nagoya Univ., CVPRW 2024) - https://www.kaggle.com/datasets/atomscott/teamtrack | soccer, basketball, **handball** | Static side-view fisheye (Z CAM E2, 6K/8K) for all three sports; basketball also has drone side view + drone top view (multi-view); handball = single static side-view fisheye (full-pitch by design; 6 m line visibility not checked). MOT boxes for every player. | **MIT** (Kaggle dataset license field); project site CC BY-SA 4.0 | 17.7 GB on Kaggle (also Google Drive) | Best license-clean static-camera source for handball and basketball multi-view. Fisheye needs undistort before homography. No audio guaranteed. |
| **SoccerTrack** (same group) - https://www.kaggle.com/datasets/atomscott/soccertrack | soccer | 8K wide-view fisheye (static) + DJI Mavic 3 top-view drone, time-synced, with GNSS player positions. University soccer. | **LGPL-3.0** (Kaggle license field) | 6.8 GB | Gold for multi-view / "auto-director" demo: two synchronized angles of the same play. Full-pitch 11v11, not small-sided. |
| **BaseballCV `international_amateur_baseball_game_videos`** - https://huggingface.co/datasets/dyland222/international_amateur_baseball_game_videos | baseball | 206 mp4 files (README says 205) of amateur games from the Alfredo Harp Helu Baseball Academy (Mexico). | **No license declared** on the HF dataset card (card has no license field / no README). BaseballCV code is AGPL-3.0 (dual-licensed). Treat as research/demo-only; ask the maintainers before using in the Devpost video. | 387.5 GB total; files 125 MB - 3.4 GB each | Huge but unvetted; pick 1-2 files after previewing. Do not bulk-download. |
| **SportsMOT** - https://github.com/MCG-NJU/SportsMOT | basketball, soccer, volleyball | Broadcast clips with MOT boxes | **CC BY-NC 4.0** | (size not checked) | Research-only (NC). Broadcast/panning cameras = poor fit for homography. Skip for demo. |
| **DeepSportradar instance segmentation** - https://www.kaggle.com/datasets/gabrielvanzandycke/deepsport-dataset | basketball | Still frames from fixed, calibrated Keemotion arena cameras (calibration included) | **CC BY-NC-ND 4.0** | images, not video | Useful for testing court homography only; NC-ND. |
| **roboflow/sports** - https://github.com/roboflow/sports | soccer, basketball | Code + Roboflow Universe datasets (player/ball/pitch keypoints, basketball court keypoints). Demo soccer videos come from the Kaggle DFL Bundesliga shootout (tactical broadcast cam). | Repo **MIT**; demo video license not stated; Universe datasets vary per project | small | Use the court/pitch keypoint models, not the videos. |
| **SoccerNet (incl. MV-Fouls multi-view)** | soccer | Pro broadcast, multi-view foul clips | NDA | large | Not usable for the public demo. |
| **APIDIS basketball** (UCLouvain, FP7) | basketball | 7 calibrated fixed IP cameras around an amateur basketball game (approx. synced, 22-25 fps) with action annotations (throw, violation, foul) | No public license found; research distribution | - | Historically the canonical multi-view amateur basketball set; access uncertain in 2026. Not pursued. |
| **Pexels** - pexels.com/videos | basketball, soccer, cricket (many), ultimate | 4K stock, 8-30 s, mostly drone/handheld. e.g. "Ultimate frisbee game on a sunny field" (pexels.com/video/32514516, 8 s, 3840x2160, 59.94 fps, by Usman AbdulrasheedGambo); aerial basketball court with players (pexels.com/video/27456775); ~24+ cricket match clips (e.g. 30172302 casual park match, 33907672 aerial match). | **Pexels License** (free, commercial OK, no attribution required) | small | License-clean B-roll for the Devpost video intro; too short for referee calls. No dodgeball/kickball/handball game footage found. |
| **Mixkit** - mixkit.co/free-stock-video/basketball/ | basketball | 165 basketball clips incl. "Aerial view of a blue and purple basketball court" (#1216), 1v1 outdoor games | **Mixkit License** (free) | small | B-roll only. |

---

## Files

- Search scripts: `ch13/poss/poss_flat.py` (CC-filtered search), `ch13/poss/poss_slow.py` (per-video metadata), `ch13/poss/poss_commons.py` (Commons API).
- Raw data: `ch13/poss/yt_flat.json` (all ~1,300 CC search hits by sport), `ch13/poss/full.json` (verified per-video metadata), `ch13/poss/commons.json` (Commons hits with license/size).
- Contact sheets: `ch13/thumbs/poss/sheet_*.jpg`.
