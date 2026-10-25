# Task: calibrate the `{{sport}}` check library to this setup

`checks/*.py` is Trophy's handwritten geometry-check library: pure functions over a fused 3D ball track (metres, field
frame: origin at the table centre, +x toward side B, net plane x = 0, z up from the table top). `samples/field.json`
is **this calibration**: table corners and size, net, floor height, camera positions and the uncertainty model
(`sigma_default_m`, `sigma_1view_m`, `skew_sigma_s`). Your job is to **edit the library to this setup** so that
`{{gate}}` passes on the labelled samples. Work fast and directly (the budget is 60 s, hard cap 90 s): read
`samples/field.json` and the `PARAMS` blocks, edit, run `{{gate}}`.

Do **not** read `samples/*.track3d.jsonl` (large), `schema/`, `rules/` or `reference/checks/` (identical to your
starting copy). The check API is `reference/checks_api.py`; never search the disk (reads outside the sandbox are
refused). Never rewrite a file from scratch: change parameters and, only where the gate shows a check is wrong for this
geometry, the few lines that use them.

## The library

Every file has a top-level `PARAMS = {...}` (the tunables, each with a comment) and
`check(track, field, params=None, **q)` returning a CheckResult. It may import only `math`, `statistics`,
`itertools`, `functools`, `bisect`, `heapq` and public names `from trophy_engine.checks.api import ...` (`Field`,
`Track`, `merge_params`, `result`, `refine_bounce`, `edge_probs`, `motion_sigma`, `phi`, ...). No `typing`,
`collections`, `dataclasses`, `open`, `exec`, `eval`, `getattr`, dunders.

What to specialise, per check (`PARAMS` keys):

- `phases`: the serve zone (`serve_zone_behind_m`, `serve_zone_z_m` relative to the surface), the dead-ball gap
  (`gap_s`), `floor_band_m` (the floor is `field.floor_z_m`: the table height below the surface), `still_radius_m`.
- `bounces` and `in_out` (keep their shared keys equal): `surface_band_m`, `floor_band_m` and `edge_band_m` scale with
  `uncertainty.sigma_default_m`; `timing_sigma_s` ≈ `skew_sigma_s`; `side_face_z_m`, `side_face_x_m`,
  `plane_margin_m`, `min_descent_m_s`; `in_out.net_zone_m` from the net overhang.
- `net_touch`: `window_m` (around the net plane), `touch_p`, `back_s`. `contacts`: `hit_dv_m_s`, `hit_h_jump_m_s`,
  `near_end_m` (table-end box), `min_height_m`.
- `serve_toss`: `min_toss_m` (6 in = 0.1524 m) and `max_angle_deg` (30) are the rules and stay; adapt `toss_vz_m_s`,
  `hit_dv_m_s`, `lookback_s`, `still_s` to the sigma model and the sample rate.
  Leave a parameter alone when the gate already passes it; say so in your result.

## What you have

- `samples/field.json`: this calibration.
- Labelled fused tracks (what a correct library must find: rallies, bounces with in/out margins, nets, contacts,
  serves):
  {{samples}}
- `{{gate}}`: the gate. It loads the library under the import allowlist, checks determinism, scores phases, table and
  floor bounces, in/out (never wrong at AUTO confidence), nets, contacts and serve legality against the labels, then
  replays the library's events through the rule engine with `rules/{{sport}}/rules.yaml` and compares rally winners.
  The `before` column is the unedited library. It writes `.trophy/results.json` and `.trophy/events.json`.

## Allowlist (the runner refuses anything else)

{{allowlist}}

Only `{{gate}}` may be executed. There is no network. Do not touch `checks/library.json`, `reference/`, `rules/`,
`schema/`, `samples/` or the gate script.

## Done when

`{{gate}}` passes every check. Begin your reply with a `## Plan` (3-5 lines), make the edits, run the gate, repair
what fails, and end with a `## Result` listing each parameter changed, from what to what, and why.
