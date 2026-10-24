# Replay (subatomic-hamster/replay) inventory, and what Trophy can take from it

*Compiled 2026-10-23 from the GitHub repo at commit `2db92c0` (main, pushed 2026-10-23 17:15 UTC): README, HANDOFF.md, `docs/*`, `courtcam/*`, `services/*`, `render/*`, `scripts/eval_*`, `infra/*`, `alexa/*`, and the GitHub API. I read the files but ran nothing. Every number below comes from Replay's own progress, decision and evidence docs. None of them was re-measured here.*

Trophy references are to `Cal Hacks 13 - Trophy build plan.md`: F1–F18, §6 "Sport wall" (S6 below), and F19 (rulebooks with Moss).

---

## 0. Provenance at a glance (read §6 Risks before reusing anything)

| Fact | Value |
|---|---|
| Repo | `github.com/subatomic-hamster/replay`, MIT (LICENSE added in the last commit, 2026-10-23 17:13 UTC), 0 stars, 0 forks |
| Created / first commit | 2026-09-22 04:06 UTC ("Initial commit", Subham Dash) |
| Commits | 146, all by `subatomic-hamster` (author name Subham Dash) |
| Last push | 2026-10-23 17:15 UTC, the day Cal Hacks hacking opens. The last code commit was `d87fec7` at 09:23 UTC. After it came only README and LICENSE changes |
| Purpose | Amazon Developer Hackathon entry (Fire TV track plus the AWS Builder and Open Source mini-challenges), submitted 2026-10-23 |
| courtcam | Published separately at `github.com/subatomic-hamster/courtcam`: **exists**, MIT, 0 stars, created **2026-10-23 16:33 UTC**, pushed 17:01 UTC, 33 commits. It is a `git subtree split` of `replay/courtcam` (D-36), so its history goes back to 2026-09-22, plus a standalone commit `b2f5ff5` (synthetic samples at the root, its own CI). Python `>=3.12,<3.13`. Its core dependencies are permissive. YOLO is the AGPL `[yolo]` extra |
| Compute | All measurements are from **hfbox**: a private, shared AMD RX 9070 XT 16 GB box (ROCm 7.2, torch 2.14, 16 GiB cgroup RAM), reached over the box owner's Tailscale Funnel. Its GPU lock defaults to `/workspace/airtools/.gpu.lock` (the same box as the AirTools work). The README says "EC2 GPU worker", but the CDK app has **no EC2 resource**. HANDOFF (Oct 22) says "EC2 GPU quota is 0. The GPU work stays on hfbox as a pull-based runner." |
| Demo footage | The official demo is the owner's own 2v2 pickup game: local only, never committed (D-98). The README screenshots name players "Anshul" and "Joseph" ("Lost his man, Joseph"). The public demo game is the CC BY 3.0 Nottingham vs Barking Abbey clip |
| Tests | courtcam ~192 pytest, API 308 (+1 skipped), worker 28, render 54, TV Playwright 127 (+3 skipped), web Playwright 115; GitHub Actions CI |

**Repo layout:** `apps/tv` (react-native-tvos 0.87 + react-native-video; web build via react-native-web), `apps/web` (React + Vite phone companion and the older browser TV route), `packages/tv-core` (shared TS: API client, follow-cam maths, clock, focus, mock), `services/api` (FastAPI on Lambda via Mangum), `services/worker` (stage DAG + content-hash cache), `render/replay_render` (director, compositor, hype, condensed, vertical, reel, virtual angles, Tier C avatars), `courtcam/` (the MIT CV library), `infra/` (CDK TS: the `ReplayCloud` stack plus synth-only skeletons), `alexa/` (skill package), `scripts/` (evals, smoke tests, box scripts), `experiments/tierd-*`, `docs/` (D-1…D-98 decision log, progress, licences, test data, scene format).

---

## 1. Feature inventory

