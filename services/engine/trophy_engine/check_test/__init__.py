"""check_test: the gate for a checks/ library (D-36). The Droid runs it in its sandbox; CI runs it on the golden."""

from .checks import format_table, run_check_test  # noqa: F401
