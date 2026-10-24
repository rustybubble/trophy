# Compiler: the Factory Droid that writes Trophy's sport modules (Agent 3)

**Node ≥ 20, `@factory/droid-sdk` 0.10.0 (Node entrypoint), the `droid` CLI 0.249.0, port 8200.** This is the source
of the root README's Factory section.

## Where Droid is used

Trophy keeps rules out of code: a sport is three files in `sports/<sport>/` (`config.yaml` detector parameters,
`events.py` layer 1 → layer 2 events, `rules.yaml` the CEL rule pack; see [`sports/README.md`](../../sports/README.md)).
A Factory Droid is the thing that writes and edits those files. It does three jobs, each from a trigger we designed:

| Trigger | Job | What the Droid may edit |
|---|---|---|
| a `house_rule` row with `status = 'pending'` in Spacetime (the judge typed or said a rule) | **house_rule**: implement "first to 7, win by 1" or "a serve that clips the net is a let" | `rules.yaml` only |
| a session with no approved module for its sport, plus Agent 2's scene descriptor (`scene.schema.json`) | **compile**: derive `sports/pickleball/` from the golden `sports/table_tennis/` | all three files of the new module |
| a health metric crossing a threshold (ball lost > 40 % of frames, reprojection error rising) | **retune**: adjust thresholds, or the detector logic if a parameter can't fix it | `config.yaml`, `events.py` |

Today the house-rule trigger is live through the Spacetime subscription (`trophy-droid watch`); compile and retune
run from the CLI until Agent 1 adds the `droid_run` and `sport_module` tables (row shapes in
`packages/contracts/droidrun.schema.json` and `sportmodule.schema.json`).

## Scoped access: what the Droid can touch

Each run gets a **fresh sandbox** (`data/local/droid_runs/<run_id>/workspace`, its own git repository) containing
only: the module to edit, the golden reference (compile jobs, read-only), the JSON Schemas, the scene descriptor, the
sample layer-1 logs with labels, `TASK.md` (the brief from `prompts/`) and `replay_test`, a fixed script that runs
the engine's gate. No repo, no `.env`, no secrets.

The session runs with autonomy **off**, so every edit, file creation and shell command comes back to our permission
handler ([`src/droidAgent.ts`](src/droidAgent.ts)), which proceeds only for edits inside the job's allowlist and for
`./replay_test`; everything else is cancelled and recorded as a `blocked` step. Web fetch, web search, sub-agents,
skills and automation tools are disabled. The runner does not take the agent's word for anything: after each turn it
diffs the sandbox with git, **fails the run if any path outside the allowlist changed**, runs `replay_test` itself,
and enforces a 90 s wall clock (`DROID_TIMEOUT_S`). Inside `events.py` the engine's loader refuses imports outside a
small stdlib allowlist and the usual escape hatches (`exec`, `eval`, `open`, `__import__`, dunder access).

## The loop and the test gate

draft → `replay_test` → repair, at most `DROID_MAX_ATTEMPTS` (3) times. The gate
(`services/engine/trophy_engine/replay_test`) replays every sample log through the candidate module and checks: the
module loads (schemas + allowlist), `events()` runs, every event validates against `trophy.event.v1`, the run is
deterministic, the surface-bounce count matches the labels, bounces alternate sides, and bounce times match the labels
(recall/precision). It prints a before/after table and writes it as `DroidRunResults` JSON. The rule engine's
"calls that would change" column joins the table in stage 2.

## Visible work

Every change to the run row (`DroidRun`, `droidrun.schema.json`: plan, steps, diff, test table, blocked calls, timings,
token usage) is pushed to the sinks as it happens: stderr, `data/local/droid_runs/<run_id>/run.jsonl`, and for
house rules the Spacetime `house_rule` row via `update_house_rule_progress`, which Agent 1's dashboard panel renders.

## Approval

A `ready` run is not applied. `trophy-droid approve <run_id>` copies the module to `data/local/modules/<sport>/v<n>/`
with a `SportModuleRow`, and the worker hot-loads from there (judge approval in the dashboard calls the same path
through `approve_house_rule`). The sandbox and its commit stay as the artifact.

## Where it can go wrong, and how we contain it

- **A wrong edit** (a rule that fires on the wrong event, a threshold that drops real bounces): the gate replays
  labelled logs, so a module that loses bounces or breaks the schema never becomes `ready`; the judge sees the diff and
  the table before approving.
- **A misread rule** ("let" implemented as a point): the gate cannot judge intent, so the plan and the diff are shown
  in plain text and a human approves; the engine replay of calls (stage 2) will show "calls that would change".
- **Runaway or malicious code** in `events.py`: the import allowlist, no network, the file allowlist, the timeout and
  the throwaway workspace.
- **No key, no run.** The compiler refuses to start without `FACTORY_API_KEY` (`.env`, never committed). There is no
  stub backend and no keyless mode.

## Run it

```bash
npm i -g @factory/cli@0.249.0                 # the droid CLI (or set DROID_EXEC_PATH)
cd services/engine && uv sync                  # the gate's interpreter
cd ../compiler && npm run cli -- house-rule --sport table_tennis --text "a serve that clips the net is a let"
npm run cli -- compile --sport pickleball --from table_tennis    # scene + samples default to evals/fixtures/synthetic/pickleball
npm run cli -- watch                           # subscribe to pending house rules in Spacetime (needs SPACETIME_COMPILER_TOKEN)
npm run cli -- approve <run_id>
```

The CLI runs through `tsx` (the generated Spacetime bindings use extensionless imports, which Node's type stripping can't resolve). Tests: `npx vitest run --root services/compiler` (the run-loop tests use the real sandbox and the real gate with a
scripted agent; they skip when the engine venv is missing). No test calls Factory.

Contracts: `docs/plan/interfaces-v1.md` §18. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Measured numbers
go in `docs/progress.md` and `docs/status/a3.md`.
