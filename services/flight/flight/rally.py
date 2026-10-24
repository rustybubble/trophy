"""Rally events and point outcomes from a side-view ball track + table geometry (fixes EVT-1).

Measurements (perception): bounces (vertical reversal at table height over the table, horizontal direction kept),
hits (horizontal reversal), ball dead (lost for good, or dropped below the table outside it). Each carries the side
(A = left of the net as filmed, B = right) and a heuristic confidence.

Decision (kept separate, as rule packs do in the engine, D-18): `referee()` applies the basic table-tennis point
rules to a rally's event sequence - service bounces once on each side, each return must bounce once on the far side,
no volleys, no second bounce, a ball that dies after a hit that didn't land on the far side loses the point for the
hitter. Anything ambiguous is returned as undecided with the reason, never guessed.
Units: working-image pixels (1280x720) and seconds. Side-on camera at the net line assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .table import Table

FPS = 60.0  # velocity thresholds are per 1/60 s; times come from each row's t (seconds)
MIN_GAP_S = 1.2  # a rally ends when the ball is unseen this long
BOUNCE_BAND_PX = 18  # vertical tolerance around the table surface band
END_MARGIN_PX = 12
SMOOTH_K, SMOOTH_K_LOW = 3, 1
# position smoothing (samples) at 60 fps / at lower frame rates


@dataclass
class Ev:
    kind: str  # "bounce" | "hit" | "dead"
    t: float
    seq: int
    x: float
    y: float
    side: str  # "A" | "B"
    conf: float
    why: str = ""


@dataclass
class Rally:
    no: int
    t_start: float
    t_end: float
    events: list[Ev] = field(default_factory=list)
    winner: str | None = None
    reason: str = ""
    confidence: float = 0.0


def _smooth(v: np.ndarray, k: int = 3) -> np.ndarray:
    if len(v) < k:
        return v
    pad = np.pad(v, (k // 2, k // 2), mode="edge")
    return np.convolve(pad, np.ones(k) / k, mode="valid")


def segments(rows: list[dict]) -> list[list[dict]]:
    """Runs of the same track with observed points, as lists of rows (in time order)."""
    out: list[list[dict]] = []
    cur: list[dict] = []
    for r in rows:
        if r["state"] != "observed":
            continue
        if cur and (r["track_id"] != cur[-1]["track_id"] or r["t"] - cur[-1]["t"] > 10 / FPS):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return [s for s in out if len(s) >= 6]


def events_for(seg: list[dict], table_at, fps: float = FPS) -> list[Ev]:
    """Bounces and hits along one continuous track segment. `table_at(seq)` gives the Table for that frame; `fps` is
    the stream's frame rate."""
    seq = np.array([r["seq"] for r in seg], float)
    tt = np.array([r["t"] for r in seg], float)
    # velocity windows before / after a candidate, tuned at 60 fps (2 samples). Hits keep that span in time (1 sample
    # at 30 fps); bounces keep >= 2 samples, since at 30 fps one sample often straddles the bounce and reads ~0.
    n_hit = max(1, round(2 * fps / FPS))
    n = max(2, n_hit)
    x = _smooth(np.array([r["x"] for r in seg], float), SMOOTH_K if fps >= 45 else SMOOTH_K_LOW)
    y = _smooth(np.array([r["y"] for r in seg], float), SMOOTH_K if fps >= 45 else SMOOTH_K_LOW)
    dt = np.diff(tt) * FPS  # velocities in px per 1/60 s, whatever the stream's frame rate
    vx = np.diff(x) / dt
    vy = np.diff(y) / dt
    evs: list[Ev] = []
    i = n
    while i < len(vx) - n:
        hit_bx, hit_ax = vx[i - n_hit : i].mean(), vx[i : i + n_hit].mean()
        before_x, after_x = vx[i - n : i].mean(), vx[i : i + n].mean()
        before_y, after_y = vy[i - n : i].mean(), vy[i : i + n].mean()
        s = int(seq[i])
        tb: Table | None = table_at(s)
        px, py = float(x[i]), float(y[i])
        # hit: horizontal reversal at decent speed
        if np.sign(hit_bx) != np.sign(hit_ax) and min(abs(hit_bx), abs(hit_ax)) > 1.5:
            side = tb.side(px) if tb else ("A" if hit_bx < 0 else "B")
            conf = min(1.0, min(abs(hit_bx), abs(hit_ax)) / 6)
            evs.append(Ev("hit", float(tt[i]), s, px, py, side, round(conf, 2)))
            i += 2 * n_hit
            continue
        # bounce: falling then rising, horizontal direction kept, at the table surface, over the table
        if before_y > 1.0 and after_y < -1.0 and np.sign(before_x) == np.sign(after_x) and tb is not None:
            top = tb.top_y(px)
            on_band = top - BOUNCE_BAND_PX <= py <= top + tb.thickness + BOUNCE_BAND_PX
            if on_band and tb.over(px, END_MARGIN_PX):
                dist_net = abs(px - tb.net_x)
                conf = min(1.0, (before_y - after_y) / 8) * (0.6 if dist_net < 15 else 1.0)
                evs.append(Ev("bounce", float(tt[i]), s, px, py, tb.side(px), round(conf, 2)))
                i += 2 * n_hit
                continue
        i += 1
    return evs


