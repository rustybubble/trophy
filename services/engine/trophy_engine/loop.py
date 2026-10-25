"""``trophy-engine run``: the live loop. Redis ``ev:*`` (consumer group ``engine``) and ``ctl:engine`` in, Spacetime
out. With ``--field`` the engine also consumes fused 3D ball samples (D-36): from the Redis stream ``trk:ball3d``, or
``--track3d <file.track3d.jsonl>`` replayed on the clock; the session's check library (``--checks``, default the
golden ``sports/<sport>/checks``) turns them into events through ``TrackEventer``. Events after a scored point are
dropped until the next rally starts (the ball is dead whatever the track says). Background AI votes run only when
every voter's key is present (``--votes``); there is no stub voter.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import redis
from trophy.streams import CTL_ENGINE, EVENT_STREAMS, EventConsumer, parse_ctl

from .ask import AskConfigError, Phraser, TrackStore, make_app, serve
from .checks.events import TrackEventer
from .checks.library import load_field, load_library
from .decide import BackgroundDecider, BitdeerVoter, ClaudeVoter, GeminiVoter, VoterConfigError
from .engine import Engine
from .state import MemoryState, SpacetimeState, StateWriter
from .track_source import RedisTrackSource, replay_file

ROOT = Path(__file__).resolve().parents[3]
log = logging.getLogger("trophy.engine")


def _dotenv(root: Path = ROOT) -> dict[str, str]:
    p = root / ".env"
    out: dict[str, str] = {}
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip()
    return out


def build_decider(env: dict[str, str], state: StateWriter, engine: Engine) -> BackgroundDecider:
    """All three voters, each requiring its own key. A missing key is a configuration error, not a silent skip."""
    voters = [ClaudeVoter.from_env(env), GeminiVoter.from_env(env), BitdeerVoter.from_env(env)]

    def on_result(req: dict[str, Any], res: dict[str, Any]) -> None:
        g = engine.games.get(req["game_id"])
        call = next((c for c in g.calls if c["id"] == req["call_id"]), None) if g else None
        if call is not None:
            call["suggested"] = res["suggested"]
            state.update_call_status(call["id"], call["status"], suggested=res["suggested"])

    return BackgroundDecider(voters, state.post_ai_vote, on_result)


class TrackFeeder:
    """Fused samples -> checks -> events -> the engine, with the dead-ball rule after a scored point."""

    def __init__(self, engine: Engine, eventer: TrackEventer, game_id: str, store: TrackStore | None = None) -> None:
        self.engine = engine
        self.eventer = eventer
        self.game_id = game_id
        self.store = store  # the ask service's memory of this game, when it runs
        self.scored_rally: int | None = None
        self.n_samples = 0
        self.n_events = 0

    def feed(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        self.n_samples += 1
        if self.store is not None:
            self.store.push(row)
        calls = self._handle(self.eventer.push(row))
        if self.store is not None:
            if self.eventer.last_phases is not None:
                self.store.set_segments(self.eventer.last_phases["segments"])
            for c in calls:
                self.store.add_call(c)
            if calls:
                g = self.engine.games.get(self.game_id)
                if g is not None:
                    sc = g.score()
                    self.store.set_score(
                        {"points": dict(sc.points), "server": sc.server, "display": sc.display(*g.sides)}
                    )
        return calls

    def tick(self, now_s: float) -> list[dict[str, Any]]:
        return self._handle(self.eventer.tick(now_s))

    def _handle(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for ev in events:
            rn = ev.pop("rally_no_hint", None)
            if self.scored_rally is not None and rn == self.scored_rally:
                continue  # the point was called; the rest of this rally's track is the ball being picked up
            self.n_events += 1
            out = self.engine.feed(ev)
            calls += out
            if any(c.get("points") or c.get("outcome") == "let" for c in out):
                self.scored_rally = rn
        return calls


def make_feeder(
    engine: Engine, game_id: str, sport: str, field_path: Path, checks_dir: Path | None, store: TrackStore | None = None
) -> TrackFeeder:
    fld = load_field(field_path)
    lib = load_library(checks_dir or ROOT / "sports" / sport / "checks")
    eventer = TrackEventer(lib, fld, game_id=game_id, sport=sport)
    if store is not None:
        store.library = lib
        store.set_field(fld)
    log.info(
        json.dumps(
            {
                "svc": "engine",
                "msg": "checks loaded",
                "dir": str(lib.path),
                "checks": lib.names(),
                "calibrated": lib.calibrated,
            }
        )
    )
    return TrackFeeder(engine, eventer, game_id, store)


def start_ask(env: dict[str, str], store: TrackStore, session_dir: Path) -> Any:
    """Ask the ref over the live checks (D-36 §5). Needs ANTHROPIC_API_KEY: without it the service answers 503
    not_configured, never a made-up answer."""
    phraser = None
    err = None
    try:
        phraser = Phraser.from_env(env)
    except AskConfigError as e:
        err = str(e)
        log.warning(json.dumps({"svc": "engine", "msg": "ask: Claude not configured", "detail": err}))
    app = make_app(store, phraser, session_dir=session_dir, config_error=err)
    server = serve(app)
    log.info(json.dumps({"svc": "engine", "msg": "ask service up", "port": getattr(server.config, "port", None)}))
    return server


CHECK_ALIASES = {"bounce_side": "in_out", "edge_hit": "in_out", "double_bounce": "bounces"}  # the referee's catalog


def make_check_runner(store: TrackStore):
    """run_check over the session's fused 3D track (interfaces-v1 section 20): the referee's check names, a moment or
    a rally window -> the check's own CheckResult fields plus the inputs it ran with. KeyError = no such check."""

    def run_check(game_id: str, name: str, t: float | None, window: dict[str, Any] | None, args: dict[str, Any]):
        lib = CHECK_ALIASES.get(name, name)
        if lib not in store.library.checks:
            raise KeyError(name)
        snap = store.snapshot()
        track, fld = snap["track"], store.field
        if fld is None or not len(track.samples):
            return {"error": "no_data"}
        seg = store.rally(int(window["rally_no"])) if window and window.get("rally_no") else store.last_rally()
        if window and window.get("t0") is not None:
            t0, t1 = float(window["t0"]), float(window.get("t1") or track.t1)
        elif t is not None and seg is None:
            t0, t1 = t - 1.5, t + 1.5
        elif seg is not None:
            t0 = float(seg["t_start_s"])
            t1 = float(seg["t_end_s"]) if seg.get("t_end_s") is not None else track.t1
        else:
            t0, t1 = track.t0, track.t1
        if lib == "in_out":
            q = {"t_s": t if t is not None else t1}
        elif lib == "serve_toss":
            q = {"t_start": t0}
        else:
            q = {"t0": t0, "t1": t1}
        res = store.library.run(lib, track, fld, None, **q)
        return {
            "check": name,
            "verdict": res.get("verdict") if isinstance(res.get("verdict"), str) else None,
            "p": res.get("p"),
            "evidence": {
                **(res.get("evidence") or {}),
                **({"result": res["verdict"]} if not isinstance(res.get("verdict"), str) else {}),
            },
            "inputs": {"check": lib, **q, "game_id": game_id},
            "calibrated": bool(res.get("calibrated", False)),
        }

    return run_check


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trophy-engine", description="Trophy rule engine: events + ctl in, calls out")
    ap.add_argument("--redis", default=None, help="REDIS_URL (default from env/.env)")
    ap.add_argument("--state", choices=["spacetime", "memory"], default="spacetime")
    ap.add_argument("--votes", action="store_true", help="run decide() voters (needs ANTHROPIC/GEMINI/BITDEER keys)")
    ap.add_argument("--modules", type=Path, default=ROOT / "sports")
    ap.add_argument("--log-json", action="store_true")
    ap.add_argument(
        "--exit-when-idle", type=float, default=0.0, help="stop after this many seconds without events (tests, replays)"
    )
    ap.add_argument(
        "--dead-after-point",
        type=float,
        default=2.0,
        help="after a point called on a bounce, ignore events until ball_dead or this many seconds (0 = off)",
    )
    ap.add_argument(
        "--server-from-first-hit",
        action="store_true",
        help="real play: the first racket hit of a rally names the server",
    )
    ap.add_argument(
        "--field", type=Path, default=None, help="field.json: consume fused 3D samples through the checks (D-36)"
    )
    ap.add_argument(
        "--checks", type=Path, default=None, help="the session's checks/ (default sports/<sport>/checks, uncalibrated)"
    )
    ap.add_argument(
        "--track3d", type=Path, default=None, help="replay a *.track3d.jsonl instead of the trk:ball3d stream"
    )
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed (0 = as fast as possible)")
    ap.add_argument("--game-id", default="g_track3d1", help="game to create for --track3d replay (memory state)")
    ap.add_argument("--sport", default="table_tennis")
    ap.add_argument("--ask", action="store_true", help="serve POST /ask over the live checks (needs ANTHROPIC_API_KEY)")
    ap.add_argument(
        "--session-dir", type=Path, default=None, help="where pending checks are written (data/local/sessions/<id>)"
    )
    a = ap.parse_args(argv)
    env = {**_dotenv(), **os.environ}
    logging.basicConfig(level=logging.INFO, format="%(message)s" if a.log_json else "%(asctime)s %(name)s %(message)s")
    state: StateWriter = SpacetimeState() if a.state == "spacetime" else MemoryState()
    engine = Engine(
        state,
        modules_dir=a.modules,
        dead_after_point_s=a.dead_after_point,
        server_from_first_hit=a.server_from_first_hit,
    )
    if a.votes:
        try:
            engine.decider = build_decider(env, state, engine)
        except VoterConfigError as e:
            print(f"--votes needs every voter key: {e}", file=sys.stderr)
            return 3
    if a.track3d is not None:
        # replay a recorded 3D track through the checks and the engine, no Redis needed
        if a.field is None:
            a.field = a.track3d.parent / "field.json"
        engine.create_game(a.game_id, a.sport, t0_ms=0, params={"replay": str(a.track3d)})
        engine.start_game(a.game_id, "A")
        store = (
            TrackStore(load_library(a.checks or ROOT / "sports" / a.sport / "checks"), sport=a.sport) if a.ask else None
        )
        feeder = make_feeder(engine, a.game_id, a.sport, a.field, a.checks, store)
        if store is not None:
            start_ask(env, store, a.session_dir or ROOT / "data" / "local" / "sessions" / a.game_id)
        t_last = 0.0
        for row, now_s in replay_file(a.track3d, speed=a.speed):
            t_last = now_s
            for c in feeder.feed(row):
                log.info(
                    json.dumps(
                        {
                            "svc": "engine",
                            "game_id": a.game_id,
                            "msg": "call",
                            "rule": c["rule_id"],
                            "text": c["text"],
                            "t_game_s": c["t_game_s"],
                        }
                    )
                )
        for c in feeder.tick(t_last + 5.0):
            log.info(
                json.dumps(
                    {"svc": "engine", "game_id": a.game_id, "msg": "call", "rule": c["rule_id"], "text": c["text"]}
                )
            )
        log.info(
            json.dumps(
                {
                    "svc": "engine",
                    "msg": "replay done",
                    "samples": feeder.n_samples,
                    "events": feeder.n_events,
                    "calls": len(engine.games[a.game_id].calls),
                }
            )
        )
        if store is not None:
            log.info(json.dumps({"svc": "engine", "msg": "ask service stays up for questions (ctrl-c to stop)"}))
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                pass
        return 0
    r = redis.Redis.from_url(a.redis or env.get("REDIS_URL") or "redis://127.0.0.1:6379/0")
    consumer = EventConsumer(r, group="engine", consumer=f"engine-{os.getpid()}", streams=list(EVENT_STREAMS))
    ctl_last = _stream_tail(r, CTL_ENGINE)  # start after what is there; never re-arm at "$", which drops commands
    track_src = RedisTrackSource(r) if a.field is not None else None
    feeders: dict[str, TrackFeeder] = {}  # game_id -> feeder, created when the game goes live
    ask_store: TrackStore | None = None
    if a.field is not None:  # the session's 3D track: the referee's run_check and (with --ask) POST /ask read it
        ask_store = TrackStore(load_library(a.checks or ROOT / "sports" / a.sport / "checks"), sport=a.sport)
        engine.check_runner = make_check_runner(ask_store)
        if a.ask:
            start_ask(env, ask_store, a.session_dir or ROOT / "data" / "local" / "sessions" / "live")

    def reply(stream: str, payload: dict[str, Any]) -> None:
        r.xadd(stream, {"json": json.dumps(payload)}, maxlen=10, approximate=True)
        r.expire(stream, 300)

    engine.reply = reply
    log.info(
        json.dumps(
            {"svc": "engine", "msg": "started", "state": a.state, "votes": a.votes, "track3d": a.field is not None}
        )
    )
    idle_since = time.monotonic()
    while True:
        if track_src is not None:
            for row, _now_s in track_src.poll(block_ms=10):
                gid = str(
                    row.get("game_id") or next((g for g, st in engine.games.items() if st.game["status"] == "live"), "")
                )
                g = engine.games.get(gid)
                if g is None or g.game["status"] != "live":
                    continue
                f = feeders.get(gid)
                if f is None:
                    try:
                        f = feeders[gid] = make_feeder(engine, gid, g.game["sport"], a.field, a.checks, ask_store)
                    except Exception:  # noqa: BLE001 - a bad library must not stop the referee's other inputs
                        log.exception("checks failed to load")
                        continue
                t0 = time.perf_counter()
                for c in f.feed(row):
                    log.info(
                        json.dumps(
                            {
                                "svc": "engine",
                                "game_id": gid,
                                "msg": "call",
                                "rule": c["rule_id"],
                                "text": c["text"],
                                "ms": round((time.perf_counter() - t0) * 1000, 1),
                                "source": "track3d",
                            }
                        )
                    )
        rejected0 = consumer.rejected
        ctl_last, n = step(engine, consumer, r, ctl_last)
        if a.exit_when_idle > 0:
            if n or consumer.rejected != rejected0:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since > a.exit_when_idle:
                return 0


