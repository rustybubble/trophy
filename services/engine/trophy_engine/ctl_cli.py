"""``trophy-ctl``: publish a control command to ``ctl:engine`` (the same stream the gateway writes), for rehearsals
and tests without phones. ``--dry`` runs the command through an in-process engine with the memory state instead.

    trophy-ctl create_game g_demo0001 --sport table_tennis
    trophy-ctl start_game g_demo0001 --args '{"first_server": "A"}'
    trophy-ctl submit_house_rule g_demo0001 --args '{"text": "first to 7, win by 1", "source": "typed"}'
    trophy-ctl approve_house_rule g_demo0001 --args '{"rule_version": "...", "pack_path": "..."}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import redis
from trophy.streams import make_ctl, publish_ctl

from .loop import _dotenv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trophy-ctl", description=__doc__.splitlines()[0])
    ap.add_argument("cmd")
    ap.add_argument("game_id")
    ap.add_argument("--args", default="{}", help="JSON args")
    ap.add_argument("--sport", help="create_game shortcut")
    ap.add_argument("--by", default=None, help="by_cam_id (judge/cam)")
    ap.add_argument("--redis", default=None)
    a = ap.parse_args(argv)
    args = json.loads(a.args)
    if a.sport:
        args.setdefault("sport", a.sport)
        args.setdefault("t0_ms", 0)
    cmd = make_ctl(a.cmd, a.game_id, args, a.by)
    env = {**_dotenv(), **os.environ}
    r = redis.Redis.from_url(a.redis or env.get("REDIS_URL") or "redis://127.0.0.1:6379/0")
    entry = publish_ctl(r, cmd)
    print(json.dumps({"req_id": cmd.req_id, "stream_id": entry}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
