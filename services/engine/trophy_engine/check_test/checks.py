"""The gate's checks. Every check is one row of the test table: name, before (baseline library), after (candidate).

For each fixture (``<name>.track3d.jsonl`` + ``<name>.labels3d.json`` next to ``field.json``): the library loads
under the allowlist; every check is deterministic; `phases` finds the labelled rallies (count, starts, ends);
`bounces` finds the labelled table bounces (recall, precision, position error) and the floor bounces; `in_out` is
right on every labelled margin and never wrong at AUTO confidence; `net_touch` finds the labelled nets;
`contacts` recall; `serve_toss` height and angle error and legality; then the events the library produces run
through the rule engine with the sport's rules.yaml and the rally winners are compared with the labels.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..checks.api import Field, Track
from ..checks.library import CheckLibrary, LibraryError, load_field, load_library, read_track, validate_against

AUTO_P = 0.9


@dataclass
class Fixture:
    name: str
    track: Track
    labels: dict[str, Any]


@dataclass
class GateResult:
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


def load_fixtures(samples_dir: Path, fld: Field) -> list[Fixture]:
    out = []
    for log in sorted(samples_dir.glob("*.track3d.jsonl")):
        name = log.name.removesuffix(".track3d.jsonl")
        lp = log.with_name(f"{name}.labels3d.json")
        if not lp.is_file():
            raise FileNotFoundError(f"{log}: no {lp.name} next to it")
        labels = json.loads(lp.read_text("utf8"))
        errs = validate_against("Track3DLabels", labels)
        if errs:
            raise ValueError(f"{lp}: {errs}")
        out.append(Fixture(name=name, track=read_track(log, fld), labels=labels))
    if not out:
        raise FileNotFoundError(f"{samples_dir}: no *.track3d.jsonl fixtures")
    return out


def _match(det: list[float], lab: list[float], tol: float) -> tuple[int, list[int | None]]:
    """Greedy time matching; returns (matched, index of the detection matched to each label or None)."""
    used: set[int] = set()
    matched = 0
    assign: list[int | None] = []
    for lt in lab:
        best = None
        for i, dt_ in enumerate(det):
            if i in used:
                continue
            d = abs(dt_ - lt)
            if d <= tol and (best is None or d < best[0]):
                best = (d, i)
        if best is None:
            assign.append(None)
        else:
            used.add(best[1])
            matched += 1
            assign.append(best[1])
    return matched, assign


def _tol(labels: dict[str, Any], key: str, default: float) -> float:
    return float((labels.get("tol") or {}).get(key, default))


def run_check_test(
    library_dir: Path,
    samples_dir: Path,
    *,
    field_path: Path | None = None,
    baseline_dir: Path | None = None,
    rules_dir: Path | None = None,
    game_id: str = "g_synth001",
) -> GateResult:
    t0 = time.perf_counter()
    tests: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    cand_events: dict[str, list[dict[str, Any]]] = {}

    def row(name: str, ok: bool, after: str, before: str = "", detail: str = "") -> None:
        tests.append({"name": name, "before": before, "after": after, "pass": bool(ok), "detail": detail})

    try:
        lib = load_library(library_dir)
        row("library:load", True, f"ok ({len(lib.checks)} checks: {', '.join(lib.names())})")
    except LibraryError as e:
        for err in e.errors:
            row("library:load", False, "fail", detail=err)
        return _finish(tests, counts, cand_events, t0)
    missing = [n for n in ("phases", "bounces", "in_out", "contacts", "net_touch", "serve_toss") if n not in lib.checks]
    if missing:
        row("library:required", False, f"missing {missing}")
        return _finish(tests, counts, cand_events, t0)
    base: CheckLibrary | None = None
    if baseline_dir is not None:
        try:
            base = load_library(baseline_dir)
        except LibraryError as e:
            row("baseline:load", False, "fail", detail="; ".join(e.errors))
    try:
        fld = load_field(field_path or samples_dir / "field.json")
        fixtures = load_fixtures(samples_dir, fld)
    except (LibraryError, FileNotFoundError, ValueError) as e:
        row("samples:load", False, "fail", detail=str(e))
        return _finish(tests, counts, cand_events, t0)

    for fx in fixtures:
        pre = f"{fx.name}:"
        L = fx.labels
        tol_t = _tol(L, "t_s", 0.06)
        try:
            ph = lib.run("phases", fx.track, fld, t1=fx.track.t1 + 2.0)
            bn = lib.run("bounces", fx.track, fld)
            ct = lib.run("contacts", fx.track, fld)
            nt = lib.run("net_touch", fx.track, fld)
        except Exception as e:  # noqa: BLE001 - any exception is a failed check, reported to the Droid
            row(f"{pre}checks:run", False, f"{type(e).__name__}: {e}")
            continue
        row(
            f"{pre}checks:run",
            True,
            f"phases {ph['ms']} ms, bounces {bn['ms']} ms, contacts {ct['ms']} ms, net {nt['ms']} ms",
        )
        # deterministic
        try:
            again = lib.run("bounces", fx.track, fld)
            det = {k: v for k, v in again.items() if k != "ms"} == {k: v for k, v in bn.items() if k != "ms"}
        except Exception:  # noqa: BLE001
            det = False
        row(f"{pre}checks:deterministic", det, "ok" if det else "bounces differs between runs")
        base_ph = base_bn = None
        if base is not None:
            try:
                base_ph = base.run("phases", fx.track, fld, t1=fx.track.t1 + 2.0)
                base_bn = base.run("bounces", fx.track, fld)
            except Exception:  # noqa: BLE001 - the baseline is informational
                pass
        # phases
        segs = ph["verdict"]["segments"]
        lab_r = L["rallies"]
        ok = len(segs) == len(lab_r)
        row(
            f"{pre}phases:count",
            ok,
            f"{len(segs)} rallies (labelled {len(lab_r)})",
            before="" if base_ph is None else str(len(base_ph["verdict"]["segments"])),
        )
        ts = _tol(L, "t_start_s", 0.2)
        te = _tol(L, "t_end_s", 0.6)
        m_start, _ = _match([s["t_start_s"] for s in segs], [r["t_start_s"] for r in lab_r], ts)
        m_end, _ = _match(
            [s["t_end_s"] for s in segs if s.get("t_end_s") is not None],
            [r["t_end_s"] for r in lab_r if r.get("t_end_s") is not None],
            te,
        )
        srv_ok = sum(1 for s, r in zip(segs, lab_r, strict=False) if s["server_side"] == r["server_side"])
        row(
            f"{pre}phases:timing",
            m_start == len(lab_r) and m_end == len(lab_r),
            f"starts {m_start}/{len(lab_r)} (±{ts} s), ends {m_end}/{len(lab_r)} (±{te} s), server {srv_ok}/{len(lab_r)}",  # noqa: E501
        )
        # bounces
        det_t = [b for b in bn["verdict"] if b["surface"] == "table"]
        lab_t = [b for b in L["bounces"] if b["surface"] == "table"]
        m, assign = _match([b["t_s"] for b in det_t], [b["t_s"] for b in lab_t], tol_t)
        side_ok = sum(
            1 for lab, i in zip(lab_t, assign, strict=False) if i is not None and det_t[i]["side"] == lab["side"]
        )
        pos_err = [
            ((det_t[i]["pos_m"][0] - lab["pos_m"][0]) ** 2 + (det_t[i]["pos_m"][1] - lab["pos_m"][1]) ** 2) ** 0.5
            for lab, i in zip(lab_t, assign, strict=False)
            if i is not None and lab.get("pos_m")
        ]
        recall = m / len(lab_t) if lab_t else 1.0
        precision = m / len(det_t) if det_t else 1.0
        mean_err = sum(pos_err) / len(pos_err) if pos_err else 0.0
        ok = (
            recall >= _tol(L, "min_recall", 1.0)
            and precision >= _tol(L, "min_precision", 0.9)
            and side_ok == m
            and mean_err <= _tol(L, "pos_m", 0.05)
        )
        before = ""
        if base_bn is not None:
            bt = [b for b in base_bn["verdict"] if b["surface"] == "table"]
            bm, _ = _match([b["t_s"] for b in bt], [b["t_s"] for b in lab_t], tol_t)
            before = f"{bm}/{len(lab_t)} recall"
        row(
            f"{pre}bounces:table",
            ok,
            f"{m}/{len(lab_t)} recall, {m}/{len(det_t)} precision, sides {side_ok}/{m}, pos err {mean_err * 100:.1f} cm (±{tol_t} s)",  # noqa: E501
            before=before,
        )
        det_f = [b for b in bn["verdict"] if b["surface"] == "floor"]
        lab_f = [b for b in L["bounces"] if b["surface"] == "floor"]
        mf, _ = _match([b["t_s"] for b in det_f], [b["t_s"] for b in lab_f], tol_t + 0.04)
        row(f"{pre}bounces:floor", mf == len(lab_f), f"{mf}/{len(lab_f)} floor bounces found ({len(det_f)} detected)")
        # in_out on every labelled bounce that has a margin (edge and side-face cases), plus clear bounces
        n_io = n_ok = n_auto_wrong = 0
        details = []
        for lab in L["bounces"]:
            if lab["surface"] == "floor":
                continue
            try:
                r = lib.run("in_out", fx.track, fld, t_s=lab["t_s"])
            except Exception as e:  # noqa: BLE001
                details.append(f"in_out@{lab['t_s']}: {type(e).__name__}: {e}")
                continue
            truth_in = lab.get("in", True) and lab["surface"] == "table"
            n_io += 1
            v = r["verdict"]
            pred_in = v == "in" or (v == "edge" and (r["p"] or 0) >= 0.5)
            right = v != "no_bounce" and pred_in == truth_in
            n_ok += int(right)
            if r["p"] is not None and (r["p"] >= AUTO_P or r["p"] <= 1 - AUTO_P) and not right:
                n_auto_wrong += 1
                details.append(
                    f"AUTO wrong at t={lab['t_s']}: {v} p={r['p']} (truth {'in' if truth_in else 'out'}, margin {lab.get('margin_m')})"  # noqa: E501
                )
            elif not right:
                details.append(
                    f"wrong at t={lab['t_s']}: {v} p={r['p']} (truth {'in' if truth_in else 'out'}, margin {lab.get('margin_m')})"  # noqa: E501
                )
        min_acc = 0.9
        ok = n_io > 0 and n_auto_wrong == 0 and n_ok / n_io >= min_acc
        row(
            f"{pre}in_out:accuracy",
            ok,
            f"{n_ok}/{n_io} right, {n_auto_wrong} wrong at AUTO confidence",
            detail="; ".join(details[:4]),
        )
        # nets
        lab_n = L.get("nets") or []
        det_n = nt["verdict"]
        mn, assign_n = _match([e["t_s"] for e in det_n], [e["t_s"] for e in lab_n], tol_t + 0.04)
        kind_ok = sum(
            1 for lab, i in zip(lab_n, assign_n, strict=False) if i is not None and det_n[i]["kind"] == lab["kind"]
        )
        row(
            f"{pre}net:recall",
            mn == len(lab_n) and kind_ok == mn and len(det_n) <= len(lab_n) + 1,
            f"{mn}/{len(lab_n)} nets, kinds {kind_ok}/{mn}, {len(det_n)} detected",
        )
        # contacts
        lab_c = L.get("contacts") or []
        det_c = ct["verdict"]
        mc, assign_c = _match([e["t_s"] for e in det_c], [e["t_s"] for e in lab_c], tol_t + 0.04)
        side_c = sum(
            1 for lab, i in zip(lab_c, assign_c, strict=False) if i is not None and det_c[i]["side"] == lab["side"]
        )
        rc = mc / len(lab_c) if lab_c else 1.0
        row(
            f"{pre}contacts:recall",
            rc >= 0.9 and side_c == mc,
            f"{mc}/{len(lab_c)} contacts, sides {side_c}/{mc}, {len(det_c)} detected",
        )
        # serves
        n_s = n_sok = 0
        h_err = []
        a_err = []
        sdet = []
        for sv in L.get("serves") or []:
            seg = next((s for s in segs if s["rally_no"] == sv["rally_no"]), None)
            t_start = seg["t_start_s"] if seg else sv.get("t_release_s", 0.0)
            try:
                r = lib.run("serve_toss", fx.track, fld, t_start=t_start)
            except Exception as e:  # noqa: BLE001
                sdet.append(f"serve {sv['rally_no']}: {type(e).__name__}: {e}")
                continue
            n_s += 1
            v = r["verdict"]
            if v == "no_serve":
                sdet.append(f"serve {sv['rally_no']}: not found")
                continue
            h_err.append(abs(v["height_m"] - sv["height_m"]))
            if sv["height_m"] >= 0.12:  # an angle needs a leg to measure on; shorter tosses are judged on height
                a_err.append(abs(v["angle_deg"] - sv["angle_deg"]))
            if v["legal"] == sv["legal"]:
                n_sok += 1
            else:
                sdet.append(
                    f"serve {sv['rally_no']}: {'legal' if v['legal'] else 'illegal'} (truth {'legal' if sv['legal'] else 'illegal'}; h {v['height_m']:.3f} vs {sv['height_m']}, a {v['angle_deg']:.0f} vs {sv['angle_deg']})"  # noqa: E501
                )
        mh = max(h_err) if h_err else 0.0
        ma = max(a_err) if a_err else 0.0
        ok = n_s > 0 and n_sok == n_s and mh <= _tol(L, "height_m", 0.03) and ma <= _tol(L, "angle_deg", 8.0)
        row(
            f"{pre}serve_toss:accuracy",
            ok,
            f"{n_sok}/{n_s} legality right, height err max {mh * 100:.1f} cm, angle err max {ma:.1f} deg (tosses >= 12 cm)",  # noqa: E501
            detail="; ".join(sdet[:4]),
        )
        # events -> rule engine -> calls
        from ..checks.events import TrackEventer  # noqa: PLC0415 - avoid a cycle at import time

        try:
            ev = TrackEventer(lib, fld, game_id=game_id, sport=L.get("sport", fld.sport))
            events = ev.feed_all(fx.track)
            cand_events[fx.name] = events
            counts[fx.name] = {
                t: sum(1 for e in events if e.get("type") == t)
                for t in ("bounce", "contact", "net", "ball_dead", "serve_toss")
            }
            row(f"{pre}events:build", True, f"{len(events)} events")
        except Exception as e:  # noqa: BLE001
            row(f"{pre}events:build", False, f"{type(e).__name__}: {e}")
            continue
        calls, err = _replay_calls(events, rules_dir, L, game_id)
        if err:
            row(f"{pre}calls:replay", False, err)
            continue
        winners = _winners(calls)
        lab_w = {r["rally_no"]: r.get("winner") for r in lab_r}
        n_right = sum(1 for k, w in lab_w.items() if winners.get(k) == w)
        row(
            f"{pre}calls:winners",
            n_right == len(lab_w) and len(winners) == len(lab_w),
            f"{n_right}/{len(lab_w)} rally winners match ({len(winners)} rallies scored)",
            detail="; ".join(
                f"rally {k}: got {winners.get(k)} want {w}" for k, w in lab_w.items() if winners.get(k) != w
            )[:400],
        )
    return _finish(tests, counts, cand_events, t0)


def _replay_calls(events: list[dict[str, Any]], rules_dir: Path | None, labels: dict[str, Any], game_id: str):
    """Run the events through the engine with the sport's module (rules.yaml), in memory; stop feeding a rally
    once it has been scored (the ball is dead whatever the track says next)."""
    from ..engine import Engine
    from ..state import MemoryState

    try:
        sport = labels.get("sport", "table_tennis")
        root = Path(__file__).resolve().parents[4]
        mod_dir = rules_dir or root / "sports" / sport
        eng = Engine(MemoryState(), modules_dir=mod_dir.parent)
        eng.create_game(game_id, sport, t0_ms=0, module_dir=mod_dir, params={"synthetic": True, "label": "SYNTHETIC"})
        eng.start_game(game_id, labels.get("first_server") or "A")
        calls: list[dict[str, Any]] = []
        scored_rally = None
        for e in events:
            rn = e.get("rally_no_hint")
            if scored_rally is not None and rn == scored_rally:
                continue
            out = eng.feed({k: v for k, v in e.items() if k != "rally_no_hint"})
            for c in out:
                c["_rally_hint"] = rn
            calls += out
            if any(c.get("points") or c.get("outcome") == "let" for c in out):
                scored_rally = rn
        return calls, None
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}: {e}"


def _winners(calls: list[dict[str, Any]]) -> dict[int, str | None]:
    out: dict[int, str | None] = {}
    for c in calls:
        if c.get("points") or c.get("outcome") == "let":
            rn = int(c.get("_rally_hint") or 0)
            out.setdefault(rn, c.get("team_id") if c.get("points") else None)
    return out


def _finish(tests, counts, cand, t0) -> GateResult:
    passed = all(t["pass"] for t in tests) and bool(tests)
    n_fail = sum(1 for t in tests if not t["pass"])
    summary = f"{len(tests) - n_fail}/{len(tests)} checks passed" + ("" if passed else f" ({n_fail} failed)")
    return GateResult(
        passed=passed,
        tests=tests,
        calls_changed=[],
        engine="checks over track3d -> events -> rule engine with rules.yaml, in memory",
        summary=summary,
        events=counts,
        duration_ms=(time.perf_counter() - t0) * 1000,
        candidate_events=cand,
    )


def format_table(res: GateResult) -> str:
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
