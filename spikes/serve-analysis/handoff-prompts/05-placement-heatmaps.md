# Optional prompt 5 — per-player ball-placement heatmaps

Add per-player table-tennis placement analysis to the existing Stats/Watch experience in **`/Users/mudu/Developer/trophy`**, using measured 3D ball trajectories and reviewable bounce candidates. This feature depends on the ball trajectory contract, not on HMR2. Inspect the receiving branch and current event/stat pipeline before adding a second bounce detector; reuse trusted existing bounce observations where possible.

Read `AGENTS.md`, `CLAUDE.md`, current contracts and `docs/plan/trophy-watch-postgame.md`. Coordinate analytics with Agent 3, perception with Agent 2, and UI/contracts with Agent 1. Reference:

- `/Users/mudu/Developer/calhacks/PLACEMENTS.md`
- `/Users/mudu/Developer/calhacks/web/multiview/placements-core.js`
- `/Users/mudu/Developer/calhacks/web/multiview/placements.js`
- `/Users/mudu/Developer/calhacks/scripts/analyze_placements.mjs`
- `/Users/mudu/Developer/calhacks/tests/test_placements.mjs`

Requirements:

1. Produce candidates only with supported before/after motion: incoming downward velocity, outgoing upward velocity, ball-centre height consistent with tabletop plus radius, bounded temporal gaps and enough samples. Preserve the evidence and rejection reason. Tune thresholds against current units/FPS rather than blindly copying the demo defaults. An inferred bounce is an estimate until reviewed or independently verified.
2. Attribute the incoming shot to a stable player/team only when the trajectory or reviewed identity supports it. Account for end changes. Exclude own-side serve bounces from target-placement totals by default; net rebounds, repeated bounces and ambiguous senders must not invent new shots or player labels. Preserve unassigned candidates for review.
3. Show one table heatmap per player, counts, sample size, a consistent colour-scale option, player-relative orientation and game-time/rally filters. Offer density and discrete zones with plain labels; density is not a calibrated probability. Use the rule pack's field coordinates and table dimensions.
4. Let a reviewer inspect a candidate, seek both source videos to its time, and confirm/correct/exclude it. Keep original measurements and review edits separate, with estimated/confirmed/manual provenance. Scope stored reviews to the source/game and analysis fingerprint so settings imported from another clip cannot apply unrelated edits. Respect existing judge permissions if persisting shared reviews.
5. Export a PNG heatmap and CSV/JSON containing all candidates, inclusion flags and provenance. Stats unavailable from the data should say unavailable, not zero. Placement analytics must not rewrite points, line calls or engine state.

Acceptance: test serve own-side exclusion, end changes, gaps, net rebound, ambiguous attribution, review persistence isolation and export totals. Demonstrate on a real trajectory while reporting candidate count and reviewed count separately. The prototype's bounce candidates have no independent bounce ground truth; do not present them as measured detection accuracy. Run relevant frontend/core checks and update docs with the actual result and limitations.
