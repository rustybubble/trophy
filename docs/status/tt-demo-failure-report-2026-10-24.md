# Failed acceptance: two-camera table-tennis demo

Date: 2026-10-24 (America/Los_Angeles)

Branch: `codex/tt-demo-failure-status`

Scope: status and failure reporting only; preserve the existing implementation without fixes.

## Overall status

**The implementation does not satisfy the requested fully functioning demo on the two supplied recordings.** A video player, estimated avatars, manual score controls and synthetic rule examples exist, but the central real-footage perception and referee flow is incomplete and unreliable.

The user's review identifies three blocking failures:

1. **Ball detection glitches can identify the wrong object and make the reported ball position teleport across the screen.** The overlay and trail therefore cannot be trusted as a continuous ball trajectory.
2. **The 3D rendering is not clean enough, and the real ball does not appear in the 3D scene.** Mesh presence and animation are not visual acceptance or validated reconstruction.
3. **Point detection does not work as intended.** The current list is a collection of detector-activity intervals, including arbitrary time splits, rather than verified rally boundaries and automatically determined outcomes.

Earlier descriptions such as “working demo,” “source-derived replay,” or “75 tests pass” must not be interpreted as passing these product requirements. The earlier status and build guide remain implementation records; this report supersedes their readiness assessment. This follow-up made no detector, fusion, segmentation, rendering, scoring, API, test, or configuration fixes.

## Acceptance against the requested flow

| Required behavior | Current state | Acceptance |
|---|---|---|
| Follow the real ball consistently in both clips | False localizations, missing observations and large adjacent-frame jumps; detector switching adds discontinuities | **Failed** |
| Watch a rally, automatically determine the point, update score and speak the call | Recorded footage does not produce automatic point awards; score controls require human resolution | **Failed** |
| Determine meaningful point start/end times | Activity-gap heuristic and 12-second subdivision; no validated legal in-play/terminal-event model | **Failed** |
| Synchronized two-camera source playback | Shared seeking/speed exists; audio offset is approximate and capture-time accuracy remains unverified | Partial infrastructure only |
| Inspect a clean 3D reconstruction with the ball and decisive contact | Approximate body animation; no real 3D ball positions, no reconstructed ball trail/contact | **Failed** |
| Show measured real serve height/direction and evaluate supported faults | No validated metric release/apex/contact measurements on these clips | **Not delivered on real footage** |
| Resolve real edge/top-versus-side contact | No validated contact evidence or real edge accuracy evaluation | **Not delivered on real footage** |
| Challenge a detected point and review the decisive instant | Controls exist, but bookmark is the candidate interval end, not a detected decisive contact; real calls remain pending | Partial UI only |
| Propagate real observations/calls through production services | Metadata export exists; live Redis/Spacetime, Cartesia and AI challenge-vote integration not exercised | **Incomplete** |

## 1. Ball detection: false objects and teleporting positions

### Observed problem and user impact

A wrong detection is still drawn as a ball marker. When the next frame selects a different object, the marker can jump hundreds or thousands of source pixels. A trail can connect those unrelated locations into a false path. Missing detections can also make the marker disappear and later reappear far away. This prevents reliable bounce/contact inference and undermines source-crop selection and point segmentation.

The user directly reported the visual defect. The read-only cache audit below confirms substantial position discontinuities. It does **not** independently label every jump as a false detection: camera motion and genuine motion must be considered when reviewing each interval. No new inference or tuning was performed for this report.

### Read-only continuity audit

Source coordinates are in the original **3840 × 2160** images. Count a pair only when source sequence numbers are consecutive, both positions are finite, and source timestamp separation is greater than zero and at most 0.020 seconds. These clips run at 60 FPS, so normal adjacent separation is approximately 16.67 ms.

