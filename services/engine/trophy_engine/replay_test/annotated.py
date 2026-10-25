"""The gate's checks over hand-annotated events (D-44) and over the live session (D-43).

Annotated fixtures: ``<clip>.events.jsonl`` (one trophy.event.v1 per line, ``source: annotated``) and
``<clip>.labels.json`` (``{calls: [{t_s, rule_id?, outcome, team_id, at_fault}], teams?, first_server?, tol_t_s?}``).
An interpreter (the sport's rules.yaml) passes when replaying the events through the engine reproduces every labelled
call (outcome, the team it favours, the team at fault, within ``tol_t_s``) and makes no unlabelled decisive call.

Session: ``session.json`` as the engine dumps it for a house rule. The candidate must replay it without error; with a
baseline pack (the pack in force), every play whose decisive call changes is a ``calls_changed`` row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..rejudge import (
    Replay,
    at_fault_id,
    change_rows,
    decisive,
    describe,
    rally_changes,
    read_session,
    replay_doc,
    replay_session,
    signature,
)
from ..sportmod.loader import SportModule, validate_event

DEFAULT_TOL_S = 0.5
Row = dict[str, Any]


def _expected(lab: dict[str, Any]) -> str:
    s = str(lab.get("outcome"))
    if lab.get("team_id"):
        s += f" → {lab['team_id']}"
    if lab.get("at_fault"):
        s += f" ({lab['at_fault']} at fault)"
    return s


def _matches(call: dict[str, Any], lab: dict[str, Any], tol: float) -> bool:
    return (
        abs(float(call.get("t_game_s", 0.0)) - float(lab["t_s"])) <= tol
        and call.get("outcome") == lab.get("outcome")
        and (call.get("team_id") or None) == (lab.get("team_id") or None)
        and at_fault_id(call) == (lab.get("at_fault") or None)
        and (not lab.get("rule_id") or call.get("rule_id") == lab["rule_id"])
    )


def load_fixtures(d: Path) -> list[tuple[str, list[dict[str, Any]], dict[str, Any]]]:
    out = []
    for f in sorted(d.glob("*.events.jsonl")):
        name = f.name.removesuffix(".events.jsonl")
        lab = f.with_name(f"{name}.labels.json")
        if not lab.is_file():
            raise FileNotFoundError(f"{f.name}: no {lab.name} next to it")
        events = [json.loads(line) for line in f.read_text("utf8").splitlines() if line.strip()]
        out.append((name, events, json.loads(lab.read_text("utf8"))))
    if not out:
        raise FileNotFoundError(f"{d}: no *.events.jsonl fixtures")
    return out


def _replay(mod: SportModule, events: list[dict[str, Any]], labels: dict[str, Any]) -> Replay:
    return replay_session(
        sport=mod.sport,
        pack=mod.rules,
        events=events,
        module_dir=mod.path,
        teams=labels.get("teams") or None,
        params=labels.get("params") or {},
        first_server=str(labels.get("first_server") or "A"),
        dead_after_point_s=labels.get("dead_after_point_s"),
    )


def annotated_rows(
    mod: SportModule, base: SportModule | None, fixtures: Path, *, informational: bool = False
) -> tuple[list[Row], list[Row]]:
    """Test rows and calls_changed rows for every annotated fixture. ``informational`` (house rules): a label that no
    longer reproduces is shown, not failed, since a house rule may change outcomes on purpose."""
    tests: list[Row] = []
    changed: list[Row] = []

    def row(name: str, ok: bool, after: str, before: str = "", detail: str = "", gate: bool = True) -> None:
        if not gate and not ok:
            detail = f"(house rule: shown, not gated) {detail}".strip()
            ok = True
        tests.append({"name": name, "before": before, "after": after, "pass": bool(ok), "detail": detail})

    try:
        fx = load_fixtures(fixtures)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        row("fixtures:load", False, "fail", detail=str(e))
        return tests, changed
    for name, events, labels in fx:
        pre = f"{name}:"
        bad = [f"event {i}: {err}" for i, ev in enumerate(events) for err in validate_event(ev)]
        row(f"{pre}events:schema", not bad, "ok" if not bad else f"{len(bad)} invalid", detail="; ".join(bad[:5]))
        cand = _replay(mod, events, labels)
        if cand.error:
            row(f"{pre}calls:replay", False, cand.error)
            continue
        again = _replay(mod, events, labels)
        det = [signature(c) for c in again.calls] == [signature(c) for c in cand.calls]
        row(f"{pre}calls:deterministic", det, "ok" if det else "differs between runs")
        calls = [c for c in cand.calls if c.get("kind") != "info"]
        base_rep = _replay(base, events, labels) if base is not None else None
        row(
            f"{pre}calls:replay",
            True,
            f"{sum(1 for c in calls if decisive(c))} decisive calls",
            before="" if base_rep is None else f"{sum(1 for c in base_rep.calls if decisive(c))} decisive calls",
        )
        tol = float(labels.get("tol_t_s", DEFAULT_TOL_S))
        used: set[int] = set()
        for i, lab in enumerate(labels.get("calls") or []):
            hit = next((j for j, c in enumerate(calls) if j not in used and _matches(c, lab, tol)), None)
            near = [c for c in calls if abs(float(c.get("t_game_s", 0)) - float(lab["t_s"])) <= tol]
            if hit is not None:
                used.add(hit)
            got = describe(calls[hit]) if hit is not None else ("; ".join(describe(c) for c in near) or "no call")
            row(
                f"{pre}call:{i + 1}@{float(lab['t_s']):g}s",
                hit is not None,
                got,
                before=f"expect {_expected(lab)}",
                detail="" if hit is not None else f"expected {_expected(lab)} within ±{tol} s",
                gate=not informational,
            )
        extra = [c for j, c in enumerate(calls) if j not in used and decisive(c)]
        row(
            f"{pre}calls:no_extra",
            not extra,
            "ok" if not extra else "; ".join(f"{describe(c)} @{c['t_game_s']:g}s" for c in extra)[:200],
            detail="" if not extra else "decisive calls with no label",
            gate=not informational,
        )
        if base_rep is not None and not base_rep.error:
            changed += change_rows(rally_changes(base_rep, cand), prefix=f"{name}: ")
    return tests, changed


def session_rows(mod: SportModule, base: SportModule | None, session: Path) -> tuple[list[Row], list[Row]]:
    """The live session (D-43): the candidate replays it; with the baseline, the plays it would change."""
    try:
        doc = read_session(session)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return [{"name": "session:load", "before": "", "after": "fail", "pass": False, "detail": str(e)}], []
    cand = replay_doc(doc, mod.rules, mod.path)
    n_ev = len(doc["events"])
    if cand.error:
        return [{"name": "session:replay", "before": "", "after": cand.error, "pass": False, "detail": ""}], []
    plays = sum(1 for c in cand.calls if decisive(c))
    tests: list[Row] = []
    changed: list[Row] = []
    before = ""
    if base is not None:
        b = replay_doc(doc, base.rules, base.path)
        if not b.error:
            changed = change_rows(rally_changes(b, cand))
            before = f"{sum(1 for c in b.calls if decisive(c))} decisive calls, score {_score(b)}"
    tests.append(
        {
            "name": "session:replay",
            "before": before,
            "after": f"{n_ev} events → {plays} decisive calls, score {_score(cand)}",
            "pass": True,
            "detail": "",
        }
    )
    tests.append(
        {
            "name": "session:calls_changed",
            "before": "",
            "after": f"{len(changed)} play(s) change in this game",
            "pass": True,
            "detail": "; ".join(f"{c['before']} ⇒ {c['after']}" for c in changed[:5]),
        }
    )
    return tests, changed


def _score(rep: Replay) -> str:
    return "–".join(str(v) for v in rep.score.values()) or "0–0"
