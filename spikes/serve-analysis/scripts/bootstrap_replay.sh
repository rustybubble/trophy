#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then bash scripts/bootstrap.sh --sample; fi
if [ ! -x .venv-pose/bin/python ]; then .venv/bin/python -m venv .venv-pose; fi
.venv/bin/uv pip sync --python .venv-pose/bin/python requirements-pose.lock
.venv/bin/python scripts/setup_assets.py --sample
.venv/bin/python scripts/setup_replay_assets.py
