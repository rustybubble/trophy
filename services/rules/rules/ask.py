"""Ask the ref: Moss top-k -> Claude answers only from those clauses, with citations (interfaces-v1 §17)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from .llm import ClaudeJSON
from .search import RuleHit

NOT_FOUND = "I couldn't find that rule."
MAX_QUOTE_WORDS = 25

ASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "true only if the clauses answer the question"},
        "answer": {
            "type": "string",
            "description": "<= 3 sentences, cites rule ids like (2.6.2); empty when not found",
        },
        "speech": {"type": "string", "description": "the same answer as plain speech: no rule ids, no markdown"},
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
    "You are the referee's rulebook assistant for a pickup game. Answer ONLY from the rule clauses provided; "
    "never use outside knowledge. If the clauses do not answer the question, set found=false and leave answer "
    "empty. Otherwise answer in at most 3 short sentences, cite the rule ids you relied on in parentheses, and "
    "give `speech`, the same answer phrased for text-to-speech with no rule ids, markdown or symbols. "
    "Each citation quote must be copied verbatim from the clause (at most 25 words)."
)


class Citation(BaseModel):
    rule_id: str
    title: str
    url: str
    quote: str


class AskResult(BaseModel):
    answer: str
    speech: str
    citations: list[Citation]
    found: bool
    claude_ms: float


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def clip_words(s: str, n: int = MAX_QUOTE_WORDS) -> str:
    words = s.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def verified_quote(quote: str, clause: str) -> str:
    """The quote, clipped to 25 words, if it occurs in the clause; else the clause's first 25 words."""
    q = clip_words(quote).rstrip("…").strip()
    if q and _norm(q) in _norm(clause):
        return clip_words(q)
    return clip_words(clause)


def clauses_block(hits: list[RuleHit]) -> str:
    return "\n\n".join(f"[{h.rule_id}] {h.title}\n{h.text}" for h in hits)


def not_found(claude_ms: float = 0.0) -> AskResult:
    return AskResult(answer=NOT_FOUND, speech=NOT_FOUND, citations=[], found=False, claude_ms=claude_ms)


async def answer(llm: ClaudeJSON, question: str, sport: str, hits: list[RuleHit]) -> AskResult:
    user = f"Sport: {sport}\nQuestion: {question}\n\nRule clauses:\n{clauses_block(hits)}"
    data, ms = await llm.complete(system=SYSTEM, user=user, schema=ASK_SCHEMA, label="ask")
    if not data.get("found") or not data.get("answer", "").strip():
        return not_found(ms)
    by_id = {h.rule_id: h for h in hits}
    cites: list[Citation] = []
    for c in data.get("citations", []):
        h = by_id.get(c.get("rule_id", ""))
        if h is None or any(x.rule_id == h.rule_id for x in cites):
            continue  # a citation to a clause we did not retrieve is dropped, never invented
        cites.append(
            Citation(rule_id=h.rule_id, title=h.title, url=h.url, quote=verified_quote(c.get("quote", ""), h.text))
        )
    if not cites:
        return not_found(ms)
    speech = re.sub(r"\s*\(?\b\d+(?:\.\w+)+\)?", "", data.get("speech") or data["answer"]).strip() or data["answer"]
    return AskResult(answer=data["answer"].strip(), speech=speech, citations=cites, found=True, claude_ms=ms)
