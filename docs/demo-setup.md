# Fixed-camera demo and re-record kit

This is a capture and labelling procedure, not a claim that the current tracker meets the evaluation gates.
Do not begin filming without the user's approval and the consent of every person in frame. Agree on local
storage, who can view it, and whether any separate public use is permitted. Keep footage, source frames,
labels and identifying reports under ignored `data/local/`. Clear the background of non-consenting people.

## Mount and capture

1. Fix the camera on a tripod beside the long side of the table, with its lens on the **net line** (x=0),
   approximately 2–3 m outside the sideline. Start with the lens 0.4–0.7 m above the tabletop (about
   1.2–1.5 m above the floor); record the actual height and distance. This is a starting setup, not a validated
   metric camera model. Frame both end lines, the whole table, each server's palm and the toss apex.
2. Use landscape orientation and the same rear lens throughout. Lock focus/exposure if the device permits;
   record actual resolution, frame rate and exposure settings. Do not handhold, pan, zoom, change lenses or
   move the tripod after calibration. Recalibrate under a new camera id if it moves.
3. Use bright, even, diffuse lighting with no strong reflections. Check a fast ball for motion blur and
   LED flicker in the actual recording, not just the preview. Use a **white ball** against a contrasting
   background. A visible slow/held ball is still a ball, not a negative example.
4. Place a **vertical 6-inch ruler behind the end line** for staged serve evidence, near the release plane.
   Six inches is 152.4 mm; add a separate 160 mm mark when testing a 16 cm profile. Keep ruler scale, release
   and apex in the same measured plane; an arbitrary background ruler does not establish airborne height.
   Record the ruler's location and a still. Keep the ruler out of active play after staged tests.
5. Calibrate with the named table corners and check reprojection on independent tabletop points. Validate
   elevated reference points near release/apex separately before treating toss height or angle as metric
   ground truth. Four coplanar points alone do not establish trusted airborne geometry.
6. Record a short empty-table lead-in/out, then visible held/slow balls, real rallies and staged edge/side
   and serve cases. Preserve originals and clock/source metadata. Use the 720p30 live stream for the live-path
   test; phone-recorded HQ video is separate evidence. Do not label HQ playback performance as live tracking speed.

Before a longer session, play back the actual archive and check focus, ruler visibility, frames, clock error,
HLS finalization, calibration trust and storage space. Record the pack version/profile, camera settings,
consent reference, calibration revision, encoder and source hashes in the session notes.

## Independent label set

A suggested first acceptance set is at least 20 independently labelled rally outcomes, 10 staged top-edge/side
contacts and 12 staged serves, plus no-ball frames spread across the session. These are targets, not achieved
counts. Balance legal/fault and easy/near-threshold cases. Include floor bounces after a point and pre-serve
bounces to expose phantom rallies. Include low and angled serves separately, with an explicit rule profile.

Split by recording session before tuning. Keep a new session held out and do not tune after inspecting its
report. Two neighbouring frames of the same contact are not independent test examples. Have a second person
review ambiguous outcomes without looking at the model's decisions. Mark unresolved truth as null; do not
infer a point winner from disappearance or classify an occluded contact as edge/side. Record disagreements.

## Label and evaluate

1. Start the recorder before capture and stop/finalize it after the game. Confirm `meta.json` has `closed: true`
   and no error. Each camera's source JPEGs and `index.jsonl` map native `seq` to `t_game_s`; HLS media time is
   recording-relative. Never label a held HLS frame as a fresh observed frame.
2. Freeze output **before human review or correction** using the evaluator's capture command. It exports
   Spacetime game/call/rally/observation metadata and the recorder's ball tracks. It makes no model calls.
   A state snapshot cannot reconstruct earlier versions of calls. Reviewed/voided calls stay visible in reports,
   with a warning; they are not silently removed to improve results.
3. Initialize an empty label file from the finalized archive. It records index hashes and invents no outcomes.
   Review original source frames and HQ evidence. Edit the JSON using the example below; label all events in
   any interval marked `complete: true`. Sparse labels are allowed, but unmatched predictions outside complete
   intervals cannot be called false positives.
