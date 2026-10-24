# Engine (Agent 3)
**py3.11, cel-python.** Consumes `ev:*` and `ctl:engine`; applies `rulepacks/*.yaml` (CEL conditions, scoring templates, the confidence gate, the foul policy); writes calls, scores, rallies and challenges to Spacetime; hot-loads approved house rules. Its `decide/` module runs **background** AI votes (Claude ‖ Gemini ‖ Bitdeer Model Studio + geometry) on close or challenged calls, so voters never delay a call. `replay_test` replays event logs through a pack (used by tests and by the Droid).

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