The thresholds **384 px** and **960 px** describe displacement exceeding 10% and 25% of image width. They are diagnostic reporting thresholds, **not** calibrated physical speed limits, confidence intervals, or confirmed error counts. Missing frames and reappearances across gaps are excluded, so this table does not capture every visible teleport or dropout.

| Camera | Cached detector | Adjacent valid pairs | Jumps >384 px | Jumps >960 px | Largest jump |
|---|---|---:|---:|---:|---:|
| Side | Conservative color/motion | 3,034 | 55 | 45 | 2,837.0 px |
| Side | Grayscale BlurBall | 2,136 | 32 | 17 | 2,325.4 px |
| Side | Selected hybrid | 3,480 | **213** | **134** | **2,909.8 px** |
| Diagonal | Conservative color/motion | 2,739 | 70 | 28 | 2,075.1 px |
| Diagonal | Grayscale BlurBall | 1,954 | 15 | 6 | 2,496.6 px |
| Diagonal | Selected hybrid | 3,009 | **88** | **41** | **2,496.6 px** |

The selected hybrid has **301 adjacent-frame jumps >384 px**, including **175 >960 px** across both views. Of its >384 px jumps, **174 side-view** and **57 diagonal-view** jumps coincide with a change between neural and color-fallback detector identity. These are descriptive counts on different sets of valid frame pairs; they must not be presented as controlled false-positive rates or proof that every detector switch is wrong. Both component detectors also have large discontinuities on their own.

Machine-readable evidence, source-cache hashes, per-camera counts and the five largest jump examples for each variant: [continuity audit](../../evals/reports/ttclips-continuity-audit-2026-10-24.json).

### Specific source intervals to review

| Camera | Source frames | Source time | Displacement | Cached transition |
|---|---|---|---:|---|
| Side | 6395 → 6396 | 106.5833 → 106.6000 s | 2,886.6 px | Color fallback → neural |
| Side | 6397 → 6398 | 106.6167 → 106.6333 s | 2,909.8 px | Neural → color fallback |
| Side | 5627 → 5628 | 93.7833 → 93.8000 s | 2,764.4 px | Neural → color fallback |
| Diagonal | 5995 → 5996 | 99.9167 → 99.9333 s | 2,260.6 px | Color fallback → neural |
| Diagonal | 5996 → 5997 | 99.9333 → 99.9500 s | 2,496.6 px | Neural → neural |
| Diagonal | 4861 → 4862 | 81.0167 → 81.0333 s | 2,075.1 px | Color fallback → color fallback |

For example, the side hybrid moves from approximately `(648.8, 1327.5)` to `(3504.0, 766.5)` between frames 6397 and 6398. The large visible change is real in the cached coordinates; whether each selected pixel is the ball requires direct source-frame review.

### Code-supported failure mechanisms

- **Neural selection is not a temporally validated track.** `tools/track_tt_blurball.py:track` chooses the connected component with the largest heatmap mass for each output head. The selected location has no hard association, displacement, acceleration, rally-state or cross-camera consistency acceptance gate in that path. A strong response on an unrelated object is retained.
- **Color/motion is not ball identity.** `OrangeTracker.update` in `services/flight/flight/recording.py` filters HSV, component size, compactness and motion, with a weak temporal preference. Skin, paddles or scene details can compete with the ball; camera movement also creates background motion. The earlier broad-color experiment explicitly locked onto skin and was rejected, but the retained conservative variant is not established as free of false objects.
- **Fusion does not reconcile detector disagreement.** `tools/fuse_tt_tracks.py:fuse` retains every nonmissing neural detection and substitutes a color candidate when neural output is missing and its heuristic score is at least 0.6. Source-identity equality prevents timestamp mixing; it does not verify object identity. There is no spatial/kinematic/cross-view check before switching sources, and a wrong nonmissing neural position is not challenged by the color result.
- **Heuristic score is not calibrated correctness.** Neither a heatmap peak nor the color score is a measured probability that the pixel is the real ball. The 0.6 fallback threshold does not establish reliability.
- **The source trail accepts spatial jumps.** `apps/tt-demo/app.js:drawSources` breaks trails on missing positions or time gaps, but not on excessive spatial displacement. Consecutive wrong positions can therefore be connected across the screen. The source crop can follow a wrong detected pixel as well.
- **Preprocessing loses information.** Original 4K frames are resized to 720p and then to a 512 × 288 model input. The small, blurred orange ball may become weak or disappear. Max-channel grayscale is an experimental color adaptation, not a validation of orange-ball performance on these phones.

