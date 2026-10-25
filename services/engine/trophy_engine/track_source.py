"""Where fused 3D ball samples come from at run time (D-36): a Redis stream from perception, or a recorded
``*.track3d.jsonl`` replayed on the clock. Each source yields ``(row, now_s)`` where ``now_s`` is game time.

Stream contract (provisional, track3d.schema.json): ``XADD trk:ball3d * json <Track3DSample>``; the engine reads it
with XREAD from ``$`` so a restart never replays old samples. Nothing here interprets the samples; the checks do.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

TRACK_STREAM = "trk:ball3d"


def replay_file(
    path: str | Path, *, speed: float = 0.0, t0_wall: float | None = None
) -> Iterator[tuple[dict[str, Any], float]]:
    """Yield the file's samples. ``speed`` 0 = as fast as possible (tests, the gate); 1 = real time; 2 = twice."""
    rows = [json.loads(line) for line in Path(path).read_text("utf8").splitlines() if line.strip()]
    rows.sort(key=lambda r: float(r["t_s"]))
    if not rows:
        return
    start_t = float(rows[0]["t_s"])
    wall0 = t0_wall if t0_wall is not None else time.monotonic()
    for r in rows:
        t = float(r["t_s"])
        if speed > 0:
            due = wall0 + (t - start_t) / speed
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        yield r, t


class RedisTrackSource:
    """XREAD ``trk:ball3d`` (field ``json``) in blocks; ``poll`` returns the new samples (possibly none)."""

    def __init__(self, r: Any, stream: str = TRACK_STREAM, last: str = "$") -> None:
        self.r = r
        self.stream = stream
        self.last = last

    def poll(self, block_ms: int = 20, count: int = 200) -> list[tuple[dict[str, Any], float]]:
        res = self.r.xread({self.stream: self.last}, count=count, block=block_ms)
        out: list[tuple[dict[str, Any], float]] = []
        for _stream, entries in res or []:
            for entry_id, fields in entries:
                self.last = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                raw = fields.get(b"json") if b"json" in fields else fields.get("json")
                if raw is None:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                out.append((row, float(row.get("t_s", 0.0))))
        return out
