# Contracts

JSON Schemas shared by every service and app. **Change them only with a `docs/decisions.md` entry**, and tell the other owners.

- `event.schema.json`: family → engine (Redis streams `ev:*`)
- `call.schema.json`: engine → SpacetimeDB `call` table → phones/dashboard
- `decide.schema.json`: the `decide()` request/response (Snap → Gemini → Claude → geometry)
- `rulepack.schema.json`: `rulepacks/*.yaml` (CEL conditions, tiers, scoring templates, coach, calibration)

Generate TypeScript types (e.g. `json-schema-to-typescript`) and Python models (e.g. `datamodel-code-generator`) from these, rather than hand-writing them.
