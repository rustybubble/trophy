"""JSON-lines logging: `{"svc": "rules", "msg": ..., ...}` on stderr. Never a key, never a full prompt."""

from __future__ import annotations

import json
import sys
import time
from typing import Any


def jlog(msg: str, **kw: Any) -> None:
    row = {"svc": "rules", "t_srv_ms": int(time.time() * 1000), "msg": msg, **kw}
    sys.stderr.write(json.dumps(row, default=str) + "\n")
    sys.stderr.flush()
