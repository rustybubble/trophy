"""Grounding: a generated tip may only state facts present in the stats it was given.

Adapted from Replay's `services/api/replay_api/narrate/grounding.py` (subatomic-hamster/replay
@ 2db92c0, MIT; Copyright (c) 2026 Replay). Replay grounds play-by-play lines against game
events; here the facts are a stats table, so the check keeps Replay's number, name and
invented-fact rules and drops the action/direction/score-state rules:

- numbers: every digit string, number word or ordinal in the tip must be a number in the
  stats (a "60%" and a "0.6" count as 60 and 0.6; "Player 2" labels are blanked first);
- names: every capitalised word must be a side, a player, a stat word or ordinary English;
- invented facts: injuries, coaches, careers, seasons, records, streaks, referees, and
  gendered pronouns (the stats carry no gender) are rejected.

The check is deliberately conservative: a false rejection only costs Claude's phrasing (a
template tip is used instead); a false acceptance would put an invented fact on the screen.
"""

from __future__ import annotations

import re
from typing import Any

UNITS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
]  # fmt: skip
NUM_WORDS = {w: i for i, w in enumerate(UNITS)}
TENS = {
    w: 10 * (i + 2)
    for i, w in enumerate(["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"])
}
TENS["hundred"] = 100
OTHER_NUMS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "once": 1, "twice": 2, "double": 2}
OTHER_NUMS |= {"triple": 3, "pair": 2, "couple": 2, "dozen": 12, "half": 0.5}

INVENTED = re.compile(
    r"\b(?:injur\w*|coach\w*|referee\w*|career\w*|season\w*|record\w*|streak\w*|mvp|veteran|rookie"
    r"|last (?:week|game|time|match)|yesterday|tomorrow|crowd|fans|timeouts?|overtime|halftime"
    r"|dunk\w*|lay-?ups?|free throws?|buzzer\w*|knees?|wrists?|footwork|stance|posture)\b",
    re.I,
)
GENDERED = re.compile(r"\b(?:he|him|his|himself|she|her|hers|herself|guy|girl|man|woman)\b", re.I)

# capitalised words that are ordinary English (sentence starts, coaching imperatives), not names
COMMON_WORDS = """
    the a an and but or so then now what that this these those it its there here with from off on in into to for of
    by after before as at no not yes another over up down out back just still both all every each score point points
    team player players possession ball serve serves serving shot shots rally rallies pass passes steal turnover
    look watch play who will can nobody everyone side their they them we our you your i my me well ok okay right
    sure next later early how why where when since while if once best most more less fewer only also too very really
    quite much many few some any none made makes missed misses shooting passing scoring efficient efficiency
    distance total overall strong solid keep try focus consider work worth plenty stay cover move get take use push
    aim practice hold find build trust attack defend drive shoot finish go let make you're you've you'll we're let's
    are is was were be been being do does did have has had should could would may might must against per between
    during about above below under across good great nice big small long short fast slow high low late same
    different average rate ratio percent percentage faults fault edge edges net outs receive receiving received won
    lost wins loss losses games game set sets
"""
COMMON = frozenset(COMMON_WORDS.split())  # noqa: SIM905 (a word list reads better as prose)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’]*")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*%?\s*", v)
        if m:
            return float(m.group(1))
    return None


def build_facts(stats: dict[str, Any], *, side: str, sides: list[str] | None = None) -> dict[str, Any]:
    """The facts a tip may state: the numbers in the stats (every number in a value, plus
    numbers inside string values such as a score "11-7") and the words a tip may capitalise."""
    numbers: set[float] = set()
    words: set[str] = set()
    for k, v in stats.items():
        words.update(t.lower() for t in _TOKEN.findall(k.replace("_", " ")))
        n = _as_number(v)
        if n is not None:
            numbers.add(n)
            if isinstance(v, str) and v.strip().endswith("%"):
                numbers.add(round(n / 100, 4))
            elif 0 < n < 1:
                numbers.add(round(n * 100, 4))
        elif isinstance(v, str):
            numbers.update(float(x.replace(",", "")) for x in _NUM.findall(v))
            words.update(t.lower() for t in _TOKEN.findall(v))
    labels = [side, *(sides or [])]
    for lab in labels:
        words.update(t.lower() for t in _TOKEN.findall(lab))
    return {"side": side, "sides": sorted(set(labels)), "numbers": sorted(numbers), "words": sorted(words)}


def numbers_in(text: str) -> list[float]:
    low = text.lower()
    found = [float(n.replace(",", "")) for n in _NUM.findall(low)]
    toks = re.findall(r"[a-z]+", low)
    i = 0
    while i < len(toks):
        w = toks[i]
        if w in TENS:
            val = TENS[w]
            if i + 1 < len(toks) and toks[i + 1] in NUM_WORDS and 0 < NUM_WORDS[toks[i + 1]] < 10:
                val += NUM_WORDS[toks[i + 1]]
                i += 1
            found.append(float(val))
        elif w in NUM_WORDS:
            found.append(float(NUM_WORDS[w]))
        elif w in OTHER_NUMS:
            found.append(float(OTHER_NUMS[w]))
        i += 1
    return found


def _blank_labels(text: str, labels: list[str]) -> str:
    for lab in sorted(labels, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(lab)}(?!\w)", " _ ", text)
    return text


def check(text: str, facts: dict[str, Any]) -> dict[str, Any]:
    """`{"ok": bool, "violations": [{"kind", "detail"}]}` for one tip."""
    out: list[dict[str, str]] = []
    if not text.strip():
        out.append({"kind": "empty", "detail": "no text"})
    rest = _blank_labels(text.replace("’", "'"), facts["sides"])
    numbers = {float(n) for n in facts["numbers"]}
    words = set(facts["words"])
    known = COMMON | words | set(NUM_WORDS) | set(TENS) | set(OTHER_NUMS)
    for n in numbers_in(rest):
        if n not in numbers:
            out.append({"kind": "absent_number", "detail": f"{n:g}"})
    for tok in _TOKEN.findall(rest):
        if tok[0].isupper() and re.sub(r"'s?$", "", tok.lower()) not in known:
            out.append({"kind": "unknown_name", "detail": tok})
    for m in INVENTED.finditer(rest):
        out.append({"kind": "invented_fact", "detail": m.group(0)})
    for m in GENDERED.finditer(rest):
        out.append({"kind": "invented_attribute", "detail": m.group(0)})
    return {"ok": not out, "violations": out}
