# Contracts (`@trophy/contracts`)

JSON Schemas (draft 2020-12) shared by every service and app. **After C0 these win over `docs/plan/interfaces-v1.md`**; the doc is the narrative. Agent 1 maintains them: change them in a `contracts/<topic>` PR, update producers and consumers together, run `make contracts`, and record breaking changes in `docs/decisions.md`.

| Schema | Root type | Also defines | Where it travels |
|---|---|---|---|
| `event.schema.json` | `Event` (`trophy.event.v1`) | every `*Payload` (bounce, serve_toss, contact, net, ball_dead, …), `PosM`, `EdgeProbs` | Redis `ev:*` (field `json`) and the Spacetime `observation` table (§7) |
| `call.schema.json` | `Call` (`trophy.call.v1`) | `Cue`, `Overlay`, `EvidenceWindow`, `BounceMark` | engine → Spacetime `call` → phones, dashboard (§10) |
| `ctl.schema.json` | `CtlCommand` (`trophy.ctl.v1`) | `<Cmd>Args` per command, `WsClientMessage`, `WsServerMessage`, `ClockSample` | gateway → `ctl:engine`; `/api/ws/ctl` (§9, §13) |
| `state.schema.json` | `StateTables` | `Game`, `Camera`, `Rally`, `Score`, `Challenge`, `HouseRule`, `AiVote`, `TrackSample`, `Ask` | Spacetime rows as clients see them, `*_json` columns parsed (§11) |
| `calibration.schema.json` | `Calibration` | `CalibrationRequest`, `TapPoint` | `/api/calibrate` ↔ courtcam-adapter; `calib:{cam}` (§6) |
| `frame.schema.json` | `FrameMeta` | (the 16-byte WS header is in the description) | Redis `frames:{cam}` (§5) |
| `tracks.schema.json` | `BallTrackSample` | `PlayersTrackSample`, `PlayerBox` | Redis `trk:ball:{cam}`, `trk:players:{cam}` (§8) |
| `decide.schema.json` | `Decide` | `DecideRequest`, `Vote`, `DecideResult` | engine ↔ voters (§15) |
| `rulepack.schema.json` | `RulePack` | `Rule`, `Team`, `FieldTemplate`, `Scoring`, `Ensemble` | `rulepacks/*.yaml` |

## Generated code (never hand-edit)
`make contracts` (`node scripts/gen-contracts.mjs`) writes:
- **TypeScript:** `gen/ts/*.ts`, re-exported from `@trophy/contracts` (`import type { Call, Event } from "@trophy/contracts"`). Uses `json-schema-to-typescript`.
- **Python (Pydantic v2):** `packages/py-trophy/trophy/contracts/*.py`, re-exported from `trophy.contracts`. Uses `datamodel-code-generator` (pinned in py-trophy's dev group). The `schema` field is `schema_` in Python (alias `schema`), so always dump with `by_alias=True` (the `trophy.events` helpers do).

CI fails if the generated files are stale.
