#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "${TROPHY_PYTHON:-}" ]; then
  trophy_python="$TROPHY_PYTHON"
elif command -v python3.12 >/dev/null; then
  trophy_python="$(command -v python3.12)"
elif [ -x "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]; then
  trophy_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
else
  trophy_python="$(command -v python3)"
fi
"$trophy_python" -c 'import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12 (set TROPHY_PYTHON=/path/to/python3.12)"'
if [ ! -x .venv/bin/python ]; then
  "$trophy_python" -m venv .venv
fi
.venv/bin/python -m pip install uv==0.13.5
.venv/bin/uv pip sync --python .venv/bin/python requirements.lock
.venv/bin/python scripts/setup_assets.py "$@"
