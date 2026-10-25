"""Build ``trophy.call.v1`` rows: text and speech templates, cue, evidence windows, overlay (interfaces-v1 §10)."""

from __future__ import annotations

import re
from typing import Any

from trophy.ids import new_ulid

_TPL = re.compile(r"\{([a-zA-Z_][\w.]*)\}")


def _lookup(path: str, ctx: dict[str, Any]) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render(template: str, ctx: dict[str, Any]) -> str:
    def sub(m: re.Match[str]) -> str:
        v = _lookup(m.group(1), ctx)
        if v is None:
            return m.group(0)
        if isinstance(v, float):
            return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:.0f}"
        return str(v)

    return _TPL.sub(sub, template)


def cue_for(kind: str, outcome: str, team_id: str | None, team_color: str | None) -> dict[str, str]:
    if kind in ("point", "basket"):
        return {"beep": "short", "flash": team_id or "none"}
    if kind == "violation":
        return {"beep": "double", "flash": team_color or team_id or "none"}
    if kind in ("edge_call", "line_call"):
        return {"beep": "short", "flash": "none"}
    if kind == "foul_flag":
        return {"beep": "long", "flash": "none"}
    return {"beep": "none", "flash": "none"}


def evidence_for(ev: dict[str, Any], before_s: float = 2.0, after_s: float = 1.0) -> list[dict[str, Any]]:
    t = float(ev.get("t_game_s", 0.0))
    cams = ev.get("cams") or []
    out = []
    for e in ev.get("evidence") or []:
        if "t0_s" in e and "t1_s" in e:
            out.append({"cam_id": e["cam_id"], "t0_s": float(e["t0_s"]), "t1_s": float(e["t1_s"])})
    if not out:
        out = [{"cam_id": c, "t0_s": round(max(0.0, t - before_s), 3), "t1_s": round(t + after_s, 3)} for c in cams]
    return out


def overlay_for(ev: dict[str, Any], lines: list[str]) -> dict[str, Any] | None:
    o: dict[str, Any] = {}
    if ev.get("type") == "bounce" and ev.get("pos_m"):
        pos = ev["pos_m"]
        o["bounce_marks"] = [
            {
                "pos_m": [pos.get("x", 0.0), pos.get("y", 0.0)],
                "sigma_m": float(ev.get("sigma_m", 0.02)),
                "t_game_s": ev.get("t_game_s"),
            }
        ]
    if lines:
        o["lines"] = lines
    if ev.get("type") == "serve_toss":
        o["serve_toss_event_id"] = ev.get("id")
    return o or None


def build_call(
    *,
    game_id: str,
    ev: dict[str, Any],
    rule: dict[str, Any],
    rule_version: str,
    rally_no: int,
    outcome: str,
    team_id: str | None,
    points: int | None,
    p: float,
    p_source: str,
    tier: str,
    shown: str,
    ctx: dict[str, Any],
    team_name: str | None,
    team_color: str | None,
    lines: list[str],
    emotion: str | None,
    now_ms: float,
    why: str | None = None,
    at_fault: dict[str, str] | None = None,
    source: str = "sensed",
) -> dict[str, Any]:
    tctx = {
        **ctx,
        "team": team_name or team_id or "",
        "team_id": team_id or "",
        "p": round(p * 100),
        "outcome": outcome,
        "at_fault": (at_fault or {}).get("name", ""),
    }
    text = render(str(rule.get("text") or f"{rule.get('name', rule['id'])}: {outcome}"), tctx)[:80]
    speech = render(str(rule.get("speech") or text), tctx)
    if at_fault and "{at_fault}" not in str(rule.get("speech") or rule.get("text") or ""):
        speech = f"{speech.rstrip()} {fault_phrase(at_fault['name'])}"  # every call says who is at fault (D-44)
    call: dict[str, Any] = {
        "schema": "trophy.call.v1",
        "id": new_ulid(),
        "game_id": game_id,
        "t_game_s": float(ev.get("t_game_s", 0.0)),
        "rule_id": str(rule["id"]),
        "rule_version": rule_version,
        "rally_no": rally_no,
        "kind": str(rule.get("kind") or "info"),
        "outcome": outcome,
        "p": round(max(0.0, min(1.0, p)), 4),
        "p_source": p_source,
        "tier": tier,
        "shown": shown,
        "text": text,
        "speech": speech,
        "cue": cue_for(str(rule.get("kind") or "info"), outcome, team_id, team_color),
        "event_ids": [str(ev.get("id", ""))],
        "evidence": evidence_for(ev),
        "status": "final",
        "created_at_ms": now_ms,
    }
    if team_id:
        call["team_id"] = team_id
    if points:
        call["points"] = int(points)
    if emotion:
        call["emotion"] = emotion
    ov = overlay_for(ev, lines)
    if ov:
        call["overlay"] = ov
    if rule.get("rule_ref"):
        call["rule_ref"] = str(rule["rule_ref"])
    if why:
        call["why"] = why[:140]
    call["at_fault"] = at_fault
    call["source"] = source
    return call


def fault_phrase(name: str) -> str:
    return f"{name}'s fault." if not name.endswith("s") else f"{name}' fault."
