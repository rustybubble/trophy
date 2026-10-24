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
| `decide()`: Claude ‖ Gemini ‖ Bitdeer in parallel, 4 s each, blended with geometry (uncalibrated), one `ai_vote` per voter, never on the live path | `decide/` |
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

**Keys.** `--votes` needs `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` + `GEMINI_MODEL`, and `BITDEER_API_KEY`; a missing one
is a startup error, not a skipped voter. Commentary through Claude needs `ANTHROPIC_API_KEY`. No test makes a live call:
the voters are exercised through recorded response shapes on an injected HTTP transport.

Contracts: `docs/plan/interfaces-v1.md` §9–§11, §15, §19; `packages/contracts/{call,ctl,decide,state,sportmodule,scene,droidrun}.schema.json`.
