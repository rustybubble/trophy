# Flight: the ping-pong vision module
**py3.11, numpy 1.26.4, opencv-contrib 4.10.0.84 (CPU).** Reads every frame from `frames:{cam}`, tracks the ball, finds the table, and emits **measurements** (D-18): `bounce`, `contact` and `ball_dead` events on `ev:flight` (the engine's hot path), mirrored into Spacetime `observation`, plus `trk:ball:{cam}` every frame and a 10 Hz `track_sample`. It never writes frames to Spacetime.

Not built yet: `net`, edge-class probabilities, audio-timed bounces, `serve_toss` (D-22) and metric calibration. Every payload carries `calib_untrusted: true` and `d_lines_m` is empty, so the engine must cap these calls at BETA.

```
uv run python -m flight.live --game <g_id | next> [--post-calls]
```
`--post-calls` is an **interim** stand-in for the engine: it judges each finished rally with `flight.rally.referee` and posts a `point` call (`p_source: "heuristic"`), the rally row and the score, using `SPACETIME_ENGINE_TOKEN`. Drop it once Agent 3's engine consumes `ev:flight`.

## How it works
- `colour.py`: a per-camera ball colour model. It starts from loose defaults and is learnt from the camera's own stream (`LiveLearner`): blobs that fly on a smooth parabola are taken as the ball, other moving orange blobs as distractors.
- `balltrack.py`: bright-orange blobs plus a shake-compensated motion test, then a gated single-target tracker. Detections must be physically reachable from the last observation (no teleports). New tracks need 3 consistent moving detections. Gaps are bridged by prediction (never reported as "observed"). Still objects are dropped. Dropped frames restart the track.
- `table.py`: the table top (a pale surface band) and the net (the darkest column above it).
- `rally.py`: bounces (a vertical reversal on the table band), hits (a horizontal reversal), ball dead (below the table, or lost), and `referee()`, which applies basic point rules and returns undecided rather than guessing.

## Tools (`tools/tt_*.py`, run with `uv run --project services/flight`)
`tt_track.py` (`--live` simulates the phone path: 30 fps, 4:2:0 JPEG q70, online colour learning), `tt_eval.py` (against `evals/labels/ttclips-*.json`), `tt_rally.py`, `tt_review.py` (a local review page with the video, the track, events, decisions and a side-elevation view), `tt_sheet.py`.

Measured numbers: `docs/status/a1.md` ("Table-tennis tracker"). Contracts: `docs/plan/interfaces-v1.md`.
