"""``new-check-test``: the gate of a Droid ``new_check`` job (interfaces-v1 section 20). It runs inside the jailed
sandbox, so the Droid-written check never runs in the engine.

    new-check-test --checks checks --samples samples --field samples/field.json --rules rules/<sport>
                   --new <name> --session session/track3d.jsonl --session-field session/field.json
                   --query session/query.json [--json out.json] [--answer out.answer.json] [--quiet]

Passes when (1) the whole library, the new check included, still passes ``check-test`` on the labelled samples (the
existing checks are unchanged: the Droid may only create ``checks/<name>.py``), (2) the new check loads under the
import allowlist, and (3) run twice on the session's own track with the question's arguments it returns the same
valid CheckResult. The answer it gives on the session track goes to ``--answer``: that is what the referee speaks.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ..checks.library import LibraryError, load_field, load_library, read_track
from .checks import format_table, run_check_test


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="new-check-test", description=__doc__.splitlines()[0])
    for k in ("checks", "samples", "field", "rules", "session", "session-field", "query"):
        ap.add_argument(f"--{k}", required=k not in ("rules",), type=Path)
    ap.add_argument("--new", required=True, help="the new check's name (checks/<name>.py)")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--answer", type=Path, default=None)
    ap.add_argument("--events", type=Path, default=None)  # accepted so the gate script's fixed flags fit
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    res = run_check_test(a.checks, a.samples, field_path=a.field, rules_dir=a.rules)
    tests = list(res.tests)
    answer: dict | None = None

    def row(name: str, ok: bool, after: str, detail: str = "") -> None:
        tests.append({"name": name, "before": "", "after": after, "pass": bool(ok), "detail": detail})

    try:
        lib = load_library(a.checks)
        ok = a.new in lib.checks
        row(f"{a.new}:load", ok, "loaded" if ok else f"no checks/{a.new}.py with a check()")
        if ok:
            fld = load_field(a.session_field)
            track = read_track(a.session, fld)
            q = json.loads(a.query.read_text("utf8"))
            first = lib.run(a.new, track, fld, None, **q)
            second = lib.run(a.new, track, fld, None, **q)
            same = {k: v for k, v in first.items() if k != "ms"} == {k: v for k, v in second.items() if k != "ms"}
            row(f"{a.new}:session", True, f"verdict {first.get('verdict')!r}, p {first.get('p')}")
            row(f"{a.new}:deterministic", same, "same result twice" if same else "results differ")
            if same:
                answer = {"check": a.new, "inputs": q, **{k: v for k, v in first.items() if k != "ms"}}
    except (LibraryError, OSError, ValueError, TypeError, KeyError) as e:
        row(f"{a.new}:session", False, "failed", f"{type(e).__name__}: {e}"[:300])
    passed = all(t["pass"] for t in tests)
    out = {
        **res.to_json(),
        "tests": tests,
        "passed": passed,
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    out["summary"] = f"{sum(t['pass'] for t in tests)}/{len(tests)} checks passed; new check {a.new!r}"
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1), "utf8")
    if a.answer and answer is not None and passed:
        a.answer.write_text(json.dumps(answer, indent=1), "utf8")
    if not a.quiet:
        res.tests, res.passed, res.summary = tests, passed, out["summary"]
        print(format_table(res))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
