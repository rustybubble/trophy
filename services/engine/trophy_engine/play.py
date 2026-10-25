"""`trophy-play`: replay labelled-synthetic layer-1 logs through a sport module and feed the LIVE engine over Redis.

    trophy-play --game <game_id>                       # a game the gateway created (POST /api/games); phones join it
    trophy-play --new-game                             # or create one directly on ctl:engine (no gateway needed)
    trophy-play --game g_x --speed 2 --loop            # faster, and start over at the end

Every event this publishes is SYNTHETIC: it comes from `evals/fixtures/synthetic/<sport>/*.l1.jsonl` run through the
module's `events.py` (exactly what the Droid's gate replays), paced in real time by `t_game_s`, onto `ev:flight`. The
engine (`trophy-engine`) consumes them like perception's events, so calls, scores, rallies, moments and the spoken
lines appear on every phone and the dashboard through Spacetime. Nothing here is a measurement of real footage.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path

import redis
from trophy.events import parse_event
from trophy.streams import make_ctl, publish_ctl, publish_event

from .replay_test.checks import load_samples
from .sportmod.loader import load_module

ROOT = Path(__file__).resolve().parents[3]
log = logging.getLogger("trophy.play")


def _dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip()
    return out


def _new_game_id() -> str:
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
    return "g_" + "".join(secrets.choice(alphabet) for _ in range(8))


def events_for(module_dir: Path, samples_dir: Path, game_id: str) -> list[tuple[str, str | None, list[dict]]]:
    """(sample name, labelled server, layer-2 events) per fixture, in order; events carry the live game id."""
    mod = load_module(module_dir)
    out = []
    for s in load_samples(samples_dir):
        state = mod.state(game_id)
        out.append((s.name, s.labels.get("first_server"), [dict(ev) for ev in mod.events(iter(s.observations), state)]))
    return out


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trophy-play", description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--game", help="an existing game id (created by the gateway or an earlier --new-game)")
    g.add_argument("--new-game", action="store_true", help="send create_game + start_game on ctl:engine first")
    ap.add_argument("--sport", default="table_tennis")
    ap.add_argument("--module", type=Path, default=None, help="sports/<sport> (default: sports/--sport)")
    ap.add_argument(
        "--samples", type=Path, default=None, help="dir of *.l1.jsonl + *.labels.json (default: the synthetic fixtures)"
    )
    ap.add_argument("--speed", type=float, default=1.0, help="playback speed (2 = twice as fast)")
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between fixtures (the players walk back)")
    ap.add_argument("--loop", action="store_true", help="start over when the fixtures run out")
    ap.add_argument("--redis", default=None)
    ap.add_argument(
        "--first-server", default=None, help="team that serves first (default: the fixture's label, else A)"
    )
    ap.add_argument("--no-start", action="store_true", help="with --new-game: create the game, leave it in the lobby")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    env = {**_dotenv(), **os.environ}
    r = redis.Redis.from_url(a.redis or env.get("REDIS_URL") or "redis://127.0.0.1:6379/0")
    module_dir = a.module or ROOT / "sports" / a.sport
    samples_dir = a.samples or ROOT / "evals" / "fixtures" / "synthetic" / a.sport

    game_id = a.game or _new_game_id()
    plan = events_for(module_dir, samples_dir, game_id)
    first_server = a.first_server or next((srv for _, srv, _ in plan if srv), None) or "A"

    if a.new_game:
        publish_ctl(
            r,
            make_ctl(
                "create_game",
                game_id,
                {
                    "sport": a.sport,
                    "t0_ms": time.time() * 1000,
                    "params": {"synthetic": True, "label": "SYNTHETIC: trophy-play replay of labelled fixtures"},
                },
            ),
        )
        log.info("create_game %s (%s)", game_id, a.sport)
    for cam in ("c_syn001", "c_syn002"):
        args = {"cam_id": cam, "label": f"SYNTHETIC {cam}", "role": "cam"}
        publish_ctl(r, make_ctl("register_camera", game_id, args))
    if not a.no_start:
        publish_ctl(r, make_ctl("start_game", game_id, {"first_server": first_server}))
        log.info("start_game %s, first server %s", game_id, first_server)

    time.sleep(
        0.5
    )  # let the engine take the ctl commands before the first event (it reads ev:* and ctl:engine in turn)
    total = sum(len(evs) for _, _, evs in plan)
    looping = ", looping" if a.loop else ""
    log.info("%d synthetic events from %d fixtures; speed x%.1f%s", total, len(plan), a.speed, looping)
    offset = 0.0  # fixtures have their own t_game_s origin; play them back to back on the live game clock
    t_wall0 = time.monotonic()
    while True:
        for name, server, evs in plan:
            if not evs:
                continue
            if server and not a.first_server:  # each fixture was generated with its own server; referee it that way
                publish_ctl(r, make_ctl("set_server", game_id, {"team_id": server}))
                time.sleep(0.2)
            t_first = evs[0]["t_game_s"]
            for ev in evs:
                due = offset + (ev["t_game_s"] - t_first)
                while (time.monotonic() - t_wall0) * a.speed < due:
                    time.sleep(0.005)
                live = {**ev, "game_id": game_id, "t_game_s": round(due, 4)}
                publish_event(r, parse_event(live))
                payload = json.dumps(ev.get("payload") or {})[:80]
                log.info("%-9s %-10s t=%7.2fs conf=%.2f %s", name, ev["type"], due, ev.get("conf", 0.0), payload)
            offset += (evs[-1]["t_game_s"] - t_first) + a.gap
        if not a.loop:
            break
    log.info("done: %d events into game %s", total, game_id)
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
