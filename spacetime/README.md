# SpacetimeDB module: live game state (owner D)

Self-hosted with `spacetime start` in a container on the live VM; the same module is published to Maincloud as a fallback. Write the module in Rust or C# (or TypeScript if the current SpacetimeDB version supports TypeScript modules; check the docs). Clients use the **TypeScript SDK**. The Python engine calls reducers through the **HTTP API**.

## Tables (first pass)
`game` · `player` (enrolled name/face consent flag) · `camera` (phone, pose, clock-offset fit) · `rally` · `event_summary` · `call` (Call contract) · `challenge` · `score` · `house_rule` (text, status, plan, diff, results, pack_version) · `highlight` · `watch_session` (watch-party playback state, reactions)

## Reducers
`join_game` · `register_camera` · `post_call` · `challenge` · `resolve_challenge` · `submit_house_rule` · `update_house_rule` · `approve_house_rule` · `post_highlight` · `watch_sync` · `react`

Why SpacetimeDB is core: it's the single live shared state for phones, dashboard, engine, Droid and watch parties. That's also what the SpacetimeDB prize asks for (concept-v3 §9).
