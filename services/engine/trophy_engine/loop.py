"""``trophy-engine run``: the live loop. Redis ``ev:*`` (consumer group ``engine``) and ``ctl:engine`` in, Spacetime
out. Background AI votes run only when every voter's key is present (``--votes``); there is no stub voter.
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

from .decide import BackgroundDecider, BitdeerVoter, ClaudeVoter, GeminiVoter, VoterConfigError
from .engine import Engine
from .state import MemoryState, SpacetimeState, StateWriter

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


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trophy-engine", description="Trophy rule engine: events + ctl in, calls out")
    ap.add_argument("--redis", default=None, help="REDIS_URL (default from env/.env)")
    ap.add_argument("--state", choices=["spacetime", "memory"], default="spacetime")
    ap.add_argument("--votes", action="store_true", help="run decide() voters (needs ANTHROPIC/GEMINI/BITDEER keys)")
    ap.add_argument("--modules", type=Path, default=ROOT / "sports")
    ap.add_argument("--log-json", action="store_true")
    a = ap.parse_args(argv)
    env = {**_dotenv(), **os.environ}
    logging.basicConfig(level=logging.INFO, format="%(message)s" if a.log_json else "%(asctime)s %(name)s %(message)s")
    state: StateWriter = SpacetimeState() if a.state == "spacetime" else MemoryState()
    engine = Engine(state, modules_dir=a.modules)
    if a.votes:
        try:
            engine.decider = build_decider(env, state, engine)
        except VoterConfigError as e:
            print(f"--votes needs every voter key: {e}", file=sys.stderr)
            return 3
    r = redis.Redis.from_url(a.redis or env.get("REDIS_URL") or "redis://127.0.0.1:6379/0")
    consumer = EventConsumer(r, group="engine", consumer=f"engine-{os.getpid()}", streams=list(EVENT_STREAMS))
    ctl_last = "$"
    log.info(json.dumps({"svc": "engine", "msg": "started", "state": a.state, "votes": a.votes}))
    while True:
        for stream, entry_id, ev in consumer.read(block_ms=50):
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
        for entry_id, fields in _read_ctl(r, ctl_last):
            ctl_last = entry_id
            try:
                cmd = parse_ctl(fields[b"json"])
                engine.handle_ctl(cmd.model_dump(by_alias=True, exclude_none=True, mode="json"))
            except Exception:  # noqa: BLE001
                log.exception("ctl failed")


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
