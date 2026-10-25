"""Rally state: what the rules may ask about the current rally (``rally.*`` in CEL).

Everything here is a measurement the engine keeps for the rule pack; the pack decides what it means (D-18). The
evidence fields (time since the last bounce, hits seen since it, how surely the last bounce was sided) exist so a
pack can refuse to call a point on weak evidence instead of the engine hard-coding that policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# One line per `rally.*` field, in the order view() emits them. `trophy_engine.vocabulary` renders this for the Droid;
# a test asserts the keys match view().
RALLY_FIELDS: dict[str, str] = {
    "rally_no": "1-based rally counter in this game",
    "server_side": "side serving this rally (A | B)",
    "receiver": "the other side",
    "phase": "'serve' until the serve has bounced on both sides (or a hit follows the first bounce), then 'rally'",
    "bounces": "bounces seen so far in this rally (any surface)",
    "surface_bounces": "bounces on the play surface (table/court) so far",
    "last_bounce_side": "side of the most recent bounce ('' before the first)",
    "last_bounce_surface": "surface of the most recent bounce ('' before the first)",
    "last_hitter": "side of the most recent racket contact ('' if none seen)",
    "at_fault_side": "the side that loses if the ball dies now: last bounce side, else the server",
    "contacts": "racket contacts seen so far in this rally",
    "nets": "net events seen so far in this rally",
    "shots": "alias of surface_bounces",
    "duration_s": "seconds since the rally opened",
    "last_bounce_t_s": "game time of the most recent bounce (0 before the first)",
    "last_bounce_side_p": "P(the most recent bounce was on the side it was given), from its x and sigma "
    "(1 before the first)",
    "hits_since_last_bounce": "racket contacts seen after the most recent bounce",
    "hit_since_last_bounce": "true when at least one racket contact followed the most recent bounce",
    "t_since_last_bounce_s": "seconds from the most recent bounce to this event (-1 before the first bounce)",
    "t_since_last_contact_s": "seconds from the most recent racket contact to this event (-1 if none seen)",
}


@dataclass
class RallyState:
    rally_no: int
    server_side: str  # "A" | "B"
    t_start_s: float
    phase: str = "serve"  # serve | rally
    bounces: int = 0
    surface_bounces: int = 0
    last_bounce_side: str = ""
    last_bounce_surface: str = ""
    last_hitter: str = ""
    contacts: int = 0
    nets: int = 0
    event_ids: list[str] = field(default_factory=list)
    last_t_s: float = 0.0
    last_bounce_t_s: float = 0.0
    last_bounce_side_p: float = 1.0
    hits_since_last_bounce: int = 0
    last_contact_t_s: float = -1.0

    @property
    def receiver(self) -> str:
        return "B" if self.server_side == "A" else "A"

    @property
    def at_fault_side(self) -> str:
        """The side that loses if the ball dies now: whoever's side it last bounced on, else the server."""
        return self.last_bounce_side or self.server_side

    def view(self, now_s: float | None = None) -> dict[str, Any]:
        """The `rally.*` activation. `now_s` is the time of the event being judged (for the t_since_* fields)."""
        t = self.last_t_s if now_s is None else now_s
        return {
            "rally_no": self.rally_no,
            "server_side": self.server_side,
            "receiver": self.receiver,
            "phase": self.phase,
            "bounces": self.bounces,
            "surface_bounces": self.surface_bounces,
            "last_bounce_side": self.last_bounce_side,
            "last_bounce_surface": self.last_bounce_surface,
            "last_hitter": self.last_hitter,
            "at_fault_side": self.at_fault_side,
            "contacts": self.contacts,
            "nets": self.nets,
            "shots": self.surface_bounces,
            "duration_s": max(0.0, self.last_t_s - self.t_start_s),
            "last_bounce_t_s": self.last_bounce_t_s,
            "last_bounce_side_p": self.last_bounce_side_p,
            "hits_since_last_bounce": self.hits_since_last_bounce,
            "hit_since_last_bounce": self.hits_since_last_bounce > 0,
            "t_since_last_bounce_s": round(t - self.last_bounce_t_s, 4) if self.bounces else -1.0,
            "t_since_last_contact_s": round(t - self.last_contact_t_s, 4) if self.last_contact_t_s >= 0 else -1.0,
        }

    def apply(self, ev: dict[str, Any]) -> None:
        """Update after the rules have seen the event (rules see the state *before* the event)."""
        self.event_ids.append(str(ev.get("id", "")))
        self.last_t_s = float(ev.get("t_game_s", self.last_t_s))
        t = ev.get("type")
        p = ev.get("payload") or {}
        if t == "bounce":
            self.bounces += 1
            self.last_bounce_side = str(ev.get("side") or p.get("side") or "")
            self.last_bounce_surface = str(p.get("surface", ""))
            self.last_bounce_t_s = self.last_t_s
            self.last_bounce_side_p = float(ev.get("side_p", 1.0))
            self.hits_since_last_bounce = 0
            if self.last_bounce_surface != "floor":
                self.surface_bounces += 1
            if self.phase == "serve" and self.surface_bounces >= 2:
                self.phase = "rally"
        elif t == "contact":
            self.contacts += 1
            self.hits_since_last_bounce += 1
            self.last_contact_t_s = self.last_t_s
            self.last_hitter = str(ev.get("side") or p.get("side") or "")
            if self.phase == "serve" and self.surface_bounces >= 1:
                self.phase = "rally"
        elif t == "net":
            self.nets += 1
