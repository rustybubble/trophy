"""Ask the ref: Moss top-k -> Claude answers only from those clauses -> a server-side grounding gate (§17, brief §2.3).

The gate is not a fallback: a citation survives only if its rule id was retrieved and its quote is a verbatim
(whitespace-normalised) substring of that clause, at most 25 words. An answer with no surviving citation is
returned as "couldn't find", never rewritten.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Citation, RuleHit

MAX_QUOTE_WORDS = 25
SOURCE_NAMES = {"ittf": "ITTF", "usap": "USA Pickleball", "fiba": "FIBA", "bwf": "BWF", "fivb": "FIVB"}

ASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "true only if the clauses answer the question"},
        "answer": {
            "type": "string",
            "description": "at most 3 short sentences, citing clause ids in square brackets like [ittf:2.6.2]; "
            "empty when found is false",
        },
        "speech": {
            "type": "string",
            "description": "the answer as it should be spoken aloud: at most 2 sentences, no ids, no markdown; "
            "read numbers naturally (law two point six two, sixteen centimetres)",
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string", "description": "one of the provided clause ids, exactly"},
                    "quote": {
                        "type": "string",
                        "description": "a passage copied verbatim from that clause, at most 25 words",
                    },
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
    "You are Trophy, the referee's rulebook assistant for a pickup game. You answer ONLY from the official rule "
    "clauses provided in the message; you never use outside knowledge, never guess and never add conditions the "
    "clauses do not state. If the clauses do not answer the question, set found=false and leave answer and "
    "citations empty. Otherwise: `answer` is at most 3 short sentences for a screen, citing the clause ids you "
    "relied on in square brackets, e.g. [ittf:2.6.2]; `speech` is the same answer for text-to-speech, at most 2 "
    "sentences, with no ids, no symbols and numbers read naturally ('at least sixteen centimetres', 'law two point "
    "six two'); every citation's `quote` is copied verbatim from that clause and is at most 25 words. Quote the "
    "words that answer the question, not the whole clause."
)


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def clip_words(s: str, n: int = MAX_QUOTE_WORDS) -> str:
    words = s.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def verify_quote(quote: str, clause: str) -> str | None:
    """The clause's own text for the quoted span, or None when the quote isn't in the clause or is > 25 words."""
    q, c = _norm(quote).strip(" .,;:\"'"), _norm(clause)
    if not q or len(q.split()) > MAX_QUOTE_WORDS:
        return None
    i = c.lower().find(q.lower())
    return c[i : i + len(q)] if i >= 0 else None


def verify_citations(raw: list[dict[str, Any]], hits: list[RuleHit]) -> tuple[list[Citation], list[dict[str, str]]]:
    """-> (surviving citations in order, dropped [{rule_id, why}])."""
    by_id = {h.rule_id: h for h in hits}
    out: list[Citation] = []
    dropped: list[dict[str, str]] = []
    for c in raw:
        rid, quote = str(c.get("rule_id", "")).strip(), str(c.get("quote", ""))
        h = by_id.get(rid)
        if h is None:
            dropped.append({"rule_id": rid, "why": "not retrieved"})
            continue
        if any(x.rule_id == rid for x in out):
            continue
        verified = verify_quote(quote, h.text)
        if verified is None:
            dropped.append({"rule_id": rid, "why": "quote not verbatim or > 25 words"})
            continue
        out.append(Citation(rule_id=rid, title=h.title, url=h.url, quote=verified))
    return out, dropped


def source_name(hits: list[RuleHit], sport: str) -> str:
    slug = hits[0].rule_id.split(":", 1)[0] if hits and ":" in hits[0].rule_id else ""
    return SOURCE_NAMES.get(slug, sport.replace("_", " "))


def not_found_text(hits: list[RuleHit], sport: str) -> str:
    return f"I couldn't find that rule in the {source_name(hits, sport)} laws."


def clauses_block(hits: list[RuleHit]) -> str:
    return "\n\n".join(f"[{h.rule_id}] {h.title}\n{h.text}" for h in hits)


def user_message(question: str, sport: str, hits: list[RuleHit]) -> str:
    return f"Sport: {sport.replace('_', ' ')}\nQuestion: {question}\n\nOfficial clauses:\n{clauses_block(hits)}"


def strip_ids(speech: str) -> str:
    """Belt and braces: no clause ids or brackets reach the speech synthesiser."""
    s = re.sub(r"\[[^\]]*\]", "", speech)
    s = re.sub(r"\b[a-z]{2,6}:\d+(?:\.\w+)+\b", "", s)
    return re.sub(r"\s+", " ", s).strip()
