# Task: derive the `{{sport}}` sport module from `{{base_sport}}`

You are compiling a new sport module for Trophy, a universal AI referee for pickup games. A sport module is three
files in `sports/{{sport}}/`:

- `config.yaml`: detector parameters (court template and size, ball colour/size, fps, bounce/net/dead thresholds). Schema: `schema/sportmodule.schema.json`.
- `events.py`: `events(observations, state) -> Iterable[dict]`, turning layer-1 observations (camera calibrations and per-frame ball samples) into layer-2 events (`bounce`, `contact`, `net`, `ball_dead`) as `trophy.event.v1` dicts. It must be pure and deterministic and may import only `math`, `statistics`, `collections`, `collections.abc`, `dataclasses`, `typing`, `itertools`, `functools`, `bisect`, `heapq`, `enum`, `operator` and `trophy_engine.sportmod.api` (the event builders and geometry helpers; see how the reference uses them).
- `rules.yaml`: the rule pack (CEL `when` conditions over `ev`, `rally`, `game`, `params`; outcomes; tier ceilings; scoring params). Schema: `schema/rulepack.schema.json`. Perception never decides a point: only the rules do.

## What you have

- `reference/{{base_sport}}/`: the handwritten golden module. Read all three files first; derive, do not start from scratch.
- Scene descriptor: {{scene}} (cameras with homographies, the best-matching court template and its size, ball blob, people count).
- Sample layer-1 logs with labels (what a correct module must find):
{{samples}}
- `./replay_test`: the test gate. It loads the module (schemas + import allowlist), runs `events()` on every sample, validates every event, checks determinism, compares the surface-bounce count and timing with the labels, and checks that bounces alternate sides. Run it after every change. It writes `.trophy/results.json` and `.trophy/events.json` (the events you produced per sample, useful for debugging).

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network. Do not touch `reference/`, `schema/`, `samples/` or `replay_test`.

## What `{{sport}}` needs

Adapt the court geometry (dimensions, the play surface is the ground for court sports, net height), the ball (colour, size in pixels from the scene), the bounce thresholds (longer flights mean lower vertical pixel velocity at the bounce), and the rules: scoring params (e.g. pickleball: side-out or rally scoring to 11, win by 2; serve diagonally; the two-bounce rule; the non-volley zone / kitchen as a `zones` entry and a `violation` rule with `tier: BETA`, `check: ensemble`). Keep `field.frame` consistent with the reference (origin at the court centre, +x toward end B, z up, net plane x = 0). Keep rule ids snake_case and give every rule `text` and `speech`.

## Done when

`./replay_test` passes every check. Begin your reply with a `## Plan` section, then make the edits, run the gate, repair what fails, and end with a `## Result` section stating what changed and what the gate reported.
