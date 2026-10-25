"""``check-test``: the CLI the Droid runs inside its sandbox (and pytest/CI run on the golden library).

    check-test --checks checks --samples samples [--field samples/field.json] [--baseline reference/checks]
               [--rules sports/table_tennis] [--json out.json] [--events out.events.json] [--quiet]

Exit code 0 when every check passes, 1 otherwise. ``--json`` writes a DroidRunResults object.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checks import format_table, run_check_test


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="check-test", description=__doc__.splitlines()[0])
    ap.add_argument("--checks", required=True, type=Path, help="the candidate checks/ directory")
    ap.add_argument(
        "--samples", required=True, type=Path, help="directory of *.track3d.jsonl + *.labels3d.json (+ field.json)"
    )
    ap.add_argument("--field", type=Path, default=None)
    ap.add_argument("--baseline", type=Path, default=None, help="a checks/ directory to show as 'before'")
    ap.add_argument("--rules", type=Path, default=None, help="sports/<sport> module whose rules.yaml scores the events")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--events", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    res = run_check_test(a.checks, a.samples, field_path=a.field, baseline_dir=a.baseline, rules_dir=a.rules)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res.to_json(), indent=1), "utf8")
    if a.events:
        a.events.parent.mkdir(parents=True, exist_ok=True)
        a.events.write_text(json.dumps(res.candidate_events, indent=1), "utf8")
    if not a.quiet:
        print(format_table(res))
    return 0 if res.passed else 1


if __name__ == "__main__":
    sys.exit(main())