### Why the reported localization numbers do not establish a working tracker

The selected hybrid localized **82/89** visible labels within a **32-source-pixel** tolerance on a short development interval. That still includes **three wrong localizations and four missing observations**. Sparse frame-center accuracy does not test the continuity between those frames, reject teleports, establish a negative-frame false-positive rate, or prove event accuracy.

The grayscale component's later slow/held-ball evaluation was **6/19** visible labels. The hybrid was selected after viewing the component evaluations, so it has **no independent held-out result**. Labels are approximate, from one visual reviewer, and cover a small fraction of the 13,238 source frames. There are no labeled absent-ball negatives establishing the rate of hallucinated detections.

The new continuity audit makes the missing evaluation dimension explicit: an improved sparse localization count can coexist with much worse-looking temporal behavior. No prior summary number overrides the observed playback failure.

## 2. 3D rendering: visual quality below target and ball absent

### Ball absence is a missing reconstruction, not a successful abstention deliverable

The existing real scene has **1,615 frames and zero frames with a 3D ball position**. Every frame's ball state is `unavailable_dynamic_metric_calibration`; `position` is null. `tools/build_tt_scene.py:build` writes that unavailable state rather than reconstructing the ball for these recordings. The generic stereo geometry module exists, but is not producing a real ball trajectory for this scene.

`apps/tt-demo/scene.js:draw` makes the ball visible only when a finite 3D position exists. It therefore cannot show a real ball, ball trail, bounce or paddle-contact event with the current scene data. This is a substantive missing feature, not merely an opacity, marker-size or WebGL issue. Synthetic fixture balls do not satisfy the real-recording requirement.

The real scene's camera list is also empty. The UI's Side/Diagonal 3D buttons fall back to generic scene presets; they are not validated reconstructions of the recording cameras.

### Rendering quality is not accepted

The user reports that the 3D rendering is not clean enough. Earlier browser checks established that two connected meshes rendered and animated without console errors; those checks did not establish acceptable silhouette, shoulder/arm deformation, crouches, foot behavior, hand detail, paddle placement or motion stability against the supplied visual target.

The implementation uses:

- A procedural generic skinned mesh with a grid shader, rather than validated body-surface fitting.
- Side-view monocular body estimates sampled at nominal 15 Hz; this is not validated two-view motion capture.
- Approximate camera geometry from manually selected coplanar corners plus table-region image stabilization; both phones move.
- Explicit display priors: player roots constrained to end lanes, lateral root depth set to zero, bounded root height and median/Savitzky–Golay smoothing. These can produce plausible-looking motion while remaining wrong relative to the source; smoothing is not reconstruction accuracy.
- Missing/rejected poses and estimated hidden legs. Detection/render coverage does not demonstrate stable or anatomically convincing motion.
- A paddle attached to an estimated wrist; paddle-face orientation, hand association and ball impact are not measured.

The complete visual target—clean continuous bodies, readable fast motion, a measured ball trajectory, recording-camera agreement and an inspectable decisive event—has **not** been achieved. No new cosmetic adjustments, smoothing, avatar changes or invented ball positions were made in this reporting pass.

## 3. Point detection is not working as intended

The session contains **15 candidate intervals; all 15 are unresolved and all 15 have no winner**. This count is not the number of correctly detected real points.

The implementation in `services/flight/flight/recording.py:rally_candidates`:

