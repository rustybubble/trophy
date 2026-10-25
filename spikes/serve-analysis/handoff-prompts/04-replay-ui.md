# Prompt 4 — put synchronized videos and reconstructed 3D into Trophy

Integrate a usable reconstructed replay into **`/Users/mudu/Developer/trophy`**, following the current React/TypeScript app structure and existing replay/Watch entry points. Consume the versioned import/reconstruction manifest from the backend tasks. Deliver an end-to-end path from selecting an imported rally to inspecting its sources and 3D reconstruction; keep ball-only output useful while body processing is pending or unavailable.

Read `AGENTS.md`, `CLAUDE.md`, current contract schemas, `docs/plan/interfaces-v1.md`, `docs/plan/trophy-watch-postgame.md`, and the current replay/Watch UI. Agent 1 owns this integration. Use the working reference at:

- `/Users/mudu/Developer/calhacks/web/hmr2/index.html`
- `/Users/mudu/Developer/calhacks/web/hmr2/viewer.js`
- `/Users/mudu/Developer/calhacks/web/hmr2/style.css`
- `/Users/mudu/Developer/calhacks/artifacts/user-two-camera/reconstruction/scene.json`
- `/Users/mudu/Developer/calhacks/HMR2_REPLAY.md`

Requirements:

1. Build a React view with two real source videos and a 3D table/ball/body view, sharing a game-time playhead. Support play/pause, seek, 0.25×/0.5×/1×, frame stepping, orbit, overhead and recording-camera views. Map each video's media time using the saved alignment; don't derive the second video time from the first clip's raw media time. Use video-frame callbacks for overlays where supported and correct drift after seeks/buffering/rate changes.
2. Render the actual exported HMR2 mesh sequence. Preserve stable player IDs, units and field axes; use one explicit world→renderer transform. Use ball radius 0.02 m. Respect validity masks and unsupported time intervals: rejected/missing ball samples must disappear rather than receive a fabricated path. Interpolate mesh display frames only within valid supported intervals. The official source-camera view should use calibrated projection rather than a visually guessed orbit angle.
3. Label the view plainly as an estimated reconstruction, with accessible alignment/calibration status and meaningful coverage. Do not label image residuals as 3D accuracy. Let users compare the reconstruction directly against source overlays. Body processing failure should leave source playback and available ball reconstruction usable.
4. Integrate job loading, progress and actionable failure states through existing gateway/auth conventions. Load mesh assets on demand and bound memory for long clips with chunking or the agreed artifact format. Validate manifest/asset dimensions and version before allocating. Dispose geometry, video callbacks and listeners on navigation; do not place raw video or mesh arrays into Spacetime.
5. Offer downloads of generated comparison/orbit videos and diagnostics when those artifacts exist, with scoped backend URLs. Adapt the prototype's Three.js code into the repo's bundler/dependencies; don't copy its standalone server/import-map assumptions into production.

Acceptance: verify real source/mesh/ball alignment on the supplied reconstructed interval; exercise end-of-clip, reverse seeking, slow motion, buffering, missing ball, body-job failure, missing/corrupt assets and untrusted calibration. Run the app's relevant typecheck/build and a browser smoke test. Include an explicitly synthetic small fixture only for isolated UI cases, and use the real local artifacts for the actual integration demonstration. Report changed routes/components, contract dependencies, verification and a runnable demo path. This is reconstructed replay, not an engine that predicts true racket impacts or future ball motion.