def live_runs(seg: list[dict], table_at) -> list[tuple[list[dict], bool]]:
    """Split a track segment into in-play runs. A run ends "dead" once the ball is clearly below table level
    (3 frames in a row) - on the floor or under the table; afterwards the ball (picked up, bounced around) is
    ignored until it is next seen above the table (the next serve toss). Returns (points, ended_dead)."""
    runs: list[tuple[list[dict], bool]] = []
    cur: list[dict] = []
    below = 0
    idle = False
    for r in seg:
        tb = table_at(r["seq"])
        if tb is None:
            if not idle:
                cur.append(r)
            continue
        top = tb.top_y(r["x"])
        if idle:
            if r["y"] < top - 20:
                idle = False
                cur = [r]
            continue
        cur.append(r)
        below = below + 1 if r["y"] > top + tb.thickness * 2.0 else 0
        if below >= 3:
            runs.append((cur[:-2], True))
            cur, below, idle = [], 0, True
    if cur and not idle:
        runs.append((cur, False))
    return [(run, dead) for run, dead in runs if len(run) >= 6]


def build_rallies(rows: list[dict], table_at) -> list[Rally]:
    ts = np.array([r["t"] for r in rows], float)
    fps = 1.0 / float(np.median(np.diff(ts))) if len(ts) > 1 else FPS  # every row is one frame, seen or not
    rallies: list[Rally] = []
    closed = True
    for sg in segments(rows):
        for run, dead in live_runs(sg, table_at):
            evs = events_for(run, table_at, fps)
            t0, t1 = run[0]["t"], run[-1]["t"]
            if rallies and not closed and t0 - rallies[-1].t_end <= MIN_GAP_S:
                r = rallies[-1]
                r.events = [e for e in r.events if e.kind != "dead"]
            else:
                r = Rally(len(rallies) + 1, t0, t1)
                rallies.append(r)
            r.events.extend(evs)
            r.t_end = t1
            last = run[-1]
            tb = table_at(last["seq"])
            side = tb.side(last["x"]) if tb else "A"
            why = "dropped below the table" if dead else "lost from view"
            r.events.append(Ev("dead", t1, last["seq"], last["x"], last["y"], side, 0.7 if dead else 0.4, why))
            closed = dead
    for r in rallies:
        r.winner, r.reason, r.confidence = referee(r.events)
    return [r for r in rallies if any(e.kind in ("hit", "bounce") for e in r.events)]


