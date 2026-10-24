#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# An explicit interpreter makes isolated ML runtimes possible. Playback itself
# uses only the Python standard library; inference dependencies are optional.
TROPHY_PYTHON="${TROPHY_PYTHON:-python3}"
exec "$TROPHY_PYTHON" tools/tt_demo.py "$@"
