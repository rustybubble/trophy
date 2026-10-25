# Task: write the `{{sport}}` rule pack from the laws

`sports/{{sport}}/rules.yaml` holds the pack's `params`, `field` and `scoring` blocks (the table and the scoring
system) and an **empty `rules:` list**. Write the rules. Every rule comes from a law in {{laws}} and uses only the
vocabulary in {{vocabulary}} (every `ev.*`, `rally.*`, `game.*`, `params.*` field the engine can supply, rendered
from the engine's code). For each law that a referee decides during a rally, produce **either** a rule carrying
`rule_ref: "<clause id>"` **or** a line under `## Not encodable` in your result naming the measurement that is
missing. Never approximate a law with a field that does not carry the information.

## What makes a good pack

- Rules run in order; the first scoring rule that fires (kind `point`/`violation` with `points`, or `outcome: let`)
  ends the rally. Put specific rules (a serve let) before general ones (a net into one's own side).
- `tier: AUTO` only for a geometric fact at p >= 0.90 in the event (`ev.payload.p_in`, `ev.conf`); `BETA` for
  anything close or judged (edges, nets, dead balls); `PLAYERS` when the sensors cannot judge.
- `kind: point` with `team:` (CEL for the side that wins; `opponent(side)` is available) and `points: 1`;
  `outcome: let` replays with no team. `text` (<= 80 chars, may use `{team}`) and `speech` are spoken by the referee.
- Evidence first. The samples include a judge-labelled recording of real play: it contains weak single-camera
  bounces, a single-camera net reversal, bounces a few centimetres from the net whose side is uncertain
  (`ev.side_p`), and same-side bounces with a racket contact between them (`rally.hit_since_last_bounce`) or more
  than a second apart (`rally.t_since_last_bounce_s`). A pack that calls points on those is wrong; the label says
  that span was ONE rally with one winner. Use `params.evidence_min_cams` + `params.evidence_min_conf` and the
  `rally.*` evidence fields so a point is called only on evidence that supports it.
- Add any new `params:` you need (keep the existing ones). Keep rule ids snake_case.

## Working method

1. Run `{{gate}}` once with the empty list to see every sample's events (`.trophy/events.json`) and the labels
   each expects (`.trophy/results.json`: `calls:winner`).
2. Write the pack. Run `{{gate}}`; repair until it passes: every sample must replay as exactly one point to its
   labelled winner, and the `rules:coverage` row tells you which of your rules never fired (no evidence either way;
   keep them if the law is clear, say so in your result).

## Running the gate (read this before your first command)

Run the gate as exactly `{{gate}}`: no `cd`, no pipes, no `| tail`, no `;`, no redirects, no other command, or the
sandbox refuses it. Its output is the test table. Then read `.trophy/results.json` and `.trophy/events.json` with
your file-reading tool (paths relative to the sandbox root); never search the disk for them.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `{{gate}}` may be executed. There is no network. Do not read `samples/*.jsonl` directly (large); the gate's
`.trophy/events.json` has what you need.

## Done when

`{{gate}}` passes every check. Begin with `## Plan` (3-6 lines), write the rules, run the gate, repair, and end with
`## Result`: a table `law | rule id | tier | evidence (which sample fired it, or "none")`, then `## Not encodable`
with one line per law you could not encode and the missing measurement.
