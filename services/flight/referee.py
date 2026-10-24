"""Local deterministic referee for recorded TT evidence, separate from perception.

This module is an engine handoff, not a detector and not the production shared-state
writer. Only validated rule triggers or an explicit player resolution score points.
All intervals below are externally validated uncertainty bounds, not invented sigma.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

PROFILE = "ittf-2026-01-01+ttr-2025-upward-chord-v1"
SOURCE = "https://documents.ittf.sport/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf"
TTR_SOURCE = "https://www.ittf.com/2025/04/13/enhanced-table-tennis-review-system-to-feature-at-ittf-mens-and-womens-world-cup-macao-2025/"
POINT_RULES = {
    "incorrect_service": "2.10.1.1",
    "incorrect_return": "2.10.1.2",
    "non_net_touch_before_opponent": "2.10.1.3",
    "missed_opponent_court": "2.10.1.4",
    "through_net": "2.10.1.5",
    "obstruction": "2.10.1.6",
    "deliberate_double_strike": "2.10.1.7",
    "illegal_racket": "2.10.1.8",
    "table_moved": "2.10.1.9",
    "net_touched": "2.10.1.10",
    "free_hand_table": "2.10.1.11",
}
LET_RULES = {
    "service_net": "2.9.1.1",
    "receiver_not_ready": "2.9.1.2",
    "external_disturbance": "2.9.1.3",
    "official_interruption": "2.9.1.4",
    "order_correction": "2.9.2.1",
    "expedite_interruption": "2.9.2.2",
}


def _interval(value: Any, low: float = 0) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        a, b = map(float, value)
    except (TypeError, ValueError):
        return None
    return (a, b) if math.isfinite(a) and math.isfinite(b) and low <= a <= b else None


def assess_serve(
    height_interval_m=None,
    angle_interval_deg=None,
    *,
    calibrated=False,
    release_observed=False,
    timing_validated=False,
    measurement_validated=False,
    relaxation=False,
    other_requirements_verified=False,
) -> dict:
    """Assess only toss checks. Passing both does not establish service legality.

    Angle convention: atan2(horizontal release-to-apex displacement, vertical
    rise), using only the upward segment. This is Trophy's convention; the TTR
    announcement supplies a threshold but no technical estimator definition.
    """
    result = {
        "profile": PROFILE,
        "rule_refs": ["2.6.2"],
        "source": SOURCE,
        "ttr_source": TTR_SOURCE,
        "status": "unavailable",
        "height": "unavailable",
        "angle": "unavailable",
        "full_service_legality": "unverified",
        "angle_estimator": "upward release-to-apex chord from vertical",
        "official_angle_estimator_verified": False,
    }
    if relaxation:
        return {**result, "status": "official_input_required", "rule_refs": ["2.6.7"]}
    if not all((calibrated, release_observed, timing_validated, measurement_validated)):
        return {**result, "reason": "Metric calibration, release, timing and measurement validation are required."}
    h, a = _interval(height_interval_m), _interval(angle_interval_deg)
    if h:
        result["height"] = "fail" if h[1] < 0.16 else "pass" if h[0] >= 0.16 else "uncertain"
    if a and a[1] <= 180:
        result["angle"] = "fail" if a[0] > 30 else "pass" if a[1] <= 30 else "uncertain"
    checks = [result["height"], result["angle"]]
    result["status"] = (
        "toss_fault_supported"
        if "fail" in checks
        else "toss_checks_pass"
        if checks == ["pass", "pass"]
        else "review_needed"
    )
    # This input is supplied by an official/validated upstream evidence, not pose.
    if other_requirements_verified and result["status"] == "toss_checks_pass":
        result["full_service_legality"] = "verified_by_external_evidence"
    return result


@dataclass
class Referee:
    first_server: str = "A"
    best_of: int = 5
    initial_points: dict = field(default_factory=lambda: {"A": 0, "B": 0})
    mode: str = "singles"
    _calls: dict = field(default_factory=dict, init=False)
    _history: list = field(default_factory=list, init=False)
    _events: dict = field(default_factory=dict, init=False)
    _order: list = field(default_factory=list, init=False)

    def __post_init__(self):
        if self.first_server not in ("A", "B") or self.best_of < 1 or self.best_of % 2 != 1:
            raise ValueError("Need first_server A/B and a positive odd best_of")
        if set(self.initial_points) != {"A", "B"} or any(
            type(p) is not int or p < 0 for p in self.initial_points.values()
        ):
            raise ValueError("Initial points must be non-negative integers for A and B")
        if max(self.initial_points.values()) >= 11 and abs(self.initial_points["A"] - self.initial_points["B"]) >= 2:
            raise ValueError("Initial score must be inside an unfinished game")

    @staticmethod
    def other(team):
        if team not in ("A", "B"):
            raise ValueError("Team must be A or B")
        return "B" if team == "A" else "A"

    def snapshot(self) -> dict:
        points = dict(self.initial_points)
        games = {"A": 0, "B": 0}
        game_no, completed = 1, []
        between, match_winner = False, None
        for rally_id in self._order:
            c = self._calls[rally_id]
            if c["status"] != "point":
                continue
            if match_winner:
                continue
            if between:
                points = {"A": 0, "B": 0}
                game_no += 1
                between = False
            points[c["winner"]] += 1
            a, b = points["A"], points["B"]
            if max(a, b) >= 11 and abs(a - b) >= 2:
                winner = "A" if a > b else "B"
                games[winner] += 1
                completed.append({"game_no": game_no, "points": dict(points), "winner": winner})
                between = True
                if games[winner] >= self.best_of // 2 + 1:
                    match_winner = winner
        # Between games retain the completed game's final score for display;
        # name the server due in the next game, with first service alternating.
        serving_game = game_no + int(between and not match_winner)
        first = self.first_server if serving_game % 2 else self.other(self.first_server)
        total = 0 if between else sum(points.values())
        switch = 0 if between else total // 2 if min(points.values()) < 10 else 10 + total - 20
        server = first if switch % 2 == 0 else self.other(first)
        ends_swapped = ((game_no - 1) % 2 == 1) ^ (game_no == self.best_of and max(points.values()) >= 5)
        return deepcopy(
            {
                "profile": PROFILE,
                "points": points,
                "games": games,
                "server": server,
                "receiver": self.other(server),
                "game_no": game_no,
                "status": "match_complete" if match_winner else "between_games" if between else "in_game",
                "match_winner": match_winner,
                "completed_games": completed,
                "ends_swapped": ends_swapped,
                "mode": self.mode,
                "history": self._history,
                "calls": list(self._calls.values()),
            }
        )

    def _record(
        self,
        event_id,
        rally_id,
        status,
        reason,
        *,
        winner=None,
        rule_refs=None,
        source="validated_evidence",
        evidence_refs=None,
        correction=False,
    ):
        if not isinstance(event_id, str) or not event_id or not isinstance(rally_id, str) or not rally_id:
            raise ValueError("Stable nonempty event_id and rally_id are required")
        if event_id in self._events:
            return deepcopy(self._events[event_id])
        if winner is not None:
            self.other(winner)
        old = self._calls.get(rally_id)
        if old and old["status"] in ("point", "let") and not correction:
            return deepcopy(old)
        if correction and not old:
            raise ValueError("Cannot correct an unknown rally")
        if self.snapshot()["match_winner"] and not correction and status == "point":
            raise ValueError("Match is complete")
        if rally_id not in self._order:
            self._order.append(rally_id)
        call = {
            "event_id": event_id,
            "rally_id": rally_id,
            "status": status,
            "winner": winner,
            "reason": reason,
            "rule_refs": rule_refs or [],
            "source_edition": "ITTF Statutes 2026, effective 2026-01-01",
            "source_url": SOURCE,
            "profile": PROFILE,
            "source": source,
            "tier": "PLAYERS DECIDE" if source == "manual" or status == "review_needed" else "BETA",
            "probability": None,
            "evidence_refs": evidence_refs or [],
            "revision": 1 + (old["revision"] if old else 0),
        }
        if correction:
            call["supersedes"] = old["event_id"]
        self._calls[rally_id] = call
        call["score_after"] = self.snapshot()["points"]
        self._history.append(deepcopy(call))
        self._events[event_id] = deepcopy(call)
        return deepcopy(call)

    def submit(self, event: dict) -> dict:
        """Accept an evidence envelope; pixel tracks/disappearance alone are reviews.

        Required ids: event_id, rally_id. For supported outcomes use
        evidence={verified:True, refs:[...], trigger:<POINT_RULES/LET_RULES key>,
        offender:'A'|'B', ...}. The caller must validate these facts separately.
        A winner field from perception is deliberately ignored.
        """
        eid, rid = event.get("event_id"), event.get("rally_id")
        if eid in self._events:
            return deepcopy(self._events[eid])
        e = event.get("evidence") or {}
        trigger = e.get("trigger")
        if self.mode != "singles":
            return self._record(
                eid, rid, "review_needed", "Doubles/accessibility order requires official input in this demo."
            )
        if e.get("verified") is not True or not e.get("refs") or e.get("conflicting"):
            return self._record(
                eid,
                rid,
                "review_needed",
                "Insufficient or conflicting terminal evidence; players decide.",
                evidence_refs=e.get("refs"),
            )
        if trigger in LET_RULES:
            if trigger == "service_net" and not (e.get("otherwise_correct_service") or e.get("receiver_obstructed")):
                return self._record(
                    eid,
                    rid,
                    "review_needed",
                    "Net contact alone does not establish a service let.",
                    evidence_refs=e["refs"],
                )
            if trigger == "receiver_not_ready" and e.get("receiver_attempted_return") is not False:
                return self._record(
                    eid,
                    rid,
                    "review_needed",
                    "Receiver readiness requires no attempted return.",
                    evidence_refs=e["refs"],
                )
            return self._record(
                eid,
                rid,
                "let",
                "Rally is a let: " + trigger.replace("_", " ") + ".",
                rule_refs=[LET_RULES[trigger]],
                evidence_refs=e["refs"],
            )
        if trigger in POINT_RULES and e.get("offender") in ("A", "B"):
            # A simultaneously supported let takes precedence over a point.
            if e.get("let_applies") is True:
                return self._record(
                    eid,
                    rid,
                    "let",
                    "Verified let takes precedence over point award.",
                    rule_refs=["2.9", "2.10.1"],
                    evidence_refs=e["refs"],
                )
            return self._record(
                eid,
                rid,
                "point",
                "Point: " + trigger.replace("_", " ") + ".",
                winner=self.other(e["offender"]),
                rule_refs=[POINT_RULES[trigger]],
                evidence_refs=e["refs"],
            )
        return self._record(
            eid,
            rid,
            "review_needed",
            "No supported point/let trigger. Ball loss or an edge position alone is insufficient.",
            evidence_refs=e["refs"],
        )

    def resolve(self, rally_id, winner, event_id, reason="Players resolved the point"):
        """Explicit human action. winner=None means a manually agreed let."""
        old = self._calls.get(rally_id)
        return self._record(
            event_id,
            rally_id,
            "point" if winner else "let",
            reason,
            winner=winner,
            source="manual",
            rule_refs=["2.5.3" if winner is None else "2.5.4"],
            correction=bool(old and old["status"] in ("point", "let")),
        )

    def correct(self, rally_id, winner, event_id, reason="Judge corrected the point after review"):
        return self._record(
            event_id,
            rally_id,
            "point" if winner else "let",
            reason,
            winner=winner,
            source="manual",
            correction=True,
            rule_refs=["3.2.7.1", "3.3.2.8"],
        )
