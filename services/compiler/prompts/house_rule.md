# Task: apply a house rule to `{{sport}}`

The judge added this house rule, in their own words:

> {{text}}

Implement it by editing **only** `sports/{{sport}}/rules.yaml`. Work fast and directly: read `sports/{{sport}}/rules.yaml`,
make the edit, run `./replay_test`. Do not read the sample logs (`samples/*.l1.jsonl` are large), the schemas or
`events.py`; everything you need is here.

## How rules.yaml works

- A scoring change ("first to 7", "win by 1") is a change to `scoring.params` (`points_to_win`, `win_by`,
  `serves_per_turn`, `deuce_serves_per_turn`, `games_to_win`).
- A new rule is an entry in `rules:`, checked in order; the first scoring rule that fires ends the rally. Fields:
  `id` (snake_case), `name`, `tier` (`AUTO` for a geometric fact, `BETA` for anything close or judged), `kind`
  (`point` | `violation` | `edge_call` | `info`), `when` (CEL), `check: code`, `outcome`, optional `team` (CEL
  giving the side that wins the point) and `points: 1`, `text` (≤ 80 chars, may use `{team}`), `speech`,
  `requires: [<event type>]`, `house_rule: true`.
- A rule that replays the point (a let) is `kind: point`, `outcome: let`, with no `team` and no `points`.
- CEL vocabulary: `ev.type` (`bounce` | `contact` | `net` | `ball_dead` | `serve_toss`), `ev.side`,
  `ev.payload.*` (bounce: `surface` table|floor, `p_in`, `edge.top_edge/side_face/surface`; net: `kind`
  touch|into|over, `from_side`; ball_dead: `reason`), `rally.phase` (`serve` | `rally`), `rally.bounces`,
  `rally.surface_bounces`, `rally.last_bounce_side`, `rally.at_fault_side`, `rally.server_side`, `rally.receiver`,
  `game.points.A`, `params.*`; functions `opponent(side)`, `phi(x)`, `has(ev.payload.edge)`.
- Put a rule that must win over an existing one **before** it in the list (e.g. a serve let before `net_into_own_side`).
- If the rule needs a measurement no event carries, say so in your result instead of inventing one.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `./replay_test` may be executed. There is no network.

## Done when

`./replay_test` passes (it checks the pack still loads and every sample still produces its labelled calls). Begin
with a `## Plan` (3-5 lines), make the edit, run the gate, and end with a `## Result` quoting the rule you added or
the params you changed.
