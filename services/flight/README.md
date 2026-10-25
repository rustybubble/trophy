# Flight: ball track → field-frame 3D map (table tennis MVP)

**py3.11, numpy 1.26.4, opencv-python-headless 4.10.0.84. CPU only; no model is required.** Turns one or two
fixed phone clips into the Droid brief's `field.json` + `track3d.jsonl`
([agent-3-droid-realtime.md](../../docs/plan/prompts/agent-3-droid-realtime.md)), plus `events.json` and a
browser point-cloud viewer. Rationale: [sport-feasibility.md](../../docs/plan/sport-feasibility.md).

```
candidates  BlurBall cache / BlurBall CSV / classical (MOG2 + colour + size)   ← the only sport-specific piece
tracker     constant-velocity gate, kink gate, birth after 3 consistent hits, death after 6 misses
calibration four table corners once per camera → focal from the homography → PnP pose (+ line refinement)
lift        time-aligned DLT triangulation, reprojection gate, pixel-Jacobian covariance + clock-skew term
bounces     2D kink time per camera → per-camera plane lift extrapolated to that instant → inverse-variance combine
events      bounce (side, line distances, edge band), contact (velocity impulse), dead ball, serve toss (parabola fit)
```

## Run it
```bash
cd services/flight && uv sync
# 1. synthetic two-camera rally with truth (labelled SYNTHETIC)
uv run python -m flight.cloud synth --out /tmp/synth0
# 2. from the rendered videos with the classical detector, or from BlurBall caches (tracker-branch JSON / CSV)
uv run python -m flight.cloud run --field /tmp/synth0/field.json --cam side=/tmp/synth0/side.mp4 --cam diag=/tmp/synth0/diag.mp4 --out /tmp/synth0/out
uv run python -m flight.cloud eval --out /tmp/synth0/out --truth /tmp/synth0/truth.json
open /tmp/synth0/out/viewer.html
```
Real clips: `frame0` writes the first frame so you can read the four corner pixels; `calibrate --cam side --video
side.mp4 --corners x,y,... --refine` solves the pose into `field.json`; then `run` with `--cam side=side.mp4
--cam diag=diag.mp4 [--offset diag=0.012] [--ball orange]`, or with `--cam side=side-blurball-gray.json` to start
from the tracker branch's cached BlurBall output. Corner order: A-right, B-right, B-left, A-left (counter-clockwise
from above). Both phones must be still for the whole clip; they may stand anywhere.

## Measured (synthetic only, 2026-10-24, this Mac)
No real footage was available on this machine. Numbers below are from `flight.synth` rallies (two cameras, 30 fps,
12 ms clock skew, 1.5 px detection noise, 8 % misses, 5 % false blobs) and say nothing yet about real video.

| Input (seed 0) | track3d error vs truth | bounces | contacts | serve toss |
|---|---|---|---|---|
| rendered videos, classical detector | median 2.6 cm, p95 5.2 cm, 100 % within 3σ | 7/7 matched, xy median 3.0 cm, max 4.6 cm | 6/7 | height 13 cm vs 20 cm true: the resting ball is invisible to background subtraction, so release is unobserved (`release_observed: false`) |
| BlurBall-like cache | median 1.4 cm, p95 3.0 cm, 100 % within 3σ | 6/7, xy median 2.7 cm, max 11.9 cm | 5/7 | wrong: the cache has a 3-frame hole at the contact, so the impulse is smeared |
| 10 seeds, 66 bounces (caches) | — | xy median 1.8 cm, p90 6.3 cm, max 23 cm; timing median 3.8 ms; 91 % within 3σ | — | — |

Throughput: both 1280×720 videos, 175 frames each, in 3.0 s wall on the CPU (about 60 fps per camera, classical).
Tests: `uv run pytest` (13; calibration, detector, tracker, end-to-end synthetic).

## Known limits
- The classical detector cannot see a ball at rest, so the serve release needs a learned detector (BlurBall) or
  the tracker's last known position; `serve_toss.release_observed` says which.
- Bounce timing comes from 30 fps samples: a 10 ms error is 3–5 cm at rally speed. The timing term is in σ.
- A few bounces per rally still miss by more than 10 cm (late-rally, fast balls with sparse samples); the worst
  case on synthetic data was 23 cm. Those carry a large σ and would be BETA, not AUTO.
- Focal length comes from the table homography; a near-fronto-parallel view leaves it poorly constrained and the
  code falls back to a default and says so (`f_source: "default"`). Pass `--f-px` when known.
- Clock skew between phones is taken from `field.json` (`time.skew_sigma_s`); a measured offset goes in `--offset`.
