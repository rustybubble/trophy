"""The table-tennis check library v1 as the referee knows it (agent-3-droid-realtime.md §6).

The engine owns the implementations (golden library, edited per calibration by the Droid). The referee only needs
names, arguments and what comes back, so it can route a question and phrase the result. A question that matches no
entry becomes a `request_check` (the "give me a moment" path).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CheckSpec:
    name: str
    about: str  # what the check answers, in the judge's words
    args: tuple[str, ...]  # "t" = one instant (a bounce/contact), "rally" = a whole rally, "window" = [t0, t1]
    returns: str
    tier: str  # tier ceiling from the brief
    verdicts: tuple[str, ...] = field(default_factory=tuple)


CHECKS: dict[str, CheckSpec] = {
    s.name: s
    for s in (
        CheckSpec(
            "in_out",
            "Was the ball in, out, or on the edge at a bounce; which line and by how much.",
            ("t",),
            "verdict in|out|edge, p, evidence {line, margin_m, sigma_m, t_game_s}",
            "AUTO",
            ("in", "out", "edge"),
        ),
        CheckSpec(
            "bounce_side",
            "Which side of the table (A or B) the ball bounced on.",
            ("t",),
            "verdict A|B, p, evidence {d_to_line_m, sigma_m, t_game_s}",
            "AUTO",
            ("A", "B"),
        ),
        CheckSpec(
            "edge_hit",
            "Whether a bounce hit the top edge (good), the side face (fault) or missed the edge.",
            ("t",),
            "verdict top_edge|side_face|miss, p",
            "BETA",
            ("top_edge", "side_face", "miss"),
        ),
        CheckSpec(
            "net_touch",
            "Whether the ball touched the net during a window.",
            ("window",),
            "verdict yes|no, p, evidence {x_at_net_m, z_at_net_m}",
            "BETA",
            ("yes", "no"),
        ),
        CheckSpec(
            "serve_toss",
            "Was the serve legal: toss height (must rise more than 6 in) and angle from vertical (within 30 deg).",
            ("rally",),
            "verdict legal|too_low|angled, p, evidence {height_m, angle_deg, sigma_height_m, sigma_angle_deg}",
            "AUTO",
            ("legal", "too_low", "angled"),
        ),
        CheckSpec(
            "double_bounce",
            "Whether the ball bounced twice on one side in a rally.",
            ("rally",),
            "verdict yes|no, p, evidence {side, t_first_s, t_second_s}",
            "AUTO",
            ("yes", "no"),
        ),
        CheckSpec(
            "phases",
            "When the rally started and ended; between-points state.",
            ("window",),
            "verdict rally_start|rally_end|between_points, p, evidence {t_game_s}",
            "BETA",
        ),
        CheckSpec(
            "rally_summary",
            "Shots in the rally, the longest exchange, the fastest ball, where the bounces landed.",
            ("rally",),
            "evidence {shots, longest_shots, speed_max_mps, bounces}; informational, no verdict",
            "PLAYERS",
        ),
    )
}


def catalog_text() -> str:
    """One line per check, for the router prompt."""
    return "\n".join(f"- {s.name}({', '.join(s.args)}): {s.about} Returns {s.returns}." for s in CHECKS.values())
