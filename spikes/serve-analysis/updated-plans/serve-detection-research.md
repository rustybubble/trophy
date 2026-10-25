# Serve detection: research, footage probe, and implementation decision

Investigated 2026-10-24. This is a researched design, with one executed ball-tracking probe. It is not a trained or validated automatic serve detector.

## Decision

Add a temporal **serve-contact event spotter** alongside BlurBall. Use E2E-Spot's accessible RegNet-Y 200MF + GSM + GRU implementation as the first trainable reference, adapted to table-tennis serve and ordinary-stroke labels. Run it separately on each camera, associate detections through session timestamps and player identity, and use hand/ball observations to verify and refine candidates. Keep the measured toss and referee decision downstream.

This changes the previous plan's assumption that pretrained ball/pose/hand outputs plus deterministic logic would necessarily be sufficient. They remain valuable inputs, and a deterministic sequence detector is a useful baseline, but their reliability for recognizing uncut real serves has not been established. A trained event spotter is now the recommended experiment, rather than adding more ball models speculatively.

There are three different outputs:

1. A serve occurred, attributed to a player, around a contact-time interval.
2. The release/apex/contact sequence is sufficiently observed to measure the toss.
3. A particular rule violation is supported by those measurements.

Output 1 can succeed while output 2 is unavailable. Output 1 must not require a legal toss, correct position, an open palm, or successful bounces. Dropped/caught tosses without a strike require a separate attempt/review path; detecting a serve contact does not cover them.

## What the actual footage establishes

Both supplied recordings decode as 3840 x 2160 at 60 FPS. Camera 1 has 6,457 frames; camera 2 has 6,781. Overview sheets at four-second intervals show complementary views, camera movement, hand occlusion, pickups, waiting, and ball handling. These overview sheets are a discovery aid, not frame-accurate event annotations.

Camera 1's 5–8 second inspection shows preparation followed by the opening toss/strike around 7.2–7.9 seconds. The existing 8–11 second ball test starts after that opening action. Its detection coverage therefore does not validate release/toss detection.

Executed a new probe on the 61 chronological camera-1 frames from 7.0 through 8.0 seconds. Used the pinned, unmodified BlurBall checkpoint on CPU, max-channel grayscale, threshold 0.65, and stride-one three-frame windows. Compared the full native view against a fixed native upper-body ROI `[500,700,1800,1500]`, chosen manually and unchanged across frames.

| Input | Frames with any selected detection | Timed model loop, excluding warmup |
| --- | ---: | ---: |
| Full view | 34/61 | 14.79 s |
| Upper-body ROI | 31/61 | 14.61 s |

The overlay inspection shows missed held-ball observations, missing toss observations, and false selections on the table/hand. Both paths follow later outgoing-ball frames more convincingly. A crop alone is not an established solution. The counts above measure detection existence, including false detections; they are not recall, accuracy, or serve-detection performance. One manually selected serve cannot establish comparative model quality.

Reproduce from this workspace:

```bash
.venv/bin/python artifacts/serve-investigation/probe_tracking.py
```

Evidence: `artifacts/serve-investigation/tracking-probe.json`, `tracking-probe.jpg`, `source-metadata.json`, `camera1-overview.jpg`, `camera2-overview.jpg`, `early-serve.jpg`, `second-attempt.jpg`, and `late-serve.jpg`. Original files were only read. The probe does not implement automatic crop selection or serve recognition.

The room now also has an experimental short-segment geometry output at `artifacts/user-two-camera/hmr2/geometry.json`; this is newer than the earlier summary saying no reconstruction existed. It explicitly lacks metric ground truth. Its ball-fit timing estimate and earlier audio timing estimate differ, so neither should be treated as verified serve-time synchronization.

## Online sources and what is actually usable

### 1. MSAGSM: the closest direct event-spotting research

