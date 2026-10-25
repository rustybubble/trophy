# Task: repair the `{{sport}}` rule pack after a judge's correction

The judge watched the play and ruled, in their own words:

> {{text}}

The pack scored that span wrongly. Edit **only** `sports/{{sport}}/rules.yaml` so that `{{gate}}` passes on every
sample, including the judge-labelled recording. Work from evidence, not guesses:

- {{vocabulary}}: the complete vocabulary, every `ev.*`, `rally.*`, `game.*` and `params.*` field the engine can
  supply, rendered from the engine's code. A condition may use nothing else.
- {{laws}}: the sport's laws (paraphrased, with ITTF clause ids for `rule_ref`).
- `.trophy/results.json` after a gate run: per sample, `calls:replay` lists the calls the pack produced and
  `calls:winner` what the label expects (one rally = exactly one point call to the labelled winner).
- `.trophy/events.json` after a gate run: every event of every sample in order, with `cams`, `conf`, `pos_m`,
  `sigma_m`, `payload.p_in`, and the contacts between bounces.

## How to work

1. Run `{{gate}}` first; read the two `.trophy` files for the recorded sample.
2. For each wrong call, find in the events what the rule did not check: how many cameras saw the bounce and how
   confident it was, how sure its side was (`ev.side_p`, from its distance to the net and its sigma), whether a
   racket contact came between two same-side bounces (`rally.hit_since_last_bounce`), how long apart they were
   (`rally.t_since_last_bounce_s`; after a table bounce the ball is back down within about a second), whether the
   ball was in (`ev.payload.p_in`), whether a net reversal was seen by one camera only.
3. Express the fix as rule conditions and/or `params:` values. `params.evidence_min_cams` with
   `params.evidence_min_conf` makes a bounce or net seen by fewer cameras AND with lower confidence an observation
   only (it never reaches the rules or the rally state). Ground every condition in a law from {{laws}}: a double
   bounce is the ball touching the opponent's court again before the opponent strikes it (2.10.1.3), a net into
   one's own side is a failed return (2.7.1, 2.10.1.2). Never special-case a time, an id or a sample name.
4. Run `{{gate}}`; repair until it passes. The synthetic samples must keep their labelled winners; the recorded
   sample must score as exactly one point to the labelled winner.

## Running the gate (read this before your first command)

Run the gate as exactly `{{gate}}`: no `cd`, no pipes, no `| tail`, no `;`, no redirects, no other command, or the
sandbox refuses it. Its output is the test table. Then read `.trophy/results.json` and `.trophy/events.json` with
your file-reading tool (paths relative to the sandbox root); never search the disk for them.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `{{gate}}` may be executed. There is no network. Do not read `samples/*.jsonl` directly (large): the gate's
`.trophy/events.json` has what you need.

## Done when

`{{gate}}` passes every check. Begin your reply with `## Plan` (3-5 lines), make the edits, run the gate, and end
with `## Result`: each rule or param changed, the evidence in the sample that justified it, and the law it follows.