4. Validate labels, then score the frozen predictions. Keep actual evidence/labels/reports local. Commit only
   non-identifying synthetic examples and a measured status summary. Inspect every error before drawing conclusions.

```bash
python tools/eval_live.py capture --recording data/local/recordings/g_example \
  --profile table_tennis@1-house-config-hash --output data/local/evals/g_example/predictions.json
python tools/eval_live.py init --recording data/local/recordings/g_example \
  --profile table_tennis@1-house-config-hash --output data/local/evals/g_example/labels.json
# Edit labels.json after independent source review.
python tools/eval_live.py check-labels data/local/evals/g_example/labels.json
python tools/eval_live.py score --labels data/local/evals/g_example/labels.json \
  --predictions data/local/evals/g_example/predictions.json --output data/local/evals/g_example/report.json
```

Capture reads `SPACETIME_ENGINE_TOKEN` from `.env`/the environment; it never prints the token. `--uri`,
`--module` and `--env-file` support an isolated local database. A capture or label file is never overwritten
by `capture`/`init`. Profile and source-index hashes must match when scoring.

Example label entries (illustrative values, **not measured ground truth**):

```json
{
  "schema": "trophy.eval_labels.v1",
  "game_id": "g_example",
  "rule_profile": "table_tennis@1-house-config-hash",
  "split": "development",
  "labeller": "reviewer-1",
  "reviewer": "reviewer-2",
  "coverage": [{"t0_s": 0, "t1_s": 20, "tasks": ["rally", "edge", "serve"], "complete": true}],
  "rallies": [{"id": "r1", "t_start_s": 1, "t_end_s": 5, "winner_team_id": "A", "tolerance_s": 1, "boundary_tolerance_s": 0.2}],
  "edges": [{"id": "e1", "cam_id": "c_example", "t_game_s": 3, "outcome": "edge_good", "tolerance_s": 0.1}],
  "serves": [{"id": "s1", "t_game_s": 1, "outcome": "illegal_toss_height", "tolerance_s": 0.25}],
  "no_ball_frames": [{"cam_id": "c_example", "seq": 0}]
}
```

Keep the `sources` field produced by `init`. Label one physical event once, even if multiple cameras see it;
use `cam_id` to anchor the evidence if needed. Edges are `edge_good`, `side_fault` or null. Serves are `legal`,
`illegal_toss_height`, `illegal_toss_angle`, `other_serve_fault` or null; optional `acceptable_outcomes` can name
multiple independently established faults. Use null when evidence is missing. Do not substitute a different
profile to match the predictions. Store toss measurement/rule notes as extra label fields if useful.

For a legal serve, silence alone does not prove the engine processed the serve. An explicit runtime
`serve_evaluations` record with outcome `legal` is needed for correct legal-classification credit; otherwise
it is reported as a missed label. The existing fault-call path still evaluates labelled faults and false
fault calls on legal serves. No legality is inferred from raw trajectory measurements by this evaluator.

## Reading the report

- Rally outcomes, edge/side and serve faults each report **n, correct, accuracy and Wilson 95% CI**; n=0 gives
  null accuracy/CI. Unknown truth is counted separately. Association is one-to-one by time, never by outcome.
- Rally boundary accuracy is separate from winner accuracy: a correct winner with a wrong start/end remains
  a boundary error. Missed labels and spurious predicted boundaries in exhaustive intervals are separate counts.
- Edge/serve duplicates and other unmatched calls count as false positives only in complete labelled intervals.
- No-ball false positives use exact `(cam_id, seq)` labels and explicit track rows. Report labelled count,
  evaluated count, missing samples, false-positive count/rate and Wilson CI. Missing samples are never true negatives.
- Manual calls are excluded from automatic accuracy; reviewed-call contamination is flagged. Synthetic runs carry
  `synthetic: true`. Repeated frames/correlated contacts reduce statistical independence; Wilson intervals do not
  correct that dependence, so report session/event counts alongside the sample counts.

The existing moving-camera clips can validate transport and playback. They do not become a trusted metric
serve/edge/outcome benchmark just because the new recorder works. New filming still needs explicit approval.
