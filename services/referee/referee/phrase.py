"""Claude phrases what a check measured; it never computes or changes a number.

Every number Claude may say is pre-formatted here (centimetres, degrees, percent) and the spoken line is checked
against that set afterwards. A line that fails the check, or a Claude error, falls back to a deterministic rendering
of the same measurements, labelled `by: "template"` so the transcript is honest about who wrote it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from trophy.contracts import CheckResult

from .catalog import CHECKS, CheckSpec
from .llm import JSONCompleter, LLMError

PHRASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "speech": {"type": "string", "description": "<= 2 short sentences, <= 30 words, plain speech for TTS"},
        "answer": {"type": "string", "description": "the same answer for the screen; may use symbols"},
    },
    "required": ["speech", "answer"],
    "additionalProperties": False,
}

PHRASE_SYSTEM = (
    "You are Trophy, the referee's voice at a pickup game. A geometry check over the tracked ball has already "
    "measured the answer; phrase it for the players. Use only the facts given, with the numbers exactly as written "
    "(you may drop a number, never change or add one). Lead with the verdict in the first three words. Give the "
    "margin when there is one. When `confidence` is below 90 percent say the percentage; at or above, you may say "
    "'clear' instead. If `calibrated` is false, say the setup is uncalibrated so the answer is provisional. "
    "At most two short sentences and 30 words. No markdown, no rule numbers, no hedging beyond what the facts say."
)

EXPLAIN_SYSTEM = (
    "You are Trophy, the referee's voice at a pickup game. The judge asks why a call was made. Explain it from the "
    "call facts given (what was called, the rule, the measured reason, the confidence), with the numbers exactly as "
    "written. One or two short sentences, at most 30 words, plain speech."
)


@dataclass
class Phrased:
    speech: str
    answer: str
    by: str  # claude | template
    ms: float = 0.0


def fmt_num(v: Any, nd: int = 1) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:.{nd}f}"
    return s[:-2] if s.endswith(".0") else s


def facts_for(result: CheckResult, question: str) -> dict[str, Any]:
    """The numbers Claude may say, already in spoken units."""
    ev = dict(result.evidence or {})
    facts: dict[str, Any] = {
        "check": result.check,
        "verdict": (result.verdict or "").replace("_", " "),
        "confidence_percent": fmt_num(100 * result.p, 0) if result.p is not None else None,
        "calibrated": result.calibrated,
        "tier": result.tier,
    }
    for k, v in ev.items():
        if not isinstance(v, int | float) or isinstance(v, bool):
            if isinstance(v, str):
                facts[k] = v.replace("_", " ")
            continue
        if k.endswith("_m"):
            facts[k[:-2] + "_cm"] = fmt_num(100 * v, 1)
        elif k.endswith("_rad"):
            facts[k[:-4] + "_deg"] = fmt_num(v * 57.29577951308232, 0)
        elif k.endswith("_mps"):
            facts[k[:-4] + "_kmh"] = fmt_num(v * 3.6, 0)
        elif k.endswith("_s"):
            facts[k] = fmt_num(v, 1)
        else:
            facts[k] = fmt_num(v, 1) if isinstance(v, float) else v
    facts["question"] = question
    return facts


_NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers_ok(speech: str, facts: dict[str, Any]) -> bool:
    """Every digit-number in the line must be one of the pre-formatted facts (or the same value re-rounded)."""
    allowed: set[float] = set()
    for v in facts.values():
        if isinstance(v, bool) or v is None:
            continue
        for tok in _NUM.findall(str(v)):
            allowed.add(round(float(tok), 3))
    for tok in _NUM.findall(speech):
        f = float(tok)
        if round(f, 3) in allowed or round(f) in {round(a) for a in allowed}:
            continue
        return False
    return True


def template_check(result: CheckResult, spec: CheckSpec | None) -> Phrased:
    """Deterministic rendering of the measurement (used when Claude fails or says a number it was not given)."""
    ev = result.evidence or {}
    v = (result.verdict or "").replace("_", " ")
    conf = f" {fmt_num(100 * result.p, 0)} percent." if result.p is not None and result.p < 0.9 else " Clear."
    cal = "" if result.calibrated else " The setup is uncalibrated, so this is provisional."
    parts: list[str] = []
    if result.check == "in_out":
        m = ev.get("margin_m")
        line = str(ev.get("line", "")).replace("_", " ")
        where = f" by {fmt_num(abs(float(m)) * 100)} centimetres" if isinstance(m, int | float) else ""
        parts.append(f"{v.capitalize()}{where}{(', ' + line) if line else ''}.")
    elif result.check == "bounce_side":
        parts.append(f"Side {v}.")
    elif result.check == "edge_hit":
        words = {"top edge": "Top edge, good ball.", "side face": "Side face, fault.", "miss": "No edge, clean bounce."}
        parts.append(words.get(v, f"{v.capitalize()}."))
    elif result.check == "net_touch":
        parts.append("Yes, it touched the net." if v == "yes" else "No net touch.")
    elif result.check == "serve_toss":
        h = ev.get("height_m")
        a = ev.get("angle_deg")
        detail = []
        if isinstance(h, int | float):
            detail.append(f"toss {fmt_num(100 * h)} centimetres")
        if isinstance(a, int | float):
            detail.append(f"{fmt_num(a, 0)} degrees from vertical")
        lead = {"legal": "Legal serve", "too low": "Fault, toss too low", "angled": "Fault, toss not vertical"}.get(
            v, v
        )
        parts.append(f"{lead}{(': ' + ', '.join(detail)) if detail else ''}.")
    elif result.check == "double_bounce":
        parts.append("Yes, two bounces on one side." if v == "yes" else "No, one bounce.")
    elif result.check == "rally_summary":
        shots = ev.get("shots")
        sp = ev.get("speed_max_mps")
        bits = []
        if shots is not None:
            bits.append(f"{shots} shots")
        if isinstance(sp, int | float):
            bits.append(f"fastest ball {fmt_num(sp * 3.6, 0)} kilometres an hour")
        parts.append((", ".join(bits) or "No rally data") + ".")
        return Phrased(" ".join(parts) + cal, " ".join(parts), "template")
    else:
        parts.append(f"{v.capitalize() or result.check}.")
    speech = (" ".join(parts) + conf + cal).strip()
    return Phrased(speech, speech, "template")


async def phrase_check(llm: JSONCompleter | None, question: str, result: CheckResult) -> Phrased:
    spec = CHECKS.get(result.check)
    if result.error or (result.verdict is None and result.check != "rally_summary"):
        return template_error(result)
    facts = facts_for(result, question)
    if llm is None:
        return template_check(result, spec)
    user = "Facts (JSON): " + _json(facts) + (f"\nWhat the check measures: {spec.about}" if spec else "")
    try:
        data, ms = await llm.complete(system=PHRASE_SYSTEM, user=user, schema=PHRASE_SCHEMA, label="phrase")
    except LLMError:
        t = template_check(result, spec)
        return t
    speech = str(data.get("speech", "")).strip()
    answer = str(data.get("answer", "")).strip() or speech
    if not speech or len(speech.split()) > 40 or not numbers_ok(speech, facts):
        t = template_check(result, spec)
        t.ms = ms
        return t
    return Phrased(speech, answer, "claude", ms)


def template_error(result: CheckResult) -> Phrased:
    err = result.error or "no_data"
    if err == "no_such_check":
        s = "I don't have a check for that yet."
    elif err == "no_data":
        s = "I didn't track the ball well enough there to say."
    elif err == "timeout":
        s = "The check didn't come back in time."
    else:
        s = "That check failed, so I can't say."
    return Phrased(s, s, "template")


async def phrase_explain(llm: JSONCompleter | None, question: str, call: dict[str, Any]) -> Phrased:
    facts = {
        "called": call.get("text"),
        "outcome": str(call.get("outcome", "")).replace("_", " "),
        "rule": call.get("rule_id"),
        "reason": call.get("why"),
        "confidence_percent": fmt_num(100 * float(call["p"]), 0) if isinstance(call.get("p"), int | float) else None,
        "tier": call.get("tier"),
        "status": call.get("status"),
        "question": question,
    }
    fallback_speech = ". ".join(s for s in (str(call.get("text") or ""), str(call.get("why") or "")) if s).strip()
    fallback = Phrased(fallback_speech or "I have no call to explain.", fallback_speech, "template")
    if llm is None:
        return fallback
    try:
        data, ms = await llm.complete(
            system=EXPLAIN_SYSTEM, user="Call facts (JSON): " + _json(facts), schema=PHRASE_SCHEMA, label="explain"
        )
    except LLMError:
        return fallback
    speech = str(data.get("speech", "")).strip()
    if not speech or len(speech.split()) > 40 or not numbers_ok(speech, facts):
        fallback.ms = ms
        return fallback
    return Phrased(speech, str(data.get("answer") or speech).strip(), "claude", ms)


def score_line(ctx: dict[str, Any]) -> Phrased:
    """Deterministic: the score and the server from the game context the phone sent."""
    scores = ctx.get("scores") or []
    teams = {t.get("team_id"): t.get("name") or t.get("team_id") for t in (ctx.get("teams") or [])}
    if not scores:
        s = "I don't have a score yet."
        return Phrased(s, s, "template")
    ordered = sorted(scores, key=lambda s: str(s.get("team_id")))
    pts = [f"{teams.get(s.get('team_id'), s.get('team_id'))} {s.get('points', 0)}" for s in ordered]
    speech = ", ".join(pts) + "."
    if len(ordered) == 2:
        a, b = ordered
        if a.get("points", 0) != b.get("points", 0):
            lead = a if a.get("points", 0) > b.get("points", 0) else b
            low = min(a.get("points", 0), b.get("points", 0))
            speech = f"{lead.get('points')} to {low}, {teams.get(lead.get('team_id'), lead.get('team_id'))} leads."
        else:
            speech = f"{a.get('points', 0)} all."
    srv = ctx.get("server_team_id")
    if srv:
        speech += f" {teams.get(srv, srv)} to serve."
    return Phrased(speech, speech, "template")


def _json(o: Any) -> str:
    import json

    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))
