# Trophy clip library: public footage for every sport

*2026-10-23. Use this when the team can't film a sport itself. Clips were picked for how many Trophy features they exercise:*
- *a fixed camera with the court or target visible (homography),*
- *several synced angles (3D, auto-director),*
- *audio,*
- *full-body players (feet and wrists),*
- *visible close calls and violations,*
- *a "Play of the Game" moment,*
- *and a license that allows reuse.*

*Full candidate lists (2–4 per sport, with weaknesses and alternatives) are in [research notes](../research/), in the three `clips-*-family-full-list.md` files.*

**How it was checked:**
- Licenses were read from each YouTube watch page or the Commons file page.
- Camera angles were checked from YouTube's auto-generated preview frames. No videos were downloaded.
- **Not checked:** whether ball sounds are actually audible. Listen before relying on a clip for the bounce, rim or chain classifiers.
- ✓ = CC BY confirmed on the page.
- † = it came up in YouTube's Creative Commons search filter, but the page check was rate-limited. Open the page and confirm the "Creative Commons Attribution" line before using it in the demo video.

---

## 1. License rules

Use any footage whose permissions cover the intended use; CC BY / CC0 are convenient defaults. Check the actual source and applicable terms before relying on this dated inventory. See [media guidance](../rules-compliance.md).

| License or source | Use guidance |
|---|---|
| **CC BY / CC0** | Reuse within the terms; preserve required credits and any change notices in `credits.json` and exports |
| **CC BY-SA** | Reuse when applicable attribution and share-alike obligations can be met |
| **Pexels / Mixkit / Pixabay** | Check the asset's current license and intended use; often useful for B-roll |
| **Research / non-commercial datasets** | Verify each dataset's evaluation, demo, redistribution and commercial-use permissions separately |
| **Standard YouTube license** | Do not infer reuse permission from availability or attribution; obtain permission where needed |
| **Re-uploaded broadcasts tagged CC** | Verify the uploader can grant the rights before reuse |

**Etiquette:** one uploader (Rob Alexander, soccer) asks to be told if anyone filmed doesn't want to be public. **Anonymize or blur non-consenting people in shared clips**, which is also a chance to show off Trophy's privacy blur.

---

## 2. Hero clip per sport

The score (out of 10) is how many Trophy features the clip exercises. The last column marks sports to film yourselves or to stage.

