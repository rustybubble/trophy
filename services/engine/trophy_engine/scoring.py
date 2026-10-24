"""Scores derived by replaying the call log (so undo and overturn are exact), and the serve rotation.

Template ``rally`` (table tennis, pickleball rally scoring): ``points_to_win``, ``win_by``, ``serves_per_turn``,
``deuce_serves_per_turn`` (from points_to_win-1 all), ``games_to_win``. Every param is overridable per game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COUNTED_STATUSES = frozenset({"final", "upheld", "challenged"})
SCORING_KINDS = frozenset({"point", "violation", "basket", "score_update"})


@dataclass
class ScoringParams:
    points_to_win: int = 11
    win_by: int = 2
    serves_per_turn: int = 2
    deuce_serves_per_turn: int = 1
    games_to_win: int = 1
    cap: int | None = None  # a hard cap ("win by 1 at 15"), None = none

    @classmethod
    def from_pack(cls, pack: dict[str, Any], overrides: dict[str, Any] | None = None) -> ScoringParams:
        p = dict((pack.get("scoring") or {}).get("params") or {})
        p.update({k: v for k, v in (overrides or {}).items() if k in cls.__dataclass_fields__})
        return cls(**{k: v for k, v in p.items() if k in cls.__dataclass_fields__})


@dataclass
class GameScore:
    points: dict[str, int]
    games: dict[str, int]
    game_over: bool
    match_over: bool
    winner: str | None
    game_point_for: list[str]  # sides one point from winning the current game
    match_point_for: list[str]
    server: str
    serving_points_left: int

    def display(self, a: str = "A", b: str = "B") -> str:
        return f"{self.points.get(a, 0)}–{self.points.get(b, 0)}"


def counts_for_score(call: dict[str, Any]) -> bool:
    return (
        call.get("kind") in SCORING_KINDS
        and call.get("status") in COUNTED_STATUSES
        and bool(call.get("team_id"))
        and int(call.get("points") or 0) != 0
    )


def _game_won(points: dict[str, int], sp: ScoringParams) -> str | None:
    for side, pts in points.items():
        other = max(v for s, v in points.items() if s != side) if len(points) > 1 else 0
        if pts >= sp.points_to_win and pts - other >= sp.win_by:
            return side
        if sp.cap is not None and pts >= sp.cap:
            return side
    return None


def replay_score(
    calls: list[dict[str, Any]], sp: ScoringParams, first_server: str = "A", sides=("A", "B")
) -> GameScore:
    """Walk the call log in order and derive points, games, the current server and game/match points."""
    games = {s: 0 for s in sides}
    points = {s: 0 for s in sides}
    game_first_server = first_server
    game_over = False
    match_over = False
    winner: str | None = None
    for c in sorted(calls, key=lambda c: (float(c.get("t_game_s", 0)), str(c.get("created_at_ms", 0)))):
        if not counts_for_score(c):
            continue
        if match_over:
            break
        if game_over:  # a new game starts with the next point
            points = {s: 0 for s in sides}
            game_first_server = "B" if game_first_server == "A" else "A"
            game_over = False
            winner = None
        team = str(c["team_id"])
        if team not in points:
            continue
        points[team] = max(0, points[team] + int(c.get("points") or 0))
        w = _game_won(points, sp)
        if w:
            games[w] += 1
            game_over = True
            winner = w
            if games[w] >= sp.games_to_win:
                match_over = True
    server, left = _server(points, sp, game_first_server)
    gp = [] if game_over else [s for s in sides if _is_game_point(points, s, sp)]
    mp = [s for s in gp if games[s] + 1 >= sp.games_to_win]
    return GameScore(points, games, game_over, match_over, winner, gp, mp, server, left)


def _is_game_point(points: dict[str, int], side: str, sp: ScoringParams) -> bool:
    nxt = dict(points)
    nxt[side] += 1
    return _game_won(nxt, sp) == side


def _server(points: dict[str, int], sp: ScoringParams, first_server: str) -> tuple[str, int]:
    total = sum(points.values())
    deuce_at = (sp.points_to_win - 1) * len(points)
    other = "B" if first_server == "A" else "A"
    if total >= deuce_at and all(p >= sp.points_to_win - 1 for p in points.values()):
        turns_before = deuce_at // sp.serves_per_turn
        extra = (total - deuce_at) // sp.deuce_serves_per_turn
        n = turns_before + extra
        left = sp.deuce_serves_per_turn - (total - deuce_at) % sp.deuce_serves_per_turn
    else:
        n = total // sp.serves_per_turn
        left = sp.serves_per_turn - total % sp.serves_per_turn
    return (first_server if n % 2 == 0 else other), left


@dataclass
class ScoreRows:
    rows: list[dict[str, Any]] = field(default_factory=list)


def score_rows(game_id: str, gs: GameScore, now_ms: float, sides=("A", "B")) -> list[dict[str, Any]]:
    return [
        {
            "game_id": game_id,
            "team_id": s,
            "points": gs.points[s],
            "games": gs.games[s],
            "sets": None,
            "display": gs.display(*sides) if s == sides[0] else gs.display(sides[1], sides[0]),
            "updated_at_ms": now_ms,
        }
        for s in sides
    ]
