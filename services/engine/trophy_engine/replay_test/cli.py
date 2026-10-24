"""``replay-test``: the CLI the Droid runs inside its sandbox (and pytest runs in CI).

    replay-test --module sports/table_tennis --samples samples \
        [--baseline sports/table_tennis] [--json out.json] [--events out.events.json]

Exit code 0 when every check passes, 1 otherwise. ``--json`` writes a DroidRunResults object (droidrun.schema.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checks import format_table, run_replay


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="replay-test", description=__doc__.splitlines()[0])
    ap.add_argument("--module", required=True, type=Path, help="sports/<sport> directory (the candidate)")
    ap.add_argument("--samples", required=True, type=Path, help="directory of *.l1.jsonl + *.labels.json")
    ap.add_argument("--baseline", type=Path, default=None, help="a module to show as 'before'")
    ap.add_argument("--json", type=Path, default=None, help="write the results table as JSON (DroidRunResults)")
    ap.add_argument("--events", type=Path, default=None, help="write the candidate's events per sample as JSON")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    res = run_replay(a.module, a.samples, baseline_dir=a.baseline)
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
