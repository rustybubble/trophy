# Recorder (Agent 1)
Reads `frames:{cam}` and writes 2 s H.264 segments (`h264_videotoolbox` on the Mac) + a per-frame index + copies of `trk:*` to `data/local/recordings/{game}/{cam}/` (gitignored). It powers instant replay and the crops for AI votes. **Video never goes into Spacetime.**

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
