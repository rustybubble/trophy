# Compiler: the Factory Droid that writes Trophy's sport modules (Agent 3)

**Node ≥ 20, `@factory/droid-sdk` 0.10.0 (Node entrypoint), the `droid` CLI 0.249.0, port 8200.** This is the source
of the root README's Factory section.

## Where Droid is used

Trophy keeps rules out of code: a sport is a module in `sports/<sport>/` (`config.yaml` detector parameters,
`events.py` layer 1 → layer 2 events, `rules.yaml` the CEL rule pack; see [`sports/README.md`](../../sports/README.md))
plus, since D-36, a **check library** `sports/<sport>/checks/*.py`: handwritten geometry checks (`phases`, `bounces`,
`in_out`, `net_touch`, `contacts`, `serve_toss`, `rally_summary`) over a fused 3D ball track, with `library.json`
saying whether they were calibrated. A Factory Droid is the thing that writes and edits those files. It does four
jobs, each from a trigger we designed:

| Trigger                                                                                                               | Job                                                                                                                                                    | What the Droid may edit                                              |
| --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| a `house_rule` row with `status = 'pending'` in Spacetime (the judge typed or said a rule)                            | **house_rule**: implement "first to 7, win by 1" or "a serve that clips the net is a let"                                                              | `rules.yaml` only                                                    |
| a session with no approved module for its sport, plus Agent 2's scene descriptor (`scene.schema.json`)                | **compile**: derive `sports/pickleball/` from the golden `sports/table_tennis/`                                                                        | all three files of the new module                                    |
| a health metric crossing a threshold (ball lost > 40 % of frames, reprojection error rising)                          | **retune**: adjust thresholds, or the detector logic if a parameter can't fix it                                                                       | `config.yaml`, `events.py`                                           |
| the judge finishes camera setup: corners, clap sync, a warm-up recording (`field.json` + labelled `track3d` fixtures) | **calibrate_checks**: specialise the golden check library to this calibration (sigma model, surface/floor bands, serve zone, dead-ball gap, edge band) | every `checks/<name>.py` of the copied library; never `library.json` |
| the judge rules on the dashboard that a span of play was ONE rally won by X (`label_rally`; a `house_rule` row with `source = correction`) | **correction**: repair the pack so the judge-labelled recording replays as the judge ruled, every other sample unchanged | `rules.yaml` only |
| the CLI, once per sport (`trophy-droid compile-rules`) | **compile_rules**: write the whole `rules:` list from `sports/<sport>/laws.md` against the synthetic samples and every judge-labelled recording | `rules.yaml` only |

Today the house-rule trigger is live through the Spacetime subscription (`trophy-droid watch`); compile, retune and
calibrate run from the CLI until Agent 1 adds the `droid_run` and `sport_module` tables (row shapes in
`packages/contracts/droidrun.schema.json` and `sportmodule.schema.json`; `calibrate_checks` is already in the
`kind` enum, with `trigger.source = "session"`).

## Scoped access: what the Droid can touch

Each run gets a **fresh sandbox** (`~/.trophy/droid_runs/<run_id>/workspace`, or under `DROID_RUNS_DIR`; its own git repository) containing
only what the job needs, `TASK.md` (the brief from `prompts/`) and one fixed gate script that runs the engine's gate
with a pinned interpreter, module and samples. No repo, no `.env`, no secrets.

- **Module jobs:** the module to edit, the golden reference (compile jobs, read-only), the JSON Schemas, the scene
  descriptor, the sample layer-1 logs with labels, and `replay_test`.
- **calibrate_checks:** `checks/` (a copy of the golden library incl. `library.json`), `reference/checks/` (the same
  copy, read-only; the gate's _before_ column), `samples/field.json` + `*.track3d.jsonl` + `*.labels3d.json`,
  `rules/<sport>/` (the module, read-only; the gate scores the library's events with its `rules.yaml`),
  `schema/track3d.schema.json`, and `check_test`.

Enforcement is layered, because the SDK's own permission handler turned out not to be enough (measured 2026-10-24:
autonomy _off_ offers no Edit tool, autonomy _low_ auto-approves edits without asking; D-35):

1. **A PreToolUse hook in every sandbox** (`.factory/hooks.json` → [`hooks/guard.py`](hooks/guard.py), read-only):
   the Droid CLI runs it before each `Edit|Create|ApplyPatch|MultiEdit|Write|Execute`; it allows only the job's
   allowlisted files and the job's gate (`.trophy/allowlist.json` `commands`: `./replay_test` or `./check_test`,
   optionally prefixed with `cd <sandbox> &&`) and blocks everything else with exit 2, with the reason sent back to
   the model and recorded as a `blocked` step.
