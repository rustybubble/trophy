# Engine (Agent 3)
**py3.11, `uv`.** Stage 1 (this PR) ships the sport-module layer: the API `events.py` may use
(`trophy_engine.sportmod.api`), the loader with its import allowlist, **`replay-test`** (the Droid's test gate: replays
layer-1 logs through a module and prints a before/after table, also as `DroidRunResults` JSON) and **`trophy-synth`**
(labelled-synthetic layer-1 logs, labels and scene descriptors). Stage 2 adds rule evaluation (CEL over `ev`, `rally`,
`game`, `params`), rally scoring, the confidence gate, calls written to Spacetime, and the "calls that would change"
column of the gate. Stage 3 adds `decide/` (background AI votes) and the live path.

```bash
cd services/engine && uv sync
uv run replay-test --module ../../sports/table_tennis --samples ../../evals/fixtures/synthetic/table_tennis
uv run trophy-synth --sport pickleball --out ../../evals/fixtures/synthetic/pickleball --name rally_03 --seed 5
uv run pytest -q
```

Contracts: `docs/plan/interfaces-v1.md`; `packages/contracts/{sportmodule,scene,droidrun}.schema.json`. Sport
modules: `sports/README.md`.
