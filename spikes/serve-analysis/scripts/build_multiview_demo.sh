#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python scripts/download_multiview_samples.py
.venv/bin/python scripts/setup_replay_assets.py
for trophy_camera in side oblique; do
  trophy_output="artifacts/multiview/gray-$trophy_camera"
  if [ ! -f "$trophy_output/report.json" ]; then
    .venv/bin/python -m trophy "samples/tt3d/game_00/$trophy_camera-010.mp4" \
      --output "$trophy_output" --device auto --threshold .65 --max-frames 1000 --photometric max-channel-gray
  fi
  .venv-pose/bin/python scripts/extract_poses.py "samples/tt3d/game_00/$trophy_camera-010.mp4" \
    --config "configs/tt3d-$trophy_camera.json" --output "artifacts/multiview/poses-$trophy_camera.json"
done
.venv/bin/python scripts/build_multiview.py --config configs/tt3d-multiview.json --output artifacts/multiview/demo
.venv/bin/python scripts/evaluate_multiview.py --ball artifacts/multiview/demo/scene.json \
  --detections artifacts/multiview/gray-side/detections.json --reference samples/tt3d/game_00/reference-010.csv \
  --camera samples/tt3d/game_00/side.yaml --output artifacts/multiview/demo/accuracy.json
for trophy_camera in side oblique; do
  trophy_output="artifacts/multiview/rally038-$trophy_camera"
  if [ ! -f "$trophy_output/report.json" ]; then
    .venv/bin/python -m trophy "samples/tt3d/game_00/038/$trophy_camera.mp4" \
      --output "$trophy_output" --device auto --threshold .65 --max-frames 1000 --photometric max-channel-gray
  fi
done
.venv/bin/python scripts/validate_multiview_second_rally.py
.venv/bin/python scripts/render_multiview_diagnostics.py --config configs/tt3d-multiview.json \
  --scene artifacts/multiview/demo/scene.json --output artifacts/multiview/demo/diagnostics.mp4
for trophy_view in orbit overhead courtside; do
  .venv/bin/python scripts/render_replay.py artifacts/multiview/demo/scene.json \
    --output "artifacts/multiview/demo/$trophy_view.mp4" --view "$trophy_view" --fps 30
done
.venv/bin/python -m pytest -q
if command -v node >/dev/null 2>&1; then
  node scripts/analyze_placements.mjs --scene artifacts/multiview/demo/scene.json --output artifacts/placements
  node --test tests/test_placements.mjs
fi
echo 'Run: .venv/bin/python scripts/serve_replay.py --directory artifacts/multiview/demo --port 8503'
