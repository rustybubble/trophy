# Task: write one new geometry check, `checks/{{name}}.py`, that answers a referee's question

A judge asked: **"{{question}}"**. No check in the library answers it. The referee's router suggested:
`{{hint}}`. Write **one new file, `checks/{{name}}.py`**, that answers it from the fused 3D ball track. Work fast and
directly (the referee is waiting: budget 60 s, hard cap 90 s): read one similar existing check, write the new one, run
`{{gate}}`, repair, done.

## The track and the API

`checks/*.py` are pure functions over a fused 3D ball track (metres, field frame: origin at the table centre, +x toward
side B, net plane x = 0, z up from the table top). Read `checks/rally_summary.py` or `checks/contacts.py` as a model
(they are short); the API they import is in `reference/checks_api.py` (read it there; never search the disk:
reads outside the sandbox are refused). Every check has a top-level `PARAMS = {...}` (each tunable with a comment) and

```python
def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    ...
    return result("{{name}}", verdict, p=probability_or_None, evidence={...}, calibrated=...)
```

`track` iterates `Sample`s with `.t` (s), `.x` `.y` `.z` and `.xyz` (metres), `.sigma` and `.n_views`; `track.t0` / `track.t1`
bound it. `result(check, verdict, *, p=None, t_s=None, sigma_m=None, evidence=None, calibrated=True, text="")` builds the
answer; put the numbers the referee should say in `evidence` (rounded), and say `calibrated=False` when the answer rests
on default uncertainties. If the track can't answer (too few samples in the window), return a verdict of `"unknown"`
with `p=0.0` instead of guessing.

The session's query arguments are `{{query}}` (`t_s` for a moment, or `t0`/`t1` for a window): accept them.

## Imports (the loader refuses anything else)

Only `math`, `statistics`, `itertools`, `functools`, `bisect`, `heapq` and
`from trophy_engine.checks.api import ...` of its public names (`Field`, `Track`, `merge_params`, `result`, `phi`,
`motion_sigma`, `line_fit`, `quad_fit`, `refine_bounce`, `edge_probs`, ...). No `typing`, `collections`,
`dataclasses`, `open`, `exec`, `eval`, `getattr` or dunders.

## The gate

`{{gate}}` (no arguments) checks that the whole library, yours included, still passes check-test on the labelled
samples, that `checks/{{name}}.py` loads under the allowlist, and that it returns the same valid result twice on the
session's own track (`session/track3d.jsonl`, `session/field.json`, `session/query.json`). Do not read
`samples/*.track3d.jsonl` or `session/track3d.jsonl` (large).

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `{{gate}}` may be executed. There is no network. Do not edit any existing check.

## Done when

`{{gate}}` passes. Begin your reply with a `## Plan` (2-4 lines), write the file, run the gate, repair what fails, and
end with a `## Result`: what the check measures and the answer it gave on the session track.
