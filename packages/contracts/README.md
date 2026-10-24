# Contracts

JSON Schemas shared by every service and app. Agents may evolve them as needed: update affected producers, consumers and checks together, and record breaking changes in `docs/decisions.md` so later work stays compatible.

- `event.schema.json`: family → engine (Redis streams `ev:*`)
- `call.schema.json`: engine → SpacetimeDB `call` table → phones/dashboard
- `decide.schema.json`: the `decide()` request/response (background voters: Claude ‖ Gemini ‖ Bitdeer + geometry)
- `rulepack.schema.json`: `rulepacks/*.yaml` (CEL conditions, tiers, scoring templates, coach, calibration)

Generate TypeScript types (e.g. `json-schema-to-typescript`) and Python models (e.g. `datamodel-code-generator`) from these, rather than hand-writing them.
