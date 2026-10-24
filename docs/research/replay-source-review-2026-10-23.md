# Replay and courtcam: direct source review (2026-10-23)

*The planning lead reviewed both repositories directly, reading fresh clones without running any code from them. This review supersedes the parts of [replay-repo-inventory.md](replay-repo-inventory.md) that it corrects. Every number quoted here is **Replay's own figure**, measured on Replay's private AMD RX 9070 XT ROCm box. None of them has been reproduced in Trophy.*

| Repo | Commit reviewed | Date | License |
|---|---|---|---|
| [subatomic-hamster/replay](https://github.com/subatomic-hamster/replay) | `2db92c0e30f22ece0ffbee0d5d39ea7012cf0011` | 2026-10-23 13:13 −0400 | MIT, "Copyright (c) 2026 Replay" (root `LICENSE`) |
| [subatomic-hamster/courtcam](https://github.com/subatomic-hamster/courtcam) | `b2f5ff582261ba680d7348149e5262ef43cab858` | 2026-10-23 12:41 −0400 | MIT, same copyright line |

When you vendor any file, copy the MIT notice into the vendored directory (for example `third_party/replay/LICENSE`) and add a row to `docs/licenses.md` with the source path and the commit above.

---

## 1. Replay: what to take

| Replay path | What it is | Verdict | Trophy consumer | Effort |
|---|---|---|---|---|
| `packages/tv-core/src/{types,discovery,replays,follow,clock,retry,display}.ts` | Pure TS with no dependencies and no React: data contracts, moment/best-play/hype/rally/caption helpers, the follow-cam spring, a media clock and retry helpers | **Vendor as-is** into `apps/watch/src/vendor/tv-core/` | Trophy Watch (Agent 1) | S |
| `packages/tv-core/src/{api,mock}.ts` | API client and a 2.4k-line mock (`X-Replay-Key` header, Replay routes) | **Adapt.** Repoint them at the Trophy post-game API | Trophy Watch | S |
| `apps/web` (Vite 7, React 19.2, TS 5.9 strict, 47-line router) | The browser "TV" screens: Library, Watch, Highlights, Replay angles, Clips, Rallies, Search, Advice, Review, Players/Profile. Plus the phone upload pages | **Adapt.** The `/tv/*` screens assume a D-pad (`platform/keys.ts`, `focus/spatial.ts`), so re-lay them out for pointer and touch. Liftable: `PlayerSurface.tsx` (`<video>` + CSS-transform crop), `SeekBarEvents`, `CourtInset`, `SelectOverlay`, `FollowFrame`, `Clips`, `Rallies`, `Search`, `Review`, `Highlights` | Trophy Watch | M |
| `apps/tv/src/scene/FreeView.web.tsx` + `scene/camera.ts` | Framework-free WebGL2 2.5D free-view player (imports only React and tv-core types) | **Vendor as-is** | Watch replay angles (P2) | S |
| `apps/tv` (react-native-tvos 0.87) | Fire TV app | **Skip.** Reimplement `MomentsLayer`, `Timeline`, `AngleView`, `StatsPanel` and `PlayerCard` in the DOM | — | — |
| `services/api/replay_api/auth.py` | Per-game HMAC upload/phone tokens + route allowlist | **Adapt** for gateway `cam_token` | Gateway (Agent 1) | S |
| `services/api/replay_api/cloud.py` | S3 storage, presigned `/media` 302 redirects, an **S3 job queue with `IfNoneMatch="*"` claims** (`cloud.py:400-409`), `remote_runner.py` pull runner | **Adapt** for post-game jobs on AWS | Post-game (Agent 1 infra, Agents 2 and 3 jobs) | M |
| `services/api/replay_api/{moments,stats,edits}.py`, `narrate/grounding.py`, `providers/query.py` | Moments rebuilt from events; box-score stats; a user-edit overlay; **grounded narration validator**; free-text query → filters | **Adapt** | Watch backend, commentary (Agent 3) | M |
| `services/worker/replay_worker/{dag,cache}.py` | Stage DAG + content-hash cache (`fcntl` flock, POSIX only, fine on macOS and Linux) | **Adapt** for the post-game pipeline | Post-game (Agent 2) | M |
| `render/replay_render` | Director (`cuts.json`), ffmpeg compositor, score bug / lower thirds / telestrator, hype, condensed, vertical 9:16, reel, `virtual/*` (SAM 2.1 via `transformers.Sam2VideoModel`) | **Adapt:** director, graphics, condensed, reel and vertical run on the CPU. Keep SAM on an NVIDIA GPU and **undo the ROCm-isms** (`cudnn.enabled=False`, forced bf16). No Remotion here, so Trophy's Remotion trophy clip stays separate | Trophy clip and condensed game (Agent 1) | M |
| `infra/lib/cloud-stack.ts` (CDK 2.272) | **The only deployed stack.** S3 media bucket (block-all, SSE, enforce-SSL, multipart-abort lifecycle, CORS exposing `ETag`/`Content-Range`), CloudFront + OAC + SPA rewrite, a Lambda Function URL API, least-privilege IAM, SSM-parameter secrets | **Adapt** for Trophy's AWS deployment (recordings bucket, Watch hosting, secrets) | Infra (Agent 1) | S–M |
| `infra/lib/{data,pipeline}-stack.ts` | Synth-only placeholders (DynamoDB; Step Functions → SageMaker `ml.g5.xlarge`) | **Skip.** They were never deployed | — | — |
| `scripts/{cloud-smoke,eval_moments,eval_calibration,eval_scene}.py` | End-to-end smoke check and evals | **Adapt** | Evals and sport wall (Agents 2 and 3) | S |
| `scripts/box-*.sh`, `scripts/hfbox/*`, `record-e2e.sh` | Replay's private GPU-box scripts (`/workspace` paths, `/proc`) | **Skip** | — | — |
| `alexa/`, `alexa_routes.py` | Alexa skill | **Skip** | — | — |

**Replay data formats Trophy aligns with** (`courtcam/courtcam/schema.py` mirrored in `packages/tv-core/src/types.ts`). Trophy's live contracts ([interfaces-v1.md](../plan/interfaces-v1.md)) are **not** these. The live pipeline needs game-clock timestamps, multi-camera and tiered calls. Trophy Watch's post-game API should emit Replay-shaped `Moment`, `BestPlay`, `Clip`, `Tracks` and `Cuts` documents, so the vendored tv-core and web components work unchanged. Key shapes:
- `Moment {id, t, t_start, t_end, kind: score|play|bookmark, label, player?{id,name,number,color_hex}, thumb_url, source?, confidence?, confirmed?}`
- `GameEvent (replay.events.v1) {id, type, t_start, t_key, t_end, player_id?, court?: [x_m, y_m], confidence, source: heuristic|vlm|user, confirmed, team?, points?, …}`
- `Tracks (replay.tracks.v1) {t0, rate_hz, frames: [{t, p: [{id, bb: [x,y,w,h] normalised, ct?: [x_m,y_m], c?}]}]}`
- `Cuts (replay.cuts.v1)`, `Clips (replay.clips.v1)`, `Triggers (replay.triggers.v1)`, `Score (replay.score.v1)`: two-team cumulative only
- Replay times are **video seconds from the start of the one recording**. Trophy's post-game exporter converts `t_game_s` into each recording's media time using that camera's clock fit.

### 1.1 Corrections to the earlier inventory
1. **AGPL is the default in the Replay workspace.** The root `pyproject.toml` line 6 depends on `courtcam[yolo]` (ultralytics). **Install courtcam on its own, from its standalone repo, without the `[yolo]` extra.** Never `uv sync` the Replay workspace into a Trophy environment.
2. **Replay commits frames of a private game.** `docs/media/*.jpg|gif` (for example `tv-follow.jpg`) show identifiable players and bystanders, and `samples/real/*.landmarks.json` includes the owner's game. **Do not copy `docs/media/` or `samples/real/`.** The labels in `samples/truth/*.json` cover CC BY clips, and those videos need attribution (`docs/test-data.md`).
3. **Replay has no face blur or anonymisation**: every "blur" in the code is a UI backdrop blur. Consent exists only for face *matching* (`tv-core/profiles.ts:232-242`, `providers/face.py`). Trophy's privacy blur (F17) must be built new.
4. Follow mode in `apps/web` uses server-side crop paths (`cropRectAt`). The client spring (`createFollowCam`) is used only by `apps/tv`.
5. FreeView (WebGL2) is portable as-is, so it's less work than the inventory's 6–12 h estimate.
6. There's **no live or phone-capture code** anywhere in Replay: no `getUserMedia`, `MediaRecorder`, WebRTC or aiortc. Phones upload a file with `<input type=file>`. Trophy's capture, ingest and live loop are all new work.
7. Test counts in the inventory (192/308/28/54) are Replay's doc figures. Counting test functions gives 171/230/30/72; parametrisation explains the gap. Nothing was re-run.
8. Compatibility: everything is **Python 3.12 only**; Node 22 and React 19.2 for the web; **no Apple Silicon handling** (SAM falls back to CPU fp32, which is about 10× slower than GPU bf16 per Replay's numbers); `h264_encoder()` doesn't use `h264_videotoolbox`.

---

## 2. courtcam: what to take

The `courtcam/*.py` package and `sports/*` are **byte-identical** in the standalone repo and in Replay's `courtcam/` subtree. Depend on the **standalone** repo at `b2f5ff5`. **Do not redistribute its `docs/demo.gif`**: in the standalone repo it is real footage of a 2v2 pickup game (Replay's copy is synthetic).

### 2.1 Batch vs. live
- **The pipeline is batch and file-to-file** (`pipeline.py:1`). `run()` (`pipeline.py:653`) transcodes the whole video to a 30 fps CFR mezzanine first. The `Detector` protocol is file-based: `__call__(video: Path, *, stride, max_frames) -> Iterator[FrameDets]` (`detect.py:86`). `identity.identify`, `ball.scan`, pose and events all decode the video themselves.
- **Per-frame-callable pure functions that the live path can use:** `calibrate.homography / calibrate / camera_calibration / camera_matrix / project`, all of `distortion.*`, `court.to_court / inside / polygon_px`, `triggers.detect_gestures / held / resolve`, `plays.run_machine / run_sequence`, `audio.features / onsets`, `ball.arrivals` and `_made`, and the setup-time `autocalib.autocalibrate` (4–12 s per frame, so suggestions only).
- **Windowed logic that must be re-run on a rolling buffer:** `held()` (0.8 s), `ball.arrivals` (1.0 s after, 3.0 s rearm), `court.fit_check` and `on_court` (whole tracklets), `rally_segments` (2.5 s smoothing). Nothing in courtcam is incremental out of the box.
- **Python 3.12 is declared but not required by the syntax.** Every file parses under 3.11.9: there are no PEP 695 generics and no 3.12-only stdlib calls. Nothing was run. The **real conflict is `opencv-python-headless` vs. `opencv-contrib-python`**, which both provide `cv2`. Keep courtcam in its own venv (`services/courtcam-adapter`, py3.12 as declared), or install it `--no-deps` in a shared env.

### 2.2 APIs Trophy uses (units and conventions)
| Module | Key API | Notes | Verdict | Consumer |
|---|---|---|---|---|
| `calibrate` | `homography(landmarks_px: dict[str,(x,y)], template) -> (H px→m, residuals_px)` (`:35`); `calibrate(landmarks, profile, variant, *, max_error_px=5, standard)` → `courtcam.calib.v1` {H, H_inv, residuals_px, court_polygon_m/px, labels_swapped, …} (`:191`); `camera_calibration(calib, profile)` → {K, R, t, dist [k1], focal_px, camera_position_m, mirrored} (`:375`, needs `image_size`); `camera_matrix` → 3×4 P (`:471`) | **RANSAC only with ≥ 6 landmarks** (`RANSAC_MIN_POINTS = 6`, `:28`); 4–5 points use plain least squares. The gate is max(5 px, 1% of click span). Mirrored labels get fixed (`labels_swapped`) | **Depend** | Agent 2: `/calibrate` (M1); K, R, t per phone for serve-toss height (M2) and triangulation |
| `distortion` | `undistort_points(pts, k1, (w,h))`, `estimate_k1(px, m, size)` (≥ 8 points and ≥ 30% gain) | A 1-parameter division model about the image centre | **Depend** | M2 phone lenses |
| `autocalib` / `templatefit` | `autocalibrate(frame_bgr, profile, …) -> Proposal{landmarks_px, ok, score, k1}`; `ok` needs a score ≥ 0.90 | Slow, and refused on real basketball. **Suggestions only.** The VLM backend defaults to `claude-sonnet-5` | Depend (suggestions) | Agent 1's "suggested corners" (M2+) |
| `court` | `to_court(tracklets, H, …)`; `fit_check(…) -> {trusted, on_court_share, height_share}` (`:133-208`) | `trusted` needs ≥ 0.35 of players on the court AND ≥ 0.4 of boxes plausibly person-sized | **Depend.** `trusted = false` → tier ceiling BETA | Agents 2 and 3 (M3) |
| `detect`, `track` | `Detection(track_id, box xywh px top-left, conf)`, `FrameDets(index, t = index/fps, dets)`; `Tracklet(...)`, `feet_px()` | `make_detector` accepts only `"yolo"` (AGPL) or `"synthetic"`. **`run()` can't take a Detector instance.** Either call `detect.run_detect(video, path, MyDetector(), …)` and drive the stage functions, or pre-write `_work/dets.json`. Also **pass `pose="vit"` or `"none"`, or a custom Poser**: `pose="auto"` imports ultralytics | Write an RF-DETR + ByteTrack adapter | Agent 2 (M3) |
| `identity` | `identify(video, tracks, profile, …) -> [PlayerTrack(player_id "pN", team 0/1, color_hex, …)]`; pure helpers `net_side`, `split_teams`, `matchup_teams` | Batch; decodes the video | Vendor and adapt per camera | Agent 2 (M3 teams without pinnies) |
| `pose` | `Poser = (frame_idx, BGR, [xywh]) -> [(kp (17,3) px + score, conf) \| None]` | COCO-17. Backends: yolo (AGPL), vit (Apache), synthetic. **Plug rtmlib in as a Poser** | Adapt | X-gesture (M3) |
| `ball` | `hoops(calib, profile)`; `scan(video, hoops, cfg)` (batch); `arrivals(doc, cfg) -> [Arrival(made: bool \| None, confidence = min(.95, .35+.04n))]` | `made = None` means **"can't tell"** at the rim edge → BETA. Replay's figures: shot P/R 0.90/0.90 and make/miss 8/9 on Nottingham Q1 (**its tuning set**); 0.80/1.0 and 7/8 on the Q3 hold-out | Vendor; make `scan` streaming | Agent 2 (M3 basketball) |
| `triggers` | `detect_gestures(signals, cfg)`; `resolve(t, plays, cfg)` (the play ending in [t − 8 s, t + 0.5 s]); `parse_command` | X-gesture with ViTPose: 9/22 synthetic (P 1.00); YOLO-pose 0/22; 0 real false triggers | Vendor | Agents 1 and 2 (challenge gesture, M3) |
| `plays`, `events`, `profiles` | Grammars (`run_machine`, `run_sequence`); `rally_segments`; `Profile` YAML + template JSON {units m, origin text, size, court polygon, landmarks, features (polylines), net_y, rims} | Templates: basketball (FIBA/NBA/NCAA/NFHS, half and full), pickleball doubles, badminton doubles, volleyball indoor. **No zone polygons** (the kitchen exists only as lines), and **no table tennis or cornhole** | Vendor the templates into rule-pack `field` blocks, deriving zones | Agents 2 and 3 |
| `metrics`, `eventeval`, `playlog` | CLEAR-MOT/IDF1; event matching within `tol_s` | | **Depend** | Evals and the sport wall |
| `synth` | `generate(out, *, sport, variant, duration_s, fps, size, seed, camera: CameraSpec(eye, target, f_px, k1))`: per-frame boxes, court positions, 3D keypoints and **3D ball metres + `ball_px`** | Always label synthetic outputs as synthetic. The same seed with several `CameraSpec`s *may* give multi-view triangulation tests (unverified) | **Depend** for fixtures | Agents 2 and 3 |

**Conventions:** courtcam times are **float seconds from the start of the 30 fps mezzanine** (no game clock, no multi-camera sync), and its ids are per camera (`pN`). Court templates use metres, z up, right-handed, +x to the right sideline and +y into the court. The origin is the **centre of one baseline/end line** (basketball half court: baseline centre under the basket). Trophy maps them as follows: `t_game_s = t_key + camera offset`; `pos_court_m` is re-based to the pack origin; `confidence` → `conf`, noting that it is **uncalibrated**; and `sigma_m` has no courtcam source.

**Gaps that Trophy builds itself:** multi-camera fusion and identity, clock sync, streaming interfaces, ball-flight tracking and bounces, line calls, zone polygons, table tennis and every resting-object sport, `sigma_m`, and calibrated confidences.

### 2.3 courtcam inventory corrections
1. Python 3.12 is declared only (see §2.1). The blocker is the OpenCV wheel clash.
2. Plugging in a custom detector is more than "~2 h through the `Detector` protocol". `run()` takes only a detector name, so you must drive the stages, and you must also override `pose="auto"`.
3. RANSAC needs ≥ 6 landmarks.
4. The identity merge windows of 5 s / 7 m are basketball's values. The defaults are 1.5 s / 2 m (pickleball uses 3 s / 3 m).
5. Replay's make/miss 0.90/0.90 and 8/9 come from its **tuning** clip. The hold-out is 0.80/1.0 and 7/8, and these figures measure the whole shot pipeline, not `ball.py` alone.
6. "Badminton P 1.00 / R 0.86" mixes two in-sample runs (1.00/0.93 and 0.92/0.86).
7. 171 test functions. All are synthetic, and none touch real footage or streaming.
