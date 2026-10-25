"""Annotation feeder for scenarios without perception (D-44, docs/plan/judging-demo.md "Annotated fixtures").

Replays a hand-annotated ``*.events.jsonl`` (one trophy.event.v1 per line, ``source: "annotated"``, ``t_game_s`` =
seconds from the segment start) onto ``ev:flight`` on the same schedule as the replayed video. The event at clip time
``t`` goes out at server time ``wall0_ms/1000 + (t - start_s)/speed`` with game time ``t_game0_s + (t - start_s)``.
That is the mapping the frames WS uses for a phone with zero clock error, so the engine sees the event when the phones
show it. Each event is published in the same shape perception uses (``XADD ev:flight json=<event>``,
``trophy.streams.publish_event``), with a fresh id and the live game's id. It can also be mirrored into Spacetime
``observation`` through a ``trophy.world.ObservationWriter``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import redis.asyncio as aioredis
from trophy.events import event_json, parse_event
from trophy.ids import new_ulid
from trophy.streams import EV_FLIGHT, EVENT_STREAM_MAXLEN

log = logging.getLogger("gateway.annotations")


class _Mirror(Protocol):
    def post(self, ev: Any) -> None: ...


def load_events(events_path: Path) -> list[dict[str, Any]]:
    """The file's events sorted by ``t_game_s``. Bad lines are logged and skipped."""
    out: list[dict[str, Any]] = []
    for n, line in enumerate(Path(events_path).read_text("utf8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            float(d["t_game_s"])
        except (ValueError, KeyError, TypeError) as e:
            log.warning("annotation %s:%d skipped: %s", events_path, n, e)
            continue
        out.append(d)
    out.sort(key=lambda d: float(d["t_game_s"]))
    return out


async def run_feeder(
    r: aioredis.Redis,
    *,
    game_id: str,
    sport: str,
    events_path: Path,
    wall0_ms: float,
    t_game0_s: float,
    speed: float = 1.0,
    start_s: float = 0.0,
    cam_id: str | None = None,
    world: _Mirror | None = None,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> int:
    """Publish each annotated event at its scheduled server time; return how many were published.

    ``start_s`` skips events before it (times in the file are already relative to the segment start, so it's normally
    0). ``cam_id`` is the feed's camera, written into ``cams``. ``world`` is optional: when given, each event is also
    mirrored into Spacetime ``observation``. ``now`` and ``sleep`` are injectable for tests.
    """
    if speed <= 0:
        raise ValueError("speed must be > 0")
    sent = 0
    for raw in load_events(events_path):
        t = float(raw["t_game_s"])
        if t < start_s:
            continue
        due_s = wall0_ms / 1000 + (t - start_s) / speed
        wait = due_s - now()
        if wait > 0:
            await sleep(wait)
        d = {
            **raw,
            "id": new_ulid(),
            "game_id": game_id,
            "sport": sport,
            "t_game_s": round(t_game0_s + (t - start_s), 4),
            "source": "annotated",
            "cams": [cam_id] if cam_id else list(raw.get("cams") or []),
        }
        try:
            ev = parse_event(d)
        except ValueError as e:
            log.warning("annotation at t=%.2f skipped (not a valid event): %s", t, str(e)[:200])
            continue
        await r.xadd(EV_FLIGHT, {"json": event_json(ev)}, maxlen=EVENT_STREAM_MAXLEN, approximate=True)
        if world is not None:
            world.post(ev)
        sent += 1
        log.info(
            json.dumps(
                {"svc": "annotations", "game_id": game_id, "type": ev.type, "t_clip_s": t, "t_game_s": ev.t_game_s}
            )
        )
    return sent
