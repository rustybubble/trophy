"""The rule engine (interfaces-v1 §9-§11): layer-2 events + control commands in, calls, rallies, scores, challenges,
house rules, asks and moments out. Scores are derived by replaying the call log, so undo and overturn are exact.
"""

from __future__ import annotations

import logging
import queue
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from trophy.ids import new_ulid

from .calls import build_call, render
from .droid import DroidMixin, gated_file, placeholder_pack  # noqa: F401 - gated_file is re-exported
from .gate import gate
from .moments import best_play, moment_from_call, rescore_for_challenge
from .rally import RallyState
from .rules.cel import CelError, RuleSet, compile_rules, evaluate, when_true
from .scoring import GameScore, ScoringParams, replay_score, score_rows
from .sportmod.loader import SportModule, load_module
from .state import StateWriter

log = logging.getLogger("trophy.engine")
ROOT = Path(__file__).resolve().parents[3]
RALLY_OPENERS = frozenset({"bounce", "contact", "serve_toss", "shot"})
SCORING_KINDS = frozenset({"point", "violation", "basket"})
# After a point called on a bounce the ball is dead until a ball_dead event, or this long: a trailing bounce or the
# ball rolling off must not open a rally of its own and score again (review blocker 4).
DEAD_AFTER_POINT_S = 2.0
ENSEMBLE_LO, ENSEMBLE_HI = 0.35, 0.75
# A challenge re-check (D-44): the blended probability that the original call was right decides it.
UPHOLD_AT, OVERTURN_AT = 0.6, 0.4
# Kinds whose calls name a team at fault; a made basket or an info line has none.
FAULT_KINDS = frozenset({"point", "violation", "line_call", "edge_call", "foul_flag"})


class Decider:
    """What the engine needs from decide(): fire-and-forget, never on the live path."""

    def submit(self, request: dict[str, Any]) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class GameState:
    game: dict[str, Any]
    module: SportModule
    pack: dict[str, Any]
    rules: RuleSet
    rule_version: str
    params: dict[str, Any]
    scoring: ScoringParams
    first_server: str = "A"
    rally: RallyState | None = None
    rally_no: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    challenges: dict[str, dict[str, Any]] = field(default_factory=dict)
    house_rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    moments: dict[str, dict[str, Any]] = field(default_factory=dict)
    call_moment: dict[str, str] = field(default_factory=dict)
    feeds: dict[str, dict[str, Any]] = field(default_factory=dict)  # cam_id -> Feed row (D-42)
    decided: set[str] = field(default_factory=set)
    last_t_s: float = 0.0
    calib_untrusted: bool = False
    # after a point is called on a bounce, the ball is dead until the track says so (a ball_dead event), or for
    # DEAD_AFTER_POINT_S at most: players pick the ball up and knock it around, and those bounces are not a new rally
    dead_since_t_s: float | None = None
    rally_hit_seen: bool = False  # a racket hit was seen in the current rally (server_from_first_hit)
    # D-43: the pack's YAML as loaded (the Droid's next house rule starts from it: rules stack), every event of the
    # session (re-judged when a rule is applied), the applied house rules/interpreters (newest last: revert pops),
    # and the interpreter run this game waits for (a sport with no approved interpreter)
    pack_text: str = ""
    session_events: list[dict[str, Any]] = field(default_factory=list)
    applied: list[dict[str, Any]] = field(default_factory=list)
    needs_interpreter: bool = False
    interpreter_run: str | None = None

    @property
    def sides(self) -> tuple[str, str]:
        t = [x["team_id"] for x in self.game.get("teams", [])]
        return (t[0], t[1]) if len(t) >= 2 else ("A", "B")

    def team(self, team_id: str | None) -> dict[str, Any]:
        for t in self.game.get("teams", []):
            if t.get("team_id") == team_id:
                return t
        return {"team_id": team_id or "", "name": team_id or "", "color": None}

    def score(self) -> GameScore:
        return replay_score(self.calls, self.scoring, self.first_server, self.sides)


