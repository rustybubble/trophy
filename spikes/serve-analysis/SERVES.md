# Recorded-video serve detection

The implementation finds serve-contact candidates from player motion over time,
independently of whether BlurBall sees the complete toss. It exports player/time
evidence, merges synchronized camera observations, and provides a local review
page with both source videos, slow motion, player crops, corrections and export.
Serve recognition does not establish a legal toss or automatically award points.

The review UI now has a separate **Height & direction** evidence stage. See
[toss rules, overlays and calibration requirements](SERVE_LEGALITY.md). Release
and apex currently require frame review; the supplied phone geometry is
unvalidated and cannot substantiate fault calls.

## Run the trained local detector

The isolated environment preserves the existing ball and pose installations:

```bash
bash scripts/bootstrap_serves.sh
.venv-serves/bin/python scripts/detect_serves.py \
  --config configs/serve-user-two-camera.json \
  --checkpoint weights/serves/table-tennis-final.pt \
  --output artifacts/serves/my-session --max-seconds 107
.venv-serves/bin/python scripts/serve_serve_review.py \
  --directory artifacts/serves/my-session --port 8504
```

Open [serve review](http://127.0.0.1:8504/). There is also a **Find and review
serves** section in the existing Streamlit app. Outputs must use a new/empty
directory. `--device auto|cpu|mps|cuda` selects actual native execution. There is no
silent CPU fallback or hosted model. `auto` reports its selected device; explicit
unavailable accelerators fail. This is an offline model with future context.

The trained checkpoint is a local artifact. Setup downloads a verified published
initialization, not a table-tennis detector. On another checkout, train using the
commands below or transfer the trained artifact and its report. Inference rejects
the original tennis checkpoint rather than silently treating it as table tennis.

## Architecture and files

- **Visual/temporal model:** E2E-Spot's RegNet-Y 200MF + gated temporal shifts +
  bidirectional GRU, 4.45 million parameters. The published tennis model initializes
  its visual and temporal weights; a five-class head is trained for background,
  left/right serve contact and left/right ordinary stroke. Images use RGB,
  ImageNet normalization and full-view area-resized letterboxing to 224 x 128.
- **Cadence:** 48-frame windows sampled at 15 Hz, with 24-frame overlap. Weighted
  fusion exports scores only for actual sampled source timestamps. Short streams
  with fewer than eight samples yield no candidates. Long timestamp gaps split
  inference segments. Missing samples do not become invented video frames.
- **Event decoding:** sum the two serve-side outputs to recognize the action
  independently of uncertain actor identity; compare against background and
  ordinary strokes, then suppress duplicate peaks. Public validation selects a
  strong tier (0.80) and a review tier (0.20, also requiring the serve class to win).
  The review cutoff preserves validation recall while targeting at least 80%
  precision. Scores are not calibrated probabilities.
- **Actor attribution:** where player regions are configured, compare observed
  pre-contact optical flow after removing background translation. Ambiguous
  motion abstains. Motion in a camera that did not recognize the serving action
  can be inspected but cannot establish actor identity by itself. Without regions,
  side predictions remain network estimates. This distinction matters: the first
  local serve is detected but its actor stays uncertain.
- **Two-camera fusion:** `source_time = session_time + source_offset_seconds`.
  Configure stable IDs and per-camera left/right player mappings explicitly.
  Matching candidates become one stable event ID; same-camera candidates do not
  merge. A hidden camera can abstain. Player disagreement requires review.
- **Review:** candidates, confirmed actions, false detections and uncertain events
  are distinct. Corrections persist in this browser, keyed to the recording/model
  identity. Export saves the reviewed JSON. Manual corrections are labeled as such.
  Nothing in review changes game score or feeds human labels back into inference.
- **Evidence:** `serves.json`, `serves.csv`, and actual frame-level
  `view*-scores.npz`. Release/height/fault fields remain unavailable. Reported
  contact intervals describe sample resolution only, not validated error bounds.

Code is under `trophy/serves/`; commands are in `scripts/*serve*.py`; the review
page is in `web/serves/`. Source video bytes are read locally. The review server
binds to 127.0.0.1 and supports byte-range seeking only for configured media files.
No camera calibration is required for action recognition. Metric toss measurements
would require a separate validated release estimator, calibration and visual sync.

## Reproduce acquisition and training

```bash
.venv-serves/bin/python scripts/setup_serve_assets.py
.venv-serves/bin/python scripts/prepare_serve_training.py --max-serves 16 --workers 4
.venv-serves/bin/python scripts/train_serve_spotter.py --device auto
.venv-serves/bin/python scripts/prepare_local_serve_examples.py
.venv-serves/bin/python scripts/finetune_serve_spotter.py \
  --manifest artifacts/serves-data/adaptation-manifest.json --epochs 12 --steps 30
.venv-serves/bin/python scripts/calibrate_serve_decoder.py --device auto
```

Acquisition decodes short windows over HTTP ranges instead of downloading each
multi-gigabyte original video. It caches completed windows, retries failures,
checks source annotation Git blob hashes, records clip SHA-256 values and retains
actual presentation timestamps. The executed cap is 16 evenly spaced serves per
source video, plus ordinary-stroke and non-contact negatives. It is a pilot, not
the full dataset. Keep the training manifest with the checkpoint.

The public split is game_1–3 for training, game_4 for validation, and game_5 plus
test_1–7 for testing. Whole recordings stay within a split. The first pass adapts
the GRU/head on frozen features. Visual fine-tuning then adapts all weights, uses
horizontal flips with swapped player-side labels and clip-consistent photometric
augmentation, and keeps batch-normalization statistics stable for small batches.

Explicit local examples cover only the first 73 seconds of the supplied session,
including two manually annotated serve contacts and distracting ordinary activity.
Both cameras of each physical event remain in the development split. The three
later annotated serves, at approximately 76.63, 85.03 and 90.67 seconds, are excluded
from training. This is a temporal holdout from the same player/room, not evidence
of performance on unseen players/cameras. Labels are visible in the preparation
script and evaluation configs; no annotated time is read by the detector.

Checkpoint/threshold selection uses public validation only. Public test results
after development are exploratory because the baseline test split was inspected.
Selected-window metrics can count an event in overlapping examples and do not
measure false triggers over an entire recording. Use continuous evaluation too:

```bash
.venv-serves/bin/python scripts/evaluate_serve_recordings.py --device auto
.venv-serves/bin/python scripts/evaluate_serves.py \
  --predictions artifacts/serves/my-session/serves.json \
  --truth configs/serve-user-two-camera-holdout.json \
  --output artifacts/serves/my-session/holdout-evaluation.json
```

The evaluator uses one-to-one, player-correct matching within 0.35 seconds;
duplicates count as false positives. Continuous public evaluation reports serve
occurrence separately from actor-correct matching, and both threshold tiers.
Five local serving actions cannot substantiate a 98–99% reliability claim.
Toss-only, caught or dropped attempts without a striking action are not covered by
the trained contact classes. An obscured action may remain missed or need review.

## Provenance

- [E2E-Spot source](https://github.com/jhong93/spot): BSD-3-Clause; license retained
  in `vendor/e2e_spot/LICENSE`. The unmodified vendored GSM contains its BSD-2-Clause
  notice. Native subclasses replace its CUDA-only zero allocation; contiguous
  NCHW inputs avoid an observed MPS BatchNorm-backward layout error.
- [Published initialization](https://github.com/jhong93/e2e-spot-models), commit
  `10d07a4fb01f2eb76785e15552e5648bf0793509`, tennis_rny002gsm_gru_rgb/checkpoint_040.pt,
  SHA-256 `5949e3e869f20480f51d89c68514b3eda4399779d9d2ca20c9b78344b11c8e2c`.
  All 415 non-output-head tensors load; the sport-specific output layer is replaced.
- [Extended OpenTTGames annotations](https://github.com/moamal01/table_tennis_data),
  commit `36471a76b969a0340df59258a813bf8214e68e7c`; data license CC BY-NC-SA 4.0.
  Public video is from the authors' [OpenTTGames dataset](https://lab.osai.ai/).
  The research checkpoint incorporates this noncommercial dataset; code licensing
  does not remove the dataset's conditions.

The original source recordings and unrelated reconstruction code are preserved.
Dependency versions for the isolated environment are in `requirements-serves.lock`.

## Executed pilot results

Executed locally on Apple MPS after acquiring 401 public windows and adding 50
explicit local development windows. Public windows are split 144 train / 48
validation / 209 test; local windows are train-only. The frozen-feature first pass
generalized poorly, so the shipped model includes visual fine-tuning and separate
event/actor estimation. Threshold selection uses public validation only.

| Evaluation | Serve events found | Extra event candidates | Scope |
| --- | ---: | ---: | --- |
| Continuous public, strong tier | 14/15 | 0 | test_2, test_3, test_6 |
| Continuous public, review tier | 15/15 | 1 | Same three uncut recordings |
| Supplied two-camera session, review tier | 5/5 | 1 | First 107 seconds; first two serves are development examples |
| Later local temporal check, review tier | 3/3 | 1 | 73–107 s; same player/room, excluded from weight updates |

These are serving-action occurrence counts, not service-legality accuracy. At the
strong tier, public actor-correct matching is 13 true positives, one false positive
and two false negatives. In the supplied session, four true serves have the correct
actor estimate and the first actor remains unknown. The extra local candidate at
103.36 s is flagged for review, as is the lower-score true serve at 84.89 s.

The public test split and local temporal check were inspected during development;
these are exploratory results, not an untouched final benchmark or a 98–99%
reliability certification. Fifteen public events and three later local events are
too few to establish broad deployment accuracy. No automatic score/fault outcomes
are enabled.

The final demo is `artifacts/serves/final-demo/`. Continuous metrics are at
`artifacts/serves/continuous-public/continuous-evaluation.json`; local metrics and
model provenance are alongside the final demo. The model and its complete decoder
calibration report are `weights/serves/table-tennis-final.pt` and `.report.json`.
Inference over the two cached low-resolution sample streams took approximately
five seconds; initial full-resolution source decoding is a separate cached stage.

Regression checks: 67 Python tests passed, including 19 serve/event/media tests;
the review JavaScript passes Node's syntax check. Browser checks are recorded in
the final demo's validation summary.
