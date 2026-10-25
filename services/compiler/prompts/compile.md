# Task: derive the `{{sport}}` sport module from `{{base_sport}}`

You are compiling a new sport module for Trophy, a universal AI referee for pickup games. `sports/{{sport}}/` already
holds a **copy** of the golden `{{base_sport}}` module; your job is to edit it into `{{sport}}`. Work fast and
directly (the budget is 90 s): read the three files in `sports/{{sport}}/` and `scene/scene.json`, edit, run
`./replay_test`. Do not read the sample logs (`samples/*.l1.jsonl` are large), the schemas, or `reference/` (it is
identical to your starting copy).

The three files:

- `config.yaml`: detector parameters. Change the court (`template`, `length_m`, `width_m`, `net_height_m`,
  `surface: court` for a ground court, `floor_z_m: 0.0` when the play surface is the ground), the ball (`colour`,
  `diameter_m`, `radius_px` from the scene's `ball.radius_px_mean`), and the bounce thresholds: longer flights mean a
  lower vertical pixel velocity at the bounce (`min_vy_px_s` ≈ 20) and a wider `plane_margin_m` (≈ 0.5) before a
  flip counts as a floor bounce. Keep `net_x_m: 0.0`.
- `events.py`: `events(observations, state)` turning camera calibrations + ball samples into `bounce`, `contact`,
  `net`, `ball_dead` events. It is generic over `config.yaml` (it reads the court size, `surface`, thresholds) and
  normally needs **no change** for a court sport. Only touch it if `./replay_test` shows the events are wrong. It may
  import only `math`, `statistics`, `collections`, `collections.abc`, `dataclasses`, `typing`, `itertools`,
  `functools`, `bisect`, `heapq`, `enum`, `operator` and `trophy_engine.sportmod.api`.
- `rules.yaml`: the rule pack. Change `sport`, `name`, `field` (dims, landmarks at the court corners, `lines`,
  `zones` incl. the non-volley zone / kitchen 2.13 m from the net on each side, as polygons of `[x, y]` metres with
  the origin at the court centre, +x toward end B, net plane x = 0), `scoring.params` (pickleball: to 11, win by 2,
  `serves_per_turn: 1`, `deuce_serves_per_turn: 1`), the rules (the serve must bounce on the **receiver's** side
  first: fix `serve_own_side_miss`'s `when` to `ev.side == rally.server_side`; keep `double_bounce`, `off_table` →
  rename the outcome to `out`, `net_into_own_side`, `ball_dead_after_last_bounce`; replace the table-tennis edge
  and serve-toss rules with a `kitchen_volley` violation rule, `tier: BETA`, `check: ensemble`, over a
  `contact` whose `ev.payload.kind == 'racket'` with `ev.payload.height_m > 0` inside the kitchen zone; say in your
  result that the kitchen rule needs a `person_feet` observation to be exact). Keep rule ids snake_case; every rule
  needs `text` and `speech`. Drop `variants` entries that only make sense for table tennis.

## What you have

- Scene descriptor: {{scene}} (cameras with homographies, the best-matching court template and its size, ball blob, people count).
- Sample layer-1 logs with labels (what a correct module must find):
  {{samples}}
- `./replay_test`: the test gate. It loads the module (schemas + import allowlist), runs `events()` on every sample,
  validates every event, checks determinism, compares the bounce count and timing with the labels, checks that
  bounces alternate sides, then replays the events through the rule engine with your `rules.yaml` and checks the
  labelled rally winner. Run it after your edits; it writes `.trophy/results.json` and `.trophy/events.json`.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network. Do not touch `reference/`, `schema/`, `samples/` or `replay_test`.

## Done when

`./replay_test` passes every check. Begin your reply with a `## Plan` (3-5 lines), make the edits, run the gate,
repair what fails, and end with a `## Result` stating what changed and what the gate reported.