### Flight family
| Sport | Hero clip | License | Specs | Camera | What it shows off | Score | Film? |
|---|---|---|---|---|---|---|---|
| **Table tennis** | [BenSucksAtPingPong club match](https://www.youtube.com/watch?v=7maQFqJ3XQ0) | ✓ CC BY | 4K60, 9:35 | Tripod at the table corner | **A disputed edge ball at 8:36** (the challenge-replay moment), games chaptered, long rallies | 9 | Film multi-view live anyway (it's the live hero) |
| **Pickleball** | [BT Pickleball rec doubles](https://www.youtube.com/watch?v=QhLECLlXU3c) | ✓ CC BY | 4K60, 8:26 | Corner tripod | **Both kitchens + players' feet visible** (kitchen foot fault), score overlay = ground truth, near-line balls | 9 | Optional |
| **Badminton** | [Tokyo club, raw footage](https://www.youtube.com/watch?v=ShrdcaZMdS0) | ✓ CC BY | 1440p24, 44:39 | Wide static corner | 5 games chaptered, landing in/out, a let at 42:22. Weak points: 24 fps and fisheye | 8 | Optional |
| **Tennis** (single view) | [USTA 3.5 doubles league](https://www.youtube.com/watch?v=JReOUveKesY) | ✓ CC BY | 1080p60, 26 min | Behind the baseline corner | Close line calls, double bounces, service box | 8 | — |
| **Tennis** (multi-view) | [CalTennis dataset](https://huggingface.co/datasets/demalenk/caltennis) | CC BY-NC | 2–6 synced cameras at 60 Hz, **calibrated** | Fixed court cameras | **The only clean multi-view, calibrated racket-sport source**: real 3D triangulation, the auto-director and a 3D challenge replay | 9 | — (live demo only) |
| **Volleyball** (indoor) | [Almost Volleyball amateur set](https://www.youtube.com/watch?v=kVpO4ypzPYU) | ✓ CC BY | 1080p60, 15 min | Static, elevated | A full set with no edits: in/out, touch counts, net | 9 | — |
| **Volleyball** (beach) | [Amateur doubles](https://www.youtube.com/watch?v=Jz9-F1OW_rQ) | ✓ CC BY | 4K60, 9:23 | Static, behind the baseline | Beach in/out, touch counts | 8 | — |
| **Roundnet** | [Cheung Roundnet college pool play](https://www.youtube.com/watch?v=kgSM2WkQlek) | ✓ CC BY | 1080p60 | Static wide | 3-touch limit, serves. The **net is small in frame**, so crop for rim calls | 8 | **Yes**, a close phone over the net for rim vs. pocket |
| **Padel** | [Padel Match Point, 3.5 amateurs](https://www.youtube.com/watch?v=GKWNVYeEAlE) | ✓ CC BY | 1080p60, 44 min | Behind the back glass | Wall bounces, double bounce | 8 | — |
| **Squash** | [Match from above the back wall](https://www.youtube.com/watch?v=uDzznrSM5tY) | ✓ CC BY | 1080p60, 15 min | High above the back wall | Whole floor, front wall and tin in view: tin/out calls | 8 | — |
| Racquetball | [Match](https://www.youtube.com/watch?v=EckAW5V1wv0) | ✓ CC BY | 1080p60 | Fixed | Front-wall and short-serve calls | 7 | — |
| **Four square** | [Taped court game](https://www.youtube.com/watch?v=lzlcWsl4Voc) | Standard license | 1080p30, 22 min | Static, elevated corner | Out, wrong square, double bounce. The CC alternative is [GYOKq-MLQa0](https://www.youtube.com/watch?v=GYOKq-MLQa0) (480p, 74 s) | 7 | **Yes**, tape it out at the venue |
| **Cup pong** | [bpong.at tournament](https://www.youtube.com/watch?v=1Mc6mAcON5c) | ✓ CC BY | 1080p25 | Side-on, full table | Ball in cup, re-racks. The hall is noisy | 7 | **Yes** (water cups at the table) |

**Other multi-view sources:**
- **Padel:** [PadelVic](https://github.com/UPC-ViRVIG/PadelVic) has 4 cameras, two of them court-level phones at 1080p60. Research use only.
- **Volleyball:** Paul Sander's 360° rec-league videos (CC BY) could be reprojected into fake multiple angles.
- **Table tennis:** [OpenTTGames](https://lab.osai.ai/) has 120 fps footage with bounce and net labels, which makes good accuracy ground truth. CC BY-NC.

### Possession family
| Sport | Hero clip | License | Specs | Camera | What it shows off | Score | Film? |
|---|---|---|---|---|---|---|---|
| **Basketball** | [JaiArtHub outdoor half-court](https://www.youtube.com/watch?v=2NxcgKW7xFM) | ✓ CC BY | 4K60, 32:10 | **Tripod facing one hoop** | 10 games chaptered. The **score overlay is make/miss ground truth**. Also out of bounds, travels, double dribbles, fouls (evidence mode) | 9 | Optional |
| **Two-hand touch / flag** | ["Flag Football Coaching" channel, e.g. Illegal Snap](https://www.youtube.com/watch?v=V6nJyuKNstQ), plus 7 more clips | ✓ CC BY | 1080p, 15–35 s each | Static, elevated, wide | **Each clip is a labelled call**: the coach circles and names the foul (snap, flag pull, flag guarding, pass interference). Free ground truth for accuracy | 9 | **Yes**, for real two-hand touch + a staged **5-Mississippi rush** |
| **Soccer / futsal** | [Rob Alexander co-ed pickup, full game](https://www.youtube.com/watch?v=1vZ7AToa2qY) | ✓ CC BY | 4K60, 1:41:46 | Sideline tripod with a wide lens (needs undistortion) | Pop-up goals, ball out, restarts. The alternative [s6EMb1PXuHI](https://www.youtube.com/watch?v=s6EMb1PXuHI) has 12 goal timestamps | 9 | — |
| **Ultimate** | [AFDA AMUC 2024 division 2](https://www.youtube.com/watch?v=gFwXenra7kI) | ✓ CC BY | 1080p, 39:17 | Elevated, wide, with a score overlay | Drop turnovers, goals, stall counts (timer) | 8 | — |
| **Wiffle / softball** | [Slowpitch, Militia vs. Carolina OutKast](https://www.youtube.com/watch?v=8i6MPqrGIGg) | ✓ CC BY | 4K, 33:55 (condensed) | Static, behind the backstop | Fair/foul, catches, count bookkeeping. The best strike-zone angle is the [8U game](https://www.youtube.com/watch?v=vdU_pFTLjSE); actual wiffle is [bWAk4At9ESE](https://www.youtube.com/watch?v=bWAk4At9ESE) | 8 | Optional (cardboard strike target) |
| **Kickball** | [Adult night league](https://www.youtube.com/watch?v=jdsPIY_QU2w) | ✓ CC BY | 1080p, 45:39 | Action cam on the backstop | Whole diamond: fair/foul, force outs | 8 | — |
| **Cricket** | [NCA backyard](https://www.youtube.com/watch?v=y8POhHKjGlU) | ✓ CC BY | 1080p, 4:32 | Behind the bowler, real stumps | Bowled, boundary-four overlays. Tape-ball alternative: [NdysRz0ywFc](https://www.youtube.com/watch?v=NdysRz0ywFc) (720p) | 8 | Stage an **LBW** if you want that call |
| **Dodgeball** | [NUS inter-faculty games](https://www.youtube.com/watch?v=SJP8ke6de2s) | ✓ CC BY | 1080p, 4:49:32 | **Locked-off, elevated, full court** | Hits vs. catches, line crossings. **The final starts at 4:15:00** | 8 | Optional (foam balls, live) |
| **Street / ball hockey** | [Tuesday night pickup](https://www.youtube.com/watch?v=narcxP96V6o) | † confirm | 7:03 | Fixed, above the net | Goals, with GOAL overlays as ground truth | 8 | — |
| **Touch rugby** | [Dallas Touch](https://www.youtube.com/watch?v=_vfK4y6bDpg) | † confirm | 18:19 | Sideline tripod that pans (weak) | Touch count | 6 | **Yes** |
| **Team handball** | [NSW league, Sydney Uni vs. UNSW](https://www.youtube.com/watch?v=vo8hQfV9PAY) | † confirm | 1:09:03 | Fixed, elevated corner, 6 m line visible | Goals, goal-area violations | 8 | — |

**Multi-view sources for team sports:**
- **[TeamTrack](https://www.kaggle.com/datasets/atomscott/teamtrack)** (MIT, 17.7 GB): basketball from **two side views plus a drone top view**. It also has a static handball view. **Best for showing the 3D replay and auto-director on a team sport.**
- **[SoccerTrack](https://www.kaggle.com/datasets/atomscott/soccertrack)** (LGPL-3.0, 6.8 GB): wide fisheye plus drone, time-synced.

**Candidate licenses for shared videos (verify terms and participant permissions):** Wikimedia Commons clips under CC BY 4.0 (HCTV high-school baseball and basketball), CC BY-SA 4.0 (University of Alberta dodgeball, Old Markonians club cricket) and CC0 (roller hockey).

**Avoid as a dependency:** the BaseballCV amateur set (206 files, 387 GB, no license on its Hugging Face card). SportsMOT (CC BY-NC) and DeepSport (CC BY-NC-ND) are research only.

### Resting-object family
| Sport | Hero clip | License | Specs | Camera | What it shows off | Score | Film? |
|---|---|---|---|---|---|---|---|
| **Cornhole** | [UKCL "4 bagger to win game"](https://www.youtube.com/watch?v=by5-AKocoho) | ✓ CC BY | 1080p30, 28 s | **Split screen: a fixed board camera plus a player camera**, so two angles | Bag in hole / on board, a **score overlay = ground truth**, and **the 4-bagger as a ready Play of the Game**. A full match with many cancellation rounds: [OmFqxrdGexk](https://www.youtube.com/watch?v=OmFqxrdGexk) (720p) | 8 | Also live (tabletop set) |
| **Mini golf** | [Maroochy River hole 8 ace](https://www.youtube.com/watch?v=IBBQ_bgLVDQ) | ✓ CC BY | 1080p50 | Fixed tripod down the hole | An **ace at about 0:03–0:11**. Alternative: [Bq-4Z6pKyx0](https://www.youtube.com/watch?v=Bq-4Z6pKyx0) (about 15 aces from a camera on the ground) | 7 | Optional (putting mat) |
| **Bowling** | ["Bowling a Full Game Up-Close(r)… (259)"](https://www.youtube.com/watch?v=GjE8aQdeJyI) | ✓ CC BY | 1080p30, 8 min | Fixed at the pin deck (fisheye) | A full game: pin counts, strikes, spares, crash audio. Split call: Commons "4-5-7 spare conversion" (CC BY-SA 4.0) | 8 | — |
| **Darts** | ["501: INSANE Darts Match Highlights"](https://www.youtube.com/watch?v=5i7_m5eStl8) | ✓ CC BY | 1080p60 | Straight-on fixed board camera | Segment scoring, with a **501 score overlay as ground truth**. Alternative: [FNuVp4ZOs6s](https://www.youtube.com/watch?v=FNuVp4ZOs6s) (board + thrower picture-in-picture) | 8 | — (no darts at the venue) |
| **Bocce** | Commons "Bocce being played" | CC BY-SA 3.0 | 1080p, 11 s | Fixed | A clean closest-ball frame. Alternative: [u1jHCDW_8eo](https://www.youtube.com/watch?v=u1jHCDW_8eo) (pétanque club, ✓ CC BY) | 6 | — |
| **Horseshoes** | [ONTV MHPA doubles](https://www.youtube.com/watch?v=b5hwtNIxi9U) | ✓ CC BY | 720p60 | News edit | Shoes at the stake around 0:06–0:10 | 5 | **Yes** |
| **Kan Jam** | [Sly Fox Brewery final](https://www.youtube.com/watch?v=s3l_Uo74q4Y) | † confirm | 4K | Tripod, but the near can is at the frame edge | Crowd audio | 5 | **Yes** |
| **Ladder toss** | ["Ladder Ball" vlog](https://www.youtube.com/watch?v=cEMp2g-lI14) | † confirm | 1080p | Heavily edited | First-to-15 score overlay | 4 | **Yes** |
| **Disc golf putting** | [BDGC / Halo Putting League finale](https://www.youtube.com/watch?v=2Q9PDDK6f3Q) | † confirm | 1080p60 | Indoor league; the camera moves between putters | **Chain audio** (made putt vs. chain-out) | 6 | **Yes** |
| Pool | ["Awesome Break Shot!"](https://www.youtube.com/watch?v=3oDeMi2bjLg) | † confirm | — | Near-overhead, fixed, all 6 pockets | Pocket detection | 7 | — |
| Air hockey | ["Intense Air Hockey Battle!"](https://www.youtube.com/watch?v=zGbfL9Njt3o) | † confirm | 10 min | Fixed side view | Goals | 6 | — |
| Foosball | Commons "Table football.ogv" | CC BY-SA 4.0 | 1080p | Filmed at a hackathon | Goals | 4 | — |

---

## 3. Which clip shows which feature

Most public clips are **single-camera**. They show **single-view mode**: homography, ray–plane bounces, 2D tracking, calls, commentary, the coach and highlights. Only the sources marked ✅ in the 3D and auto-director columns can show triangulation and multi-camera replays.

| Feature | Best clip(s) |
|---|---|
| **Challenge replay with error ellipse** | Table-tennis edge ball at 8:36 (7maQFqJ3XQ0); pickleball near-line balls (QhLECLlXU3c); CalTennis close calls (3D, multi-view) |
| **True 3D triangulation + 3D replay** | CalTennis (tennis), TeamTrack (basketball: two side views + drone), SoccerTrack, PadelVic. Plus **your own multi-phone table tennis at the venue** |
| **Auto-director (pick the best angle per moment)** | TeamTrack basketball, CalTennis, PadelVic, UKCL cornhole split screen |
| **Measured accuracy (free ground truth)** | Score overlays: basketball (2NxcgKW7xFM), pickleball (QhLECLlXU3c), darts (5i7_m5eStl8), cornhole (by5-AKocoho), ultimate, hockey. Labelled fouls: Flag Football Coaching clips. Labelled events: OpenTTGames |
| **Audio classifiers** (bounce, rim, chains, pins, bag in hole) | Bowling pin deck (GjE8aQdeJyI), disc golf chains (2Q9PDDK6f3Q), cornhole. **Listen first**, and film your own rim/edge sounds |
| **Kitchen foot fault** | QhLECLlXU3c (feet visible at both kitchens) |
| **Two-hand touch, snap, rush count** | Flag Football Coaching clips for snaps and flag pulls. **Film two-hand touch and the 5-Mississippi rush yourselves** |
| **Evidence mode (fouls)** | Basketball pickup (2NxcgKW7xFM), pass-interference clips from the Flag Football Coaching channel |
| **Play of the Game / trophy clip** | Cornhole 4-bagger (by5-AKocoho), mini-golf ace (IBBQ_bgLVDQ), bowling strikes (GjE8aQdeJyI), dodgeball final (SJP8ke6de2s, from 4:15:00) |
| **Privacy blur** | Rob Alexander soccer pickup (lots of bystanders) |

---

## 4. What to film yourselves anyway

Public footage is weak or missing for:
- **Multi-phone views of the live sports:** table tennis, pickleball, badminton, roundnet, four square, cup pong.
- **Two-hand touch** (real touches) and **the 5-Mississippi rush**.
- **Touch rugby.**
- **Roundnet rim close-ups.**
- **Horseshoes, Kan Jam, ladder toss, disc golf putting.**
- **A staged LBW** if you want that call.

Film them with the Trophy PWA whenever useful, with participant permission; this also validates capture.

---

## 5. Getting the clips into the pipeline

1. **Download on suitable local or cloud compute.** Run `yt-dlp -f "bv*[height<=1080]+ba/b" --download-sections "*START-END"` for just the segments you need (for example `*8:20-8:50` for the edge ball). This avoids a single residential IP getting rate-limited, which happened during the research. Download Commons files directly, and datasets from Hugging Face or Kaggle.
2. Store large/private media in **ignored local storage or access-controlled object storage** as `clips/<sport>/<id>_<start>-<end>.mp4`, plus a sidecar JSON with the source URL, license, creator, segment, the calls you expect at each timestamp (ground truth), and camera notes.
3. **Calibrate once per clip**: tap the court corners on the first frame, and store the homography or PnP pose in the sidecar.
4. Play each clip through the same ingest path as a phone, so the pipeline treats it like a live camera stream. That gives the sport wall's "VERIFIED on public footage" badge and an accuracy score from the sidecar's ground truth.
5. Generate `credits.json`, and from it an end-slide credit for every CC BY clip used in the video.
6. **Before using any † clip in the demo video**, confirm its license line on the watch page.
