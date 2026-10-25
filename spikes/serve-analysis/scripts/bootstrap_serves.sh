#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${TROPHY_UV:-.venv/bin/uv}"
PYTHON="${TROPHY_PYTHON:-.venv/bin/python}"
if [ ! -x .venv-serves/bin/python ]; then
  "$UV" venv --python "$PYTHON" .venv-serves
fi
"$UV" pip install --python .venv-serves/bin/python -r requirements-serves.lock
.venv-serves/bin/python scripts/setup_serve_assets.py
