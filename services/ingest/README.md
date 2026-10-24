# Ingest: WebRTC (Agent 1, only if needed)
Used only if JPEG over WSS can't sustain 25 fps at 720p on the demo phones. aiortc 1.15.0 + `av==17.1.0`; drain receive queues into a latest-frame slot; writes the **same** `frames:{cam}` bus. Needs the LAN/Caddy origin, because tunnels carry no UDP.

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
