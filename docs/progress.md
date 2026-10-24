# Progress

## User acceptance review — 2026-10-24: failed

The requested real-footage demo is **not complete**. Ball detection glitches can cause cross-screen teleports, the 3D rendering is below target and has no real ball positions, and candidate activity windows do not constitute working point detection. Read-only audit: selected hybrid has 301 adjacent-frame jumps over 384 source pixels (175 over 960); real scene has 0/1,615 ball positions; 15/15 candidate intervals are unresolved with no winner. These are artifact diagnostics, not confirmed false-positive counts. The historical checkboxes below record implementation activity, not product acceptance. No fixes were made in this follow-up. [Comprehensive failure report](status/tt-demo-failure-report-2026-10-24.md).


Tick items and record **measured** numbers (not estimates). The gates are in `docs/plan/three-agent-plan.md` §5.

## Cal Hacks weekend (plan: `docs/plan/three-agent-plan.md` §3, §5)
- [x] **C0** contracts + codegen + py-trophy + MockState + CI: tag `wk-c0` (merged 2026-10-24, rustybubble/trophy#1; A2 acknowledged 2026-10-24; A3 acknowledgement pending)
- [ ] Spikes: tracker classical ___ fps / BlurBall MPS ___ fps (OPEN-3 → ___); Spacetime reducer→subscription **p50 3.4–5.0 ms, p95 5.1–7.6 ms** (Windows 11 localhost, not the Mac; Python HTTP → Node TS subscriber, 200 calls at 20 Hz; `spikes/spacetime-latency/`); Cartesia TTS on iPhone ✓/✗; Ink STT transcript ✓/✗; Droid hello ✓/✗; Moss query ___ ms; Claude / Gemini / Bitdeer vision calls ✓/✗; domain ___
- [ ] **C1** iPhone 720p ___ fps through the domain origin; onsets arriving; a Cartesia line plays
- [ ] **C2** `make e2e` on the CC BY ping-pong segment ✓/✗; replay API ✓/✗; `/ask` cited answer ✓/✗
- [ ] **C3** live: rallies ___/___ correct (CI ___); staged edge ___/___; staged serves ___/12 (height err ___ cm, angle err ___°); votes never delayed a call ✓/✗; call spoken p50 ___ ms; challenge → replay ___ s; 3 votes shown in ___ s; Droid rule end to end ___ s; voice ask → answer starts ___ s
- [ ] **C3b** Trophy Watch core on ping pong ✓/✗ and basketball ✓/✗: recap, moments, highlights + ★ Play of the game, condensed, replay, stats, moment search (5 queries/game: ___/5 correct)
- [ ] **C4** frozen, rehearsed 3×; 2-min video; README (Cartesia, Factory, Spacetime, Anthropic limits, Bitdeer, Moss, Apify, Gemini); Devpost writeup; Apify actor published (with the user's OK)

## Measured accuracy (from labelled evals only)
| Sport / call | n | correct | 95% CI | source clips |
|---|---|---|---|---|

## Recorded two-phone evidence path (2026-10-24, Agent 2)

- [x] Both actual 4K60 sources inspected; native PTS/seq retained; paired playback, original 4K source crops, slow motion, candidate interval selection, illustrative continuous avatars and durable player-resolution scoring run locally via `make tt-demo`.
- [x] Deterministic rules/geometry/timing/persistence/HTTP suite: 75 passing tests. This does not pass C3's real-outcome accuracy gate.
- [x] Tracker comparison: classical short-run 78.0 sequential paired FPS; RGB neural 14.31; full grayscale/block-three neural 22.26 paired FPS. Development localization 75/89 for grayscale, held-out slow-ball 6/19. Current experimental color fallback recovers 82/89 development localizations; no held-out hybrid result or joint throughput claim.
- [x] Calibration API and table template; stereo rejection gates; pinned official rule sources; complete Chapter 2 inventory. HMO full retrieval blocked (403), explicitly unread.
- [x] 62 selected-hybrid measurement events and 2,154 track samples exported; event/payload schemas checked. Live Redis/Spacetime delivery, Cartesia, challenge votes and live AUTO decisions are **not validated**.

See `docs/tt-demo.md`, `docs/status/a2.md` and `evals/reports/` for methods and limits. No score/serve/edge real-footage accuracy is claimed. The supplied moving cameras still need validated metric calibration, exposure alignment, release/contact localization and independent outcome labels before automatic adjudication.
