"""Re-judge a session under another rule pack (D-43): the same events through a fresh in-memory engine, twice.

The engine uses this when a house rule or a Droid-written interpreter is applied (the session's past plays are judged
again and changed outcomes get superseding calls), and the Droid's gate uses it with the session the engine dumped
(``session.json``) so ``calls_changed`` shows what the rule would change in *this* game before it is applied.

A play is matched across the two replays by when its rally started, so a rule that ends a rally early (a let) does not
shift every later rally's number. Only the play's decisive call counts (a point, a fault, a basket or a let).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SESSION_SCHEMA = "trophy.session.v1"


@dataclass
class Replay:
    calls: list[dict[str, Any]]
    rallies: list[dict[str, Any]]
    score: dict[str, int]
    error: str | None = None


def decisive(call: dict[str, Any]) -> bool:
    """The call that decides a play: a point/fault/basket with points, or a let."""
    if call.get("kind") == "info" or call.get("status") in ("voided", "overturned"):
        return False
    return bool(call.get("points")) or call.get("outcome") == "let"


def at_fault_id(call: dict[str, Any] | None) -> str | None:
    af = (call or {}).get("at_fault")
    return af.get("team_id") if isinstance(af, dict) else None


def describe(call: dict[str, Any] | None) -> str:
    """'fault → B (A at fault)', 'let', 'no call'."""
    if not call:
        return "no call"
    s = str(call.get("outcome") or call.get("rule_id"))
    if call.get("team_id"):
        s += f" → {call['team_id']}"
        if call.get("points") and int(call["points"]) != 1:
            s += f" +{call['points']}"
    if at_fault_id(call):
        s += f" ({at_fault_id(call)} at fault)"
    return s


def signature(call: dict[str, Any] | None) -> tuple[Any, ...]:
    if not call:
        return ()
    return (call.get("outcome"), call.get("team_id"), int(call.get("points") or 0), at_fault_id(call))


def replay_session(
    *,
    sport: str,
    pack: dict[str, Any],
    events: list[dict[str, Any]],
    module_dir: Path,
    teams: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
    first_server: str = "A",
    dead_after_point_s: float | None = None,
    server_from_first_hit: bool = False,
    game_id: str = "g_rejudge0",
) -> Replay:
    """Feed ``events`` (in order) through a fresh engine using ``pack``. Never raises: errors land in ``error``."""
    from .engine import DEAD_AFTER_POINT_S, Engine
    from .state import MemoryState

    st = MemoryState()
    try:
        eng = Engine(
            st,
            modules_dir=module_dir.parent,
            dead_after_point_s=DEAD_AFTER_POINT_S if dead_after_point_s is None else dead_after_point_s,
            server_from_first_hit=server_from_first_hit,
            now_ms=lambda: 0.0,
        )
        p = {k: v for k, v in (params or {}).items() if k not in ("synthetic", "label")}
        g = eng.create_game(
            game_id, sport, t0_ms=0, teams=[dict(t) for t in teams] if teams else None, params=p,
            module_dir=module_dir, pack=pack,
        )  # fmt: skip
        eng.start_game(game_id, first_server)
        for ev in events:
            eng.handle_event({**ev, "game_id": game_id})
        sc = g.score()
        return Replay(calls=list(g.calls), rallies=st.rows("rally"), score=dict(sc.points))
    except Exception as e:  # noqa: BLE001 - a broken pack is a failed check, reported to the Droid
        return Replay(calls=[], rallies=[], score={}, error=f"{type(e).__name__}: {e}")


def plays(rep: Replay) -> dict[float, dict[str, Any]]:
    """Rally start time (ms precision) -> that rally's decisive call."""
    starts = {int(r["rally_no"]): round(float(r["t_start_s"]), 3) for r in rep.rallies}
    out: dict[float, dict[str, Any]] = {}
    for c in rep.calls:
        if not decisive(c):
            continue
        key = starts.get(int(c.get("rally_no") or 0), round(float(c.get("t_game_s", 0.0)), 3))
        out.setdefault(key, c)
    return out


def rally_changes(base: Replay, cand: Replay) -> list[dict[str, Any]]:
    """Plays whose decisive call differs: [{t_s, rally_no, before: call|None, after: call|None}] in time order."""
    b, a = plays(base), plays(cand)
    out = []
    for key in sorted(set(b) | set(a)):
        cb, ca = b.get(key), a.get(key)
        if signature(cb) != signature(ca):
            out.append({"t_s": key, "rally_no": int((ca or cb or {}).get("rally_no") or 0), "before": cb, "after": ca})
    return out


def change_rows(changes: list[dict[str, Any]], prefix: str = "") -> list[dict[str, Any]]:
    """DroidRunCallChange rows (droidrun.schema.json) for a list of rally_changes."""
    rows = []
    for ch in changes:
        row: dict[str, Any] = {
            "rally_no": max(1, int(ch["rally_no"] or 1)),
            "t_s": ch["t_s"],
            "before": f"{prefix}{describe(ch['before'])}",
            "after": describe(ch["after"]),
        }
        cid = (ch["after"] or ch["before"] or {}).get("id")
        if cid:
            row["call_id"] = cid
        rows.append(row)
    return rows


# ---------------------------------------------------------------- the session file the engine hands the Droid


def write_session(path: Path, *, game: dict[str, Any], first_server: str, events: list[dict[str, Any]],
                  rule_version: str, dead_after_point_s: float, server_from_first_hit: bool) -> None:  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": SESSION_SCHEMA,
        "game_id": game["game_id"],
        "sport": game["sport"],
        "teams": game.get("teams") or [],
        "params": {k: v for k, v in (game.get("params") or {}).items() if k not in ("synthetic", "label")},
        "first_server": first_server,
        "rule_version": rule_version,
        "dead_after_point_s": dead_after_point_s,
        "server_from_first_hit": server_from_first_hit,
        "events": events,
    }
    path.write_text(json.dumps(doc), "utf8")


def read_session(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text("utf8"))
    if doc.get("schema") != SESSION_SCHEMA or not isinstance(doc.get("events"), list):
        raise ValueError(f"{path}: not a {SESSION_SCHEMA} file")
    return doc


def replay_doc(doc: dict[str, Any], pack: dict[str, Any], module_dir: Path) -> Replay:
    return replay_session(
        sport=str(doc["sport"]),
        pack=pack,
        events=list(doc["events"]),
        module_dir=module_dir,
        teams=doc.get("teams") or None,
        params=doc.get("params") or {},
        first_server=str(doc.get("first_server") or "A"),
        dead_after_point_s=doc.get("dead_after_point_s"),
        server_from_first_hit=bool(doc.get("server_from_first_hit")),
    )
