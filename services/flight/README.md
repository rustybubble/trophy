# Flight: the ping-pong vision module (Agent 2)
**py3.11, numpy 1.26.4, opencv-contrib 4.10.0.84, torch (MPS); Vultr GPU as the fallback.** Reads every frame from `frames:{cam}`, tracks the ball (a classical baseline or BlurBall), fits flights, times bounces with phone audio onsets, and emits **measurements**: `bounce` (with edge-class probabilities), `contact`, `net`, `ball_dead`, and **`serve_toss`** (height above the palm, angle from vertical from the hand to the hit, with σ).
- It writes `ev:flight` (the engine's hot path) **and** mirrors every event into Spacetime `observation` + a 10 Hz `track_sample` (the shared world state). It never writes frames there.
- Cards: `docs/research/build-cards-flight-family.md`.

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
