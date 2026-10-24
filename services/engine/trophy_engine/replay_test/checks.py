"""The gate's checks. Every check is one row of the test table: name, before (baseline), after (candidate), pass.

Stage 1 replays *events only* (layer 1 -> layer 2). Once the rule engine lands (stage 2) the same table grows a
"calls" section and ``calls_changed`` fills in; until then ``engine = "events-only"`` says so.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..sportmod.api import Observation
from ..sportmod.l1 import read_l1, read_labels
from ..sportmod.loader import LoadError, SportModule, load_module, validate_against, validate_event

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
    samples_dir: Path,
    *,
    baseline_dir: Path | None = None,
    game_id: str = "g_synth001",
) -> ReplayResult:
    """Replay every sample through the candidate module (and the baseline, when given)."""
    t0 = time.perf_counter()
    tests: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    cand_events: dict[str, list[dict[str, Any]]] = {}

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

    try:
        samples = load_samples(samples_dir)
    except (FileNotFoundError, ValueError) as e:
        row("samples:load", False, "fail", detail=str(e))
        return _finish(tests, counts, cand_events, t0)

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

    return _finish(tests, counts, cand_events, t0)


def _finish(
    tests: list[dict[str, Any]], counts: dict[str, dict[str, int]], cand: dict[str, list[dict[str, Any]]], t0: float
) -> ReplayResult:
    passed = all(t["pass"] for t in tests) and bool(tests)
    n_fail = sum(1 for t in tests if not t["pass"])
    summary = f"{len(tests) - n_fail}/{len(tests)} checks passed" + ("" if passed else f" ({n_fail} failed)")
    return ReplayResult(
        passed=passed,
        tests=tests,
        calls_changed=[],
        engine="events-only (rule engine arrives in stage 2; no calls replayed)",
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
