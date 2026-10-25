# Progress

Tick items and record **measured** numbers (not estimates). The gates are in `docs/plan/three-agent-plan.md` §5.

## Cal Hacks weekend (plan: `docs/plan/three-agent-plan.md` §3, §5)
- [x] **C0** contracts + codegen + py-trophy + MockState + CI: tag `wk-c0` (merged 2026-10-24, rustybubble/trophy#1; waiting on A2/A3 acknowledgement)
- [ ] Spikes: tracker classical ___ fps / BlurBall MPS ___ fps (OPEN-3 → ___); Spacetime reducer→subscription **p50 3.4–5.0 ms, p95 5.1–7.6 ms** (Windows 11 localhost, not the Mac; Python HTTP → Node TS subscriber, 200 calls at 20 Hz; `spikes/spacetime-latency/`); Cartesia TTS via a server-minted token ✓ **on an iPhone** (iOS 18.7, Firefox for iOS/WebKit, via trophy.photo: first chunk 112 ms after the request, 234 ms after the tap); Ink-2 STT transcript ✓ **from the iPhone mic** ("This is on my phone.", `turn.end` ≤ 82 ms after release); Safari itself not yet; Droid ✓ **live** (net-let house rule 30.6 s, pickleball derivation 69.2 s, both first attempt, gate 19/19; `docs/status/a3.md`); Moss query **not run** (no keys; `services/rules` built with fakes); Claude / Gemini / Bitdeer voters **not run** (no keys; `trophy_engine.decide` built with recorded shapes); domain **trophy.photo** ✓ (A → the demo PC's LAN IP; Let's Encrypt cert via Porkbun DNS-01; HTTPS verified from the PC itself, phones not yet)
- [x] **Spacetime module** (P1 §4): published locally on the demo PC; 13 writing reducers with per-service identities; `SpacetimeState` live through `wss://trophy.photo/stdb` (reducer → client callback 7–14 ms, Windows PC)
- [ ] **C1** iPhone 720p **29.9 fps received** through `https://trophy.photo` (1280×720, 0 missing frames, capture → Redis p50 145 ms / p95 351 ms, clock error ±3.7 ms; **over the last 10 s only, not yet 15 min**); onsets arriving ✓; a Cartesia line plays ✓ (spike)
- [ ] **C2** `make e2e` on the CC BY ping-pong segment ✓/✗; replay API ✓/✗; `/ask` cited answer ✓/✗
- [ ] **C3** live: rallies ___/___ correct (CI ___); staged edge ___/___; staged serves ___/12 (height err ___ cm, angle err ___°); votes never delayed a call ✓/✗; call spoken p50 ___ ms; challenge → replay ___ s; 3 votes shown in ___ s; Droid rule end to end **30.6 s** (sandbox → ready, measured 2026-10-24; approval + hot-load not yet timed live); voice ask → answer starts ___ s
- [ ] **C3b** Trophy Watch core on ping pong ✓/✗ and basketball ✓/✗: recap, moments, highlights + ★ Play of the game, condensed, replay, stats, moment search (5 queries/game: ___/5 correct)
- [ ] **C4** frozen, rehearsed 3×; 2-min video; README (Cartesia, Factory, Spacetime, Anthropic limits, Bitdeer, Moss, Apify, Gemini); Devpost writeup; Apify actor published (with the user's OK)

## Measured accuracy (from labelled evals only)
| Sport / call | n | correct | 95% CI | source clips |
|---|---|---|---|---|

## Flight MVP: clips → field-frame 3D map (branch `mvp/tt-cloud`, 2026-10-24)
**All numbers SYNTHETIC** (`services/flight/flight/synth.py`; no real footage was on this Mac). Method: `services/flight/README.md`.
- Two rendered 1280×720 30 fps videos, classical detector, CPU: track3d error vs truth **median 2.6 cm, p95 5.2 cm, 100 % within 3σ**; bounces **7/7 matched, xy median 3.0 cm, max 4.6 cm**; contacts 6/7; serve height 13 cm vs 20 cm true (release unobserved: a resting ball is invisible to background subtraction). 175 frames × 2 in 3.0 s wall.
- From BlurBall-like caches (1.5 px noise, 8 % misses, 5 % false blobs): track3d **median 1.4 cm, p95 3.0 cm**; 10 seeds / 66 bounces: xy **median 1.8 cm, p90 6.3 cm, max 23 cm**; timing median 3.8 ms; 91 % within 3σ.
- Not measured: anything on real video. The first real measurement needs two propped phones (white ball) or the tracker branch's cached BlurBall JSON copied to this machine.
