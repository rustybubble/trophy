# courtcam-adapter (Agent 2)
**py3.12, port 8050.** `POST /calibrate`: tapped landmarks → homography + camera pose (K, R, t) + overlay + `trusted` gate, using **courtcam @ `b2f5ff5`** (MIT; installed **without extras**, never via Replay's workspace, in its own venv because of an OpenCV clash). Templates come from `rulepacks/<sport>.yaml` → `field:`. API notes: `docs/research/replay-source-review-2026-10-23.md` §2.

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
