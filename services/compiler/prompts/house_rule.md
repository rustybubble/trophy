# Task: decide and apply a house rule for `{{sport}}`

The players added this house rule, in their own words:

> {{text}}

You are the deciding agent (D-43). Decide whether it **applies**: a rule of play for this sport that you can express
with the events the referee measures. If it does, implement it in `sports/{{sport}}/rules.yaml`. Either way, write
your decision to `decision.json`:

```json
{"applies": true, "rationale": "One or two sentences: what the rule changes, or why it can't apply."}
```

If it applies and the gate passes, Trophy applies it at once (no judge tap), re-judges this game's plays under it and
announces how many calls changed; the judge can undo it in one tap. If it does not apply (not about play, needs a
measurement no event carries, contradicts itself, or would make the game unplayable), leave `rules.yaml` unchanged,
set `"applies": false` and say why.

Work fast and directly: read `sports/{{sport}}/rules.yaml` (the pack in force, earlier house rules included), make the
edit, write `decision.json`, run `./replay_test`. Do not read the sample or fixture logs, the session or the schemas.

## How rules.yaml works

- A scoring change ("first to 7", "win by 1") is a change to `scoring.params` (`points_to_win`, `win_by`,
  `serves_per_turn`, `deuce_serves_per_turn`, `games_to_win`, `cap`).
- A new rule is an entry in `rules:`, checked in order; the first scoring rule that fires ends the play. Fields: `id`
  (snake_case), `name`, `tier` (`AUTO` for a geometric fact, `BETA` for anything close or judged), `kind` (`point` |
  `violation` | `basket` | `edge_call` | `info`), `when` (CEL), `check: code`, `outcome`, optional `team` (CEL: the
  team the call favours), `points: 1`, optional `at_fault` (CEL; default: the team opposite `team`), `text` (≤ 80
  chars, may use `{team}` and `{at_fault}`), `speech`, `requires: [<event type>]`, `house_rule: true`.
- A rule that replays the point (a let) is `kind: point`, `outcome: let`, with no `team` and no `points`.
- CEL vocabulary: `ev.type` (`bounce` | `contact` | `net` | `ball_dead` | `serve_toss` | `shot` | ...), `ev.side`,
  `ev.team_id`, `ev.payload.*` (bounce: `surface` table|court|floor, `p_in`, `edge.top_edge/side_face/surface`; net:
  `kind` touch|into|over, `from_side`, `serve`; contact: `kind`; ball_dead: `reason`; shot: `made`, `behind_arc_p`),
  `rally.phase` (`serve` | `rally`), `rally.bounces`, `rally.surface_bounces`, `rally.last_bounce_side`,
  `rally.at_fault_side`, `rally.server_side`, `rally.receiver`, `rally.nets`, `game.points.A`, `params.*`; functions
  `opponent(side)`, `phi(x)`, `has(ev.payload.edge)`.
- Put a rule that must win over an existing one **before** it in the list (e.g. a serve let before
  `net_into_own_side`). Disabling a rule = removing it or tightening its `when`.

## This game

{{session}}

The gate's test table shows labelled fixtures as before/after but does not fail on them: a house rule may change
outcomes on purpose. It fails if the pack doesn't load or a replay errors.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network.

## Done when

`decision.json` is written and `./replay_test` passes. Begin with a `## Plan` (3-5 lines), make the edit, run the
gate, and end with a `## Result` quoting the rule you added or the params you changed, your decision, and the
`calls_changed` the gate reported.