def step(engine: Engine, consumer: EventConsumer, r: redis.Redis, ctl_last: str, block_ms: int = 50) -> tuple[str, int]:
    """One pass of the live loop: new events into the engine, then new ctl commands. Returns the ctl cursor and how
    many entries (events, commands, rejected entries) it handled. A bad
    event, a malformed entry or a failing command is logged and skipped, never fatal (review blocker 6)."""
    rejected0 = consumer.rejected
    try:
        entries = consumer.read(block_ms=block_ms)
    except redis.RedisError:
        log.exception("event read failed")
        entries = []
    for stream, entry_id, ev in entries:
        t0 = time.perf_counter()
        try:
            calls = engine.feed(ev.model_dump(by_alias=True, exclude_none=True, mode="json"))
        except Exception:  # noqa: BLE001 - one bad event must not stop the referee
            log.exception("event failed")
            calls = []
        consumer.ack(stream, entry_id)
        for c in calls:
            log.info(
                json.dumps(
                    {
                        "svc": "engine",
                        "game_id": c["game_id"],
                        "msg": "call",
                        "rule": c["rule_id"],
                        "text": c["text"],
                        "ms": round((time.perf_counter() - t0) * 1000, 1),
                    }
                )
            )
    try:
        ctl_entries = _read_ctl(r, ctl_last)
    except redis.RedisError:
        log.exception("ctl read failed")
        ctl_entries = []
    for entry_id, fields in ctl_entries:
        ctl_last = entry_id
        try:
            cmd = parse_ctl(fields[b"json"])
            engine.handle_ctl(cmd.model_dump(by_alias=True, exclude_none=True, mode="json"))
        except Exception:  # noqa: BLE001
            log.exception("ctl failed")
    return ctl_last, len(entries) + len(ctl_entries) + consumer.rejected - rejected0


def _stream_tail(r: redis.Redis, stream: str) -> str:
    """The newest entry id of ``stream`` (``0-0`` when empty): XREAD from it returns only what arrives later. Passing
    ``$`` on every call instead loses every entry added while the loop was busy elsewhere (e.g. in the event read)."""
    tail = r.xrevrange(stream, count=1)
    if not tail:
        return "0-0"
    entry_id = tail[0][0]
    return entry_id.decode() if isinstance(entry_id, bytes) else entry_id


def _read_ctl(r: redis.Redis, last: str) -> list[tuple[str, dict[bytes, bytes]]]:
    res = r.xread({CTL_ENGINE: last}, count=50, block=10)
    out = []
    for _stream, entries in res or []:
        for entry_id, fields in entries:
            out.append((entry_id.decode() if isinstance(entry_id, bytes) else entry_id, fields))
    return out


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
