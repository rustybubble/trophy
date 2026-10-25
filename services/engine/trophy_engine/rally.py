"""Rally state: what the rules may ask about the current rally (``rally.*`` in CEL)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    net_touches: int = 0  # nets of kind touch: the ball clipped the net and went over
    event_ids: list[str] = field(default_factory=list)
    last_t_s: float = 0.0

    @property
    def receiver(self) -> str:
        return "B" if self.server_side == "A" else "A"

    @property
    def at_fault_side(self) -> str:
        """The side that loses if the ball dies now: whoever's side it last bounced on, else the server."""
        return self.last_bounce_side or self.server_side

    def view(self) -> dict[str, Any]:
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
            "net_touches": self.net_touches,
            "shots": self.surface_bounces,
            "duration_s": max(0.0, self.last_t_s - self.t_start_s),
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
            if self.last_bounce_surface != "floor":
                self.surface_bounces += 1
            if self.phase == "serve" and self.surface_bounces >= 2:
                self.phase = "rally"
        elif t == "contact":
            self.contacts += 1
            self.last_hitter = str(ev.get("side") or p.get("side") or "")
            if self.phase == "serve" and self.surface_bounces >= 1:
                self.phase = "rally"
        elif t == "net":
            self.nets += 1
            if p.get("kind") == "touch":
                self.net_touches += 1
