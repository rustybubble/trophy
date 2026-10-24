"""`rule_ref` resolution: "ITTF 2.6.2" -> the indexed clause `ittf:2.6.2` (exact), else a search on the rule text."""

from __future__ import annotations

import re

from .ask import clip_words
from .models import RuleRefOut
from .search import RuleStore

ALIASES = {
    "ittf": "ittf",
    "tte": "ittf",
    "usap": "usap",
    "usapickleball": "usap",
    "usapa": "usap",
    "fiba": "fiba",
    "bwf": "bwf",
    "fivb": "fivb",
}
_REF = re.compile(r"^\s*(?P<src>[A-Za-z][A-Za-z .]*?)\s*(?P<num>\d+(?:\.\w+)+)\s*$")
_ID = re.compile(r"^[a-z0-9_-]+:\S+$")


def parse_rule_ref(ref: str) -> str | None:
    """'ITTF 2.6.2' -> 'ittf:2.6.2'; 'ittf:2.6.2' passes through; None when it isn't a clause reference."""
    ref = ref.strip()
    if _ID.match(ref):
        return ref
    m = _REF.match(ref)
    if not m:
        return None
    src = re.sub(r"[^a-z]", "", m.group("src").lower())
    return f"{ALIASES.get(src, src)}:{m.group('num')}"


def _out(h, score: float, how: str) -> RuleRefOut:
    return RuleRefOut(rule_id=h.rule_id, title=h.title, url=h.url, quote=clip_words(h.text), score=score, how=how)


async def resolve(
    store: RuleStore,
    *,
    sport: str,
    rule_ref: str | None = None,
    rule_id: str | None = None,
    text: str | None = None,
    min_score: float,
) -> RuleRefOut | None:
    ids = [i for i in (rule_id, parse_rule_ref(rule_ref) if rule_ref else None) if i]
    if ids:
        hits = await store.get_by_ids(ids, sport=sport)
        if hits:
            return _out(hits[0], 1.0, "exact")
    if text:
        hits, _ = await store.search(sport, text, 1, alpha=0.5)
        if hits and hits[0].score >= min_score:
            return _out(hits[0], hits[0].score, "search")
    return None
