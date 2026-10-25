# Multi-angle table tennis footage (2026-10-24)

*2026-10-25 update: TT3D game_00 (both views + 3D tracks) and the 2015 Edmonton final (side 720p60 + overhead 720p30) are downloaded into `data/local/clips/library/` and built into dashboard presets (D-42, `services/gateway/scripts/build_library.py`).*

*Supersedes the "no public synchronized multi-view TT video found" line in `clips-flight-family-full-list.md`. Licenses and formats were read with `yt-dlp --print` (YouTube) and WebDAV/figshare APIs (datasets) on 2026-10-24. Nothing was downloaded.*

## A. Same match, several continuous angles (YouTube, standard license)

All from the Edmonton Table Tennis Club uploader (channel UCRvg0UedoV9hl4vg0Qd6Pfw, "Los Pepinillos" / Robert Trudell). Fixed cameras, full matches, no cuts. **Standard YouTube license**: ask the uploader before using in the demo video; fine for internal development only if permission is obtained (see `docs/rules-compliance.md`).

| Match | Angle | Video | Format | Length |
|---|---|---|---|---|
| 2015 Edmonton Open final (Kenny Li vs Ioulia Degtiar, 2015-09-06) | Side | D-FHYCRTdEc | 1080p60 | 20:00 |
| | Overhead | YSzOgrITjJI | 720p30 | 17:24 |
| | Corner #1 | 3QCJo_Q647Q | 720p30 | 17:41 |
| 2016 Edmonton Open final (Yongjun Duan vs Bryan Ho, 2016-09-04; GoPro Hero4) | Main | c5WpNhoYclw | 1080p30 | 27:23 |
| | Corner | ygp9MfltJEY | 1080p30 | 25:07 |
| | Corner 2 | lG_dvP8D1TQ | 720p30 | 26:29 |
| Christophersen vs Potaychuk, game 2 (2011) | Righty / Lefty camera | J-gXqOJFTbw / zI_l4hNx-3I | 480p30 | ~4:40 each |

Notes: the angles start and stop at different times (durations differ), so sync by audio (ball hits) or a visible event. Mixed fps (60 vs 30) means frame-level sync only at 30 Hz.

Other pairs found (also standard license, unverified sync):
- **Keshet BB, Israel Championship, Keshet vs Ashkenazi (2026-05/06):** main `-gi5MfSY9JY` 1080p59 24:24; "angle 2" `9U6imfZzRVA` 2160p30 17:50.
- **Tony N, "joung vs kevbob" (Jan 2021):** `VtrzLtOsLIU` 1080p30 8:33; "Angle 2" `nW_9bpDO2Ys` 1080p30 7:48 (titles carry different dates; check it is the same game).
- **Latvian TT Federation (LGTF):** multi-hour tournament streams labelled Camera 1/2/3 per day (e.g. Latvian Open 2026 final day: `arEmhXwlWko` 1080p60 and `hKSHQrr-2fQ` 1080p30, ~3.5 h each). Likely one camera per table, not two angles of one table: verify before relying on it.

## B. Research datasets with two calibrated views of the same rallies

### TT3D raw dataset (Gossard & Ziegler, Uni Tübingen, CVPRW 2025)
- Share: `https://cloud.cs.uni-tuebingen.de/index.php/s/SCKq85JZEmKoC6J` (Nextcloud; WebDAV works with user `SCKq85JZEmKoC6J`, empty password). Project page: https://cogsys-tuebingen.github.io/tt3d/ ; code MIT at github.com/cogsys-tuebingen/tt3d. **Dataset license not stated**: ask the authors before anything beyond evaluation.
- 3 recordings (`warmup` 33 rallies, `game_00` 72, `game_01` 74), each **split into per-rally clips (~6 s)** in two fixed views: `side/` (1080p50) and `oblique/` (1080p60). Per-recording camera pose yaml (`rvec`, `tvec`, `f`) in each view folder.
- `3d_tracking/<game>/<rally>.csv`: 200 Hz triangulated ball positions (`Frame,Timestamp,X,Y,Z`, table-centred frame, X short side, Y long side, Z up), with gaps where tracking lost the ball.
- Total ≈ 650 MB. Good for: measured 2D→3D accuracy against ground truth, a two-view challenge replay. Not a continuous game (rallies only).

### Open University multi-view table tennis sequences (Wong, Myint, Dooley, Hopgood)
- figshare 25118078, **CC BY-NC 4.0**: 3 multi-view sequences from local league matches, up to 4 Casio EX-F1 high-speed cameras, with human-labelled ball positions. Files on the record are the ground-truth zips only (FullTable 35.8 MB, HalfTable 8.4 MB, ITTF 11.5 MB); the videos are provided on request for non-commercial research (contact via the record / Patrick Wong). Related: figshare 7746203 (tracking-results video, CC BY 4.0, 85.6 MB).

## C. Still single-view (for completeness)
OpenTTGames (CC BY-NC-SA, 120 fps side view), TT4D (monocular reconstructions), "1000 Rallies" (event cameras, not released). The CC BY hero clip remains 7maQFqJ3XQ0 (single corner view).

## Recommendation
For a two-angle demo on public footage, the **2015 Edmonton final** is the best pair (side 1080p60 + overhead 720p30 of the same full match). Email the uploader for permission first. For measured 3D accuracy, use **TT3D raw** (two views + 200 Hz ground truth) and ask the authors about the license.
