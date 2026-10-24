# Progress

Tick items and record **measured** numbers (not estimates). The gates are in build plan §5 and §7.

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
- [ ] **Sat noon gate:** each P0 family makes ≥ 1 correct call

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