2. **The git audit:** after each turn the runner diffs the sandbox and **fails the run if any path outside the
   allowlist changed, or if nothing changed** (a gate that passes on an unchanged module proves nothing).
3. **The gate runs the Droid-written code jailed** (review blocker 2): the gate script takes no arguments and runs the
   engine's Python with `env -i` (only `PATH`, plus a `HOME` and `TMPDIR` inside the sandbox: no API keys), `-I -B`, and
   no network and no writes outside the sandbox (`sandbox-exec` on macOS; `unshare -rn` on Linux where the host allows
   user namespaces, network only; otherwise it says `none` in `.trophy/isolation` and on stderr). Sandboxes live in
   `~/.trophy/droid_runs` (`DROID_RUNS_DIR`), outside the repo, so none has the repo or its `.env` as an ancestor.
   Module and check code may import only `math`, `statistics`, `itertools`, `functools`, `bisect`, `heapq` and the
   engine's API modules, and from those only names in their `__all__`; a module object reached through an allowed
   module (`statistics.sys`) is refused. Approved code is never loaded automatically: the engine and `trophy-live` run
   the handwritten golden module; session checks load only with an explicit `--checks`.
4. **The runner runs the gate itself** (`replay_test` or `check_test`) and enforces a 90 s wall clock (`DROID_TIMEOUT_S`).
5. The SDK permission handler ([`src/droidAgent.ts`](src/droidAgent.ts)) still answers any confirmation that does
   arrive with the same allowlist, and refuses script-mode confirmations outright.
   Web fetch, web search, sub-agents, skills and automation tools are disabled. Inside `events.py` the engine's loader
   refuses imports outside a small stdlib allowlist and the usual escape hatches (`exec`, `eval`, `open`,
   `__import__`, dunder access); the checks loader (`trophy_engine.checks.library`) applies the same allowlist to
   `checks/*.py` and additionally requires a top-level `PARAMS` and `check()`.

**Model.** `DROID_MODEL` defaults to `claude-sonnet-5`. In SDK sessions some models (`claude-opus-5-5`,
`claude-fable-5.1`, `gpt-6-sol`; measured 2026-10-24) run in _script_ tool-execution mode, where edits happen inside a
script the permission handler can only partly inspect; the runner refuses script confirmations, so pick a model that
runs in direct mode (`claude-sonnet-5`, `claude-opus-4-8`).

## The loop and the test gate

draft → gate → repair, at most `DROID_MAX_ATTEMPTS` (3) times. Both gates print a before/after table and write it as
`DroidRunResults` JSON (`.trophy/results.json`), with the events in `.trophy/events.json`.

- **`replay_test`** (module jobs; `services/engine/trophy_engine/replay_test`) replays every sample log through the
  candidate module and checks: the module loads (schemas + allowlist), `events()` runs, every event validates against
  `trophy.event.v1`, the run is deterministic, the surface-bounce count matches the labels, bounces alternate sides, and
  bounce times match the labels (recall/precision). The rule engine's "calls that would change" column joins the
  table in stage 2.
- **`check_test`** (calibrate*checks; `services/engine/trophy_engine/check_test`) loads the candidate library under the
  import allowlist, runs every check on each labelled fused track and checks determinism, the labelled rallies
  (`phases`), table and floor bounces (recall, precision, side, position error), in/out on every labelled margin
  (never wrong at AUTO confidence), nets, contacts and serve legality; then it replays the library's events through
  the rule engine with `rules/<sport>/rules.yaml` and compares rally winners with the labels. `reference/checks` is
  the \_before* column.

### calibrate_checks (D-36)

- **Trigger:** the judge finishes camera setup; the gateway will write a `droid_run` row of kind `calibrate_checks`
  (today: `trophy-droid calibrate`). `trigger.source` is `session`; `trigger.samples` records the `field.json` and the
  samples directory the run was built from.
