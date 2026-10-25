"""General rules questions, answered only from this game's rule pack (the sport's rules.yaml plus approved house rules).

D-31 dropped Moss and the Apify rulebook index, so the grounding corpus is the pack the engine is actually enforcing.
Claude cites rule ids it was given; a citation to anything else is dropped, and a weak answer becomes
"I couldn't find that in this game's rule pack."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .llm import JSONCompleter, LLMError

NOT_FOUND = "I couldn't find that in this game's rule pack."
MAX_QUOTE_WORDS = 25


@dataclass
class Clause:
    rule_id: str
    title: str
    text: str
    ref: str = ""


@dataclass
class RuleAnswer:
    answer: str
    speech: str
    citations: list[dict[str, str]] = field(default_factory=list)
    found: bool = False
    ms: float = 0.0


ASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "true only if the clauses answer the question"},
        "answer": {
            "type": "string",
            "description": "<= 3 sentences, cites rule ids in parentheses; empty if not found",
        },
        "speech": {
            "type": "string",
            "description": "the same answer as plain speech: no ids, no markdown, <= 35 words",
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "quote": {"type": "string", "description": "<= 25 words copied verbatim from that clause"},
                },
                "required": ["rule_id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["found", "answer", "speech", "citations"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are Trophy, the referee at a pickup game, answering a rules question. Answer ONLY from the rule-pack clauses "
    "provided (they are what this game enforces, including any house rules); never use outside knowledge. If the "
    "clauses do not answer the question, set found=false and leave answer empty. Otherwise answer in at most 3 short "
    "sentences, cite the rule ids you relied on in parentheses, and give `speech`: the same answer for text-to-speech "
    "with no ids, markdown or symbols. Each citation quote must be copied verbatim from the clause (at most 25 words)."
)


def load_pack(sports_dir: Path, sport: str) -> dict[str, Any]:
    p = sports_dir / sport / "rules.yaml"
    if not p.exists():
        raise FileNotFoundError(f"no rule pack at {p}")
    with p.open("r", encoding="utf8") as f:
        return yaml.safe_load(f) or {}


def clauses_from_pack(pack: dict[str, Any], house_rules: list[dict[str, Any]] | None = None) -> list[Clause]:
    out: list[Clause] = []
    sp = (pack.get("scoring") or {}).get("params") or {}
    if sp:
        text = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sp.items())
        out.append(Clause("scoring", "Scoring", f"Scoring: {text}.", "pack"))
    params = pack.get("params") or {}
    if params:
        text = "; ".join(f"{k.replace('_', ' ')} = {v}" for k, v in params.items() if not isinstance(v, dict))
        out.append(Clause("params", "Pack parameters", text, "pack"))
    for r in pack.get("rules") or []:
        rid = str(r.get("id", ""))
        if not rid:
            continue
        bits = [str(r.get("text") or r.get("name") or rid)]
        if r.get("outcome"):
            bits.append(f"Outcome: {str(r['outcome']).replace('_', ' ')}.")
        if r.get("when"):
            bits.append(f"Condition: {r['when']}.")
        if r.get("tier"):
            bits.append(f"Tier: {r['tier']}.")
        out.append(Clause(rid, str(r.get("name") or rid), " ".join(bits), str(r.get("rule_ref") or "")))
    for i, h in enumerate(house_rules or []):
        if str(h.get("status", "approved")) not in ("approved", "ready"):
            continue
        out.append(Clause(f"house_rule_{i + 1}", "House rule", str(h.get("text", "")), "house"))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def clip_words(s: str, n: int = MAX_QUOTE_WORDS) -> str:
    w = s.split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def verified_quote(quote: str, clause: str) -> str:
    q = clip_words(quote).rstrip("…").strip()
    if q and _norm(q) in _norm(clause):
        return clip_words(q)
    return clip_words(clause)


def clauses_block(cl: list[Clause]) -> str:
    return "\n\n".join(f"[{c.rule_id}] {c.title}{(' (' + c.ref + ')') if c.ref else ''}\n{c.text}" for c in cl)


async def answer_rules(llm: JSONCompleter, question: str, sport: str, clauses: list[Clause]) -> RuleAnswer:
    if not clauses:
        return RuleAnswer(NOT_FOUND, NOT_FOUND)
    user = f"Sport: {sport}\nQuestion: {question}\n\nRule-pack clauses:\n{clauses_block(clauses)}"
    try:
        data, ms = await llm.complete(system=SYSTEM, user=user, schema=ASK_SCHEMA, label="rules")
    except LLMError:
        s = "I couldn't reach the rulebook just now."
        return RuleAnswer(s, s)
    if not data.get("found") or not str(data.get("answer", "")).strip():
        return RuleAnswer(NOT_FOUND, NOT_FOUND, ms=ms)
    by_id = {c.rule_id: c for c in clauses}
    cites: list[dict[str, str]] = []
    for c in data.get("citations") or []:
        h = by_id.get(str(c.get("rule_id", "")))
        if h is None or any(x["rule_id"] == h.rule_id for x in cites):
            continue
        title = h.title + (f" ({h.ref})" if h.ref and h.ref not in ("pack", "house") else "")
        cites.append(
            {"rule_id": h.rule_id, "title": title, "url": "", "quote": verified_quote(str(c.get("quote", "")), h.text)}
        )
    if not cites:
        return RuleAnswer(NOT_FOUND, NOT_FOUND, ms=ms)
    speech = re.sub(r"\s*\(?\b[a-z_]*\d*(?:\.\w+)+\)?", "", str(data.get("speech") or data["answer"])).strip()
    return RuleAnswer(str(data["answer"]).strip(), speech or str(data["answer"]).strip(), cites, True, ms)