class Engine(DroidMixin):
    def __init__(
        self,
        state: StateWriter,
        *,
        modules_dir: Path | None = None,
        decider: Decider | None = None,
        now_ms=None,
        labels_dir: Path | None = None,
        dead_after_point_s: float = DEAD_AFTER_POINT_S,
        server_from_first_hit: bool = False,
        approved_dir: Path | None = None,
        sessions_dir: Path | None = None,
    ) -> None:
        self.state = state
        # D-43 (set by the live loop; None in tests unless given): approved interpreters (data/local/modules/<sport>/
        # v<n>, newest wins over sports/<sport>) and where the session snapshots for the Droid go (data/local/sessions)
        self.approved_dir = approved_dir
        self.sessions_dir = sessions_dir
        # The ball stays dead after a point called on a bounce until a ball_dead event (or this many seconds; 0 turns
        # it off). server_from_first_hit (real play; off for the hand-written sequences of the tests and the gate):
        # the first racket hit of a rally names the server (a serve is a hit, ITTF 2.6.3); when that hit was not
        # seen, the side of the first bounce does (a legal serve lands there first), so no serve fault is unseen.
        self.dead_after_point_s = dead_after_point_s
        # set by the live loop: run a session check (game_id, check, t, window, args) -> CheckResult fields, and
        # XADD a reply to the referee's stream (interfaces-v1 section 20)
        self.check_runner = None
        self.reply = None
        # set by the live loop with a 3D track: start a Droid new_check job (game_id, question, hint, query, reply)
        self.new_check = None
        self.server_from_first_hit = server_from_first_hit
        self.modules_dir = modules_dir or ROOT / "sports"
        self.decider = decider
        self.now_ms = now_ms or (lambda: time.time() * 1000.0)
        self.labels_dir = labels_dir or ROOT / "evals" / "labels"
        self.games: dict[str, GameState] = {}
        # Commands produced off the loop thread (the background challenge verdict): handled by drain() on the loop.
        self.inbox: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        # Crops for the voters: (game_id, evidence windows) -> <= 4 base64 JPEGs. Set once the gateway serves
        # GET /api/replay/{game_id}/frames (interfaces §13); until then votes run on observations and facts only.
        self.crops: Any = None

    # ------------------------------------------------------------ games

    def create_game(
        self,
        game_id: str,
        sport: str,
        *,
        t0_ms: float | None = None,
        teams: list[dict[str, Any]] | None = None,
        params: dict[str, Any] | None = None,
        module_dir: Path | None = None,
        pack: dict[str, Any] | None = None,
    ) -> GameState:
        mdir = module_dir or self.module_dir_for(sport)
        mod = load_module(mdir, rules_optional=True)
        pack_text = (mdir / "rules.yaml").read_text("utf8") if pack is None and (mdir / "rules.yaml").is_file() else ""
        if pack is None:
            pack = mod.rules
        needs_interpreter = not pack  # an annotated sport whose interpreter the Droid has not written yet (D-43)
        if needs_interpreter:
            pack = placeholder_pack(sport)
        if not pack_text:
            pack_text = yaml.safe_dump(pack, sort_keys=False)
        params = dict(params or {})
        variant = params.pop("variant", None)
        merged = dict(pack.get("params") or {})
        if variant:
            merged.update((pack.get("variants") or {}).get(variant) or {})
        merged.update(params)
        teams = (
            teams
            or [dict(t) for t in pack.get("teams", [])]
            or [
                {"team_id": "A", "name": "Team A"},
                {"team_id": "B", "name": "Team B"},
            ]
        )
        for t in teams:
            t.setdefault("name", t["team_id"])
        now = self.now_ms()
        game = {
            "game_id": game_id,
            "sport": sport,
            "pack_version": str(pack.get("version", "1")),
            "status": "lobby",
            "t0_ms": t0_ms if t0_ms is not None else now,
            "period_no": 1,
            "rally_no": 0,
            "server_team_id": None,
            "teams": teams,
            "params": {**merged, **({"synthetic": True, "label": params["label"]} if params.get("synthetic") else {})},
            "created_at_ms": now,
        }
        g = GameState(
            game=game,
            module=mod,
            pack=pack,
            rules=compile_rules(pack),
            rule_version=str(pack.get("version", "1")),
            params=merged,
            scoring=ScoringParams.from_pack(pack, merged),
            pack_text=pack_text,
            needs_interpreter=needs_interpreter,
        )
        self.games[game_id] = g
        self.state.upsert_game(game)
        self.state.set_score(score_rows(game_id, g.score(), now, g.sides))
        return g

    def start_game(self, game_id: str, first_server: str | None = None) -> None:
        g = self.games[game_id]
        g.first_server = first_server or g.sides[0]
        g.game["status"] = "live"
        g.game["server_team_id"] = g.score().server
        self.state.upsert_game(g.game)
        if g.needs_interpreter:
            self.request_interpreter(g, "sport_module", f"no approved interpreter for {g.game['sport']}")

    # ------------------------------------------------------------ events

    def handle_event(self, ev: dict[str, Any]) -> list[dict[str, Any]]:
        g = self.games.get(str(ev.get("game_id")))
        if g is None or g.game["status"] != "live":
            return []
        t = float(ev.get("t_game_s", 0.0))
        g.last_t_s = t
        if g.dead_since_t_s is not None:
            if ev.get("type") == "ball_dead" or t - g.dead_since_t_s > self.dead_after_point_s:
                g.dead_since_t_s = None
            if ev.get("type") == "ball_dead" or g.dead_since_t_s is not None:
                return []
        if _pre_serve_floor_bounce(ev, g):
            return []  # the ball bounced on the floor before the serve (players do that): not part of a rally
        if g.rally is None:
            if ev.get("type") not in (g.pack.get("rally_openers") or RALLY_OPENERS):
                return []
            self._open_rally(g, t)
        assert g.rally is not None
        payload = ev.get("payload") or {}
        if (
            self.server_from_first_hit
            and g.rally.phase == "serve"
            and g.rally.bounces == 0
            and payload.get("side") in g.sides
            and (
                ev.get("type") == "contact"  # the serve was seen: the hitter serves
                or (ev.get("type") == "bounce" and payload.get("surface") != "floor" and not g.rally_hit_seen)
            )  # the serve's hit was not seen: a legal serve lands on the server's side first, so that side serves
        ):
            g.rally_hit_seen = g.rally_hit_seen or ev.get("type") == "contact"
            hitter = payload["side"]
            if g.score().server != hitter:
                g.first_server = g.sides[1] if g.first_server == g.sides[0] else g.sides[0]
                g.rally.server_side = hitter
                g.game["server_team_id"] = hitter
                self.state.upsert_game(g.game)
        calib_untrusted = bool((ev.get("payload") or {}).get("calib_untrusted")) or g.calib_untrusted
        activation = {"ev": _strip_none(ev), "rally": g.rally.view(), "game": self._game_view(g), "params": g.params}
        posted: list[dict[str, Any]] = []
        scoring_call: dict[str, Any] | None = None
        for cr in g.rules.rules:
            if not when_true(cr, activation):
                continue
            rule = cr.rule
            call = self._make_call(g, ev, cr, activation, calib_untrusted)
            if call.get("outcome") == "let" or (rule.get("kind") in SCORING_KINDS and call.get("points")):
                if scoring_call is None:
                    scoring_call = call
                continue
            posted.append(call)
        if scoring_call is not None:
            posted.append(scoring_call)
        for call in posted:
            self._post(g, call)
        g.rally.apply(ev)
        if scoring_call is not None:
            self._end_rally(g, scoring_call)
            if ev.get("type") != "ball_dead" and self.dead_after_point_s > 0:
                g.dead_since_t_s = t
        return posted

    def _make_call(
        self, g: GameState, ev: dict[str, Any], cr, activation: dict[str, Any], calib_untrusted: bool
    ) -> dict[str, Any]:
        rule = cr.rule
        p_source = "geometry" if cr.p is not None else "heuristic"
        try:
            p = float(evaluate(cr.p, activation)) if cr.p is not None else float(ev.get("conf", 1.0))
        except (CelError, TypeError, ValueError):
            p, p_source = float(ev.get("conf", 1.0)), "heuristic"
        p = max(0.0, min(1.0, p))
        team_id: str | None = None
        if cr.team is not None:
            try:
                team_id = str(evaluate(cr.team, activation)) or None
            except CelError:
                team_id = None
        outcome = str(rule.get("outcome") or rule["id"])
        points = int(rule.get("points") or 0) if team_id and outcome != "let" else 0
        tier, shown = gate(p, str(rule.get("tier", "BETA")), str(rule.get("kind", "info")), calib_untrusted)
        gs = g.score()
        emotion = (
            "excited"
            if team_id and points and (team_id in gs.game_point_for or team_id in gs.match_point_for)
            else None
        )
        team = g.team(team_id)
        at_fault = self._at_fault(g, cr, activation, team_id, outcome)
        call = build_call(
            game_id=g.game["game_id"],
            ev=ev,
            rule=rule,
            rule_version=g.rule_version,
            rally_no=g.rally.rally_no if g.rally else g.rally_no,
            outcome=outcome,
            team_id=team_id,
            points=points,
            p=p,
            p_source=p_source,
            tier=tier,
            shown=shown,
            ctx=activation,
            team_name=team.get("name"),
            team_color=team.get("color"),
            lines=list(((g.pack.get("field") or {}).get("lines") or {}).keys())[:6],
            emotion=emotion,
            now_ms=self.now_ms(),
            why=self._why(ev),
            at_fault=at_fault,
            source="annotated" if ev.get("source") == "annotated" else "sensed",
        )
        return call

    def _at_fault(
        self, g: GameState, cr, activation: dict[str, Any], team_id: str | None, outcome: str
    ) -> dict[str, str] | None:
        """The team that committed the fault: the rule's `at_fault` CEL expression, else the team the call does not
        favour for a point/violation/line call. None for a let, a made basket or an info line."""
        at: str | None = None
        if cr.at_fault is not None:
            try:
                at = str(evaluate(cr.at_fault, activation)) or None
            except CelError:
                at = None
        elif team_id and outcome != "let" and str(cr.rule.get("kind")) in FAULT_KINDS:
            a, b = g.sides
            at = b if team_id == a else a if team_id == b else None
        if not at:
            return None
        return {"team_id": at, "name": str(g.team(at).get("name") or at)}

    @staticmethod
    def _why(ev: dict[str, Any]) -> str | None:
        p = ev.get("payload") or {}
        if ev.get("type") == "bounce" and ev.get("pos_m"):
            d = p.get("d_lines_m") or {}
            if d:
                k, v = min(d.items(), key=lambda kv: kv[1])
                sigma_cm = float(ev.get("sigma_m", 0)) * 100
                return f"bounce {abs(v) * 100:.0f} cm {'inside' if v >= 0 else 'outside'} {k}, σ {sigma_cm:.0f} cm"
        if ev.get("type") == "net":
            return f"net {p.get('kind')} from side {p.get('from_side')}"
        if ev.get("type") == "ball_dead":
            return f"ball {p.get('reason')} after the last bounce"
        if ev.get("type") == "serve_toss":
            deg = float(p.get("angle_from_vertical_rad", 0)) * 57.3
            return f"toss {float(p.get('height_m', 0)) * 100:.1f} cm, {deg:.0f}° from vertical"
        return None

    def _post(self, g: GameState, call: dict[str, Any]) -> None:
        g.calls.append(call)
        self.state.post_call(call)
        rule = g.rules.by_id(call["rule_id"])
        if rule is not None and rule.rule.get("check") == "ensemble" and ENSEMBLE_LO < call["p"] < ENSEMBLE_HI:
            self._spawn_decide(g, call, rule.rule)

    def _spawn_decide(
        self, g: GameState, call: dict[str, Any], rule: dict[str, Any], challenge_id: str | None = None
    ) -> None:
        if self.decider is None or call["id"] in g.decided:
            return
        ens = rule.get("ensemble") or {}
        options = list(ens.get("options") or [call["outcome"], f"not_{call['outcome']}"])
        ev = next((e for e in [self._event_for(g, call)] if e), None)
        p_geo = {
            o: (call["p"] if o == call["outcome"] or o == options[0] else (1.0 - call["p"]) / max(1, len(options) - 1))
            for o in options
        }
        req = {
            "schema": "trophy.decide.v1",
            "req_id": new_ulid(),
            "game_id": g.game["game_id"],
            "call_id": call["id"],
            "question": str(ens.get("question") or f"Is the call '{call['outcome']}' correct?"),
            "options": options,
            "context": f"{call.get('text', '')}. {call.get('why') or ''}".strip(),
            "images": list(self.crops(g.game["game_id"], call.get("evidence") or []))[:4] if self.crops else [],
            "observations": [ev] if ev else [],
            "p_geometry": p_geo,
            "timeout_s": 4,
        }
        if challenge_id:  # a challenge is not on the call's clock: give the voter a little longer
            req["challenge_id"] = challenge_id
            req["timeout_s"] = 6
            # the option that means "the call was right": the outcome itself, else the first option (geometry's pick)
            req["original_option"] = call["outcome"] if call["outcome"] in options else options[0]
        g.decided.add(call["id"])
        self.decider.submit(req)

    def _event_for(self, g: GameState, call: dict[str, Any]) -> dict[str, Any] | None:
        return getattr(g, "_last_events", {}).get(call["event_ids"][0]) if call.get("event_ids") else None

    def _open_rally(self, g: GameState, t: float) -> None:
        g.rally_no += 1
        server = g.score().server
        g.rally = RallyState(rally_no=g.rally_no, server_side=server, t_start_s=t, last_t_s=t)
        g.rally_hit_seen = False
        g.game["rally_no"] = g.rally_no
        g.game["server_team_id"] = server
        self.state.open_rally(
            {
                "game_id": g.game["game_id"],
                "rally_no": g.rally_no,
                "status": "open",
                "t_start_s": t,
                "t_end_s": None,
                "winner_team_id": None,
                "summary": None,
            }
        )

    def _end_rally(self, g: GameState, call: dict[str, Any]) -> None:
        assert g.rally is not None
        before = g.score()
        rally_view = g.rally.view()
        after = self._recompute(g)
        winner = call.get("team_id") if call.get("points") else None
        self.state.close_rally(
            {
                "game_id": g.game["game_id"],
                "rally_no": g.rally.rally_no,
                "status": "closed",
                "t_start_s": g.rally.t_start_s,
                "t_end_s": float(call["t_game_s"]),
                "winner_team_id": winner,
                "summary": {
                    "shots": rally_view["shots"],
                    "duration_s": round(rally_view["duration_s"], 3),
                    "outcome": call["outcome"],
                    "let": call["outcome"] == "let",
                },
            }
        )
        self._write_moment(g, call, rally_view, before, after)
        g.rally = None
        if after.match_over and g.game["status"] == "live":
            self._info(
                g,
                f"Game, {g.team(after.winner).get('name', after.winner)}. {after.display(*g.sides)}",
                emotion="excited",
            )
            self.end_game(g.game["game_id"])
        elif after.game_over and not before.game_over:
            self._info(g, f"Game, {g.team(after.winner).get('name', after.winner)}")

    def _write_moment(
        self, g: GameState, call: dict[str, Any], rally_view: dict[str, Any], before: GameScore, after: GameScore
    ) -> None:
        team = call.get("team_id")
        m = moment_from_call(
            call,
            rally={**rally_view, "t_start_s": g.rally.t_start_s if g.rally else call["t_game_s"] - 2},
            score_after=after.display(*g.sides),
            game_point=bool(team and team in before.game_point_for),
            match_point=bool(team and team in before.match_point_for),
            game_winner=bool(after.game_over and not before.game_over and after.winner == team),
            team_name=str(g.team(team).get("name", team)),
        )
        if m is not None:
            g.moments[m["moment_id"]] = m
            g.call_moment[call["id"]] = m["moment_id"]
            self._post_game(self.state.upsert_moment, m)

    def _recompute(self, g: GameState) -> GameScore:
        gs = g.score()
        self.state.set_score(score_rows(g.game["game_id"], gs, self.now_ms(), g.sides))
        g.game["server_team_id"] = gs.server
        return gs

    def _game_view(self, g: GameState) -> dict[str, Any]:
        gs = g.score()
        return {
            "status": g.game["status"],
            "rally_no": g.rally_no,
            "points": gs.points,
            "games": gs.games,
            "server_side": gs.server,
            "game_point_for": gs.game_point_for,
            "match_point_for": gs.match_point_for,
            "game_over": gs.game_over,
        }

    def _info(
        self,
        g: GameState,
        text: str,
        *,
        speech: str | None = None,
        emotion: str | None = None,
        points: int = 0,
        team_id: str | None = None,
        kind: str = "info",
        outcome: str = "info",
        rule_id: str = "info",
    ) -> dict[str, Any]:
        call: dict[str, Any] = {
            "schema": "trophy.call.v1",
            "id": new_ulid(),
            "game_id": g.game["game_id"],
            "t_game_s": g.last_t_s,
            "rule_id": rule_id,
            "rule_version": g.rule_version,
            "kind": kind,
            "outcome": outcome,
            "p": 1.0,
            "p_source": "manual",
            "tier": "AUTO",
            "shown": "auto",
            "text": text[:80],
            "speech": speech or text,
            "cue": {"beep": "none", "flash": "none"},
            "event_ids": [],
            "evidence": [],
            "status": "final",
            "created_at_ms": self.now_ms(),
        }
        if g.rally_no:
            call["rally_no"] = g.rally_no
        if emotion:
            call["emotion"] = emotion
        if team_id:
            call["team_id"] = team_id
        if points:
            call["points"] = points
        g.calls.append(call)
        self.state.post_call(call)
        return call

    # ------------------------------------------------------------ control commands

    def handle_ctl(self, cmd: dict[str, Any]) -> None:
        name = cmd["cmd"]
        game_id = cmd["game_id"]
        args = cmd.get("args") or {}
        by = cmd.get("by_cam_id")
        if name == "create_game":
            if game_id not in self.games:
                self.create_game(
                    game_id, args["sport"], t0_ms=args.get("t0_ms"), teams=args.get("teams"), params=args.get("params")
                )
            return
        if name == "feed_schedule":
            self._feed_schedule(game_id, args)
            return
        g = self.games.get(game_id)
        if g is None:
            log.warning("ctl %s for unknown game %s", name, game_id)
            return
        handler = getattr(self, f"_ctl_{name}", None)
        if handler is None:
            log.warning("ctl %s not handled", name)
            return
        handler(g, args, by)

    def _ctl_register_camera(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        self.state.upsert_camera(
            {
                "cam_id": a["cam_id"],
                "game_id": g.game["game_id"],
                "label": a.get("label", ""),
                "role": a.get("role", "cam"),
                "device": a.get("device") or {},
                "calibration": None,
                "calib_trusted": False,
                "connected": True,
                "fps_in": 0.0,
                "sync_err_ms": 0.0,
                "last_seen_ms": self.now_ms(),
            }
        )

    def _ctl_camera_health(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        self.state.upsert_camera(
            {
                "cam_id": a["cam_id"],
                "game_id": g.game["game_id"],
                "label": a.get("label", ""),
                "role": a.get("role", "cam"),
                "calib_trusted": a.get("calib_trusted", False),
                "connected": bool(a.get("connected", True)),
                "fps_in": float(a.get("fps_in", 0.0)),
                "sync_err_ms": float(a.get("sync_err_ms", 0.0)),
                "last_seen_ms": float(a.get("last_seen_ms") or self.now_ms()),
            }
        )

    def _ctl_set_calibration(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        calib = a.get("calibration") or {}
        g.calib_untrusted = not bool(calib.get("trusted", False))
        self.state.upsert_camera(
            {
                "cam_id": a["cam_id"],
                "game_id": g.game["game_id"],
                "label": a.get("label", ""),
                "role": a.get("role", "cam"),
                "calibration": calib,
                "calib_trusted": bool(calib.get("trusted", False)),
                "connected": True,
                "fps_in": 0.0,
                "sync_err_ms": 0.0,
                "last_seen_ms": self.now_ms(),
            }
        )

    def _ctl_start_game(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        self.start_game(g.game["game_id"], a.get("first_server"))

    # ------------------------------------------------------------ replayed feeds (D-42)

    def _feed_schedule(self, game_id: str, a: dict[str, Any]) -> None:
        """A scenario goes live: reset the game to its sport and teams (reset), then write one feed row per angle."""
        g = self.games.get(game_id)
        if a.get("reset") or g is None:
            t0 = g.game["t0_ms"] if g is not None else a.get("t0_ms")
            sport = str(a.get("sport") or (g.game["sport"] if g else "table_tennis"))
            teams = [dict(t) for t in a.get("teams") or []] or None
            g = self.create_game(game_id, sport, t0_ms=t0, teams=teams, params=dict(a.get("params") or {}))
            self.start_game(game_id)
        now = self.now_ms()
        for f in a.get("feeds") or []:
            row = {**f, "game_id": game_id, "updated_at_ms": now}
            g.feeds[row["cam_id"]] = row
            self.state.upsert_feed(row)

    def _ctl_viewer_status(self, g: GameState, a: dict[str, Any], by: str | None) -> None:
        if not by:
            return
        self.state.upsert_viewer(
            {
                "viewer_id": by,
                "game_id": g.game["game_id"],
                "cam_id": str(a.get("cam_id") or ""),
                "name": str(a.get("name") or "")[:40],
                "connected": bool(a.get("connected", True)),
                "playing": bool(a.get("playing", False)),
                "drift_ms": round(float(a.get("drift_ms") or 0.0), 1),
                "last_seen_ms": self.now_ms(),
            }
        )

    # ------------------------------------------------------------ challenges (D-44)

    def drain(self) -> int:
        """Handle commands queued from other threads (the background verdict). Called by the live loop."""
        n = 0
        while True:
            try:
                cmd = self.inbox.get_nowait()
            except queue.Empty:
                return n
            n += 1
            try:
                self.handle_ctl(cmd)
            except Exception:  # noqa: BLE001 - a bad internal command must not stop the referee
                log.exception("internal ctl failed")

    def _ctl_challenge(self, g: GameState, a: dict[str, Any], by: str | None) -> None:
        call = next((c for c in g.calls if c["id"] == a["call_id"]), None)
        if call is None or call["status"] not in ("final", "upheld") or call.get("kind") == "info":
            log.warning("challenge: call %s not challengeable", a.get("call_id"))
            return
        if any(ch["call_id"] == call["id"] and ch["status"] == "open" for ch in g.challenges.values()):
            return
        ch = {
            "challenge_id": new_ulid(),
            "game_id": g.game["game_id"],
            "call_id": call["id"],
            "by_cam_id": by or "",
            "status": "open",
            "result": None,
            "created_at_ms": self.now_ms(),
            "resolved_at_ms": None,
        }
        g.challenges[ch["challenge_id"]] = ch
        call["status"] = "challenged"
        self.state.open_challenge(ch)
        self._info(g, f"Challenge: {call['text']}", speech="Challenge. Let's look at the replay.", rule_id="challenge")
        rule = g.rules.by_id(call["rule_id"])
        if self.decider is not None:
            g.decided.discard(call["id"])  # a challenge always gets a fresh re-check
            self._spawn_decide(g, call, rule.rule if rule else {}, challenge_id=ch["challenge_id"])
        else:  # no model voter configured: the geometry alone decides, at once
            self.inbox.put(self._verdict_cmd(g, ch, call, {call["outcome"]: call["p"]}, []))

    def _verdict_cmd(
        self, g: GameState, ch: dict[str, Any], call: dict[str, Any], probs: dict[str, float], votes: list[dict]
    ) -> dict[str, Any]:
        """The automatic resolution of a challenge from the blended probabilities (uncalibrated) and the votes."""
        p_orig = float(probs.get(call["outcome"], call["p"]))
        if p_orig >= UPHOLD_AT:
            result = "upheld"
        elif p_orig <= OVERTURN_AT:
            result = "overturned"
        else:
            result = "players_decide"
        claude = next((v for v in votes if v.get("backend") == "claude" and v.get("rationale")), None)
        what = call["text"].rstrip(".")
        head = {
            "upheld": f"The call stands: {what}.",
            "overturned": f"Overturned: {what} is reversed. Replay the point.",
            "players_decide": f"Too close to call: {what}. Players decide.",
        }[result]
        facts = [f"Replay shows {self._plain(g, call['why'])}." if call.get("why") else ""]
        if call.get("source") == "annotated":
            facts.append("From the marked events on the recording.")
        if claude:
            first = re.split(r"(?<=[.!?])\s", str(claude["rationale"]).strip(), maxsplit=1)[0].rstrip(".")
            facts.append(f"Claude agrees: {first}." if claude.get("choice") == call["outcome"] else f"Claude: {first}.")
        facts.append(f"Confidence {round(p_orig * 100)}% (uncalibrated).")
        explanation = ""
        for part in (f for f in [head, *facts] if f):  # whole sentences only, 240 chars at most
            if len(explanation) + len(part) + 1 > 240:
                break
            explanation = f"{explanation} {part}".strip()
        return {
            "cmd": "resolve_challenge",
            "game_id": g.game["game_id"],
            "by_cam_id": None,
            "args": {
                "challenge_id": ch["challenge_id"],
                "result": result,
                "explanation": explanation,
                "auto": True,
                "p_original": round(p_orig, 3),
            },
        }

    @staticmethod
    def _plain(g: GameState, why: str) -> str:
        """Measurement facts in words a player would say: line names and sigma spelled out."""
        a, b = g.sides
        words = {
            "end_A": f"{g.team(a).get('name', a)}'s end line",
            "end_B": f"{g.team(b).get('name', b)}'s end line",
            "side_left": "the left sideline",
            "side_right": "the right sideline",
        }
        for k, v in words.items():
            why = why.replace(k, v)
        name = {a: g.team(a).get("name", a), b: g.team(b).get("name", b)}
        why = re.sub(
            r"net (into|touch) from side (\w+)",
            lambda m: f"the ball {'went into' if m[1] == 'into' else 'touched'} the net "
            f"from {name.get(m[2], m[2])}'s side",
            why,
        )
        return re.sub(r",?\s*σ\s*(\d+)\s*cm", r", give or take \1 cm", why)

    def challenge_verdict(self, req: dict[str, Any], res: dict[str, Any]) -> None:
        """From the decider's thread: queue the verdict for the loop (the engine is single-threaded)."""
        g = self.games.get(req["game_id"])
        ch = g.challenges.get(req.get("challenge_id", "")) if g else None
        call = next((c for c in g.calls if c["id"] == req["call_id"]), None) if g else None
        if g is None or ch is None or call is None or ch["status"] != "open":
            return
        p_final = dict(res.get("p_final") or {})
        probs = {call["outcome"]: float(p_final.get(req.get("original_option") or call["outcome"], call["p"]))}
        self.inbox.put(self._verdict_cmd(g, ch, call, probs, list(res.get("votes") or [])))

    def _ctl_resolve_challenge(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        ch = g.challenges.get(a["challenge_id"])
        if ch is None or ch["status"] != "open":
            return
        result = a["result"]
        call = next(c for c in g.calls if c["id"] == ch["call_id"])
        call["status"] = {"upheld": "upheld", "overturned": "overturned"}.get(result, "players_decide")
        explanation = str(a.get("explanation") or "")[:240] or None
        ch.update(
            {
                "status": "resolved",
                "result": result,
                "resolved_at_ms": self.now_ms(),
                "decided_by": "auto" if a.get("auto") else "judge",
                "p_original": a.get("p_original"),
                "explanation": explanation,
            }
        )
        self.state.resolve_challenge(ch)
        if explanation:
            call["explanation"] = explanation
        self.state.post_call(call)  # status + explanation on the challenged call itself
        if result == "overturned":
            rep = a.get("replacement") or {}
            new = dict(call)
            outcome = rep.get("outcome") or "let"
            new.update(
                {
                    "id": new_ulid(),
                    "outcome": outcome,
                    "p": 1.0,
                    "p_source": "manual" if not a.get("auto") else "ensemble",
                    "tier": "AUTO",
                    "shown": "auto",
                    "status": "final",
                    "supersedes": call["id"],
                    "created_at_ms": self.now_ms(),
                    "text": f"Overturned: {outcome.replace('_', ' ')}"[:80],
                    "speech": explanation or f"Overturned. {outcome.replace('_', ' ')}.",
                    "explanation": explanation,
                    "at_fault": None,
                    "cue": {"beep": "double", "flash": "none"},
                }
            )
            if rep.get("team_id"):
                new["team_id"] = rep["team_id"]
                new["points"] = call.get("points") or 1
            else:
                new.pop("team_id", None)
                new.pop("points", None)
            g.calls.append(new)
            self.state.post_call(new)
        else:
            label = "Upheld" if result == "upheld" else "Players decide"
            self._info(
                g,
                f"{label}: {call['text']}",
                speech=explanation or ("Call stands." if result == "upheld" else "Too close. Players decide."),
                rule_id="challenge_verdict",
            )
        mid = g.call_moment.get(call["id"])
        if mid and result in ("upheld", "overturned"):
            m = rescore_for_challenge(g.moments[mid], result)
            g.moments[mid] = m
            self._post_game(self.state.upsert_moment, m)
        self._recompute(g)

    def _ctl_set_server(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        want = str(a["team_id"])
        if g.score().server != want:
            g.first_server = g.sides[1] if g.first_server == g.sides[0] else g.sides[0]
        if g.rally is not None and g.rally.bounces == 0:
            g.rally.server_side = want
        self._recompute(g)
        self._info(g, f"Server: {g.team(want).get('name', want)}")

    def _ctl_undo_last_call(self, g: GameState, _a: dict[str, Any], _by: str | None) -> None:
        for c in reversed(g.calls):
            if c.get("points") and c["status"] in ("final", "upheld", "challenged"):
                c["status"] = "voided"
                self.state.update_call_status(c["id"], "voided")
                self._recompute(g)
                self._info(g, f"Undone: {c['text']}", speech="Last call undone.")
                return

    def _ctl_adjust_score(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        delta = int(a["delta"])
        name = g.team(a["team_id"]).get("name", a["team_id"])
        self._info(
            g,
            f"Score adjusted: {name} {delta:+d}",
            kind="score_update",
            outcome="adjust",
            points=delta,
            team_id=a["team_id"],
            rule_id="adjust_score",
        )
        self._recompute(g)

    def _ctl_end_period(self, g: GameState, _a: dict[str, Any], _by: str | None) -> None:
        g.game["period_no"] = int(g.game.get("period_no", 1)) + 1
        self.state.upsert_game(g.game)

    def _ctl_end_game(self, g: GameState, _a: dict[str, Any], _by: str | None) -> None:
        self.end_game(g.game["game_id"])

    def end_game(self, game_id: str) -> None:
        g = self.games[game_id]
        if g.rally is not None:
            self.state.close_rally(
                {
                    "game_id": game_id,
                    "rally_no": g.rally.rally_no,
                    "status": "voided",
                    "t_start_s": g.rally.t_start_s,
                    "t_end_s": g.last_t_s,
                    "winner_team_id": None,
                    "summary": None,
                }
            )
            g.rally = None
        g.game["status"] = "ended"
        self.state.upsert_game(g.game)
        bp = best_play(list(g.moments.values()))
        if bp is not None:
            bp["is_best_play"] = True
            self._post_game(self.state.set_best_play, game_id, bp["moment_id"], list(bp.get("reasons", [])))

    def _ctl_ask_logged(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        self.state.post_ask(
            {
                "ask_id": new_ulid(),
                "game_id": g.game["game_id"],
                "sport": g.game["sport"],
                "question": a["question"],
                "answer": a["answer"],
                "citations": a.get("citations") or [],
                "moss_ms": a.get("moss_ms"),
                "latency_ms": float(a.get("latency_ms", 0)),
                "created_at_ms": self.now_ms(),
                # the referee's fields (interfaces-v1 section 20; the ask table has these columns since #27)
                **{k: a[k] for k in ("speech", "kind", "check", "p", "calibrated") if a.get(k) is not None},
                **({"by_cam_id": a.get("by_cam_id") or _by} if (a.get("by_cam_id") or _by) else {}),
            }
        )

    # ------------------------------------------------------------ the referee's checks (interfaces-v1 section 20)

    def _check_time(self, g: GameState, args: dict[str, Any]) -> tuple[float | None, dict[str, Any] | None]:
        """args.t_game_s, else ref: last (the newest call) | last_rally | call:<id>. Returns (t, rally window)."""
        if args.get("t_game_s") is not None:
            return float(args["t_game_s"]), None
        ref = str(args.get("ref") or "last")
        calls = [c for c in g.calls if c.get("kind") != "info" and c.get("status") not in ("voided", "overturned")]
        if ref.startswith("call:"):
            c = next((c for c in g.calls if c["id"] == ref[5:]), None)
            return (float(c["t_game_s"]), None) if c else (None, None)
        if ref == "last_rally":
            return None, {"t0": args.get("t0_s"), "t1": args.get("t1_s"), "rally_no": args.get("rally_no")}
        return (float(calls[-1]["t_game_s"]), None) if calls else (None, None)

    def _ctl_run_check(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        t0 = time.perf_counter()
        name = str(a["check"])
        t, window = self._check_time(g, a.get("args") or {})
        reply: dict[str, Any] = {"check": name, "calibrated": False}
        if self.check_runner is None:
            reply["error"] = "no_data"  # no fused 3D track in this session (the one-camera path has none)
        elif t is None and window is None:
            reply["error"] = "no_data"
        else:
            try:
                reply = {**reply, **self.check_runner(g.game["game_id"], name, t, window, a.get("args") or {})}
            except KeyError:
                reply["error"] = "no_such_check"
            except Exception as e:  # noqa: BLE001 - the referee gets an honest error, never a made-up answer
                reply["error"] = f"failed:{type(e).__name__}"
        reply["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        self._reply(a.get("reply_to"), reply)

    def _ctl_request_check(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """No session check answers the question: a Droid writes one (a new_check job, in its jailed sandbox, gated on
        the session's own track) and the answer goes to reply_to when it is ready. Without a fused 3D track there is
        nothing to write a check over, so the referee hears that at once instead of waiting 95 s."""
        reply_to = a.get("reply_to")
        if self.new_check is None:
            self._reply(reply_to, {"check": "new", "calibrated": False, "error": "no_data", "latency_ms": 0.0})
            return
        args = a.get("args") or {}
        t, window = self._check_time(g, args)
        if window and window.get("t0") is not None:
            query = {"t0": float(window["t0"]), "t1": float(window.get("t1") or window["t0"] + 3.0)}
        elif t is not None:
            query = {"t0": t - 1.5, "t1": t + 1.5, "t_s": t}
        else:
            query = {}
        self.new_check(
            g.game["game_id"], str(a.get("question") or ""), str(a.get("check_hint") or ""), query,
            lambda payload: self._reply(reply_to, payload),
        )  # fmt: skip

    def _reply(self, stream: Any, payload: dict[str, Any]) -> None:
        if not stream or self.reply is None:
            log.warning("check reply dropped (no reply_to or no Redis): %s", payload.get("check"))
            return
        try:
            self.reply(str(stream), payload)
        except Exception:  # noqa: BLE001
            log.exception("check reply to %s failed", stream)

    def _ctl_bookmark(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        t = float(a.get("t_game_s", g.last_t_s))
        m = {
            "moment_id": new_ulid(),
            "game_id": g.game["game_id"],
            "kind": "bookmark",
            "t_game_s": t,
            "t_start_s": max(0.0, t - 8.0),
            "t_end_s": t + 0.5,
            "label": str(a.get("label") or "Bookmark")[:80],
            "team_id": None,
            "track_id": None,
            "call_id": None,
            "rally_no": g.rally_no or None,
            "score_after": g.score().display(*g.sides),
            "tags": ["bookmark"],
            "highlight_score": 0.1,
            "reasons": ["bookmarked by a player"],
            "is_best_play": False,
            "thumb_t_s": t,
        }
        g.moments[m["moment_id"]] = m
        self._post_game(self.state.upsert_moment, m)

    def _ctl_clip_that(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """Trigger-to-play: the moment that ends within [t - 8 s, t + 0.5 s] gets the `clipped` tag."""
        t = float(a.get("t_game_s", g.last_t_s))
        cands = [m for m in g.moments.values() if t - 8.0 <= float(m.get("t_end_s", m["t_game_s"])) <= t + 0.5]
        if not cands:
            return
        m = max(cands, key=lambda m: float(m.get("t_end_s", m["t_game_s"])))
        m["tags"] = list(dict.fromkeys(list(m.get("tags", [])) + ["clipped"]))
        self._post_game(self.state.upsert_moment, m)

    def _ctl_review_call(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        call = next((c for c in g.calls if c["id"] == a["call_id"]), None)
        if call is None:
            return
        truth = (
            call["outcome"] if a["result"] == "confirm" else (a.get("replacement") or {}).get("outcome", "corrected")
        )
        self.labels_dir.joinpath(g.game["sport"]).mkdir(parents=True, exist_ok=True)
        with self.labels_dir.joinpath(g.game["sport"], f"{g.game['game_id']}.jsonl").open("a", encoding="utf8") as f:
            import json

            f.write(
                json.dumps(
                    {
                        "t_game_s": call["t_game_s"],
                        "rule_id": call["rule_id"],
                        "truth_outcome": truth,
                        "labeller": "judge",
                        "source": "review",
                    }
                )
                + "\n"
            )
        if a["result"] == "correct" and call.get("points"):
            call["status"] = "voided"
            self.state.update_call_status(call["id"], "voided")
            rep = a.get("replacement") or {}
            if rep.get("team_id"):
                self._info(
                    g,
                    f"Corrected: point {g.team(rep['team_id']).get('name')}",
                    kind="point",
                    outcome=str(rep.get("outcome", "corrected")),
                    points=call.get("points") or 1,
                    team_id=rep["team_id"],
                    rule_id=call["rule_id"],
                )
            self._recompute(g)

    def _post_game(self, write, *args: Any) -> None:
        """Moments and the best play are post-game data: a failed Spacetime write is logged, never raised, so it can't
        leave a rally open or stop scoring (review blocker 3)."""
        try:
            write(*args)
        except Exception:  # noqa: BLE001 - the live game must go on
            log.exception("post-game write %s failed", getattr(write, "__name__", write))

    # ------------------------------------------------------------ helpers for replay / tests

    def remember_event(self, ev: dict[str, Any]) -> None:
        g = self.games.get(str(ev.get("game_id")))
        if g is not None:
            cache = getattr(g, "_last_events", None)
            if cache is None:
                cache = {}
                g._last_events = cache  # type: ignore[attr-defined]
            cache[str(ev.get("id"))] = ev
            if len(cache) > 200:
                for k in list(cache)[:100]:
                    cache.pop(k, None)

    def feed(self, ev: dict[str, Any]) -> list[dict[str, Any]]:
        self.remember_event(ev)
        self.record_session_event(ev)
        return self.handle_event(ev)


def _pre_serve_floor_bounce(ev: dict[str, Any], g: GameState) -> bool:
    if ev.get("type") != "bounce" or (ev.get("payload") or {}).get("surface") != "floor":
        return False
    return g.rally is None or (g.rally.phase == "serve" and g.rally.bounces == 0 and not g.rally_hit_seen)


def render_text(template: str, ctx: dict[str, Any]) -> str:  # re-exported for tests
    return render(template, ctx)


def _strip_none(obj: Any) -> Any:
    """CEL has no comparison with null on maps, and ``has(m.k)`` needs the key absent: drop None values for rules."""
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none(v) for v in obj]
    return obj
