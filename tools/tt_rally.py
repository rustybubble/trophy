"""Rallies, events and point outcomes from a tracker run (tools/tt_track.py output with tables).

    uv run --project services/flight python tools/tt_rally.py data/local/tt-track/side_full.jsonl \
        --out data/local/tt-track/side_rallies.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from flight.rally import build_rallies
from flight.table import Table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("track", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    raw = [json.loads(line) for line in a.track.read_text("utf8").splitlines()]
    tables = {r["seq"]: Table(*r["tb"][:4], r["tb"][4], r["tb"][5]) for r in raw if "tb" in r}

    def table_at(seq: int) -> Table | None:
        t = tables.get(seq)
        if t is None:
            return None
        half = max(t.net_x - t.x_left, t.x_right - t.net_x)  # ends are often hidden by players: symmetric about net
        return dataclasses.replace(t, x_left=t.net_x - half, x_right=t.net_x + half)

    rows = [dict(r, x=r.get("wx"), y=r.get("wy")) for r in raw]
    rallies = build_rallies(rows, table_at)
    for r in rallies:
        seq = " ".join(f"{e.kind[0].upper()}{e.side}@{e.t:.2f}" for e in r.events)
        head = f"rally {r.no:2d} {r.t_start:6.2f}-{r.t_end:6.2f}s  winner {r.winner or '?'}"
        print(f"{head}  ({r.reason}; conf {r.confidence:.2f})")
        print(f"          {seq}")
    if a.out:
        a.out.write_text(json.dumps([dataclasses.asdict(r) for r in rallies], indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
