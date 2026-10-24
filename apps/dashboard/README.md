# Live dashboard (owner D)

**Stack:** Vite + React + strict TypeScript (+ Three.js/Spark where 3D is needed), SpacetimeDB TypeScript SDK. Built to `dist/` and served by Caddy.

## Responsibilities
- Scoreboard, live calls with tier badges, challenge replays (multi-angle, slow-mo, 3D bounce mark + error ellipse), evidence mode for fouls.
- House-rule panel: the Droid's live plan, diff, test table, and an Approve button.
- Ask-the-ref transcript with quoted rule clauses. **Sport wall:** 28 tiles (LIVE / VERIFIED / PACK) with measured accuracy and the reliability diagram.
- Everything subscribes to SpacetimeDB.
