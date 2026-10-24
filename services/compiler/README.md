# Compiler: Factory Droid house rules (Agent 3)
**Node 20, `@factory/droid-sdk`, port 8200.**
- **Trigger:** a new `house_rule` row in Spacetime.
- **Sandbox:** a throwaway workspace containing only the pack YAML, schema, `replay_test` and the relevant Moss rule clauses; no network beyond Factory; 90 s timeout.
- **Loop:** draft → test → repair (max 3).
- **Output:** the plan, steps, diff and test table are streamed to the dashboard; the judge approves; the engine hot-loads.
- **Fallback:** a Claude-only compiler.
- The root README must explain where and how Droid is used (a Factory requirement).

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