1. Keeps frames with any reported ball x-coordinate.
2. Groups detections until a gap exceeds 0.8 seconds, with short-run filtering.
3. Splits long runs into chunks up to **12 seconds**.
4. Assigns `evidence_s` to the chunk end, `status="unresolved"` and `winner=None`.

There is no validated service-start, legal in-play, paddle-contact, table-bounce, terminal-event or winner sequence underlying these intervals. Its `envelope` parameter is not used to classify acoustic impacts. Wrong detections can join unrelated actions; missing detections can split one rally; fixed 12-second chunks can divide a rally or group unrelated activity. For example, the adjacent intervals at 15.2833–27.2833 and 27.2833–28.4333 seconds reflect this subdivision mechanism, not evidence that a point ended at 27.2833 seconds.

For hybrid playback, segmentation uses the side-view neural track, not the fused track and not corroborated two-view events. Improving color fallback coverage therefore does not fix the point list. `boundary_uncertainty_s=0.8` is a configured heuristic, not an uncertainty interval validated against labeled rally boundaries.

In `tools/tt_demo.py:Demo.advance`, automatic synthetic faults are handled only for the synthetic dataset. There is no real-recording automatic point-award branch. Real score updates are explicit player/official resolutions through `/api/resolve`. Those controls and score-state tests do not constitute automatic point detection or correct real score calling. Initial 0–0/server A is setup, not recovered game state.

“Go to evidence” and Challenge seek to the candidate interval end. That timestamp is not established as the deciding contact, so review can freeze at an irrelevant frame. The UI label “Point” risks overstating what is only an activity candidate. No end-to-end real point-boundary/winner accuracy has been measured against a reviewed rally inventory.

## 4. Calibration, synchronization and rule evidence gaps

Both original sources are 4K60 with audio, approximately 107.62 seconds side and 113.02 seconds diagonal. The recordings have visible camera movement. A fixed plane homography cannot recover arbitrary airborne height or establish moving-camera metric accuracy.

Audio gives an estimated diagonal offset of **+0.039 s** relative to the side/session clock, with a reported conservative **±0.0276 s heuristic estimate**. It is not a statistically calibrated capture-time confidence bound. Exposure timing, rolling shutter, position-dependent acoustic travel and drift remain unverified. Shared video playback is not proof that exposures are synchronized tightly enough for impact triangulation.

The real recordings lack validated metric ball release/apex/contact measurements, open-palm evidence, edge/top-versus-side contact classification and terminal-event provenance. The hand/pose model output counts are coverage, not proof of these facts. Rulebook inventory and deterministic source-cited rule handling cannot supply missing observations.

The official serve profile and geometry math have synthetic tests. The shared production serve payload still contains the older rise/fall-angle interpretation and unavailable-evidence limitations. No production schema migration was completed. The official HMO full text remains unavailable after 403 responses; no HMO review is claimed.

## 5. Performance, tests and integration are not product acceptance

- The prior **75 passing tests** cover synthetic geometry/facts, score-state behavior, persistence, HTTP safeguards, serialization and limited source-identity behavior. They do not establish continuous ball identity, clean avatar rendering, real 3D reconstruction or correct automatic rally segmentation/winners.
- The grayscale neural component processes the full sources at approximately **22.26 sequential paired FPS**, below the 25 paired FPS target. These are offline preprocessing measurements; smooth 60 FPS video playback is not live inference speed.
- Combined hybrid end-to-end throughput has not been measured. Cache fusion timing is not a processing benchmark.
- The standalone local player/referee path is separate from the intended live service architecture. Redis/Spacetime delivery, Cartesia, challenge voters, house-rule compilation and the full `make e2e` path have not been demonstrated here.
- No labeled 20-rally scoring evaluation, 10-edge-contact evaluation, 12-staged-serve evaluation or real metric 3D/serve error evaluation passed the requested gates.
- On a fresh checkout, footage, previews, weights and preprocessed session/scene caches are absent because they remain ignored local files. Pushing the branch does not make the real demo reproducible without those separately authorized inputs/assets and preprocessing. Public BlurBall checkpoint use remains unapproved.