- **Sandbox:** see above. The prompt is [`prompts/calibrate_checks.md`](prompts/calibrate_checks.md): edit the copied
  library to this calibration, never rewrite a file, do not read the large tracks, `## Plan` first, `## Result` last,
  60 s target / 90 s cap.
- **Allowlist:** every `checks/<name>.py` the copied library holds (enumerated at sandbox time; 7 today), nothing
  else: not `checks/library.json`, not `reference/`, `rules/`, `samples/`, `schema/` or the gate. The guard's
  `commands` is `["./check_test"]`, so `./replay_test` is refused in a calibrate sandbox and vice versa.
- **Gate:** `./check_test` (above). The runner runs it itself after every turn that changed an allowlisted file.
- **Approve:** `trophy-droid approve <run_id> [--session <id>]` copies `workspace/checks/` to
  `data/local/sessions/<session_id>/checks/` (the session from `--session`, else the job that started the run
  (`job.json` beside `run.jsonl`), else the run id), writes `library.json` there as `{"calibrated": true, run_id,
session_id, field, field_sha256, approved_at_ms, approved_by}` (the engine reads `calibrated`) and a
  `SportModuleRow` as `sport_module.json`, and marks the run `approved`. Module runs keep the
  `data/local/modules/<sport>/v<n>` path.
- **Session lifecycle:** the library lives as long as the session; a new calibration is a new run whose approval
  replaces it. If the run fails, the session uses the golden library unedited with `calibrated: false` on every check,
  and the judge view says so.

## Laws, labels and evidence: where the Droid's facts come from

The Droid never guesses a rule and never sees a hand-written one for `compile_rules`. Its sandbox carries three
kinds of evidence and nothing else:

- **`context/laws.md`**: the sport's laws, paraphrased with clause ids (`sports/<sport>/laws.md`; the ITTF Handbook
  chapter 2 for table tennis). Every rule it writes cites one as `rule_ref`. A retrieval service can replace the
  file: the seam is `Job.lawsPath`, and `MOSS_PROJECT_ID`/`MOSS_PROJECT_KEY` are reserved in `.env.example` for a Moss
  index of scraped rulebooks (the Apify -> Moss design of interfaces §17). No Moss project exists yet, so there is no
  Moss code: the file is the source until the user creates one.
