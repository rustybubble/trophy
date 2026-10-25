# Sport modules: the Factory Droid's unit of work

`sports/<sport>/` holds exactly three files. They are the only files the Droid compiler may edit (the runner enforces
the allowlist; the agent is not trusted to), and together they turn layer-1 observations into calls:

| File | What it holds | Checked by |
|---|---|---|
| `config.yaml` | Detector parameters: court template and size, ball colour and size bounds, fps, confidence thresholds, bounce/net/dead settings | `packages/contracts/sportmodule.schema.json` |
| `events.py` | `events(observations, state) -> Iterable[Event]`: layer 1 (camera calibrations + ball samples) → layer 2 (`bounce`, `contact`, `net`, `ball_dead`) as `trophy.event.v1` dicts. Pure, deterministic, **imports only from the allowlist** (`trophy_engine.sportmod.loader.ALLOWED_IMPORTS`: a few stdlib modules + `trophy_engine.sportmod.api`). No I/O, no network | the loader's AST check + `event.schema.json` on every emitted event |
| `rules.yaml` | The rule pack: CEL `when` conditions over `ev`, `rally`, `game`, `params`; outcomes; tier ceilings; scoring params. "First to 7" is a param change | `packages/contracts/rulepack.schema.json` (the CEL engine evaluates it in stage 2) |

**Layers (D-18, D-21).** Layer 1 (`camera`, `ball_sample`) is written by perception. Layer 2 is a pure function of
layer 1 (`events.py`). Layer 3 (calls, points, score) is a pure function of layer 2 (the engine + `rules.yaml`).
Perception never calls points; if a rule needs a measurement that isn't in the DB, add an observation or event type
through a `contracts/*` PR.

**The test gate.** `replay-test --module sports/<sport> --samples <dir>` replays every `*.l1.jsonl` log in the
directory through `events.py` and checks the result against the `*.labels.json` next to it: the module loads
(schemas + allowlist), `events()` runs, every event validates, the run is deterministic, the surface-bounce count is
within tolerance, bounces alternate sides, and bounce times match the labels (recall/precision). `--json` writes the
table as `DroidRunResults` for the dashboard. The Droid must make this pass before a module can be approved.

**`sports/table_tennis/`** is the handwritten golden reference. The demo never depends on the Droid producing it; the
Droid's job is deriving other sports from it (`sports/pickleball/` in the demo) and applying house rules.

Fixtures: `evals/fixtures/synthetic/<sport>/` (labelled synthetic; `trophy-synth` generates them). Recorded logs from
real games go to `data/local/` (gitignored) and are labelled before they join a gate.

## `checks/`: geometry over the fused 3D track (D-36)

`sports/<sport>/checks/*.py` is the handwritten **golden check library**: one file per question the referee can be
asked about the 3D ball track (`track3d.schema.json`: fused `t_s, xyz_m, sigma_m, conf` samples plus a `field.json`
calibration). Each file has `PARAMS` (its defaults) and `check(track, field, params=None, **q) -> CheckResult`, imports
only `trophy_engine.checks.api` and a few stdlib modules (the loader's allowlist), and never decides a point.

| Check | Answers | How |
|---|---|---|
| `phases` | where rallies start and stop | still ball in a serve zone, then a sustained rise = release; floor, a gap or a still ball = end |
| `bounces` | every bounce with position, σ, side, surface, edge split | z minima; the incoming free flight (`z + g t²/2` is a line) solved for where it meets the surface |
| `in_out` | in / out / edge at an instant, with p | the bounce nearest the asked time; p = Φ(margin / σ), σ grows with speed × timing skew |
| `contacts` | racket hits | a velocity jump near an end line, above the surface |
| `net_touch` | touch / into at the net | plane crossings with clearance over the cord; a below-cord crossing that comes back is `into` |
| `serve_toss` | toss height and angle, legality (D-22) | release = held mean; apex = fitted parabola; hit = the velocity kink; one horizontal velocity for both legs |
| `rally_summary` | duration, peak speed | informational |

`library.json` says whether the library is **calibrated**: the golden one is not (every result carries
`calibrated: false`, which caps calls at BETA). A Droid `calibrate_checks` run (`services/compiler`) copies this library
into a sandbox with the session's `field.json` and warm-up samples, edits it to the setup, passes `check-test`, and the
judge approves it into `data/local/sessions/<id>/checks/` with `calibrated: true`.

The gate: `check-test --checks sports/table_tennis/checks --samples evals/fixtures/synthetic/table_tennis_3d`
(fixtures from `trophy-synth3d`, SYNTHETIC, labelled). The engine consumes the same checks live:
`trophy-engine --field field.json [--checks <dir>] [--track3d game.track3d.jsonl --speed 1] [--ask]`.