The complete staged whitespace check also identifies existing whitespace in the vendored Three.js source and the vendored BlurBall YAML. Those files were left byte-for-byte unchanged under the no-fixes instruction.

No tests or inference were rerun to imply improvement during this reporting task. The additional work was read-only inspection of existing code/artifacts and documentation of failures.

## 6. Severity and outstanding acceptance gates

| ID | Severity | Open issue | Evidence needed before closure; no fix performed here |
|---|---|---|---|
| DET-1 | Blocking | Ball marker teleports or identifies a wrong object | Source-reviewed false objects, temporal continuity and reacquisition evaluation across both full clips, including detector switches and absent-ball negatives |
| EVT-1 | Blocking | Activity windows presented as points; no reliable point boundaries or automatic winners | Independent rally inventory with event reasons and start/end/winner labels; whole-sequence evaluation on an untouched split |
| REC-1 | Blocking | Real 3D ball and trajectory missing | Validated time-varying camera/timing inputs and source-linked real ball reconstruction with quantified rejection/error |
| VIS-1 | Blocking for requested demo | 3D bodies/motion below visual target | Explicit source-versus-render acceptance for silhouettes, shoulders, swings, crouches, feet, hands and paddles; user acceptance |
| GEO-1 | Blocking for metric calls | Unverified moving-camera geometry and exposure alignment | Independent calibration/height validation and cross-time alignment checks with defensible uncertainty |
| SRV-1 | Blocking for serve feature | Release/open-palm/toss/contact evidence unavailable or unreliable | Reviewed real serves, measurable uncertainty, applicable rule/profile support and production contract alignment |
| EDGE-1 | Blocking for edge feature | No measured top/side contact distinction | Reviewed real edge/side cases with contact geometry, ball extent and timing/localization bounds |
| INT-1 | Incomplete integration | Production state, voice and challenge-vote path unvalidated | Actual delivery/latency/failure evidence through owning services; no simulated success |
| EVAL-1 | Blocking for reliability claim | Sparse development metrics and tests do not measure product failures | Independent negative/visible/event labels, real continuity/point metrics and visual acceptance; retain failed results |

These are acceptance requirements and investigation gaps, not changes made or promises that any particular technique will fix the recordings.

## 7. Artifacts, provenance and preservation

- Original evaluation record: [ttclips-2026-10-24.json](../../evals/reports/ttclips-2026-10-24.json). Its measurements are retained; its checklist does not override this failed-acceptance report.
- New read-only artifact audit: [ttclips-continuity-audit-2026-10-24.json](../../evals/reports/ttclips-continuity-audit-2026-10-24.json), including input-cache SHA-256 values and pixel/time examples. It contains no video, frames or player pose data.
- Earlier implementation/handoff record: [a2.md](a2.md). Build instructions: [tt-demo.md](../tt-demo.md).
- Source pointers: `tools/track_tt_blurball.py`, `tools/fuse_tt_tracks.py`, `services/flight/flight/recording.py`, `tools/build_tt_demo.py`, `tools/build_tt_scene.py`, `tools/tt_demo.py`, `apps/tt-demo/app.js`, `apps/tt-demo/scene.js`, `apps/tt-demo/avatar.js`.
- Prior uncommitted implementation is included in this branch as a snapshot, so another engineer can inspect the actual failing state. There are no fixes in this follow-up. Executable/configuration/test/asset content is checked against a pre-report SHA-256 manifest before commit.
- Footage, model checkpoints, 4K crops, screenshots, full pose/hand caches, local score audits and generated preview videos remain local and ignored. No new media is published. Only code, existing approved static assets, documentation, non-identifying labels and aggregate audit reports are pushed.