def other(side: str) -> str:
    return "B" if side == "A" else "A"


def referee(events: list[Ev]) -> tuple[str | None, str, float]:
    """Basic point rules over one rally's events. Returns (winner side or None, reason, confidence).

    A real fault ends the rally, so an apparent fault followed by more play (a later hit by the other side) is
    treated as a detection gap: the state resyncs at that hit and the rally continues. Only how the rally actually
    ends decides the point; each resync lowers the confidence.
    """
    evs = [e for e in events if e.kind in ("hit", "bounce")]
    dead = next((e for e in reversed(events) if e.kind == "dead"), None)
    if not evs:
        return None, "no hits or bounces seen", 0.0
    if not any(e.kind == "bounce" for e in evs):
        # every served point bounces; hits alone are usually a ball being handled between points
        return None, "no bounce seen (ball handling, or the rally wasn't tracked)", 0.0
    conf = float(min([e.conf for e in evs] + [1.0]))
    st = {"hitter": None, "landed": False, "serve": 0, "last": None}  # serve: 0 none, 1 serve in flight, 2 rally
    resyncs = 0

    def play_continues(k: int, faulty: str) -> bool:
        return any(e.kind == "hit" and e.side != faulty for e in evs[k + 1 :])

    k = 0
    while k < len(evs):
        e = evs[k]
        hitter, landed, serve, last = st["hitter"], st["landed"], st["serve"], st["last"]
        fault: tuple[str, str] | None = None  # (loser, reason)
        if e.kind == "hit":
            if hitter is not None and e.side == hitter and last is None:
                k += 1
                continue  # same player again before any bounce: the toss, then the strike (or a re-swing)
            if hitter is not None and not landed and serve == 2 and e.side != hitter:
                fault = (e.side, f"volley: side {e.side} hit the ball before it bounced on their side")
            elif hitter is not None and serve == 1:
                fault = (hitter, "serve didn't bounce on both sides before the return")
            if fault is None:
                st.update(hitter=e.side, landed=False, last=None, serve=1 if hitter is None else 2)
        elif hitter is None:
            # the serve hit wasn't seen: a serve bounces first on the server's own side, so infer the server
            st.update(hitter=e.side, serve=1, last=e.side)
            conf *= 0.8
        elif serve == 1:
            if last is None and e.side != hitter:
                fault = (hitter, "serve didn't bounce on the server's side first")
            elif last is None:
                st["last"] = e.side
            elif e.side == hitter:
                fault = (hitter, "serve bounced twice on the server's side")
            else:
                st.update(serve=2, landed=True, last=e.side)
        elif not landed:
            if e.side == hitter:
                fault = (hitter, f"side {hitter}'s shot bounced on their own side")
            else:
                st.update(landed=True, last=e.side)
        elif e.side == last:
            fault = (e.side, f"second bounce on side {e.side}")
        if fault is not None:
            loser, reason = fault
            if play_continues(k, loser):
                # play went on: this was a missed/false event, not a fault. Resync at the next hit.
                resyncs += 1
                conf *= 0.85
                k = next(j for j in range(k + 1, len(evs)) if evs[j].kind == "hit")
                st.update(hitter=None, landed=False, last=None, serve=2)
                st["hitter"] = evs[k].side
                k += 1
                continue
            note = f"; {resyncs} detection gap(s) skipped" if resyncs else ""
            return other(loser), reason + note, conf
        k += 1
    hitter, landed, last = st["hitter"], st["landed"], st["last"]
    note = f"; {resyncs} detection gap(s) skipped" if resyncs else ""
    why = dead.why if dead else "ended"
    if hitter is None:
        return None, "rally ended before a hit was seen", 0.0
    if landed:
        return hitter, f"side {last} didn't return a ball that landed ({why}){note}", conf * 0.8
    return other(hitter), f"side {hitter}'s shot didn't land on the far side ({why}){note}", conf * 0.8