Columns: **What** it does · **Where** it lives · **Method / model** · **Measured** (from Replay's docs) · **Gaps**.

### 1.1 Fire TV app (`apps/tv`, `packages/tv-core`)

| Feature | What | Where | Method | Measured | Gaps |
|---|---|---|---|---|---|
| Home | Hero art, Games row, resume ("Resume m:ss" / "Start over"), processing first, waiting-for-upload last | `apps/tv/src/screens/Home.tsx`, `resume.ts` | Hero frame = top hype candidate's scoring moment (`moments.hero_time`). Resume in SharedPreferences, 50 games | Works on the Stick (AFTSS, Fire OS 7) | The live library still had stale synthetic games at handoff |
| Watch / player | D-pad playback, court-line timeline with moment notches, sprite seek previews, Rew/FF scrub, layered Back, 5 s auto-hide, play/pause state | `screens/Watch.tsx`, `playback/*`, `components/Timeline.tsx` | react-native-video (Media3; patched TextureView); storyboard sheets (10×10 tiles of 320×180, one every 2 s) | Verified on the Stick | Reduced motion is not handled |
| Moments browser | Row of jump-to moments (shots, makes, steals, "Lost his man, X", your clips, your notes) with filters All / Scores / Bookmarks; "▼ Angles" marks moments that have replay angles | `components/MomentsLayer.tsx`; API `moments.py` | Labels are built only from event fields (unknown `made` → "Shot", never "basket"); one 480×270 thumb per moment | 33 moments on Nottingham; 3 in a 45 s cut | Chips show where you are but don't seek (by design) |
| Follow a player | Pick a player on the video (markers, spatial arrows), the camera follows them ("Following Anshul"), a ring on the player, "Lost sight of X" | `components/FollowFrame.tsx`, `SelectOverlay.tsx`; `tv-core/src/follow.ts` (`createFollowCam`) | Client-side spring camera from the track chunks: critically damped spring, 4 % dead zone, EMA-velocity lead, eased zoom, hold-and-widen through gaps, conservative id hand-off; ring on the native driver | Ring and camera respond in < 200 ms; Fire TV jank while following 6.6–14 % (native driver; JS-driven was 30–34 %); ring lag 0–90 ms; right person 94.7 % (2v2 park), 58.6–60.2 % (JaiArtHub, all dark tops); ring on the wrong kit 16 % (Nottingham) | Identity fragments on long games (59 ids for ~13 people); same-kit teammates get confused |
| Player card | Menu while following: avatar, name / "Player N", team swatch, "This game" stat line, Edit name, Their moments, View profile | `components/PlayerCard.tsx`; `tv-core statLine` | Stats counted from events.json; a stat no event credits reads "Not detected", never 0 | Verified on the device (Shots 2 / Reb 0 / Stl 1) | No jersey numbers; on volleyball only blocks are credited |
| Do more layer | Six tiles (Follow, Angles, Free view, Player POV, Watch, Stats, Commentary, On your phone, Bookmark, depending on the game), context chip, 3-key legend | `components/DoMoreLayer.tsx`, `nav.ts`, `ui.tsx` | One "remote grammar": Menu opens Do more, Back goes up a level | Verified on the Stick | n/a |
| Ways to watch | Full game / Highlights / Condensed; Highlights list (every play as a card, ★ Best play last, Play all) | `components/HighlightsLayer.tsx` | Reads the `reel`, `condensed` and `highlights` outputs | n/a | Needs the opt-in stages to have run |
| Replay angles | Cut between real and virtual angles at the same media time, 0.5× slow-mo on Rewind, "Camera 3 of 9", burned-in "VIRTUAL REPLAY \| Broadcast high" labels | `components/AngleView.tsx` | Time-aligned per-angle MP4s with posters (§2.10) | Angle cut keeps media time within 8 ms; 9–21 angles per play | Slow-mo repeats frames (no interpolation); the Select key isn't in the legend |
| Free view (2.5D) | D-pad orbit and dolly inside a clamped envelope, edge bars, view-limit gauge, presets on Rew/FF, honesty label | `scene/FreeView.web.tsx` (raw WebGL2), `scene/FreeView.native.tsx` (Kotlin GL Fabric view), `scene/camera.ts` | Renders the scene package live (§2.12) | Web renderer vs the CPU reference: 41.9 dB / SSIM 0.995; 60 fps in desktop Chromium on a GPU | The native view has no ball trail; not verified on the Fire TV |
| Commentary mode | Broadcast rendition with score bug, captions and spoken play-by-play (Kokoro) | `render` broadcast + `narrate` | §2.9 | Template captions such as "Player 9 with the steal!" | The Commentary on/off toast was not verified on the device |
| Stats panel | Box score, shot chart, heatmap, Review queue, Tips (advice) | `components/StatsPanel.tsx`, `screens/Review.tsx`, `screens/Advice.tsx` | API `stats.py`, `narrate/advice.py` | Review asks at most 12 questions, only ones that change score or stats | Distance advice was skewed by identity fragments (now compared only among well-covered players) |
| Clips | List with attribution, D-pad trim, 9:16 share | `screens/Clips.tsx` | API clips + `render/vertical.py` | Exports ~300 fps | n/a |
| Search | Search plays; results play on the TV | `screens/Search.tsx` | §2.15 | Live after D-93 | n/a |
| Players / Profiles | Players screen, profile detail with per-sport career stats (edits shown "EDITED · auto N"), card PNG, career reel, link suggestions | `screens/Players.tsx`, `Profile.tsx`, `ProfilePicker.tsx` | API `profiles/*` | n/a | The live API had no profiles at handoff |
| On your phone (QR) | QR codes for Clip this play, Names (Tag), Review, Search, Highlight reel | `components/PhonePanel.tsx`, `QrCode.tsx` | `POST /games/{id}/phone-link` mints a 24 h per-game HMAC phone token limited to a route allowlist | Works | n/a |
| Add game | Pick a sport → QR for phone upload → live status until ready | `screens/AddGame.tsx` | Per-game HMAC upload token (24 h) | 67 MB in 5 parts uploaded in 6 s | n/a |
| Settings / Pair | API base and key on the device; Alexa 4-digit pair code | `screens/Settings.tsx`, `Pair.tsx` | n/a | n/a | The APK embeds the API key, so it must never be committed |

### 1.2 Phone web app (`apps/web`, served by CloudFront)

| Feature | Where | Method | Measured | Gaps |
|---|---|---|---|---|
| Upload | `screens/QrUpload.tsx`, `Upload.tsx` | S3 presigned multipart: 16 MiB parts, 3 in flight, per-part retry, resumable (`GET upload/parts`); ISO-BMFF check before decode | 67 MB in 6 s | In local mode the multipart call answers 409 and falls back to a single PUT |
| Calibrate | inside the upload flow | Auto court fit (template fit) proposal → numbered dots to drag → "More points" → "Court markings" (FIBA/NBA/NCAA/NFHS) → one-tap "Tap the hoop" (`rim_top`); a proposal with `ok=false` is refused unless overridden | Autocalib ~6 s on a 45 s clip, 41 s live; hand fits 0.5–12.8 px residual | Autocalib was **refused on every real basketball clip** (scores 0.61, 0.75, 0.888 < 0.90); the owner's own advice is "drag every dot by hand" |
| Processing status | same | Live stage list from the API (`progress` merged into reads) | Fresh 45 s: 13 stages in ~40 s (in-process) / ~4 min (worker with extras) | n/a |
| Clip / Tag (Names) / Review / Search / Reel tabs | `screens/Phone.tsx`, `api/phone.ts` | Phone token allowlist; Tag hides tracks seen < 5 s; Names tab sets pickup scoring (2s & 3s / 1s & 2s) and teams | Reel: 9:16 → Make → "Download reel (28 s)" in ~10 s | 16:9 "clips" are time ranges on the wide video, not rendered files |
| Share clip | same | Open the clip from the TV QR, trim, save and share (Web Share) | n/a | n/a |
| Profiles + face enrollment | `screens/PhoneProfiles.tsx` | Consent-gated, 1–10 own photos, "Delete my face data" | §2.3 | Never exercised end to end against real face models in the UI |
| "Play on the TV" / "Watch it" | Search and Review | `POST /games/{id}/tv/play` → TV polls `/tv/commands` (3 s) | Walked: "a steal" → the TV plays from 0:40 | n/a |

### 1.3 API (`services/api/replay_api`, FastAPI → Lambda via Mangum)

| Area | Files | Notes |
|---|---|---|
| Core game routes | `main.py` (54 KB) | Games, media (`/media` = presigned 302 with signature windows and `Cache-Control`), players PATCH (name ≤ 60 chars, team), events PATCH (made/confirmed/dismissed), score, plays, clips, triggers (tap), bookmarks, notes (`POST /games/{id}/notes` loads a play log), scoring mode (`PUT /games/{id}/scoring`) |
| Cloud routes | `cloud_routes.py`, `cloud.py`, `remote_runner.py`, `auth.py` | Multipart upload; the **worker claim protocol** (§2.18); HMAC upload and phone tokens; per-route minimal S3 pulls (`game_dir_with`, D-86) |
| Discovery | `discovery_routes.py` | hype, rallies, condensed, vertical exports, reel (`POST /games/{id}/exports/reel {aspect}`), best play (`GET /games/{id}/best-play`) |
| Moments and storyboard | `moments.py` | `moments`, `clip_moments`, `note_moments`, `best_play`, hero, storyboard |
| Narration | `narrate/commentary.py`, `grounding.py`, `advice.py`, `search.py`, `routes.py` | §2.9, §2.15 |
| Query | `providers/query.py` | Rule grammar first, then an LLM that may only fill a schema-validated filter |
| Profiles | `profiles/routes.py`, `card.py`, `career.py`, `faces.py` | SQLite (DynamoDB stub); deterministic card JSON + an 810×1080 PNG |
| Stats | `stats.py` | box score, shot chart, heatmap, distance covered, review queue (≤ 12) |
| Edits overlay | `edits.py` | `edits.json`: patch / add / merges / score. Re-applied after every worker stage restore, so corrections survive re-runs |
| Providers | `providers/{tts,llm,embeddings,speaker,face,storage,jobs,index,labeler,profiles}.py`, `_runner.py`, `aws.py` | Protocol + local implementation; AWS stubs (Polly, Rekognition, DynamoDB). Local models run as subprocesses in their own venvs under `flock gpu.lock timeout 900` |
| Alexa | `alexa_routes.py`, `alexa_verify.py` | §2.17 |
| Readiness | `readiness.py` | ETA and readiness fields |

### 1.4 Worker pipeline (`services/worker`, courtcam stages + Replay stages)

A per-game DAG of `Stage(name, version, fn, inputs, outputs, params, after, resource gpu|cpu|io, fanout, default)`. The cache key is sha256(stage + version + item + params + sha256 of every input file). GPU tasks run one at a time under a box-wide flock; the CPU pool is 2 and the IO pool 4; one JSON line per task goes to `_work/worker.jsonl`. `python -m replay_worker dag > infra/dag.json` mirrors the DAG into a Step Functions skeleton (placeholders only).

Default stages, from courtcam (`stages/courtcam.py`): `ingest → calibrate → detect → track → court → identity → tracks → crops`, `audio`, `pose` (fan-out per chunk), `events` (+ `ball.json`), `triggers`, then `game`, `plays`, `storyboard`, `moments`.
Opt-in stages, on by default on the runner (`REPLAY_WORKER_STAGES=hype,condensed,replays,scene,tierc_manifest`): `hype`, `condensed`, `vertical`, `reel` (`stages/discovery.py`); `camera`, `plate`, `highlights`, `segment` (SAM), `tiera`, `tierb`, `scene`, `replays` (`stages/virtual.py`); `tierc_scene`, `tierc`, `tierc_manifest` (`stages/tierc.py`); `director`, `broadcast` (`stages/broadcast.py`); `commentary`, `embeddings`, `search_index` (`stages/narrate.py`); `face_match` (`stages/faces.py`); `preview`.

**Throughput (hfbox):** Kennesaw 240 s cold 76.4 s (3.1× realtime), warm 1.4 s. Nottingham 241 s: default stages 261 s from `process` to `ready`; 693 s with every extra forced. CC BY pickleball 90 s: cold 92.8 s, warm 1.4 s. The owner's 6:37 demo game: replay stages alone ~12 min. A fresh 45 s upload: ~40 s in-process (13 stages) or ~4 min through the runner with extras. YOLO11m at stride 2: 4.1–4.6× realtime.

### 1.5 Render (`render/replay_render`)

`director.py` (cuts.json), `camera.py` (operator-smoothed virtual cameras), `compositor.py` (one H.264 broadcast rendition), `graphics.py` (score bug, lower thirds, sting, Barlow OFL), `audio.py` (ducking, procedural stings), `hype.py`, `condensed.py`, `vertical.py`, `reel.py`, `review.py` (shot chart PNG), `jitter.py`, `virtual/{segment,tiera,tierb,scene,replays}.py`, `avatars/*` (Tier C: `lift`, `place`, `motion`, `skeleton`, `imageview`, `proxy`, `render`, `scene`, `evaluate`). The CPU renderer runs ~100 fps at 1080p.

### 1.6 Voice and Alexa

* **"Replay, clip that"** (courtcam `triggers.py`): voice (Whisper-small over loud voiced segments + difflib fuzzy match against "replay … clip <that|name>"), X gesture (pose), phone tap. One resolution rule maps each to a play (§2.16).
* **Kokoro-82M** speaks the commentary (§2.9). ECAPA speaker verification and openWakeWord were installed but stay opt-in or off.
* **Alexa skill** "Replay Court": PairIntent, ClipThatIntent, ExportReelIntent (§2.17).

### 1.7 Infra (`infra/`)

`ReplayCloud` (`lib/cloud-stack.ts`): Lambda (python3.12 arm64) behind a Function URL; a private media S3 bucket; CloudFront + OAC serving the phone app at `/` and the TV web build at `/tvapp/`, with a CloudFront Function for SPA rewrites; a runtime `config.json`; SSM SecureStrings `/replay/{api-key,worker-key,upload-token-secret,alexa-skill-id}`; CloudWatch Logs. No VPC, NAT, API Gateway or tables, so ~$0.50–1/month idle. `ReplayData` / `ReplayPipeline` (DynamoDB, Step Functions + SageMaker placeholders) are synth-only skeletons. Lambda concurrency is limited to 10 on the account, which makes 429s a demo risk (the clients retry since D-87).

### 1.8 Evaluation tooling, test data, experiments

`scripts/eval_calibration.py`, `eval_moments.py`, `eval_scene.py`, `courtcam eval` (CLEAR-MOT/IDF1 in `metrics.py`), `courtcam eval-events` (`eventeval.py`, play-log truth), `docs/evidence/D97-tracking/players_eval.py`, `courtcam synth` (a 79 KB synthetic generator for 5 scenes with ground truth), `scripts/cloud-smoke.py`, `experiments/tierd-*` (§2.13–2.14). Details in §3.

---

## 2. Deep dives

### 2.1 Sport profiles: how the core avoids branching on the sport

* **Format:** `courtcam/sports/<id>.yaml` plus a court template JSON per variant (metres, a fixed origin convention, `+x` to the right sideline, `+y` into the court). Loaded into pydantic configs in `profiles.py`: `CourtCfg`, `PlayersCfg`, `DetectionCfg`, `TrackingCfg`, `FollowCamCfg`, `TeamsCfg`, `ShotCfg`, `BallCfg`, `ScoringCfg`, `PossessionCfg`, `LostManCfg`, `PoseCfg`, `AudioCfg`, `TriggerCfg`, `RallyCfg`.
* **Rule:** "Core modules must never branch on the sport id" (REPLAY_PLAN §12 rule 6). Behaviour comes from data:
  * `events: [...]` picks detectors from `events.DETECTORS`. Basketball: `[shot, possession, lost_man, hype]`. Volleyball: `[rally, block, hype]`. Pickleball and badminton: `[rally, hype]`.
  * `team_rule: jersey_color | net_side`, plus `teams.colors` for net sports.
  * `plays:` grammars (state `machine` or `sequence`), `scoring:` (inside/outside/free_throw, `to: N` for pickup), `rally:` (min duration, gap bridging, `audio_fusion`, `one_touch`, `side_out`, `server_behind_line`), `followcam` (zoom as a fraction of the court's pixel width), `query_vocab` (search words), `sport_ui` (TV chips and review panels), `landmarks` + `landmarks_optional` + `landmark_descriptions` + `orientation_hint` (VLM prose), `standards` (NBA/NCAA/NFHS template sets), and a `synth` block (synthetic choreography).
  * Adding a sport takes a template JSON, a YAML and `courtcam synth --sport X`. A new event type goes into `events.DETECTORS`, never as a branch.
* **Installed sports:** basketball (half, full; FIBA, NBA, NCAA and NFHS templates), pickleball (doubles; kitchen landmarks), badminton (doubles; `singles` is an alias), volleyball (indoor; net posts and attack lines). **Only 4 sports, all court sports filmed from one fixed camera.** Field sports, target sports and table tennis are absent.
* **Trophy relevance:** this is close to what Trophy's rule pack needs for `family` / `field` / `detectors`. Trophy can copy the template JSON convention and the `machine`/`sequence` play grammars, then add `rules[]` (CEL) on top.

### 2.2 Court calibration (auto court fit + tap-to-check, metres)

Pipeline: `autocalib.py` → `templatefit.py` → `calibrate.py` → `distortion.py` → `court.py`.

1. **Proposal** (`autocalib --backend auto` = `templatefit`, no model):
   * A two-sided line mask: a pixel is paint when it is brighter, darker or more saturated than the pixels `tau` away on both sides.
   * Hough segments → merged collinear lines → convex quads from line pairs, matched to rectangles the template knows (court outline, key, kitchen).
   * Each candidate homography is scored by projecting the whole template against a distance transform. Candidates are snapped to the nearest physical pinhole camera (skew ≤ 0.05) and ranked by covered paint.
   * A lens search over k1 ∈ {−0.2, −0.4, −0.6} runs when the straight fit fails.
   * `ok` requires a line score ≥ 0.90. A `vlm` / `claude-cli` backend (Claude vision on a gridded frame, asked twice with a mirrored copy, keeping only answers that agree) is opt-in or a prior. It scored 0 of 4 at ~$0.26 and 3–14 min per clip.
2. **Tap-to-check:** the phone shows numbered dots. The user drags them, skips any that aren't visible, adds "More points", picks the court markings standard, then taps the hoop. An `ok=false` proposal is refused in courtcam, the worker, the API and the UI unless explicitly overridden (D-72).
3. **Fit:**
   * `calibrate.homography` uses any ≥ 4 landmarks the template knows, with RANSAC.
   * The reprojection gate is `max(5 px, 1 % of the clicked span)`.
   * `orient_labels` swaps mirrored left/right labels.
   * `fit_standards` picks the best marking standard.
   * `distortion.estimate_k1` fits a one-parameter Fitzgibbon division model, gated at ≥ 8 landmarks and ≥ 30 % RMS gain. Foot points are undistorted before projection.
4. **Full camera** (`camera_calibration`, D-53):
   * Focal length from the floor homography (Zhang's constraints, square pixels, principal point at the centre), pose from K⁻¹H.
   * Refined with `solvePnP` over floor plus height landmarks (`rim_top` 3.05 m, net-post tops), with a golden-section search on log f.
   * Mirrored rigs are handled (det R = −1).
5. **Fail-safe** (`court.fit_check`, D-94): if people's positions or heights disagree with the fit, `court.trusted=false` and the on-court filter removes nobody.

**Measured:**
* Synthetic (20 seeds, 1 px click noise): focal 0.25–0.64 %, rotation 0.11–0.28°, camera position 4–8 cm.
* Real floor reprojection 0.03–2.64 px; held-out hoop 53–92 px off on wide rigs.
* Template fit: 10/10 landmarks within 12 px (pickleball 1×), 1.8 px (synthetic), 4–12 s per clip.
* Lens model: badminton auditorium RMS 14.6 → 2.5 px, metre error 0.47 → 0.09 m.
* Nottingham: 13 hand points, k1 −0.415, 9.56 px (gate 16.7).

**Gaps:** autocalib is wrong on phone half-court frames and was refused on every real basketball clip. There is one radial term about a centred principal point. Hoop height is approximate on wide rigs.

### 2.3 Identity, teams, and face enrollment with consent

* **Detection and tracking** (`detect.py`): YOLO11 (`yolo11n` on CPU, `yolo11m` on GPU; imgsz 960; stride 2 = 15 Hz) with BoT-SORT in one ultralytics pass (`botsort.yaml`: track_buffer 90, no GMC, no ReID). Unconfirmed boxes are kept as id 0, for gap filling.
* **On-court filter** (`court.py`): foot point → metres. A tracklet is kept if it spends ≥ 60 % of its life inside the court + `margin_m`. Bystanders are people stationary ≥ 20 s inside a 0.5 m radius, or inside the lines < 40 % of the time (scorer's table, bench, neighbouring court).
* **Identity** (`identity.py`, 72 KB):
  * Tracklets are merged closest-first within `merge_max_gap_s` 5 s and `merge_max_dist_m` 7 m.
  * Tracklets are cut at jersey-team switches and at body-appearance changes (an HSV histogram of the upper and lower halves, Bhattacharyya distance; `appearance_cut` 0.22).
  * One global Hungarian assignment links the pieces.
  * A concurrency cap of `players.max + officials` (basketball: 10 + 3 referees) applies.
  * Games with ≤ 6 people are solved as K people (`roster_pieces` / `roster_label`).
  * `fill_gaps` takes free detector boxes (IoU ≥ 0.3 chain), and unsolved gaps are bridged for at most 2 s.
* **Teams:**
  * `jersey_color`: k-means over torso HSV histograms (8×4×4 H×S×V bins since D-97, so brightness separates red and dark kits).
  * `net_side`: the side of the net of the median court y in 60 s windows, majority-voted.
  * `matchups` (D-98): in 2v2 or 3v3 with alike kits, teams come from who guards whom.
  * A team set on the phone wins (`apply_team_edits`).
* **Faces** (`providers/face.py`, `profiles/faces.py`, D-58):
  * OpenCV Zoo **YuNet** (MIT) for detection and **SFace** (Apache-2.0 weights, training data undocumented) for embeddings.
  * Opt-in twice: `REPLAY_FACE_DIR` must be set and the models present.
  * Enrollment requires `consent=true` and 1–10 own photos. Photos are deleted after embedding, and one mean embedding per profile is kept. Delete purges it.
  * Only enrolled embeddings are ever compared. Nothing about unmatched players is stored.
  * Threshold cosine 0.45 (OpenCV's default is 0.363), plus a per-player majority (≥ 2 votes and ≥ 50 % of usable samples). The output is a *suggestion* a person confirms.
  * AWS path: Rekognition (stub).

**Measured:**
* Synthetic basketball IDF1 0.31–0.37 with YOLO (122–157 ID switches); pickleball 0.98/0.99, badminton 0.99/1.00, volleyball 0.79.
* D-97 (Nottingham, hand-labelled): player recall 0.726 → 0.876, team accuracy 0.695 → 0.98, ghost boxes per instant 1.43 → 0.64, ids 86 → 62.
* 2v2 park: 21 ids → 4, ring on the right person 94.7 %.
* Faces: usable faces in only 2.8–14.8 % of person samples; genuine match 64–72 % at 0.45, unenrolled 3 %; genuine windows suggested 39/45, unenrolled 0/47 (tuning set, not held out).

**Gaps:** fragmentation on long full-court games; alike outfits; referees counted as players; OSNet re-ID rejected as research-only; no jersey OCR.

### 2.4 Follow-cam crop paths

* **Server:** `croppath.py` writes one rect per frame at 30 Hz, normalised. The window is 16:9 and its width is court-pixel-width / `zoom` (basketball 2.4, volleyball 1.6; minimum 480 px). The camera is a critically damped spring (stiffness 7) chasing the box centre through a 4 % dead zone, with an EMA-velocity lead (τ 0.4 s, ≤ 25 % of the window). It parks through gaps.
* **Client** (D-82, the one actually used now): `tv-core/follow.ts` computes the camera every animation frame from the tracks. It hands off to an id that continues from the same spot, or holds and widens. Server crops are unused by the TV. `render/camera.py` uses the same operator model for broadcast and 9:16 (`aspect=9/16`).
* **Measured:** jitter (rms px/frame²), Kennesaw: tight 51.3 → 0.42, wide 14.5 → 0.07; courtcam follow 2.12 → 0.64. The target box was inside the window on 100 % of 60 picks × 30 s; the ring was on 68–74 % (the rest is real track loss).

### 2.5 Pose

`pose.py`: top-down pose on a **crop around each track box**, letterboxed up to 384 px, so a 60 px far player is seen ~5× larger. Backends: `yolo` (YOLO11m-pose, AGPL), `vit` (ViTPose-B, Apache-2.0, opt-in, better on small players), and `synthetic` (ground-truth oracle). One `poses/{chunk}.json` per 10 s chunk at 10 Hz (COCO-17). MotionBERT lifts to 3D only for Tier C. **Measured:** YOLO11m-pose 11 ms @960; ViTPose fp16 38 s vs YOLO 88 s on Kennesaw. Gesture recall on far players (≤ 56 px) is 0/22 with YOLO-pose and 9/22 with ViTPose. rtmlib/RTMPose is listed as a permissive alternative but was never tried.

### 2.6 Event and play detection

All of these live in `events.py` (59 KB), `ball.py`, `plays.py` and `audio.py`.

* **Shots, makes and score from the ball at the rim** (`ball.py`, D-90/92/95, classical CV, no model):
  * Each template rim is projected 3.05 m up through the full camera and snapped to the painted rim on a median frame.
  * One decode pass finds ball-sized, ball-coloured blobs moving against a running background inside a box around each rim, in rim units.
  * Each visit is a shot. Passing down through the rim's middle is a make; the rim edge is "can't tell", which goes to Review.
  * The shooter is the player whose wrist is at the start of the ball's path back from the rim. 2 vs 3 points comes from the release spot against the template zones. Free throws are detected from a still scene. Points follow `profile.scoring`, and pickup `to: N` restarts the score.
  * **Measured:** Nottingham Q1 shots P/R 0.24/0.40 → 0.90/0.90 (later P 1.0 / R 0.90), make/miss 8/9; Q3 hold-out P .80 / R 1.0, make/miss 7/8, free throws 4/4; 3x3 P/R 1.0, makes 1.0; 2v2 park hold-out P 1.0 / R .80, make/miss .714; the owner's demo game shot precision 25/25 (2 wrong shooters). Ball scan ~15 s per 120 s 1080p clip with one hoop; events stage 43–47 s per 240 s on CPU.
  * The older pose shot (arms up ≤ 1.0 s within 9 m of the rim, confirmed by a hoop-ROI frame-difference burst) gave synthetic P 1.00 / R 0.78.
* **Possession and steals** (`detect_possessions`): the offence is the team farther from the attacked rim. The cause (steal, defensive rebound, inbound) comes from what surrounds the flip. Synthetic P/R 0.79/0.77 (YOLO); unreliable on real footage because of identity fragments.
* **"Lost his man"** (`detect_lost_man`, D-98):
  * A defender shadows an opponent (median separation ≤ 2.5 m for 3 s, nearer the rim).
  * Then the two are > 3.5 m apart for ≥ 2 s, the defender is not within 2 m of another opponent (helping or switching), and the man cut ≥ 3 m toward the rim.
  * Only during live play (median speed ≥ 0.75 m/s) and not within 6 s after a make.
  * Thresholds were tuned on **one labelled lapse** in the owner's game.
* **Rallies (net sports):** motion-only by default: median player court speed with hysteresis (run > 0.5 m/s peaking ≥ 0.9 m/s), plus optional audio fusion. Also: one-touch contact sides, serve side, point winner = the next server, and pickleball side-out (USA Pickleball 4.B.6). **Measured:** real badminton 240 s P 1.00 / R 0.86–0.93; synthetic (YOLO) rallies P/R 0.90/0.83, points 0.96/0.89, contact side 143/239.
* **Blocks** (volleyball): a front-row jump at the net plus a contact sound. 14 "blocks" in 90 s of real volleyball were likely false. **No basketball block detector** (D-96: 0 of 2 truth blocks, 4 false).
* **Hype events:** loud, sustained, aperiodic RMS rises over a rolling median.
* **Plays** (`plays.py`): grammars as data. Basketball: possession_change → shot | turnover (orphan put-backs, max 40 s) and lost_man. Net sports: serve → point with contact and block members. Volleyball attack = 3 same-side contacts within 2.5 s. Exact on ground-truth plays (73/73 trigger resolution).
* **Audio** (`audio.py`, numpy only): spectral-flux onsets (rolling median + k·MAD), RMS dBFS at 10 Hz, hype segments, speech segments (loud and periodic). Audio fusion was turned **off** for real shuttle rallies (P/R 0.36 fused vs 1.00/0.86 motion-only).

### 2.7 Moments, highlights, best play, condensed game

* **Moments** (`moments.py`): one row per event worth jumping to, plus the user's clips (voice, X sign, tap) as `bookmark` moments, plus the uploader's play-log notes ("Your note: …", never merged into events). Steal and rebound windows run 4 s before to 2 s after.
* **Best play** (`moments.best_play`): the user's pick, else the last make in the final 30 s (labelled "Last basket"; it can't know the make won the game), else the top hype candidate. A ★ on the scrubber; the reel and Highlights end on it.
* **Hype meter** (`render/hype.py`, `replay.hype.v1`):
  * Noisy-or of audio loudness over a 20 s rolling median (0.85), arms-up poses (0.6) and speed bursts (0.35), at 2 Hz. Detected makes, blocks and steals lift it.
  * Candidates: score ≥ 0.4, ≥ 8 s apart, ≤ 12.
  * **Measured:** synthetic basketball P .86 / R 1.0, pickleball 1.0/1.0, badminton 1.0/0.89. Real top-5 precision 0.4 (Q1), 0.2 (Q3). The ceiling is set by unknown outcomes.
* **Highlights selection** (`virtual/replays.select`): best, then triggers, then story events (lost man), then up to `auto_n` hype fill plays (one per `PER_PLAY_S`, 3–10). Fill plays are "lite" (real-video angles only). Windows are ≤ 8 s; the best play and lost-man plays get 14–20 s with two Player's views. On the owner's demo game, highlights covered 9 of 9 hand moments and replays 6 of 9.
* **Condensed** (`condensed.py`, `replay.rallies.v1`): rallies or plays only (+1.5 s pre-roll, +1 s post), wide camera, "RALLY n/N · X SHOTS · Y S" counter, a rally browser (in order or longest). Badminton 240 s → 87.5 s in 10.6 s; Nottingham 241 → 175 s.
* **Reel** (`reel.py`): the user's clips first, then top plays (≤ 90 s), best play last, dips to black, captions from events only, 16:9 or 9:16 (following the key player). Nottingham: a 28 s reel with 5 segments in ~10 s.
* **Vertical** (`vertical.py`): 9:16 following the subject or key role, deterministic captions, content-hash spec ids, ~300 fps.

### 2.8 Director / broadcast

`director.py` → `cuts.json` (`replay.cuts.v1`):

* Wide during dead time; tight (players within 8 m of the centroid) when the median speed is > 1.1 m/s (hysteresis, 2 s bridges); long lulls alternate 12 s wide / 7 s tight.
* `follow:<shooter>` from 2.5 s before to 1 s after each shot.
* Instant replays at 0.5× start 2 s after makes, clipped plays and rallies ≥ 8 s. They cover 3 s before to 1 s after the play, are dropped under 4 s, and are ≥ 15 s apart.
* Minimum shot 3 s, no A-B-A with B < 5 s, 0.9 s smootherstep eases, a 0.7 s sting around replays.
* Rendition time equals source time, so the score and scrubber stay aligned.

`compositor.py` + `graphics.py`:
* A score bug (team chips, a team-colour flash on change, elapsed clock), LIVE / REPLAY 0.5× bugs, lower thirds ("Player N" or the roster name, "+points · total PTS"), and a 3-band sting.
* Telestrator: a 0.75 m spotlight ring, a 2.5 s trail, pass arcs, and a shot arc (parabola from 2.3 m to the 3.05 m rim, needs the pinhole fit).
* Game audio ducks 9 dB under replays and 12 dB under narration; procedural two-chord stings.
* Barlow Condensed (OFL), colours #0E1116 / #FFB800 / #E5484D.

### 2.9 Commentary, captions, Kokoro TTS

* `narrate/commentary.py` writes deterministic template lines per play event (the guaranteed path).
* An optional LLM paraphrase (Qwen3-4B-Instruct Q4_K_M on llama.cpp HIP, temperature 0, seed 0, `json_schema` output) is used **only if `grounding.check` passes**. `grounding.py` extracts names, numbers, action verb classes (with direction for passes and steals), shot values, score claims, team claims and offensive/defensive claims, and rejects anything absent from the facts.
* Timing always comes from events, never from the model.
* `narrate` lays the Kokoro WAVs (voice `am_michael`, 24 kHz) on the game clock without overlaps → `narration.wav`, which the broadcast mixer ducks under (wired in on Oct 23, `d87fec7`).
* **Measured:** template 28/28 grounded; LLM paraphrase accepted 26/28 (rejections fell back); Kennesaw 32/32 and 30/32. LLM 0.27 s per play; Kokoro 0.19 s per line on GPU (RTF 0.085), 0.35 s on CPU.
* **Gaps:** reads "Player 9", not names, unless the roster is tagged; no colour commentator; Kokoro needs `torch.backends.cudnn.enabled=False` on ROCm.

### 2.10 Replay angles

All angles of one play are rendered over the same window at the source frame rate, so the TV cuts between them without losing its place. The manifest is `replays/{play}/manifest.json`, with a poster per angle.

* **Real cameras (Tier A, `tiera.py`):** `wide`, `follow_<pid>` (the crop path), `tight_<pid>` (2.4 box-heights, operator-smoothed). 5–8 ms per frame on CPU.
* **2.5D (Tier B, `tierb.py`, D-54):**
  * The court plate is a temporal median with players masked, warped to a top-down floor (40 px/m) plus a backdrop wall.
  * Players are SAM 2.1 cutout billboards on their tracked foot points, warped G_virt·G_real⁻¹ on each player's vertical plane, with contact shadows and painter's order.
  * The hoop, backboard, net and a modelled ball parabola are drawn as geometry.
  * Angles: **`broadcast_high` ("Broadcast high")**, **`orbit`**, `push_in`.
  * Labelled "2.5D" / "flat player cutouts".
  * **Measured** (held-out synthetic): player IoU 0.80 (real view) to 0.35 (orbit −60°); floor PSNR 21–28 dB; position error 0.18 m. 32–62 ms per frame on CPU.
* **Virtual 3D (Tier C, image-based since D-88, `avatars/imageview.py`, `proxy.py`):**
  * Each tracked person is their own SAM cutout stood at their foot point on the reconstructed court.
  * Past 45° from the real camera they hand over to a 15-capsule posed proxy textured from real pixels; it fades to kit-colour silhouettes past 35–75°.
  * Unseen walls are flat median colours.
  * Angles: wing, courtside and baseline (within 60° of the real camera).
  * Every frame is labelled "VIRTUAL VIEW".
  * The older stylised capsule-mannequin path (MotionBERT or analytic lift) gave MPJPE 125–139 mm on synthetic.
* **Player's view (POV):**
  * For the key player and the 5 nearest them. The eye sits on the bridged court track and the gaze on the ball or play. The owner is hidden. The view never looks up more than 20°.
  * The best play gets a continuous 14 s POV.
  * SAM 2.1 masks came from per-player prompts held through the chunk: masked player-frames 73 % → 99.8 %.
  * A 240-frame POV takes 4.3 s.
  * Per game of 4 highlights (Nottingham): SAM 116 s, Tier B 45 s, Tier C scene 215 s, 32 renders 202–258 s.
* **SAM 2.1** (`segment.py`, D-55): `facebook/sam2.1-hiera-small`, bf16, via transformers `Sam2VideoModel`. A fresh session every 48 frames, re-prompted with every player's track box; masks are clipped to the grown track box. ~26 ms per object per frame (≈ 1 GPU-minute per 8 s play with 10 players).
* **Gaps:** the proxy and the cutout can stand ~0.3 m apart (ghosting at 45–55°); a POV under the basket looks at stand-in walls; outdoor courts get plain walls; slow-mo repeats frames; the ball is modelled, not tracked.

### 2.11 "Broadcast high" and Orbit, specifically

Both are Tier B 2.5D camera paths over the play window (`render/replay_render/virtual/tierb.py`). Free view exposes the same geometry interactively. The camera state is `{azimuth, elevation, distance, roll, fov}` around a target, clamped to an envelope derived per package from the real camera and the floor it saw. On real rigs the envelope is small: Kennesaw ±7.5–12.5° azimuth; volleyball ±17°.

### 2.12 Scene package format (`docs/scene-format.md`, `replay.scene_package.v1`)

* One highlight as data: `layout.json`, `atlas.mp4`, `floor.png` and `backdrop.png` (RGBA; alpha marks texels the real camera saw).
* The atlas is one H.264 video: the colour half on the left and the mask as luma on the right, a fixed grid of 16-multiple cells, alpha ramp 0.1–0.9. **One hardware decoder on a Fire TV.**
* Per frame and player: `{pid, cell, foot, rect, uv, depth}`. Billboards face the real camera (`facing: real`), so the real view is reproduced exactly.
* Static geometry: hoops and net. The ball is modelled (`source: "model"`), not tracked.
* The camera follows OpenCV conventions. The scene frame is the court template frame (`mirror_x` when the calibration is mirrored). A GL client needs a half-pixel shift (missing it cost ~15 dB).
* **Measured:** real-camera reproduction PSNR 21.5–28.3 dB, SSIM 0.78–0.92; novel-view silhouette IoU 0.685 at the real camera, ≥ 95 % of that up to ~13° of billboard turn; packages 1.3–4.9 MB per play.

### 2.13 Tier D experiments (`docs/tier-d.md`, `experiments/tierd-*`)

* **A. MoGe-2 metric point maps** (MIT): 0.14 s per 1080p frame, 3.2 GB. Raw clouds lose to Tier B: player IoU 0.16–0.75 vs 0.35–0.80; players 0.62 m off; 0.7 m depth smear. The hybrid version roughly ties Tier B. It is good for the static background (net, fence). Verdict: maybe later for the plate.
* **B. VGGT-1B static court:** 5.7 s for 32 frames, 8.8 GB. It correctly finds the camera static, but a tripod gives no parallax and the weights are CC-BY-NC. Dead end.
* **C. Dynamic splats / 4D** (gsplat, shape-of-motion, 4DGaussians): gsplat fails without a CUDA or HIP toolkit on ROCm. Dead end on hfbox. It needs gsplat-amd or an NVIDIA box.
* **Their own conclusion:** "revisit true multi-view or 4D only if the capture changes (two phones…)". **That is exactly Trophy's 2–4-phone setup, on NVIDIA.**

### 2.14 Voice clips: "Replay, clip that"

* Whisper-small (transformers, MIT) runs over loud voiced segments only. difflib fuzzy-matches the wake word plus a command against the roster ("clip Marcus").
* The X gesture: forearms crossed overhead held ≥ 0.9 s, or at chin or chest held 0.4 s, only from front-facing samples.
* A phone tap or an Alexa ClipThat writes a trigger.
* **Resolution:** a trigger at T belongs to the play that most recently ended in [T − 8 s, T + 0.5 s]. The clip is that play ± 1 s, owned by the gesture-maker or speaker, else the named subject.
* **Measured:** voice 37/37 synthetic lines heard (named subject 18/18; clip right 30/37, every miss a missed play); gesture 22/22 with ground-truth poses and 0 FP; real footage 0 false triggers in 480 s; demo game 5/5 X signs with 0 false (thresholds tuned on that video); resolution 73/73. Whisper-small takes 0.07 s per utterance on GPU (0.9 GB).
* **Gaps:** no real crowd-noise ASR test; speaker identity only through opt-in enrollment (no route built); the wake word is not trained (openWakeWord models are NC).

### 2.15 Search, free-text query, advice

* **Query** (`providers/query.py`): a rule grammar [player] + [event vocabulary from the profile's `query_vocab`] + [time filter]. With `REPLAY_QUERY=llm`, only unparsed text reaches an LLM, which fills a `json_schema` filter (type, made, value, rostered player, half, longest, never a time). `validate_filter` keeps only fields the text grounds. LLM median 0.58 s; "the crowd going wild" correctly yields no filter.
* **Search** (`narrate/search.py`): per play, 4 keyframes → SigLIP ViT-B-16 (open_clip, webli) image embeddings averaged, plus the template commentary text embedding. Plays are ranked by reciprocal-rank fusion of the query↔image and query↔text cosines (SigLIP's cross-modal cosines are tiny, so ranks are fused, not scores), then re-ranked by the structured filter. "a steal" and "rebound" ranked their plays first. Embedding 10 plays takes 10.5 s on GPU.
* **Advice** (`narrate/advice.py`): per-player lines from the player's own stats (shooting by value, make %, steals, turnovers, rally outcomes, distance vs the team average), each passing `grounding.check`, with "no biomechanics". Advice templates grounded 18/18.

### 2.16 Clips trim and share; heatmap, stats panel, player card; review queue; profiles

* **Clips:** `GET/PATCH /games/{id}/clips` (trim, `edited` flag), 9:16 export job, phone share.
* **Stats** (`stats.py`, recomputed per request): box score (auto-detected, mean confidence, `available` columns), shot chart (PNG via `review.py`), heatmap, distance covered (drops jumps > 9 m/s; median error 0.7–4.9 % vs synthetic).
* **Review queue:** up to 12 questions that change score or stats: "Make or miss?" first (the rim-edge "can't tell" cases), then low confidence (< 0.6) and identity. Each maps to an existing PATCH route. "Watch it" plays the clip 4 s early on the TV.
* **Player card:** see §1.1. **Collectible card** (`profiles/card.py`): deterministic JSON + an 810×1080 PNG, grounded title template (optional LLM paraphrase through the same check).
* **Profiles:** SQLite; links (game, player) → profile; renames propagate; same-name link suggestions; career stats summed at read time; user edits win and are flagged; a career reel manifest.

### 2.17 Alexa skill (`alexa/`, `alexa_routes.py`, `docs/alexa.md`)

* Invocation "replay court": `PairIntent` (a 4-digit code from `POST /tv/pair`, 5 tries, 5 min), `ClipThatIntent` (writes `clip_that` at the TV's heartbeat time, extrapolated while playing), `ExportReelIntent` (queues the reel job), plus Launch, Help, Stop and Fallback.
* `POST /alexa` verifies the signed request: web-PKI cert chain, SAN, RSA-SHA256 of the raw body, timestamp ≤ 150 s, skill id from SSM.
* The TV side: `/tv/state` heartbeat (every 10 s since D-96), `/tv/commands` 1 s poll, ack. State is 5 small JSON docs in S3.
* **Measured:** 26 tests, including a self-made CA, bad certificates, Amazon's real echo-api cert chains, and moto S3.
* **Gaps:** dropped from the Oct 22 demo walk; untested on hardware (Function URL as a wildcard-cert endpoint; Fire TV voice to a dev skill).

### 2.18 AWS infra and the worker claim protocol (`cloud_routes.py`, `remote_runner.py`, `infra/lib/cloud-stack.ts`, D-80)

* **Upload:** `POST /games/{id}/upload/multipart {size}` → `{upload_id, part_size 16 MiB, parts: [presigned PUT]}` (≤ 1000 parts, ≤ 20 GiB, 6 h URL TTL). Then `complete`, `abort`, and `GET upload/parts` to resume.
* **Jobs:** an S3 job queue with **conditional-write claims**.
* **Runner** (a pull model, no AWS credentials on the GPU box; it authenticates with the worker key):
  * `POST /worker/claim` → 204 or `{job, game_id, files}` (presigned GETs).
  * `POST /worker/jobs/{id}/progress {stage, fraction}` (protected fields can't be overwritten).
  * `POST /worker/jobs/{id}/upload-urls {paths}` → presigned PUTs.
  * `POST /worker/jobs/{id}/finish {ok, error}`.
* **Security:** per-game HMAC upload tokens and phone tokens (24 h, separate kinds, route allowlists); `/media` refuses `source.mp4` in cloud mode; ISO-BMFF validation plus an FFmpeg protocol whitelist; the runner never logs presigned URLs.
* **Gaps:** a dead runner leaves its job `running`; last write wins on edits; `/sessions` returns 501 in cloud mode; cold Lambda routes take 8–17 s on the first pull (fixed by D-86, needed a redeploy).

### 2.19 Eval scripts, synthetic data, CC BY footage

* **`scripts/eval_calibration.py`:** synthetic truth (every synth scene's true camera, clicked with Gaussian noise, through the production path) → focal %, rotation °, position m. On real `samples/real/*.landmarks.json` it reports reprojection only.
* **`scripts/eval_moments.py`:** a scorecard of a processed game against a hand list (`replay.moments-truth.v1`): tracking (ids, coverage, concurrency, off-court share), X gestures vs truth, events, plays and highlights per moment, hype, reel, replay angles and POVs, stage timings, with optional annotated frames.
* **`scripts/eval_scene.py`:** re-renders a synthetic game from orbit offsets and compares the scene package (reference renderer) for silhouette IoU and player-region PSNR.
* **`courtcam eval-events`** (`eventeval.py`): play-log truth (`replay.playlog.v1`, `use: evaluation`, never imported by the pipeline). Greedy shot matching within `tol_s`, team mapping, score error, highlight precision@k. **`courtcam eval`**: CLEAR-MOT / IDF1 / court error vs synthetic ground truth. **`players_eval.py`**: recall, ghosts and team accuracy vs hand-labelled instants.
* **`courtcam synth`:** 5 scenes (basketball half/full, pickleball, badminton, volleyball) with articulated mannequins, a ballistic ball, scripted plays, X / voice / tap triggers, Kokoro voice lines, crowd and contact audio; deterministic by seed; labelled synthetic ground truth.
* **CC BY footage** (box only; video files never committed; attribution in `docs/test-data.md`):
  * Basketball: **"25th October 2015 – Nottingham Wildcats vs Barking Abbey Crusaders wide angle cam"**, Super League Basketball (video © Peter Kaloczy), youtube.com/watch?v=aH6PRcV4DHE, CC BY 3.0, 1080p30. The public demo game `g_c8b6186280ac` is its Q1 cut, with hand truth for Q1 and Q3 (`samples/truth/nottingham_q1*.json`, `_q3.json`, `nottingham_q1_players.json`).
  * Basketball 3x3: "ČBF 3x3 Tour 22.6. Ústí nad Labem", Honza Nový, Wikimedia Commons, CC BY 3.0 (a lens-corrected fixed shot).
  * Basketball 2v2: "2v2 BASKETBALL GAME", M'ster Lewis (z5bdgHqcShw), CC BY 3.0, with hand GT (`basketball_2v2park.json`, `_dev.json`).
  * Basketball 2v2: "Fun 2v2 Basketball – Best of 2 series – vol-1", JaiArtHub (7MloXoCl6LU), CC BY 3.0.
  * Pickleball: two tournament matches by **pickleball4you** (4M58YJoZ4O4, wY_KUvQ8w7I), CC BY 3.0, fixed tripod behind the baseline. The channel has dozens more under the same licence.
  * Badminton: "2012 US Badminton Adult National Championships Mixed Doubles QF", Roy Huang (654WkfWSYf0); "Badminton recorded with fisheye lens (Hans & René)", bvconquesto (B9XLUHQfh4A, net-post fisheye, test only).
  * Volleyball: "West Washington" school livestream, CC BY, **local only because the players are minors** (D-76). Never use it.
  * `samples/real/*` are YouTube standard licence, local only, never public.

---

## 3. Mapping: Replay → Trophy

Reuse modes:
* **As-is:** pip-install courtcam or call its function unchanged.
* **Adapt:** port or modify the code or contract.
* **Reference:** reimplement from the documented method; no code copied.

Effort is hours for one Trophy engineer, including glue and a smoke test on Trophy's own data. Licences: courtcam and the rest of Replay are MIT. **The licence is not the constraint; the hackathon rule is (§6).**

| # | Replay feature / method | Trophy feature | Mode | Effort (h) | Licence notes |
|---|---|---|---|---|---|
| 1 | `calibrate.py` (any ≥ 4 template landmarks, RANSAC, gate = max(5 px, 1 % of span), `orient_labels` mirror fix, `fit_standards`) | **F3** per-phone homography | As-is (courtcam) or adapt | 2 | MIT, OpenCV Apache |
| 2 | `camera_calibration` (focal from homography via Zhang + `solvePnP` with height landmarks, mirrored rigs) | **F3** full pose for F4 triangulation and F16 | As-is | 1.5 | MIT |
| 3 | `distortion.py` one-parameter k1 division model, gated | **F3** wide or ultrawide phone lenses | As-is | 1 | MIT |
| 4 | `templatefit.py` auto court fit (line mask → Hough → template quads → distance-transform score, physical-camera snap, `ok` ≥ 0.90) | **F3** "suggested corners" (replaces TennisCourtDetector / CourtKeyNet for court sports) | As-is, suggestions only | 2 | MIT; weak on low phone angles (refused on all real basketball clips) |
| 5 | `court.fit_check` (`trusted` flag when people disagree with the fit) + D-72 refusal of `ok=false` | **F3 / F9** call-tier gate: an untrusted calibration demotes calls to BETA or PLAYERS | Reference | 1 | n/a |
| 6 | Court template JSON + sport-profile YAML (no sport branching; `events:`, `plays:` grammars, `scoring:`, `rally:`, `query_vocab`) | **F8** rule-pack `field` / `detectors` / `scoring`; the engine never branches on the sport | Adapt (schema + loader) | 3 | MIT |
| 7 | Play grammars (`plays.py` IDLE/OPEN machine and `sequence`) | **F8** rally and possession segmentation feeding rule evaluation | As-is or adapt | 2 | MIT |
| 8 | On-court filter + bystander removal (`court.py`) | **F6** people filtering at casual venues (benches, spectators, next court) | As-is | 1 | MIT |
| 9 | Identity: jersey HSV 8×4×4 k-means, `net_side`, **`matchup_teams`** (2v2/3v3), K-person roster solve, appearance cuts, `fill_gaps`, officials cap | **F6** teams (instead of or before SigLIP+UMAP+KMeans) and stable ids for coach and stats | Adapt (per-camera; feed it RF-DETR+ByteTrack boxes through a custom `Detector`) | 4 | MIT; keep YOLO out (AGPL) |
| 10 | `ball.py` ball-at-rim make/miss (classical CV, rim units, "can't tell" at the rim edge) | **F6 / rank 12** basketball make/miss (replaces reimplementing the no-licence shot-tracker repo) | As-is | 2 | MIT, no model; Q1 P/R .90/.90, make/miss 8/9 |
| 11 | Pose on upscaled track crops (`pose.py`) | **F6** pose on far players (rtmlib BodyWithFeet on crops) | Reference (swap in rtmlib) | 1 | YOLO-pose AGPL: don't use; ViTPose Apache is OK |
| 12 | `audio.py` numpy spectral-flux onsets, RMS, hype and speech segments | **F5** server-side onsets on the full recording (post-game), crowd hype for **F15** | As-is | 1 | MIT |
| 13 | Rally segmentation (median court speed + hysteresis), `one_touch` sides, serve side, side-out, `server_behind_line` winner | **F8** pickleball, badminton and volleyball scoring templates; **F13** rally boundaries for clip fetch | Adapt | 3 | MIT; real badminton P 1.00 / R .86 |
| 14 | `detect_possessions` (team geometry vs the attacked rim) | **F6** possession / "Off you" (rank 6) prior | Reference | 1.5 | MIT |
| 15 | `detect_lost_man` | **F11** coach card for basketball ("you lost your man here"); new Trophy moment type | Adapt | 2 | MIT; tuned on 1 example |
| 16 | X-gesture trigger (`triggers.py`: crossed forearms, faces-camera gate, hold times) | **F13** hands-free **"challenge" gesture** (and "clip that") | Adapt | 2 | MIT; YOLO-pose 0/22 on far players, so use rtmlib or ViTPose |
| 17 | Trigger → play resolution ([T−8 s, T+0.5 s], clip = play ± 1 s, ownership) | **F13** a challenge or voice command resolves to the right rally | As-is | 0.5 | MIT |
| 18 | Whisper-small + difflib command parser | **F13** voice fallback if Deepgram is down; Trophy keeps Deepgram for the prize | Reference | 1 | Whisper MIT |
| 19 | `metrics.py` CLEAR-MOT/IDF1, `eventeval.py`, `eval_moments.py`, `players_eval.py` | **S6** sport wall and accuracy; F6 "id-switch rate" test | As-is | 2 | MIT |
| 20 | `courtcam synth` (5 sports, labelled ground truth, scripted plays, triggers, audio) | **F8** "recorded event logs replayed are the unit tests"; CI fixtures; **F10** house-rule replay traces | As-is (basketball, pickleball, badminton, volleyball only) | 2 | MIT |
| 21 | Director rules (`cuts.json`) + `camera.smooth` operator spring | **F14** auto-director: Viterbi picks the phone; Replay's rules do the in-camera virtual framing and replay insertion | Adapt | 3 | MIT |
| 22 | Compositor + graphics (score bug, LIVE/REPLAY bugs, lower thirds, sting, telestrator ring, trail and shot arc, ducking) | **F14** trophy clip (a Python/FFmpeg fallback to Remotion), **F13** evidence overlays | Adapt | 3 | MIT; Barlow OFL; FFmpeg libx264 GPL as a subprocess only |
| 23 | Hype meter (noisy-or of loudness, arms-up and speed) + best-play rule | **F15** highlights (add PANNs cheer classes and call events) | Adapt | 2 | MIT |
| 24 | Highlight selection (`virtual/replays.select`: best → triggers → story events → fill) | **F15 / F14** "Play of the Game" pick | Reference | 1 | n/a |
| 25 | Reel (`reel.py`) and vertical 9:16 (`vertical.py`) with event-only captions | **F14** trophy clip; recap email (AgentMail) attachment | Adapt | 2 | MIT |
| 26 | Condensed game + rally browser | **New N2** | Adapt | 2 | MIT |
| 27 | **Grounded commentary**: templates + `grounding.check` validator over an LLM paraphrase | **F12** (the "can't invent plays" guarantee for Claude streaming); also F11 coach text and F9 "why" strings | Adapt (extend the action classes to 28 sports) | 4 | MIT; swap Kokoro → Cartesia (prize), Qwen → Claude |
| 28 | Kokoro-82M TTS | **F12** offline or backup voice (if Cartesia is throttled) | Reference | 1 | Apache-2.0; espeak-ng GPL via `espeakng-loader` (subprocess) |
| 29 | Query engine (rules → LLM json_schema filter + `validate_filter`) | **F19** "ask the ref" and **new N5** play search | Adapt | 2 | MIT |
| 30 | SigLIP keyframe + text embeddings with RRF ranking | **New N5** "find the play where…" | Adapt | 2 | open_clip MIT, SigLIP weights Apache-2.0 |
| 31 | Advice (grounded per-player stat lines) | **F11** coach (stat half), recap email | Adapt | 1.5 | MIT |
| 32 | Stats (box score, shot chart, heatmap, distance covered) + review queue ("can't tell" → a human settles it) | **F13** PLAYERS tier and challenge UX; **F8** calibration labelling; new N6 | Adapt | 3 | MIT |
| 33 | `edits.json` correction overlay re-applied after every cached stage | Post-game: challenge outcomes and name/team fixes survive re-processing | Reference | 1 | n/a |
| 34 | Follow-cam (client spring camera, `follow.ts`; server `croppath.py`) | **New N1** follow a player; **F13** zoom on the actor | As-is (TS) / adapt | 2 | MIT |
| 35 | Tier A angles (wide / follow / tight iso, time-aligned) | **F13** challenge replay per phone; **F14** | Adapt | 1.5 | MIT |
| 36 | SAM 2.1 chunked, re-prompted masks (`segment.py`) | **F16** cutouts; **F17** precise privacy masks (better than face boxes) | Adapt | 3 | SAM 2.1 Apache-2.0; ~26 ms per object per frame; use the CUDA path, not the ROCm bf16 workaround |
| 37 | Tier B 2.5D + **scene package** + WebGL2 Free view (orbit, broadcast high, push-in) | **F16** 3D replay (licence-clean instead of GVHMR/SMPL); presets courtside / top / **broadcast-high** | Adapt (Three.js reader of `layout.json`) | 6 | MIT + SAM Apache. Trophy has 2–4 phones, so the multi-view envelope is wider |
| 38 | Image-based virtual views + **Player's view** POV (`imageview.py`, `proxy.py`) | **F16** "first-person from the head joint" preset | Adapt | 6 | MIT; MotionBERT is research-grade (H36M): keep the analytic fallback |
| 39 | Tier D findings (MoGe-2 plate, VGGT NC, gsplat on CUDA) | **F16 / F18** decisions | Reference | 0 | MoGe-2 MIT is OK; VGGT-1B NC is not |
| 40 | Faces: YuNet + SFace, consent enrollment, enrolled-only matching, suggestions only | **F17** privacy blur (blur everyone not enrolled; deface fallback) and auto-naming | Adapt | 3 | YuNet MIT, SFace Apache (training data undocumented); insightface rejected (NC) |
| 41 | Moments + best-play rule | **F15**, **new N3** moments browser | Adapt | 2 | MIT |
| 42 | Worker DAG with a content-hash cache, fan-out, GPU lock | Post-game pipeline on the Vultr L40S (RIFE, SAM, renders) | As-is | 2 | MIT |
| 43 | Presigned multipart upload + resumable parts | **F1/F2** recording upload (port to GCS resumable or signed URLs) | Reference | 2 | MIT |
| 44 | Worker claim protocol (pull runner, no cloud creds on the GPU box) | Vultr render box ↔ GCP gateway | Reference | 2 | n/a |
| 45 | HMAC per-game phone tokens with route allowlists; QR handoff | **F1** join-by-QR security | Reference | 1.5 | n/a |
| 46 | react-native-tvos Fire TV app + tv-core | **New N4** TV app (prefer a web "TV mode" on a laptop or cast) | Reference | 8+ | MIT; needs a device and signing. Not worth it in 36 h |
| 47 | Alexa skill + TV command queue | **New N7** "Alexa, ask Trophy to challenge / clip that" | Adapt | 4 | MIT; Alexa console setup and certification are a risk |
| 48 | CC BY footage list (Nottingham, 3x3 Ústí, 2v2 park, JaiArtHub, pickleball4you, Roy Huang) + hand truth files | Trophy clip library (basketball and pickleball fallbacks) | As-is with attribution | 1 | CC BY 3.0; the truth JSON files are in the Replay repo (MIT) |
| 49 | `docs/licenses.md` (74 KB) | Trophy's licence table (SMPL, GVHMR, insightface, VGGT, openWakeWord flagged) | Reference | 0.5 | n/a |

**Not useful for Trophy's live ref:** Replay is post-game batch on one fixed camera. It has no live path, no ball tracking outside a rim box, no 3D ball, no bounce or line calls, no table-tennis, field, target or resting-object families, no multi-camera fusion, and no clock sync. F2, F4, F7, F9, F10 and F18 get nothing direct.

---

## 4. Features Replay has that Trophy's plan doesn't

| # | New feature | Replay source | Cost to add | Fit |
|---|---|---|---|---|
| N1 | **Follow a player** (pick on video, spring camera, "Lost sight of", hand-off) | `tv-core/follow.ts`, `croppath.py`, `render/camera.py` | 2–3 h on the web dashboard | High; easy demo wow |
| N2 | **Condensed game** + rally browser ("RALLY n/N · X shots") | `condensed.py` | 2 h | High for net sports |
| N3 | **Moments browser** with filters (Scores / Calls / Bookmarks), "your clips" and "your notes" as moments, **best play ★** | `moments.py`, `MomentsLayer.tsx` | 2 h | High; pairs with the call log |
| N4 | **Player's view** (virtual POV from real pixels) and **Orbit / Broadcast high / Free view** | `imageview.py`, `tierb.py`, scene package | 6–12 h | Medium; overlaps F16, heavy |
| N5 | **Search plays in plain English** ("Ana's steals in the second half") with grounded filters | `query.py`, `search.py` | 3–4 h | Medium-high; reuses Moss and Claude |
| N6 | **Stats panel**: box score, shot chart, heatmap, distance covered; **Review queue** for "can't tell" items | `stats.py`, `review.py` | 3 h | High for the post-game analyzer |
| N7 | **Alexa** "ask Trophy to clip that or challenge"; Fire TV **TV app** | `alexa/*`, `apps/tv` | 4 h Alexa / 8+ h TV | Low for Cal Hacks (no Amazon prize) |
| N8 | **X-gesture** commands (challenge or clip without a phone in hand) | `triggers.py` | 2 h | High; complements Deepgram voice |
| N9 | **"Lost his man"** defensive-lapse moments; possession causes (steal, rebound, inbound) | `events.py` | 2 h | Medium (basketball only) |
| N10 | **Player profiles and collectible cards** with career stats, cross-game linking, consented face naming | `profiles/*`, `card.py` | 4 h | Medium |
| N11 | **Highlight reel** export (16:9 / 9:16), the user's clips first, best play last | `reel.py`, `vertical.py` | 2 h | High (recap email) |
| N12 | **Pickup scoring modes** (1s & 2s to N, restart) and phone team overrides | `ScoringCfg`, `PUT /scoring` | 1 h | High (casual games) |
| N13 | **Play-log notes** (CSV/JSON) shown as moments and used as evaluation truth | `playlog.py`, `eventeval.py` | 1 h | Medium (S6) |
| N14 | **QR phone handoff** with scoped tokens (Clip / Tag / Review / Search / Reel) | `phone-link`, `auth.PHONE_ROUTES` | 2 h | High; maps to the PWA |

---

## 5. Measured numbers worth quoting (all Replay's own)

* Calibration (synthetic): focal 0.25–0.64 %, rotation 0.11–0.28°, position 4–8 cm. Real floor reprojection 0.03–2.64 px; hoop 53–92 px off on wide rigs.
* Tracking: synthetic basketball IDF1 0.31–0.37; net sports 0.79–1.00. Nottingham player recall 0.876 and team accuracy 0.98 (D-97). 2v2 follow on the right person 94.7 % (park), ~60 % (dark tops).
* Ball make/miss: Q1 shots .90/.90 and make/miss 8/9; Q3 hold-out .80/1.0 and 7/8; park hold-out 1.0/.80 and .714.
* Rallies: real badminton P 1.00 / R 0.86–0.93; synthetic points .96/.89.
* Triggers: voice 37/37 synthetic; gesture 22/22 ground-truth pose with 0 FP; 0 false triggers in 480 s of real footage; demo 5/5.
* Commentary grounding: 28/28 template, 26/28 LLM; Kokoro RTF 0.085.
* Hype: synthetic P .86–1.0; real top-5 0.2–0.4.
* Tier B: IoU 0.35–0.80 held-out; Tier C MPJPE 125–139 mm; SAM 26 ms per object per frame.
* Throughput: Kennesaw 240 s in 76 s cold; Nottingham 261 s default, 693 s with everything; demo game replays ~12 min.

---

## 6. Risks

### 6.1 Pre-existing work and the "all work done during the event" rule

* **Everything in Replay predates Cal Hacks 13.0.** The repo was created 2026-09-22. 146 commits, the last code commit 2026-10-23 09:23 UTC, before hacking opens Friday evening PT. It was **submitted to another hackathon** (Amazon Developer Hackathon: Fire TV track, AWS Builder and Open Source mini-challenges) on 2026-10-23. Re-presenting its features as Trophy's work would be (a) pre-existing code and (b) a double submission. MLH-style rules (check Cal Hacks 13's own page) usually allow open-source libraries and public code with disclosure, but not continuing a project or re-submitting one. Judges can see the commit dates.
* **What is separately published open source:** `subatomic-hamster/courtcam`, MIT, a standalone repo (created 2026-10-23 16:33 UTC from a subtree split with 33 commits of history). This is the cleanest thing to depend on: `pip install git+https://github.com/subatomic-hamster/courtcam@<sha>` as a **third-party library**, credited in the README and on Devpost as pre-existing open source ("courtcam, MIT, by the Replay team"). Note the standalone repo is only hours old, and its history shows it was written for Replay.
* **Everything else** (`render/`, `services/`, `apps/`, `packages/tv-core`, `infra/`, `alexa/`) became MIT only at 17:13 UTC on Oct 23 and is **not** a separate library. Copying it into the Trophy repo is copying another hackathon project. Safe options: treat it as **reference** (reimplement from the documented methods in `docs/decisions.md` / `scene-format.md`, which are public design notes), or vendor it as a clearly marked, unmodified third-party directory with disclosure. The "Adapt" rows in §3 should be **rewritten in the Trophy repo during the event**, not copied. Typing the method in fresh is about the same effort as porting.
* **Team overlap:** the Replay demo footage names "Anshul" and "Joseph", and hfbox's GPU lock path is `/workspace/airtools/...` (the AirTools project). If Trophy's team overlaps with Replay's, say so on Devpost: "we built Replay/courtcam before the event; at Cal Hacks we built X on top." That is the honest framing, and a strong one.
* **Media and data:** the owner's demo game, the `samples/real` YouTube clips and the volleyball footage (minors) must never appear in Trophy. Only the CC BY clips (with attribution) and synthetic data are usable.

### 6.2 The hfbox dependency

* Every number was measured on a **private shared AMD RX 9070 XT ROCm box** (16 GiB cgroup RAM, reached over Tailscale Funnel, other agents' locks). None was measured on NVIDIA or CUDA, which is what Trophy will use (GCP L4, Vultr L40S).
* ROCm-specific code is baked in:
  * `torch.backends.cudnn.enabled=False` for Kokoro, Whisper, SigLIP and MotionBERT.
  * SAM 2 forced to bf16.
  * llama.cpp HIP builds with `rocmlibs/` symlinks.
  * The CTranslate2 CPU-only note.
  * Default paths `/workspace/wt/replay-env/...`, `REPLAY_MODEL_VENVS`, and the GPU lock `/workspace/airtools/.gpu.lock` (it falls back to the cache dir elsewhere).
  * Models load through `providers/_runner.py` subprocess venvs.
  * Budget a few hours to make it run on CUDA, and re-measure speeds there.
* The live Replay runner (tmux `replay-runner`) and its keys live on hfbox. If Trophy uses hfbox at all, it competes with Replay's demo for the GPU lock, and the box has no auto-restart after an OOM. **Recommendation: don't put Trophy on hfbox.** Trophy's plan is already cloud-only (GCP / Vultr).
* The README says the worker runs on "EC2 GPU", but `infra/` has no EC2 resource, and HANDOFF says the EC2 GPU quota is 0 and the GPU runs on hfbox. Don't rely on an AWS GPU path from this repo.

### 6.3 Technical fit

* **Python 3.12 only** (`requires-python >=3.12,<3.13`). Trophy's containers are 3.10–3.11 (BlurBall, WASB, RIFE). courtcam needs its **own py3.12 container** (OK under Trophy's one-venv-per-process design) or `--ignore-requires-python` (untested).
* **AGPL:** the default detector and pose path is ultralytics YOLO11 (AGPL-3.0). Trophy should install courtcam **without** `[yolo]` and pass its RF-DETR + ByteTrack boxes through the `Detector` protocol (`FrameDets`), plus rtmlib pose. Effort ~2 h. Never ship the `[yolo]` extra.
* **Single fixed camera, post-game batch.** Nothing in Replay is live: Kennesaw ran at 3.1× realtime cold; events take 43–47 s per 240 s on CPU. Trophy's 0.3–0.7 s live calls must not wait on courtcam stages. Use courtcam for calibration, teams and post-game analysis per phone. There is no cross-camera identity or triangulation.
* **Only 4 sports** (basketball, pickleball, badminton, volleyball), all court sports. The other 24 Trophy sports need new templates and profiles, and the flight, resting and audio families have nothing here.
* **Accuracy ceilings Replay itself reports:**
  * Identity fragments on long games (59 ids for ~13 people).
  * Both teams can get the same label with alike kits.
  * Autocalibration is refused on real basketball (scores 0.61–0.888).
  * No basketball block detector.
  * The ball is tracked only near the rim.
  * The X gesture fails on far players with YOLO-pose.
  * Virtual views show only some players on older runs and ghost at 45–55°.
  * Several thresholds (lost man, X sign) were tuned on one video.
* **Heavy GPU stages:** SAM 2.1 is ~1 GPU-minute per 8 s play, and full replays ~12 min per game. Keep them on the Vultr box and outside the live demo path.
* **Licence tails if adopted:** MotionBERT (Human3.6M-trained; keep the analytic fallback), SFace (training data undocumented), ECAPA (VoxCeleb research terms), espeak-ng (GPL, inside Kokoro), FFmpeg libx264 (GPL; subprocess only), openWakeWord and VGGT (non-commercial; don't use).

### 6.4 Suggested stance for the weekend

1. Depend on **courtcam** as a disclosed, pinned, MIT third-party library for F3 calibration (`calibrate`, `distortion`, `camera_calibration`, `templatefit` as suggestions), the F6 on-court filter and teams (`identity` with a custom Detector), F6 basketball make/miss (`ball.py`), F5 / F15 audio (`audio.py`), and the S6 metrics and `synth` fixtures.
2. **Reimplement during the event**, from the public design notes, the ideas that are Replay-app code: grounded commentary validator (F12), hype + best-play + condensed + moments (F15, N2, N3), follow-cam (N1), the X-gesture challenge (N8), review queue and "can't tell" (F13), and query/search (N5).
3. Skip the Fire TV app and Alexa for Cal Hacks (no matching prize, device and signing risk). Treat the scene package and Player's view as a P2 reference for F16 only if F16 is reached.
4. Say on Devpost exactly what is pre-existing.