- **`context/events.md`**: the vocabulary, rendered by `python -m trophy_engine.vocabulary` from the engine's code:
  every `ev.*` field (event.schema.json payloads plus the engine's derived `ev.n_cams` and `ev.side_p`), every
  `rally.*` field (`trophy_engine.rally.RALLY_FIELDS`, including the evidence fields `hit_since_last_bounce`,
  `t_since_last_bounce_s`, `last_bounce_side_p`), `game.*`, the pack's `params.*` and the engine's evidence policy
  keys (`evidence_min_cams` + `evidence_min_conf`: weaker events never reach the rules). A law that needs a
  measurement not in this file is declared "not encodable" in the Droid's result instead of being approximated.
- **Samples**: the labelled synthetic rallies plus **judge-labelled recordings** of real play, both versioned
  (`evals/fixtures/recorded/<sport>`: pixel samples and the layer-2 events the engine saw, no media) and exported
  live by the engine when the judge presses "that was one rally, won by X" on the dashboard
  (`data/local/labelled/<sport>/<game>_labelNN.{l2.jsonl,labels.json}`). The gate's `calls:winner` row demands
  exactly one point call to the labelled winner, so a pack that calls five points on one rally cannot become
  `ready`, and `rules:coverage` lists the rules no sample exercised.

The judge's correction is the real-time loop: dashboard button -> `label_rally` -> the engine voids the span's
points, posts the judge's point, exports the sample and inserts the `correction` row -> `trophy-droid watch` runs
the job with a 300 s / medium-effort budget -> the Droid panel streams plan, diff and gate table -> Approve
hot-loads the repaired pack. The hand-written pack this branch started from called five points on the recorded
rally (`evals/fixtures/recorded/table_tennis/README.md`); that recording is now the regression sample every pack
job is gated on.

## Visible work

Every change to the run row (`DroidRun`, `droidrun.schema.json`: plan, steps, diff, test table, blocked calls, timings,
token usage) is pushed to the sinks as it happens: stderr, `~/.trophy/droid_runs/<run_id>/run.jsonl`, and for
house rules the Spacetime `house_rule` row via `update_house_rule_progress`, which Agent 1's dashboard panel renders.

## Measured (2026-10-24, this Mac, `claude-sonnet-5`, effort low, single runs)

| Job                                                                 | Wall time        | Attempts | Gate                                                              |
| ------------------------------------------------------------------- | ---------------- | -------- | ----------------------------------------------------------------- |
| House rule "a serve that clips the net and lands in is a let"       | 30.6 s           | 1        | 19/19 in 0.5 s                                                    |
| Derive `sports/pickleball/` from table tennis + the synthetic scene | 69.2 s           | 1        | 19/19 in 0.5 s                                                    |
| calibrate_checks on `evals/fixtures/synthetic/table_tennis_3d`      | not yet run live | —        | 25 checks; ~1.9 s per gate run with a scripted agent (2026-10-24) |
| compile_rules: the whole table-tennis pack from `laws.md` (2026-10-24, effort low, 600 s cap) | 531 s | 1 | 34/34 in 0.8 s (synthetic + the judge-labelled recording); a first run at effort medium read its inputs for 40 s and then produced nothing until its 480 s cap |
| correction: "9.2-48.1 s was ONE rally, won by B" on the live stream (2026-10-24, effort low, 300 s cap) | timed out | 1 | partial fix (`ev.side_p > 0.95` on double_bounce) after a 210 s silent gap; the cap is now 600 s and the label carries per-call evidence digests |

## Approval

A `ready` run is not applied. `trophy-droid approve <run_id>` copies the module to `data/local/modules/<sport>/v<n>/`
with a `SportModuleRow`, and the worker hot-loads from there (judge approval in the dashboard calls the same path
through `approve_house_rule`); a calibrate run goes to `data/local/sessions/<session_id>/checks/` instead (above).
The sandbox and its commit stay as the artifact.

## Where it can go wrong, and how we contain it

- **A wrong edit** (a rule that fires on the wrong event, a threshold that drops real bounces): the gate replays
  labelled logs, so a module that loses bounces or breaks the schema never becomes `ready`; the judge sees the diff and
  the table before approving.
- **A misread rule** ("let" implemented as a point): the gate cannot judge intent, so the plan and the diff are shown
  in plain text and a human approves; the engine replay of calls (stage 2) will show "calls that would change".
- **Runaway or malicious code** in `events.py` or `checks/*.py`: the import allowlist, no network, the file
  allowlist, the timeout and the throwaway workspace.
- **A library tuned to pass the gate, not the game:** the gate's synthetic truth comes from this calibration's
  geometry and the warm-up recording; `in_out` must never be wrong at AUTO confidence, and the judge sees the
  parameter diff before approving. Until a calibrate run is measured live, every check stays `calibrated: false`.
- **No key, no run.** The compiler refuses to start without `FACTORY_API_KEY` (`.env`, never committed). There is no
  stub backend and no keyless mode.

## Run it

```bash
npm i -g @factory/cli@0.249.0                 # the droid CLI (or set DROID_EXEC_PATH)
cd services/engine && uv sync                  # the gate's interpreter
cd ../compiler && npm run cli -- house-rule --sport table_tennis --text "a serve that clips the net is a let"
npm run cli -- compile --sport pickleball --from table_tennis    # scene + samples default to evals/fixtures/synthetic/pickleball
npm run cli -- calibrate --sport table_tennis --session s_demo01 # field + samples default to evals/fixtures/synthetic/table_tennis_3d
npm run cli -- watch                           # subscribe to pending house rules in Spacetime (needs SPACETIME_COMPILER_TOKEN)
npm run cli -- approve <run_id>
```

The CLI runs through `tsx` (the generated Spacetime bindings use extensionless imports, which Node's type stripping can't resolve). Tests: `npx vitest run --root services/compiler` (the run-loop tests use the real sandbox and the real gate with a
scripted agent; they skip when the engine venv is missing, and the calibrate run-loop tests also skip, saying so,
while the golden check library itself is red on the 3D fixtures). No test calls Factory.

Contracts: `docs/plan/interfaces-v1.md` §18. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Measured numbers
go in `docs/progress.md` and `docs/status/a3.md`.
