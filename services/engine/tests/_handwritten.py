"""The hand-written table-tennis pack, as a module directory for the engine-mechanics tests.

The shipped pack (sports/table_tennis/rules.yaml) is written by the Factory Droid from the laws (D-42) and may change
with every compile; the tests of the engine's own mechanics (serve faults, double bounces, edge calls, ordering) run
against the frozen hand-written rules in tests/fixtures/ so they test the engine, not the Droid's choices.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHIPPED = ROOT / "sports" / "table_tennis"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "handwritten_table_tennis.rules.yaml"
_dir: Path | None = None


def handwritten_modules_dir() -> Path:
    """`<tmp>/table_tennis/{config.yaml, events.py, rules.yaml}` with the hand-written rules; built once per process."""
    global _dir
    if _dir is None:
        base = Path(tempfile.mkdtemp(prefix="trophy-handwritten-"))
        mod = base / "table_tennis"
        mod.mkdir()
        for f in ("config.yaml", "events.py"):
            shutil.copy(SHIPPED / f, mod / f)
        shutil.copy(FIXTURE, mod / "rules.yaml")
        _dir = base
    return _dir
