"""Question -> check(s): deterministic keyword rules, no LLM. The router resolves *when* (which rally, which bounce)
by reading the store's segments and, where needed, running `bounces` / `contacts` over that rally, then names the
check the service must run and the facts Claude is allowed to phrase. Unknown questions return None."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..checks.api import Track
from .store import TrackStore


@dataclass(frozen=True)
class CheckCall:
    name: str
    kwargs: dict[str, Any]


@dataclass
class Query:
    intent: str  # in_out | serve_toss | net_touch | bounces | rally_summary | score | server
    checks: list[CheckCall]  # in order; empty for questions answered from facts alone
    facts: dict[str, Any] = field(default_factory=dict)
    scope: str = ""
    rally_no: int | None = None

    @property
    def check(self) -> str | None:
        return self.checks[0].name if self.checks else None


WORD = {
    "score": r"\b(score|points?|leading|winning|ahead|behind)\b",
    "server": r"\b(whose|who'?s|who is|who)\b.*\b(serv(e|es|ing)|turn)\b|\bserving\b",
    "net": r"\b(net|let|cord|clip(ped)?|tip(ped)?)\b",
    "double": r"\b(double|twice|two|2|how many)\b.*\bbounc\w*|\bbounc\w*\b.*\b(twice|two|2)\b",
    "stats": r"\b(how long|how many (shots|hits|strokes)|shots|strokes|fastest|how fast|speed|hardest|longest)\b",
    "serve": r"\b(serve[sd]?|service|toss(ed)?|throw|palm|vertical|high enough|6 in(ch(es)?)?)\b",
    "legal": r"\b(legal|illegal|fault|valid|ok|okay|good|fine|high|low|angle|straight)\b",
    "inout": r"\b(out|in|landed|land|bounce[sd]?|edge|lines?|long|wide|inside|outside|miss(ed)?|table|hit)\b",
    "previous": r"\b(previous|prior|before|earlier|last) (rally|point|one)\b|\b(rally|point) before\b",
    "first": r"\b(first|1st|opening)\b",
    "second": r"\b(second|2nd)\b",
    "third": r"\b(third|3rd)\b",
    "lastb": r"\b(last|final|latest) bounce\b",
    "serve_bounce": r"\bserve\b",
    "rally_n": r"\b(rally|point) (number )?(\d+)\b",
}
_RE = {k: re.compile(v) for k, v in WORD.items()}


def _norm(q: str) -> str:
    q = q.lower().replace("’", "'")
    q = re.sub(r"[^a-z0-9' ]+", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _rally_for(q: str, segs: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int | None]:
    """(segment, rally_no) the question refers to; the whole track when the engine has not set segments."""
    m = _RE["rally_n"].search(q)
    if m:
        n = int(m.group(3))
        return next((s for s in segs if int(s.get("rally_no", -1)) == n), None), n
    if not segs:
        return None, None
    idx = -2 if _RE["previous"].search(q) and len(segs) >= 2 else -1
    seg = segs[idx]
    return seg, int(seg.get("rally_no", len(segs) + idx + 1))


def _window(seg: dict[str, Any] | None, track: Track) -> tuple[float, float]:
    if seg is None:
        return track.t0, track.t1
    t0 = float(seg["t_start_s"])
    t1 = seg.get("t_end_s")
    return t0, (float(t1) if t1 is not None else track.t1)


def _rally_label(rally_no: int | None) -> str:
    return f"rally {rally_no}" if rally_no is not None else "the whole track"


def _pick_bounce(
    q: str, bounces: list[dict[str, Any]], serve_contact_t: float | None
) -> tuple[dict[str, Any] | None, str]:
    """Which bounce the question means: 'first/second/third bounce', 'the serve' (first bounce after the serve hit),
    'last bounce' or, by default, the latest one."""
    if not bounces:
        return None, "no bounce"
    if _RE["serve_bounce"].search(q):
        after = [b for b in bounces if serve_contact_t is None or float(b["t_s"]) >= serve_contact_t]
        return (after[0], "the serve's first bounce") if after else (None, "no bounce after the serve")
    for word, i in (("first", 0), ("second", 1), ("third", 2)):
        if _RE[word].search(q):
            return (bounces[i], f"bounce {i + 1}") if i < len(bounces) else (None, f"no bounce {i + 1}")
    return bounces[-1], "the last bounce"


def _bounces(store: TrackStore, track: Track, t0: float, t1: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    res = store.library.run("bounces", track, store.field, None, t0=t0, t1=t1)
    return list(res["verdict"]), res


def route(question: str, store: TrackStore) -> Query | None:
    """Map a judge's question to the check(s) that answer it over the stored track. None when nothing matches."""
    q = _norm(question)
    if not q or store.field is None:
        return None
    snap = store.snapshot()
    track: Track = snap["track"]
    if len(track) == 0:
        return None
    seg, rally_no = _rally_for(q, snap["segments"])
    t0, t1 = _window(seg, track)
    label = _rally_label(rally_no)
    base: dict[str, Any] = {"rally_no": rally_no, "t_start_s": round(t0, 3), "t_end_s": round(t1, 3)}
    if seg and seg.get("server_side"):
        base["server_side"] = seg["server_side"]

    # score / who serves: game state, not geometry
    if _RE["score"].search(q) and not _RE["inout"].search(q.replace("points", "").replace("point", "")):
        facts = {**base, "score": snap["score"] or None, "recent_calls": snap["recent_calls"][-3:]}
        return Query("score", [], facts, scope=f"{label}, game state", rally_no=rally_no)
    if _RE["server"].search(q):
        facts = {**base, "score": snap["score"] or None, "recent_calls": snap["recent_calls"][-3:]}
        return Query(
            "server", [], facts, scope=f"{label}, server {base.get('server_side', 'unknown')}", rally_no=rally_no
        )

    if _RE["net"].search(q):
        return Query(
            "net_touch",
            [CheckCall("net_touch", {"t0": t0, "t1": t1})],
            {**base, "question_about": "whether the ball touched or went into the net"},
            scope=f"{label} ({t0:.1f}-{t1:.1f} s)",
            rally_no=rally_no,
        )

    if _RE["double"].search(q):
        return Query(
            "bounces",
            [CheckCall("bounces", {"t0": t0, "t1": t1})],
            {**base, "question_about": "how many times, and on which side, the ball bounced on the table"},
            scope=f"{label} ({t0:.1f}-{t1:.1f} s)",
            rally_no=rally_no,
        )

    if _RE["stats"].search(q):
        return Query(
            "rally_summary",
            [CheckCall("rally_summary", {"t0": t0, "t1": t1}), CheckCall("contacts", {"t0": t0, "t1": t1})],
            {**base, "question_about": "rally length, shot count (the contacts) and peak ball speed"},
            scope=f"{label} ({t0:.1f}-{t1:.1f} s)",
            rally_no=rally_no,
        )

    serve_words = bool(_RE["serve"].search(q))
    inout_words = bool(_RE["inout"].search(q))
    if serve_words and (not inout_words or _RE["legal"].search(q)):
        return Query(
            "serve_toss",
            [CheckCall("serve_toss", {"t_start": t0})],
            {
                **base,
                "question_about": "whether the serve toss was legal: at least 15.24 cm up, within 30 deg of vertical",
            },
            scope=f"{label}, serve at {t0:.1f} s",
            rally_no=rally_no,
        )

    if inout_words:
        bounces, _ = _bounces(store, track, t0, t1)
        table = [b for b in bounces if b.get("surface") in ("table", "side_face")]
        serve_t = None
        if _RE["serve_bounce"].search(q):
            # the serve hit from `serve_toss` (its contact); without one, the rally's first bounce is the serve's
            sv = store.library.run("serve_toss", track, store.field, None, t_start=t0)
            if sv["verdict"] != "no_serve":
                serve_t = float(sv["evidence"]["contact"]["t_s"]) - 0.05
        b, which = _pick_bounce(q, table, serve_t)
        t_s = float(b["t_s"]) if b else t1
        facts = {
            **base,
            "bounce": which,
            "n_table_bounces": len(table),
            "question_about": "whether that bounce was in or out",
        }
        if b:
            facts["bounce_side"] = b.get("side")
        return Query(
            "in_out",
            [CheckCall("in_out", {"t_s": t_s})],
            facts,
            scope=f"{label}, {which} at {t_s:.1f} s",
            rally_no=rally_no,
        )
    return None
