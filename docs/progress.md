# Progress

Tick items and record **measured** numbers (not estimates). The gates are in build plan §5 and §7.

## Milestone 1: live ping pong + recorded basketball (plan: `docs/plan/three-agent-plan.md` §3, §6)
- [ ] **C0** contracts frozen (schemas, codegen, py-trophy, state-client MockState, synthetic fixtures, CI): tag `m1-c0`
- [ ] Ping-pong tracker spike on the M5 Pro: classical ___ fps / BlurBall MPS ___ fps; recall ___ (OPEN-3 decision: ___)
- [ ] **C1** phone → `frames:{cam}` at 720p ___ fps; `sync_err_ms` = ___; `audio_offset_ms` spread = ___
- [ ] SpacetimeDB reducer (Python HTTP) → TS subscription on the Mac = ___ ms (target < 100)
- [ ] **C2** `make e2e`: CC BY ping-pong segment → point calls; basketball segment → 2/3 calls + score; replay API returns clip + overlay
- [ ] **C3** live ping pong: `event_to_ack_ms` p50 = ___ / p95 = ___ (targets ≤ 1500 / ≤ 2500); 15-min stability ___
- [ ] **C3** rally scoring ___/___ (CI ___), target ≥ 90%; edge rule ___/20 staged (target ≥ 16), clip 8:36 edge ball p = ___
- [ ] **C3** basketball made-basket points ___/___ (CI ___), target ≥ 90%; final score matches overlay: ___
- [ ] **C3** challenge tap → replay playing = ___ s (target ≤ 4)
- [ ] **C4** sign-off: decisions, licenses and status reports filed

## Hour 0: smoke tests (build plan §8)
- [ ] GCP L4 VM up (or the Vultr fallback); `docker run --gpus all … nvidia-smi`
- [ ] A phone on 5G opens `https://$TROPHY_DOMAIN`, a WebRTC test stream reaches ingest, RTT = ___ ms
- [ ] Torch CUDA + onnxruntime-gpu actually using VRAM in each GPU container
- [ ] BlurBall heatmap on a 3-frame sample; WASB tennis weights load through the BlurBall runner
- [ ] RF-DETR-S TensorRT FPS at 720p = ___ (target ≥ 40)
- [ ] SubQ `/v1/models` lists `subq-snap-1.1`; one `choice` call returns probabilities
- [ ] Cartesia WebSocket speaks one line (auth header form that worked: ___)
- [ ] SpacetimeDB reducer (Python HTTP) → TypeScript subscription on a phone < 100 ms (measured ___)
- [ ] Droid SDK edits a toy file + runs a test in the sandbox; Moss query p95 = ___ ms
- [ ] `npx remotion lambda quotas` = ___

## P0
- [ ] F1 PWA capture · [ ] F2 ingest + clock sync · [ ] F3 calibration (courtcam)
- [ ] F4 flight on table tennis (live) · [ ] F5 audio bounces
- [ ] F6 possession on basketball (recorded; courtcam make/miss) · [ ] F7 cornhole (live)
- [ ] F8 engine + 3 packs · [ ] F9 decide() + fallback · [ ] F12 commentary (validator → Cartesia)
- [ ] F13 challenge replay + evidence mode
- [ ] **P0 checkpoint:** each P0 family makes ≥ 1 correct call

## P1
- [ ] Pickleball (kitchen fault, in/out) · [ ] Badminton · [ ] Two-hand touch (snap, rush count, touch) · [ ] Roundnet live
- [ ] F10 house-rule Droid · [ ] F19 ask-the-ref (Moss) · [ ] F11 coach
- [ ] F14 trophy clip · [ ] F15 highlights · [ ] §6 sport wall + calibration plot
- [ ] Trophy Watch: moments, best play, condensed, follow, search, stats, review queue, clips

## P2
- [ ] More verified sports · [ ] 3D / 2.5D angles · [ ] ReCamMaster · [ ] blur · [ ] watch party

## Measured accuracy (from labelled evals only)
| Sport / call | n | correct | 95% CI | source clips |
|---|---|---|---|---|
