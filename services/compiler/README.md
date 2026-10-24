# House-rule compiler: Factory Droid (owner D)

**Env:** Node 20 · @factory/droid-sdk · port 8200

## Responsibilities
- **Trigger:** a new `house_rule` row with status=pending in SpacetimeDB.
- **Sandbox:** a throwaway workspace with `rules/<sport>.yaml`, the JSON Schema, a `replay_test` harness (the last 10 rallies' event logs) and the top-k Moss rule clauses. Droid may edit only that YAML and run only `replay_test`; no network; 90 s timeout; autonomy appropriate to the scoped rule-compilation task. This runtime sandbox handles user-supplied rules; it does not restrict repository agents from changing the compiler or its design.
- **Loop:** draft the rule → run tests → repair (max 3) → stream the plan, steps, diff and test table into `house_rule.plan/diff/results` → the judge taps Approve → a reducer hot-loads the pack.
- **Fallback:** Claude-only compiler with the same schema and tests. Document the active compiler backend and its behavior.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
