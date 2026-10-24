# Task: apply a house rule to `{{sport}}`

The judge added this house rule, in their own words:

> {{text}}

Implement it by editing **only** `sports/{{sport}}/rules.yaml` (schema: `schema/rulepack.schema.json`). A scoring change ("first to 7", "win by 1") is a change to `scoring.params`. A new rule is an entry in `rules:` with a CEL `when` over `ev` (the current event: `ev.type`, `ev.side`, `ev.payload.*`), `rally` (`rally.phase` = `serve|rally`, `rally.bounces`, `rally.last_bounce_side`, `rally.last_bounce_surface`, `rally.server_side`, `rally.receiver`, `rally.last_hitter`, `rally.opponent_of(side)`), `game` and `params`; an `outcome`; a `tier` ceiling (`AUTO` only for a geometric fact, `BETA` for anything close or judged); `text` and `speech`; and `house_rule: true`. Event types available: `bounce` (payload `surface`, `side`, `d_lines_m`, `p_in`, `edge{top_edge, side_face, surface}`), `contact` (`side`, `kind`), `net` (`kind` = `touch|into|over`, `from_side`), `ball_dead` (`reason`, `last_side`), `serve_toss` (`height_m`, `angle_from_vertical_rad`, ...). A rule that replays the point uses `outcome: let` with no `team`/`points`. If the rule needs a measurement no event carries, say so in your result instead of inventing one.

## What you have

- `sports/{{sport}}/`: the current module (read `rules.yaml` fully before editing; `config.yaml` and `events.py` are read-only context).
- Sample layer-1 logs with labels:
{{samples}}
- `./replay_test`: the test gate (schema validation, the module still loads, every sample still produces the labelled bounces). Run it after your edit.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network.

## Done when

`./replay_test` passes. Begin with a `## Plan` section (what the rule means and which YAML keys change), make the edit, run the gate, and end with a `## Result` section quoting the rule you added or the params you changed.
