# Task: write the `{{sport}}` interpreter

Trophy is an AI referee. For each sport, an **interpreter** decides, from the events the referee sees, whether a play
is a point, a let, out or a fault, who it favours and who is at fault. The interpreter is the sport's rule pack:
`sports/{{sport}}/rules.yaml` (CEL rules over events; the engine runs it). {{seeded}}

Work fast and directly (the budget is 90 s): read `sports/{{sport}}/RULES.md`, `sports/{{sport}}/config.yaml`,
`reference/events.md` and `reference/table_tennis/rules.yaml` (a worked example), glance at one fixture's labels,
write the pack, run `./replay_test`, fix what fails.

## What you have (all read-only except the allowlist)

- Rulebook summary: {{rulebook}}
- The court: `sports/{{sport}}/config.yaml`
- The event vocabulary: `reference/events.md` (full schema: `schema/event.schema.json`; the pack's: `schema/rulepack.schema.json`)
- A golden pack to copy the shape from: `reference/table_tennis/rules.yaml`
- Hand-annotated plays and the calls they must produce:
{{fixtures}}
- Layer-1 golden fixtures (sports with perception only): {{samples_or_none}}

Labels are `{calls: [{t_s, outcome, team_id, at_fault, rule_id?}]}`: `team_id` is the team the call **favours** (it
scores), `at_fault` the team that committed the fault (null for a let), `t_s` the time of the event that decides it.

## How rules.yaml works

- Top level: `sport: {{sport}}`, `family: flight`, `version: 1`, `name`, `teams` (A and B), `field` (`frame` in words,
  `landmarks: []` is fine), `scoring: {template: rally, params: {points_to_win, win_by, serves_per_turn,
  deuce_serves_per_turn, games_to_win, cap?}}`, `params` (constants your rules read as `params.x`), `rules`.
- `rules:` are checked **in order** on every event; several may fire, but the first *scoring* rule (a `kind` of
  `point`/`violation`/`basket` with `points`, or `outcome: let`) ends the play. Put a specific rule (a let) before a
  general one (any net touch).
- A rule: `id` (snake_case), `name`, `tier` (`AUTO` for a measured fact, `BETA` when judged), `kind`
  (`point` | `violation` | `basket` | `line_call` | `edge_call` | `foul_flag` | `info`), `when` (CEL, true to fire),
  `check: code`, `outcome` (the label's word: `point`, `out`, `fault`, `let`, `net`, ...), `team` (CEL: the team the
  call favours), `points: 1` (2 or 3 for baskets), optional `at_fault` (CEL; default: the team opposite `team`, none
  for a let), `text` (≤ 80 chars; may use `{team}` and `{at_fault}`), `speech` (spoken: say what and who, e.g.
  `"Out. {at_fault}."`), `rule_ref` (the law you implement).
- A let is `kind: point`, `outcome: let`, with no `team` and no `points`.
- CEL: `ev.type`, `ev.side`, `ev.team_id`, `ev.payload.<field>`; `rally.phase` (`serve` | `rally`), `rally.bounces`,
  `rally.surface_bounces`, `rally.last_bounce_side`, `rally.last_hitter`, `rally.at_fault_side`, `rally.server_side`,
  `rally.receiver`, `rally.contacts`, `rally.nets`; `game.points.A`; `params.*`; functions `opponent(side)`, `phi(x)`,
  `has(ev.payload.x)` (an absent field is missing, never null: test `has()` first).
- A play opens on `bounce`, `contact`, `serve_toss` or `shot`. If plays in this sport start with another event, list
  them in a top-level `rally_openers: [...]`. After a scoring call the ball is dead until `ball_dead` or 2 s.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network.

## Done when

`./replay_test` passes: the pack loads, every fixture replays deterministically, every labelled call is reproduced
(outcome, team, at fault, within the label's tolerance) and no decisive call is made that is not labelled. Begin with
a `## Plan` (3-5 lines), write the pack, run the gate, repair, and end with a `## Result` listing your rules and the
law each implements.
