# Flight: live ball tracking and the field-frame 3D map (table tennis)

**py3.11, numpy 1.26.4, opencv-python-headless 4.10.0.84; live BlurBall adds torch 2.5.1 on MPS (extra `blurball`).**
Live: [`flight.live`](#live-one-or-more-phones-flightlive) reads the phones' frame bus and emits events (below). Offline: turns one or two
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

## Live (one or more phones): `flight.live`
```bash
cd services/flight && uv sync --extra blurball        # torch 2.5.1 (MPS); the weights stay in <repo>/weights/blurball_best
uv run --extra blurball python -m flight.live --game follow         # what `make dev` runs (Procfile `flight:`)
uv run --extra blurball python -m flight.live --game g_x --corners c_side=x,y,x,y,x,y,x,y --no-spacetime
```
- Reads every frame of each `role=cam` phone (`FrameReader`, crop-aware, D-29) → BlurBall on MPS (`flight/blurball.py`:
  BGR→RGB, dedupe by `seq`, no silent CPU fallback, weights pinned by SHA-256) or `--detector classical` → #19's gated
  tracker → `trk:ball:{cam}` every frame + 10 Hz `track_sample`.
- **Seam (D-38):** the golden `sports/table_tennis/events.py` runs live on those layer-1 samples, over the open rally
  segment, every 100 ms; events go to `ev:flight` + Spacetime `observation` once they are 0.2 s old, deduplicated by id.
  `serve_toss` comes from `flight/serve.py` (one camera, the toss plane lift, launch-direction angle, the strike from
  the horizontal-velocity impulse, σ and `evidence_missing`).
- Calibration: `calib:{cam}` (the PWA's taps; reloaded on `ctl:calib`) or `--corners` in tap order
  (A_left, A_right, B_right, B_left). The pose for the toss is solved from the homography's corners. Untrusted
  calibration → `calib_untrusted` on every event. No calibration → tracked, but no events.
- `--game follow` attaches to the newest game and switches to each new one; `next` waits for the next; or an id.
- Tools: `python -m flight.bench` (detector + tracker fps and labelled recall on phone-path frames),
  `python -m flight.feed` (plays a clip onto `frames:{cam}` as a phone, without the gateway; `--engine` also creates
  and starts the game on `ctl:engine`).

### Measured (M5 Pro, macOS 26.6.2, 2026-10-24)
| What | Input | Result |
|---|---|---|
| Live loop throughput | the user's side + diagonal 720p clips played as two phones at once (`flight.feed`, 30 s each) | **30.0 fps per camera**, ~11 ms/frame, 0 frames skipped, bus lag 3 ms, BlurBall on `mps` |
| BlurBall per frame (bench) | side clip 1–44 s, phone path | p50 2.3 ms / p95 28 ms per frame (one model run per 3 frames, 30 ms), 71 fps processing |
| Detector + tracker vs hand labels (#9's `ttclips-side-*`, orange ball, handheld) | tuning split 1–44 s | BlurBall rgb 10/11 visible tracked, 3/27 empty frames with a ball; classical 0/11, 10/28 |
| same | held-out 50–106.5 s (scored once, settings fixed on the tuning split) | BlurBall 19/34 tracked (3 wrong position), 14/35 empty frames with a ball; classical 1/34, 18/35 |
| **SYNTHETIC** live end to end | `flight.synth` side render → `flight.feed` → `flight.live` → engine (`--state memory`) | BlurBall: 7/7 bounces, sides 7/7, timing error 5–15 ms, 0 spurious; toss 19.0 ± 2.5 cm vs 20.3 cm true (release unseen → `release`,`palm` missing); bounce → `ev:flight` latency p50 356 ms / p95 390 ms; one point call "Point Team B: no return" (right by the truth). Classical: 5/7, 5 spurious |
| **SYNTHETIC** toss estimator | `tests/test_serve.py` (side-on camera at the net, 1 px noise) | legal / < 16 cm / 40° tosses recovered within 3σ; struck-on-descent and contact time right |

Nothing above is call accuracy on real play: that needs the fixed-mount, white-ball labelled session
(`docs/demo-setup.md`). The live contacts are weak (the module found 2/7 synthetic racket hits).

## Known limits
- The classical detector cannot see a ball at rest, so the serve release needs a learned detector (BlurBall) or
  the tracker's last known position; `serve_toss.release_observed` says which.
- Bounce timing comes from 30 fps samples: a 10 ms error is 3–5 cm at rally speed. The timing term is in σ.
- A few bounces per rally still miss by more than 10 cm (late-rally, fast balls with sparse samples); the worst
  case on synthetic data was 23 cm. Those carry a large σ and would be BETA, not AUTO.
- Focal length comes from the table homography; a near-fronto-parallel view leaves it poorly constrained and the
  code falls back to a default and says so (`f_source: "default"`). Pass `--f-px` when known.
- Clock skew between phones is taken from `field.json` (`time.skew_sigma_s`); a measured offset goes in `--offset`.
