"""The gate's checks. Every check is one row of the test table: name, before (baseline), after (candidate), pass.

Events (layer 1 -> layer 2) are checked against the labels; then the same events run through the rule engine with
the candidate pack (and the baseline's, when given) so the table ends with the calls each rally produced, the labelled
rally winner, and ``calls_changed``: the rallies whose scoring call differs between baseline and candidate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..sportmod.api import Observation
from ..sportmod.l1 import read_l1, read_labels
from ..sportmod.loader import LoadError, SportModule, load_module, validate_against, validate_event
from .annotated import annotated_rows, session_rows

ALLOWED_TYPES = frozenset({"bounce", "net", "ball_dead", "contact"})


@dataclass
class Sample:
    name: str
    log: Path
    labels: dict[str, Any]
    observations: list[Observation]


@dataclass
class ReplayResult:
    passed: bool
    tests: list[dict[str, Any]]
    calls_changed: list[dict[str, Any]]
    engine: str
    summary: str
    events: dict[str, dict[str, int]]
    duration_ms: float
    candidate_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "tests": self.tests,
            "calls_changed": self.calls_changed,
            "engine": self.engine,
            "summary": self.summary,
            "events": self.events,
            "duration_ms": round(self.duration_ms, 1),
        }


def load_samples(samples_dir: Path) -> list[Sample]:
    out = []
    for log in sorted(samples_dir.glob("*.l1.jsonl")):
        name = log.name.removesuffix(".l1.jsonl")
        labels_path = log.with_name(f"{name}.labels.json")
        if not labels_path.is_file():
            raise FileNotFoundError(f"{log}: no {labels_path.name} next to it")
        labels = read_labels(labels_path)
        errs = validate_against("labels", labels)
        if errs:
            raise ValueError(f"{labels_path}: {errs}")
        out.append(Sample(name=name, log=log, labels=labels, observations=read_l1(log)))
    if not out:
        raise FileNotFoundError(f"{samples_dir}: no *.l1.jsonl samples")
    return out


def _run_module(mod: SportModule, sample: Sample, game_id: str) -> list[dict[str, Any]]:
    state = mod.state(game_id)
    return [dict(ev) for ev in mod.events(iter(sample.observations), state)]


def _bounce_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e.get("type") == "bounce"]


def _surface_bounces(events: list[dict[str, Any]], labels: dict[str, Any]) -> list[dict[str, Any]]:
    play = {"table", "court"}
    return [e for e in _bounce_rows(events) if (e.get("payload") or {}).get("surface") in play]


def _labelled_surface(labels: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in labels["bounces"] if b["surface"] in {"table", "court"}]


def _match(detected: list[dict[str, Any]], labelled: list[dict[str, Any]], tol_t: float) -> tuple[int, int, int]:
    """Greedy time matching -> (matched, detected, labelled)."""
    used: set[int] = set()
    matched = 0
    for d in detected:
        best = None
        for i, lab in enumerate(labelled):
            if i in used:
                continue
            dt = abs(float(d["t_game_s"]) - float(lab["t_game_s"]))
            if dt <= tol_t and (best is None or dt < best[0]):
                best = (dt, i)
        if best is not None and d.get("side") == labelled[best[1]]["side"]:
            used.add(best[1])
            matched += 1
    return matched, len(detected), len(labelled)


def _fmt_count(events: list[dict[str, Any]] | None, labels: dict[str, Any]) -> str:
    if events is None:
        return ""
    return str(len(_surface_bounces(events, labels)))


def _alternates(bounces: list[dict[str, Any]]) -> bool:
    sides = [b.get("side") for b in bounces]
    return all(a != b for a, b in zip(sides, sides[1:], strict=False))


def _recall_str(events: list[dict[str, Any]] | None, labels: dict[str, Any]) -> str:
    if events is None:
        return ""
    m, d, n = _match(_surface_bounces(events, labels), _labelled_surface(labels), float(labels["tol_t_s"]))
    return f"{m}/{n} recall, {m}/{d} precision"


def run_replay(
    module_dir: Path,
    samples_dir: Path | None,
    *,
    baseline_dir: Path | None = None,
    game_id: str = "g_synth001",
    annotated_dir: Path | None = None,
    session: Path | None = None,
    house_rule: bool = False,
) -> ReplayResult:
    """Replay every sample through the candidate module (and the baseline, when given).

    ``annotated_dir``: hand-annotated fixtures whose labelled calls the pack must reproduce (an interpreter's gate).
    ``session``: the live session the engine dumped; with a baseline, its changed plays are ``calls_changed`` (D-43).
    ``house_rule``: labelled outcomes are shown but not gated (a house rule may change them on purpose)."""
    t0 = time.perf_counter()
    tests: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    cand_events: dict[str, list[dict[str, Any]]] = {}
    calls_changed: list[dict[str, Any]] = []

    def row(name: str, ok: bool, after: str, before: str = "", detail: str = "") -> None:
        tests.append({"name": name, "before": before, "after": after, "pass": bool(ok), "detail": detail})

    # 1. The module loads: files present, schemas valid, events.py within the allowlist, imports cleanly.
    try:
        mod = load_module(module_dir)
        row("module:load", True, "ok")
    except LoadError as e:
        for err in e.errors:
            row("module:load", False, "fail", detail=err)
        return _finish(tests, counts, cand_events, t0)

    base: SportModule | None = None
    if baseline_dir is not None:
        try:
            base = load_module(baseline_dir)
        except LoadError as e:
            row("baseline:load", False, "fail", detail="; ".join(e.errors))

    if session is not None:
        s_tests, s_changed = session_rows(mod, base, session)
        tests += s_tests
        calls_changed += s_changed
    if annotated_dir is not None:
        a_tests, a_changed = annotated_rows(mod, base, annotated_dir, informational=house_rule)
        tests += a_tests
        calls_changed += a_changed
    if samples_dir is None:
        return _finish(tests, counts, cand_events, t0, calls_changed)
    if mod.annotated:
        row("samples:load", False, "fail", detail="an annotated module (no events.py) can't run layer-1 samples")
        return _finish(tests, counts, cand_events, t0, calls_changed)
    try:
        samples = load_samples(samples_dir)
    except (FileNotFoundError, ValueError) as e:
        row("samples:load", False, "fail", detail=str(e))
        return _finish(tests, counts, cand_events, t0, calls_changed)

    for s in samples:
        labels = s.labels
        pre = f"{s.name}:"
        base_events: list[dict[str, Any]] | None = None
        if base is not None:
            try:
                base_events = _run_module(base, s, game_id)
            except Exception as e:  # noqa: BLE001 - the baseline is informational
                row(f"{pre}baseline:runs", False, f"{type(e).__name__}: {e}")
        # 2. events() runs without raising
        try:
            events = _run_module(mod, s, game_id)
        except Exception as e:  # noqa: BLE001 - any exception is a test failure, reported to the Droid
            row(f"{pre}events:runs", False, f"{type(e).__name__}: {e}")
            continue
        row(
            f"{pre}events:runs",
            True,
            f"{len(events)} events",
            before="" if base_events is None else f"{len(base_events)} events",
        )
        cand_events[s.name] = events
        counts[s.name] = {t: sum(1 for e in events if e.get("type") == t) for t in sorted(ALLOWED_TYPES)}
        # 3. every event validates against trophy.event.v1 and uses only layer-2 types
        bad = []
        for i, ev in enumerate(events):
            if ev.get("type") not in ALLOWED_TYPES:
                bad.append(f"event {i}: type {ev.get('type')!r} not in {sorted(ALLOWED_TYPES)}")
                continue
            bad += [f"event {i}: {err}" for err in validate_event(ev)]
        row(f"{pre}events:schema", not bad, "ok" if not bad else f"{len(bad)} invalid", detail="; ".join(bad[:5]))
        # 4. deterministic
        try:
            again = _run_module(mod, s, game_id)
            det = again == events
        except Exception as e:  # noqa: BLE001
            det, again = False, []
            bad = [str(e)]
        row(f"{pre}events:deterministic", det, "ok" if det else "differs between runs")
        # 5. bounce count within tolerance of the labels
        sb = _surface_bounces(events, labels)
        n_lab = len(_labelled_surface(labels))
        tol = int(labels["tol_count"])
        ok = abs(len(sb) - n_lab) <= tol
        row(
            f"{pre}bounce:count",
            ok,
            f"{len(sb)} (labelled {n_lab}, tol ±{tol})",
            before=_fmt_count(base_events, labels),
        )
        # 6. bounces alternate sides
        if labels.get("alternate_sides"):
            alt = _alternates(sb)
            row(
                f"{pre}bounce:alternate",
                alt,
                "ok" if alt else "same side twice: " + " ".join(b.get("side", "?") for b in sb),
                before=""
                if base_events is None
                else ("ok" if _alternates(_surface_bounces(base_events, labels)) else "no"),
            )
        # 7. timing recall/precision vs labelled bounces
        m, d, n = _match(sb, _labelled_surface(labels), float(labels["tol_t_s"]))
        recall = m / n if n else 1.0
        precision = m / d if d else 1.0
        ok = recall >= float(labels["min_recall"]) and precision >= float(labels.get("min_precision", 0.0))
        row(
            f"{pre}bounce:timing",
            ok,
            f"{m}/{n} recall, {m}/{d} precision (±{labels['tol_t_s']} s)",
            before=_recall_str(base_events, labels),
            detail=f"min_recall {labels['min_recall']}, min_precision {labels.get('min_precision', 0)}",
        )
        # 8. ball_dead expected
        if labels.get("expect_ball_dead"):
            has = any(e.get("type") == "ball_dead" for e in events)
            row(f"{pre}ball_dead:present", has, "ok" if has else "missing")
        # 9. calls: replay the events through the rule engine with the candidate pack (and the baseline's)
        cand_calls, cand_err = _replay_calls(mod, events, game_id, labels)
        base_calls = _replay_calls(base, base_events, game_id, labels)[0] if base is not None and base_events else []
        if cand_err:
            row(f"{pre}calls:replay", False, cand_err)
        else:
            row(
                f"{pre}calls:replay",
                True,
                _calls_summary(cand_calls),
                before=_calls_summary(base_calls) if base is not None else "",
            )
            if labels.get("rally_winner"):
                pts = [c for c in cand_calls if c.get("points")]
                won = pts[0].get("team_id") if pts else None
                ok = len(pts) == 1 and won == labels["rally_winner"]
                if house_rule and not ok:
                    ok = True  # a house rule may change who wins a labelled rally: shown, not gated
                row(
                    f"{pre}calls:winner",
                    ok,
                    f"{won or 'none'} ({len(pts)} point calls; labelled {labels['rally_winner']})",
                    before=_winner_str(base_calls) if base is not None else "",
                )
            changed = _calls_changed(base_calls, cand_calls, s.name) if base is not None else []
            calls_changed.extend(changed)

    return _finish(tests, counts, cand_events, t0, calls_changed)


def _replay_calls(mod: SportModule, events: list[dict[str, Any]], game_id: str, labels: dict[str, Any]):
    """Run the events through the engine with this module's pack, in memory. Returns (calls, error)."""
    from ..engine import Engine
    from ..state import MemoryState

    try:
        eng = Engine(MemoryState(), modules_dir=mod.path.parent)
        eng.create_game(
            game_id, mod.sport, t0_ms=0, module_dir=mod.path, params={"synthetic": True, "label": "SYNTHETIC"}
        )
        eng.start_game(game_id, labels.get("first_server") or "A")
        calls: list[dict[str, Any]] = []
        for ev in events:
            calls += eng.feed(ev)
        return calls, None
    except Exception as e:  # noqa: BLE001 - reported as a failed check for the Droid
        return [], f"{type(e).__name__}: {e}"


def _calls_summary(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return "no calls"
    return "; ".join(f"{c['rule_id']}→{c['outcome']}{' ' + c['team_id'] if c.get('team_id') else ''}" for c in calls)[
        :120
    ]


def _winner_str(calls: list[dict[str, Any]]) -> str:
    pts = [c for c in calls if c.get("points")]
    return (pts[0].get("team_id") or "?") if pts else "none"


def _calls_changed(before: list[dict[str, Any]], after: list[dict[str, Any]], sample: str) -> list[dict[str, Any]]:
    """Rallies whose scoring call differs between the baseline and the candidate pack."""

    def by_rally(calls):
        out = {}
        for c in calls:
            if c.get("points") or c.get("outcome") == "let":
                out.setdefault(int(c.get("rally_no") or 0), c)
        return out

    b, a = by_rally(before), by_rally(after)
    changed = []
    for rally in sorted(set(b) | set(a)):
        cb, ca = b.get(rally), a.get(rally)
        sb = f"{cb['outcome']} {cb.get('team_id', '')}".strip() if cb else "no call"
        sa = f"{ca['outcome']} {ca.get('team_id', '')}".strip() if ca else "no call"
        if sb != sa:
            changed.append(
                {"rally_no": rally, "call_id": ca["id"] if ca else None, "before": f"{sample}: {sb}", "after": sa}
            )
    return changed


def _finish(
    tests: list[dict[str, Any]],
    counts: dict[str, dict[str, int]],
    cand: dict[str, list[dict[str, Any]]],
    t0: float,
    calls_changed: list[dict[str, Any]] | None = None,
) -> ReplayResult:
    passed = all(t["pass"] for t in tests) and bool(tests)
    n_fail = sum(1 for t in tests if not t["pass"])
    summary = f"{len(tests) - n_fail}/{len(tests)} checks passed" + ("" if passed else f" ({n_fail} failed)")
    return ReplayResult(
        passed=passed,
        tests=tests,
        calls_changed=calls_changed or [],
        engine="events+rules (layer 1 -> events.py -> rule engine with rules.yaml, in memory)",
        summary=summary,
        events=counts,
        duration_ms=(time.perf_counter() - t0) * 1000,
        candidate_events=cand,
    )


def format_table(res: ReplayResult) -> str:
    w = max(len(t["name"]) for t in res.tests) if res.tests else 10
    wb = max([len(t.get("before", "")) for t in res.tests] + [6])
    lines = [f"{'check'.ljust(w)}  {'before'.ljust(wb)}  after", "-" * (w + wb + 40)]
    for t in res.tests:
        mark = "PASS" if t["pass"] else "FAIL"
        lines.append(f"{t['name'].ljust(w)}  {t.get('before', '').ljust(wb)}  {t['after']}  [{mark}]")
        if not t["pass"] and t.get("detail"):
            lines.append(f"{''.ljust(w)}  {t['detail']}")
    lines.append(f"{res.summary}; engine = {res.engine}; {res.duration_ms:.0f} ms")
    return "\n".join(lines)
