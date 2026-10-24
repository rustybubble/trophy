# Gateway (Agent 1)
**py3.11 FastAPI, port 8000.** Phone-facing API behind Caddy (`/api/*`). It holds **no game logic**: client actions become `ctl:engine` commands.
- `POST /games`, `/games/{id}/join` → `cam_token` (HMAC, 12 h); `/ctl` (role allowlist).
- `WS /ws/frames` (16-byte header + JPEG → clock fit → Redis `frames:{cam}`); `WS /ws/ctl` (NTP ping/pong, onsets → `ev:audio`, health, `call_ack` latency).
- `/calibrate` → courtcam-adapter; `/cams/{cam}/calibration` → `calib:{cam}`.
- `/voice/token` (short-lived Cartesia token; the key never leaves the server); `/ask` → `rules` service; `/replay/…` (clip, overlay, frames for AI-vote crops).

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
