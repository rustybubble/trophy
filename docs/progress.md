# Progress

Tick items and record **measured** numbers (not estimates). The gates are in `docs/plan/three-agent-plan.md` §5.

## Cal Hacks weekend (plan: `docs/plan/three-agent-plan.md` §3, §5)
- [x] **C0** contracts + codegen + py-trophy + MockState + CI: tag `wk-c0` (merged 2026-10-24, rustybubble/trophy#1; waiting on A2/A3 acknowledgement)
- [ ] Spikes: tracker classical ___ fps / BlurBall MPS ___ fps (OPEN-3 → ___); Spacetime reducer→subscription **p50 3.4–5.0 ms, p95 5.1–7.6 ms** (Windows 11 localhost, not the Mac; Python HTTP → Node TS subscriber, 200 calls at 20 Hz; `spikes/spacetime-latency/`); Cartesia TTS via a server-minted token ✓ (server script + desktop Chromium; **iPhone not yet**); Ink-2 STT transcript ✓ (server script, the TTS line round-trips exactly; **iPhone mic not yet**); Droid hello ✓/✗; Moss query ___ ms; Claude / Gemini / Bitdeer vision calls ✓/✗; domain **trophy.photo** (registered 2026-10-24; DNS not resolving yet at 18:50 UTC)
- [ ] **C1** iPhone 720p ___ fps through the domain origin; onsets arriving; a Cartesia line plays
- [ ] **C2** `make e2e` on the CC BY ping-pong segment ✓/✗; replay API ✓/✗; `/ask` cited answer ✓/✗
- [ ] **C3** live: rallies ___/___ correct (CI ___); staged edge ___/___; staged serves ___/12 (height err ___ cm, angle err ___°); votes never delayed a call ✓/✗; call spoken p50 ___ ms; challenge → replay ___ s; 3 votes shown in ___ s; Droid rule end to end ___ s; voice ask → answer starts ___ s
- [ ] **C3b** Trophy Watch core on ping pong ✓/✗ and basketball ✓/✗: recap, moments, highlights + ★ Play of the game, condensed, replay, stats, moment search (5 queries/game: ___/5 correct)
- [ ] **C4** frozen, rehearsed 3×; 2-min video; README (Cartesia, Factory, Spacetime, Anthropic limits, Bitdeer, Moss, Apify, Gemini); Devpost writeup; Apify actor published (with the user's OK)

## Measured accuracy (from labelled evals only)
| Sport / call | n | correct | 95% CI | source clips |
|---|---|---|---|---|
