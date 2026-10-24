# Ingest (owner A)

**Env:** py3.11 · aiortc 1.15.0 + av>=17 · host network, UDP 32768–60999

## Responsibilities
- One RTCPeerConnection per phone (non-trickle ICE). Decode frames, map RTP pts (1/90000) to the game clock with each phone's QR-calibration fit, and write `(t_game, frame)` into **per-camera shared-memory rings** (4 s).
- **Drain receive queues into a latest-frame slot** (they're unbounded). Only H.264 Constrained Baseline or VP8 are offered.
- **F2B fallback first:** JPEG over WebSocket (16-byte header: cam id, seq, phone capture time), 640×360 at 10–15 fps, latest frame wins.
- Rally clip fetch: when the engine signals the end of a point, request the 2 s 1080p chunks from each phone (the PWA uploads them to GCS).
- See `docs/research/build-cards-platform-and-post-game.md` §1–3.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
