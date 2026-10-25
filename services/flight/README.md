# Flight: the ping-pong vision module (Agent 2)
**py3.11, numpy 1.26.4, opencv-contrib 4.10.0.84, torch; BlurBall on CUDA (the Vultr box) or MPS (the Mac), never the Windows PC (D-30).** Reads every frame from `frames:{cam}`, tracks the ball with BlurBall, fits flights, times bounces with phone audio onsets, and emits **measurements**: `bounce` (with edge-class probabilities), `contact`, `net`, `ball_dead`, **`serve_toss`** (ITTF Law 2.6.2, D-31: height from palm release to apex, angle on the rise, struck on descent, with σ), `serve_hidden` and `serve_position`.
- It writes `ev:flight` (the engine's hot path) **and** mirrors every event into Spacetime `observation` + a 10 Hz `track_sample` (the shared world state). It never writes frames there.
- Cards: `docs/research/build-cards-flight-family.md`.

## Container on the Vultr box (D-30; Agent 2 owns the image, Agent 1 owns compose)
`docker-compose.yml` builds `services/flight/Dockerfile` from the repo root under the `gpu` profile (the only service with an NVIDIA reservation): `docker compose --profile gpu up -d flight`. What the image can rely on:
- **Env:** everything in `/etc/trophy/trophy.env` (incl. `SPACETIME_VISION_TOKEN`), plus `REDIS_URL=redis://redis:6379/0`, `SPACETIME_URI=http://spacetimedb:3000`, `TROPHY_DATA_DIR=/data/local`, `BLURBALL_WEIGHTS_DIR=/weights`.
- **Weights:** `/weights` is the host's `/srv/trophy/weights`, mounted **read-only**. Never `COPY` weights into the image or push it to a registry (license unstated; we use them, we don't redistribute them).
- **Base:** a CUDA 12 runtime image; log the device and execution provider actually used in `heartbeat`. `.dockerignore` keeps `.env`, `data/`, weights and footage out of the build context.
- **Frames** may carry a table `crop` (D-29): map cropped pixels back to the full view before calibration math.

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
