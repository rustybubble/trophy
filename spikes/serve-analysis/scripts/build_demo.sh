#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f artifacts/official-22-mps/detections.json ]; then
  trophy_detections=artifacts/official-22-mps/detections.json
else
  trophy_detections=artifacts/replay/ball/detections.json
  if [ ! -f "$trophy_detections" ]; then
    .venv/bin/python -m trophy samples/official-22-003.mp4 --output artifacts/replay/ball --device auto
  fi
fi
.venv-pose/bin/python scripts/extract_poses.py samples/official-22-003.mp4 \
  --config configs/official-22-003.json --output artifacts/replay/poses.json
.venv/bin/python scripts/build_replay.py samples/official-22-003.mp4 \
  --detections "$trophy_detections" --poses artifacts/replay/poses.json \
  --config configs/official-22-003.json --output artifacts/replay/demo
for trophy_view in orbit overhead courtside; do
  .venv/bin/python scripts/render_replay.py artifacts/replay/demo/scene.json \
    --output "artifacts/replay/demo/$trophy_view.mp4" --view "$trophy_view"
done
