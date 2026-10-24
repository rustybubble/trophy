# SpacetimeDB module: the shared world state (Agent 1)

**SpacetimeDB 2.13, TypeScript module**, run natively on the Mac with `spacetime start` (:3000, proxied at `/stdb/*`). Clients use the npm `spacetimedb` SDK through `@trophy/state-client`. Python services call reducers over HTTP.

**What it holds:** **metadata only. Video frames never go in here** (D-21); they stay on Redis and in the local recorder.
- **World state:** `observation` (every vision event: time, position in court metres, σ, confidence, camera) and `track_sample` (the ball at 10 Hz, rolling 120 s). Every phone, the dashboard and every agent see the same facts. Adding a camera adds rows, not schema.
- **Game state:** `game`, `camera`, `rally`, `call`, `score`, `challenge`, `ai_vote`.
- **Agents:** `house_rule` (the Factory Droid's trigger + streamed plan, diff and results) and `ask` (ask-the-ref transcripts with citations).

**Writers are backend services only:** the vision module (observations), the engine (game state, votes, asks), and the compiler (house-rule progress). Reducers check the caller's identity. Clients only subscribe.

Exact tables and reducers: `docs/plan/interfaces-v1.md` §11.
