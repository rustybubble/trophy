# Engine (Agent 3)
**py3.11, `uv`, cel-python.** Layer-2 events (`ev:*`) and control commands (`ctl:engine`) in; calls, rallies, scores,
challenges, house rules, asks and moments out, through the Spacetime reducers (engine identity). Rules live in
`sports/<sport>/rules.yaml` (CEL `when` over `ev`, `rally`, `game`, `params`; D-18) and the score is derived by
replaying the call log, so undo and overturn are exact.

| Piece | Where |
|---|---|
| Sport modules: API, loader with the import allowlist | `trophy_engine/sportmod/` |
| CEL rules (`opponent()`, `phi()`), rally state, scoring (rally template: 11, win by 2, serve every 2, alternate at deuce; params per game), the gate (tier ceiling, foul_flag ≤ BETA, untrusted calibration ≤ BETA), call building (text/speech templates, cue, evidence, overlay, emotion on game point) | `rules/`, `rally.py`, `scoring.py`, `gate.py`, `calls.py` |
| The engine: events, commands (`challenge`, `resolve_challenge`, `undo_last_call`, `adjust_score`, `set_server`, `submit/approve/reject_house_rule` with hot-load, `ask_logged`, `bookmark`, `clip_that`, `review_call`, `end_game`), moments + ★ best play | `engine.py`, `moments.py` |
| `decide()`: Claude (the only model voter, D-41), 4 s, blended with geometry (uncalibrated), one `ai_vote`, never on the live path | `decide/` |
| Grounded commentary (pbp + colour) with the template fallback the spec requires | `commentary.py` |
| State writers: Spacetime (needs `SPACETIME_ENGINE_TOKEN`) and memory (tests, replay_test) | `state.py` |
| `replay-test` (the Droid's gate: events vs labels, then calls through the engine, `calls_changed` vs a baseline), `trophy-synth`, `trophy-engine run`, `trophy-ctl` | `replay_test/`, `synth/`, `loop.py`, `ctl_cli.py` |

```bash
cd services/engine && uv sync
uv run pytest -q
uv run replay-test --module ../../sports/table_tennis --samples ../../evals/fixtures/synthetic/table_tennis
uv run trophy-engine run --state spacetime            # Redis + Spacetime; add --votes once all three voter keys are in .env
uv run trophy-ctl create_game g_demo0001 --sport table_tennis && uv run trophy-ctl start_game g_demo0001
```

**Keys.** `--votes` needs `ANTHROPIC_API_KEY`; without it `--votes` is a startup error, not a skipped voter. Commentary through Claude needs `ANTHROPIC_API_KEY`. No test makes a live call:
the voter is exercised through recorded response shapes on an injected HTTP transport.

Contracts: `docs/plan/interfaces-v1.md` §9–§11, §15, §19; `packages/contracts/{call,ctl,decide,state,sportmodule,scene,droidrun}.schema.json`.

## 3D checks, the gate and ask the ref (D-36)

- `trophy_engine/checks/`: `api.py` (the `Field`/`Track` adapter over provisional `track3d` rows, free-flight maths),
  `library.py` (loads a `checks/` directory under an import allowlist; `library.json` → `calibrated`), `events.py`
  (`TrackEventer`: samples in, `trophy.event.v1` events out, live with a 70 ms confirmation lag; events after a scored
  point are dropped until the next rally).
- `trophy_engine/check_test/`: `check-test`, the Droid's gate for a check library: loads, determinism, rally
  segmentation, bounce recall/precision/position, in/out accuracy with **no wrong call at AUTO confidence**, nets,
  contacts, serve height/angle/legality, then the events through the rule engine and the labelled rally winners.
  Writes a `DroidRunResults` JSON.
- `trophy_engine/synth/track3d.py`: `trophy-synth3d`, labelled synthetic 3D games (scenarios: clean, double bounce,
  edge in, side face, net into, toss too low, toss angled). SYNTHETIC, labelled as such in every file.
- `trophy_engine/track_source.py` + `loop.py --field`: fused samples from Redis `trk:ball3d` or a replayed file.
- `trophy_engine/ask/`: the voice question path: `TrackStore` (the live buffer), a keyword `router` to checks, a
  Claude `Phraser` (requires `ANTHROPIC_API_KEY`; no fallback), and the FastAPI `POST /ask` the gateway proxies to on
  :8100. Unknown questions return `found: false` and append to `pending_checks.jsonl` for a later Droid `new_check` run.

Measured on this Mac, 2026-10-24, synthetic fixtures (σ 1.2 cm, 6 ms skew, 3 % dropouts, 30 Hz), golden library:

| | |
|---|---|
| `check-test` on the committed fixtures (2 games, 14 rallies) | 25/25 rows pass, 1.6–1.8 s total |
| 9 random seeds × 7 rallies | 8/9 pass every row; the other misses one table bounce (28/29) and one rally winner |
| table bounce recall / precision | 100 % / 100 % on 8 of 9 seeds; mean position error 1.7–2.6 cm |
| in/out at AUTO confidence (p ≥ 0.9 or ≤ 0.1) | 0 wrong calls across all seeds after σ scales with incoming speed |
| serve toss | legality 7/7 on every seed; height error ≤ 2.8 cm; angle error ≤ 6.5° (tosses ≥ 12 cm) |
| per-check latency (full 45 s game) | phases 1.3 ms, bounces 2–3 ms, contacts 2–4 ms, net 1 ms |
| replay of a game through `TrackEventer` + engine | 928 samples → 73 events → 8 calls, every labelled winner right |

Not measured: anything on a real 3D track (none exists yet), the Droid `calibrate_checks` wall time, Claude phrasing
latency (no key used in tests).
