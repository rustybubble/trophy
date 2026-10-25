# Task: retune `{{sport}}` detection parameters

A health metric crossed its threshold during a live game:

> {{text}}

Fix it by editing `sports/{{sport}}/config.yaml` (schema: `schema/sportmodule.schema.json`) and, only if a parameter change cannot fix it, `sports/{{sport}}/events.py` (pure, deterministic, imports only from the allowlist in the loader; see `reference` usage of `trophy_engine.sportmod.api`). `rules.yaml` is read-only context.

## What you have

- Scene descriptor: {{scene}}.
- Sample layer-1 logs with labels (the logs that showed the problem, when available):
{{samples}}
- `./replay_test`: the test gate. Run it after every change; `.trophy/events.json` shows what the module produced.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network.

## Done when

`./replay_test` passes. Begin with a `## Plan` section, make minimal changes, run the gate, and end with a `## Result` section listing each parameter changed, from what to what, and why.