[MSAGSM paper, v2](https://arxiv.org/html/2507.07381v2) explicitly studies table-tennis serve-contact spotting. Its TTA benchmark has 39 games, 4,878 events, and near/far serve, forehand, backhand, and bounce classes. The E2E-Spot + MSAGSM configuration reports 69.50 mAP at one-frame tolerance and 78.12 at two frames, across the eight classes; these are not serve-only precision/recall or legality accuracy. TTA runs at 30 FPS.

The paper links [an anonymous code repository](https://anonymous.4open.science/r/MSAGSM-B0A4). Direct browser inspection on the investigation date reports that the repository has expired. Appendix C says TTA is research-only and available upon request/approval, despite the abstract's public-availability wording. This is useful design evidence but not a verified immediately downloadable table-tennis checkpoint. Use accessible E2E-Spot code instead of making this expired release a dependency.

### 2. E2E-Spot: the implementation reference

[Official E2E-Spot code](https://github.com/jhong93/spot) provides training, inference, custom event-label JSON, and RegNet-Y 200MF + GSM + GRU configuration support under BSD-3-Clause. It learns from video pixels over time, rather than requiring a complete detected ball trajectory. The authors provide [configurations and checkpoints](https://github.com/jhong93/e2e-spot-models).

The listed pretrained sports include tennis, gymnastics, skating, diving, and soccer. Tennis weights are not a table-tennis serve detector. The practical value is accessible code and transferable initialization; a table-tennis event head needs training and local evaluation. The code documents a Linux environment; Apple CPU/MPS operation and throughput have not been verified here. No source-reported GPU speed should be presented as our runtime.

### 3. Extended OpenTTGames: immediately relevant training labels

[Official annotations and scripts](https://github.com/moamal01/table_tennis_data) add stroke-contact and rally-ending labels to the original side-view OpenTTGames recordings. Labels explicitly include forms such as `left_forehand_serve`. Twelve annotated videos preserve the original five-training/seven-test structure. The [paper](https://arxiv.org/html/2512.19327v1) describes the dataset and CC BY-NC-SA 4.0 data license. The repository includes a video download script.

Use these labels for serve-contact spotting versus ordinary strokes. They do not provide palm-release times or prove service legality. Unannotated stretches must be checked before treating every frame as a trustworthy negative. Supplement the side-view data with our oblique views, beginners, ball handling, and unusual serve attempts; public match data alone will not establish those cases.

### 4. Dedicated multi-camera serve-foul paper

[Yang et al., Foul Detection for Table Tennis Serves Using Deep Learning](https://openrepository.aut.ac.nz/server/api/core/bitstreams/9d17ced2-ba07-49d4-aabb-29507355a26e/content), published December 2024, reconstructs the ball with two primary cameras and uses an additional overhead verification camera. It trains on 300 serves from three people and reports F1 0.93 for throw/apex/hit key points. Its spatial segmentation uses a serve-area coordinate threshold.

This supports the downstream idea of extracting serve key events from 3D ball motion. It does not establish reliable discovery of arbitrary serves, aborted attempts, or handling in uncut footage like ours. Key-point F1 is not full serve-fault accuracy. We did not verify downloadable trained weights/data from the checked source.

### 5. Pose-only serve recognition: useful, but headline accuracy is misleading here

[Wei and Chang, Automatic Segmentation of Table Tennis Match Video Clips Based on Player Actions](https://www.jait.us/articles/2024/JAIT-V15N12-1374.pdf) uses both players' OpenPose coordinates and a GRU to classify serve, receive, and other actions. It reports 98.4% serve recognition in its classification experiment, but its full-video clipping test extracts only 14 of 20 serves. The mean start-boundary error is 0.547 s.

The evidence supports using body motion to propose intervals even when the ball is missed. It also demonstrates why clip classification accuracy cannot stand in for reliable continuous event detection or palm-release timing. A pose-only classifier is a sensible lower-cost comparison, not an established complete solution.

### 6. EventNet: strong contact-localization evidence, release unavailable

[EventNet paper](https://arxiv.org/html/2610.08286v1) combines upper-body, table, and ball 2D keypoints temporally to locate ball-racket contacts. It reports F1 91.16% on Latte-MV and 73.08% on TTHQ; these are contact-event results, not serve classification. The substantial dataset difference is a reason to validate our camera domain.

The [linked official repository](https://github.com/MLCVLab/EventNet) displayed only README and LICENSE at inspection, despite the paper's code/models availability claim. No usable inference implementation/checkpoint was verified there. Keep this as a design reference for a later keypoint contact model.

### Other sources screened

- [Kulkarni et al., trajectory-based stroke detection](https://arxiv.org/pdf/2302.09657): identifies serves through the two-bounce pattern. That can help corroborate completed serves, but cannot be our recognition gate because faulty serves may lack either bounce.
- [TTNet](https://openaccess.thecvf.com/content_CVPRW_2020/papers/w53/Voeikov_TTNet_Real-Time_Temporal_and_Spatial_Video_Analysis_of_Table_Tennis_CVPRW_2020_paper.pdf): detects ball, bounce/net events and segmentation; the paper explicitly identifies serve spotting as an additional needed component. It is not an existing serve detector.
- [TTStroke-21 / CRISP](https://p-emartin.github.io/CRISP/): action-recognition methods and a stroke dataset; the author page says data access requires accepting particular conditions. Less immediate than the accessible Extended OpenTTGames annotations.
- [2018 high-speed serve study](https://www.mdpi.com/2075-4663/6/4/158): uses color, morphology, circle detection and background separation; reports YCbCr outperforming HSV when ball color resembles skin. Relevant to a small classical held-ball candidate baseline, not evidence of robust ordinary-phone serve discovery.

## Concrete implementation

### A. Find the serving action without a complete ball track

1. Keep source timestamps and matched player IDs. Initialize identity/racket-hand side explicitly for the controlled two-player demo; handedness and person identity are different fields. Stabilize or split moving-camera segments.
2. For the first offline experiment, feed overlapping 100-frame windows at 30 FPS to the small E2E-Spot configuration. Preserve both players and the table in the resized view; do not blindly apply a center crop that excludes a server. These are initial experiment settings, not proven optimal settings.
3. Predict per-frame classes `serve_p0`, `serve_p1`, `ordinary_strike_p0`, `ordinary_strike_p1`, and background. Train on continuous sequences including negative time, not only pretrimmed positive clips. Keep frame-rate/source-time mapping explicit. Run the two views independently at first; matched outputs become one session event, not two serves.
4. Train with the public serve-contact labels, then adapt with locally annotated full sequences. Include normal returns, table/paddle dribbling, ball passing, pickups, catching, gestures, waiting and practice swings. Include short/no-toss serves and failed serves as positive serving actions when their interpretation is clear. Do not label every unusual motion a fault.
5. Merge overlapping-window peaks in time. Learn/select acceptance and merge parameters on validation recordings. Cross-camera agreement strengthens a candidate; a second hidden view must be allowed to abstain. Do not multiply correlated view scores as if they were independent probabilities.

The proposed spotter recognizes the temporal preparation/swing/follow-through pattern from pixels; the ball is supplementary evidence. This directly addresses the observed failure where BlurBall follows the outgoing ball but misses its earlier toss. Model initialization is available, but the required table-tennis training has not been run.

### B. Verify the event sequence and preserve ambiguity

Use a sequence estimator with the normal path:

`between rallies -> preparation -> release candidate -> first strike candidate -> rally`

It must also allow preparation directly to strike for a no-toss serve, release directly to caught/dropped attempt, missing phases under occlusion, and unknown initial state when a recording begins mid-rally.

Useful evidence is ball association with the free hand before the strike, hand separation, a local ball-velocity change near the striking hand during a swing, and subsequent outbound motion/bounces. The rendered racket does not prove contact. Audio can corroborate an interval but cannot independently distinguish paddle, table, floor, and other people's sounds.

Incoming ball motion and an already-active rally favor an ordinary return. Observed possession/preparation and a first strike favor a serve. Ball absence alone must not terminate a rally and arm a new serve detector: an occlusion would otherwise create false starts. The expected server is a soft consistency check, not a hard gate that excludes wrong-player serves.

A dropped/caught toss may be an aborted service or casual handling. Intent can be unobservable. Return an attempt/review record when context cannot distinguish them. Never silently award a point from that uncertainty.

### C. Refine release and measurement only on candidate intervals

Reprocess at the native 60 FPS and original spatial detail. Use pose-guided hand/upper-body crops, with transforms saved back to source coordinates, and MediaPipe Hand Landmarker where visible. [Google's Python documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python) describes hand tracking, 21 landmarks, image/world outputs, and the required model asset. The workspace currently has no hand-landmarker asset. Its local world coordinates do not supply calibrated table-relative depth.

Retain multiple plausible ball candidates with image/temporal consistency checks; our current global highest-component selection can choose the table or hand. Benchmark existing BlurBall, native-resolution color/shape candidates, and their association on labeled held-ball/toss frames. The executed crop probe means we cannot simply assume cropping repairs the checkpoint. If this stage still misses release, fine-tune ball detection on held, slow, releasing and occluded-ball examples rather than claiming an exact release from body motion.

Bracket release between the last supported hand-associated ball frame and the first supported independently moving ball frame. Carry gaps and ambiguity into the release interval. Reconstruct metric toss motion only with calibrated, visually synchronized cameras and sufficient paired observations. Single-view action recognition can still identify a serve when metric measurement is unavailable. Do not extrapolate a smooth ballistic path through missing release/contact evidence and present it as observed footage.

### D. Output contract

```json
{
  "serve_id": "session/serve/0001",
  "player_id": "p0",
  "event_status": "candidate",
  "contact_interval_seconds": [7.70, 7.85],
  "release_interval_seconds": null,
  "supporting_views": ["camera1"],
  "measurement_status": "release_not_observed",
  "fault_decision": null,
  "revision": 1
}
```

This is an illustrative schema, not a measured contact annotation. Store evidence frame IDs, source timestamps, model/config versions and rejection reasons alongside it. Distinguish `candidate`, `confirmed`, `review_needed` and `rejected`; keep attempt records separate from contact-confirmed serves. Playback/seeking must not emit duplicate scoring events.

## Validation that can justify “reliable”

First annotate every serve/contact and confusing handling episode in both full supplied recordings. That produces a small local pilot; the 107-second shared recording and two people are not sufficient evidence of broad reliability. Mark release/contact as intervals when their exact frames are not visible. Use a second reviewer for disputed labels, retaining ambiguity instead of forcing agreement.

Split by complete recording/session and, when possible, held-out players/camera setups. Both views and overlapping clips of a physical event belong in the same split. Do not randomly split adjacent frames. Public data supports initial training, while separate local validation chooses parameters and untouched local test recordings measure transfer.

Report these separately:

- Per-serve recall across the entire test recording, including illegal/failed serves. Abstentions count against automatic coverage; they cannot disappear from the denominator.
- Precision of automatically accepted events; duplicate detections and wrong-player detections are errors.
- False activations per hour of uncut video, including pickups and waiting; review rate and automatic coverage.
- Contact timing error at several tolerances in milliseconds; release-interval coverage and width; measured-toss availability/error.
- Results by server, view, occlusion, low/no toss, failed serve, and camera movement. Report actual counts and confidence intervals.
- Offline processing time and, separately if pursued, live causal latency. Bidirectional/offline context does not establish live performance.

Proposed product targets are at least 98% serve-event recall and 99% accepted-event precision, with the review/coverage tradeoff exposed. These are goals, not current measurements. With zero errors, about 300 independent accepted events are needed for a one-sided 95% binomial lower bound near 99%; repeated clips from one person/session do not replace recording diversity. A small clean demo should be described as validated on its actual examples, not certified to those rates.

The next implementation milestone is a trained and evaluated two-view serve-contact spotter with a review queue. Automatic toss-fault decisions stay disabled until the separate release/3D measurement stage is validated.
