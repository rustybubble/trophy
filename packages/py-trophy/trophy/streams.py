"""Redis keys, event streams and control commands (interfaces-v1 §4, §7, §9)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

import redis

from .contracts import CtlCommand, Event
from .events import event_json, parse_event
from .ids import new_ulid
from .timebase import now_ms

# ---- keys ----
EV_FLIGHT = "ev:flight"
EV_PLAYERS = "ev:players"
EV_POSSESSION = "ev:possession"
EV_AUDIO = "ev:audio"
EVENT_STREAMS = (EV_FLIGHT, EV_PLAYERS, EV_POSSESSION, EV_AUDIO)
CTL_ENGINE = "ctl:engine"
CTL_CALIB = "ctl:calib"  # pub/sub channel, message = cam_id

EVENT_STREAM_MAXLEN = 20_000
CTL_STREAM_MAXLEN = 5_000

_STREAM_BY_SOURCE = {
    "flight": EV_FLIGHT,
    "players": EV_PLAYERS,
    "possession": EV_POSSESSION,
    "audio": EV_AUDIO,
}


def frames_key(cam_id: str) -> str:
    return f"frames:{cam_id}"


def trk_ball_key(cam_id: str) -> str:
    return f"trk:ball:{cam_id}"


def trk_players_key(cam_id: str) -> str:
    return f"trk:players:{cam_id}"


def game_key(game_id: str) -> str:
    return f"game:{game_id}"


def cam_key(cam_id: str) -> str:
    return f"cam:{cam_id}"


def calib_key(cam_id: str) -> str:
    return f"calib:{cam_id}"


def stream_for_event(ev: Event) -> str:
    """Default stream for an event's ``source``; synthetic/file/manual events go to ev:flight."""
    return _STREAM_BY_SOURCE.get(ev.source, EV_FLIGHT)


# ---- events ----
def publish_event(r: redis.Redis, ev: Event, stream: str | None = None) -> str:
    """XADD the event JSON (field ``json``) to ``stream`` (default: by source). Returns the entry id."""
    entry_id = r.xadd(
        stream or stream_for_event(ev),
        {"json": event_json(ev)},
        maxlen=EVENT_STREAM_MAXLEN,
        approximate=True,
    )
    return _s(entry_id)


class EventConsumer:
    """Consumer-group reader over one or more ev:* streams (the engine uses group ``engine``)."""

    def __init__(
        self,
        r: redis.Redis,
        streams: Iterable[str] = EVENT_STREAMS,
        group: str = "engine",
        consumer: str = "engine-1",
        start: str = "$",
    ) -> None:
        self.r = r
        self.streams = list(streams)
        self.group = group
        self.consumer = consumer
        for s in self.streams:
            try:
                r.xgroup_create(s, group, id=start, mkstream=True)
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    def read(self, block_ms: int = 100, count: int = 100) -> list[tuple[str, str, Event]]:
        resp = self.r.xreadgroup(self.group, self.consumer, {s: ">" for s in self.streams}, count=count, block=block_ms)
        out: list[tuple[str, str, Event]] = []
        for stream, entries in resp or []:
            for entry_id, fields in entries:
                raw = fields.get(b"json", fields.get("json"))
                out.append((_s(stream), _s(entry_id), parse_event(raw)))
        return out

    def ack(self, stream: str, *entry_ids: str) -> None:
        if entry_ids:
            self.r.xack(stream, self.group, *entry_ids)


# ---- control commands ----
GATEWAY_ONLY = frozenset({"create_game", "register_camera", "camera_health", "set_calibration", "ask_logged"})
# Which client roles may send each command through POST /api/ctl (§9). Roles are comma-combinable.
CTL_CLIENT_ROLES: Mapping[str, frozenset[str]] = {
    "start_game": frozenset({"judge"}),
    "set_server": frozenset({"judge"}),
    "challenge": frozenset({"cam", "display", "judge"}),
    "resolve_challenge": frozenset({"judge"}),
    "undo_last_call": frozenset({"judge"}),
    "adjust_score": frozenset({"judge"}),
    "end_period": frozenset({"judge"}),
    "end_game": frozenset({"judge"}),
    "submit_house_rule": frozenset({"judge"}),
    "approve_house_rule": frozenset({"judge"}),
    "reject_house_rule": frozenset({"judge"}),
    "bookmark": frozenset({"cam", "display", "judge"}),
    "clip_that": frozenset({"cam", "display", "judge"}),
    "review_call": frozenset({"judge"}),
}


def role_allows(role: str, cmd: str) -> bool:
    """True if a client with ``role`` (e.g. ``"cam,judge"``) may send ``cmd``."""
    allowed = CTL_CLIENT_ROLES.get(cmd)
    if not allowed:
        return False
    return any(r.strip() in allowed for r in role.split(","))


def make_ctl(cmd: str, game_id: str, args: Mapping[str, Any] | None = None, by_cam_id: str | None = None) -> CtlCommand:
    return CtlCommand.model_validate(
        {
            "schema": "trophy.ctl.v1",
            "req_id": new_ulid(),
            "cmd": cmd,
            "game_id": game_id,
            "t_srv_ms": now_ms(),
            "by_cam_id": by_cam_id,
            "args": dict(args or {}),
        }
    )


def publish_ctl(r: redis.Redis, cmd: CtlCommand) -> str:
    r.xadd(
        CTL_ENGINE,
        {"json": cmd.model_dump_json(by_alias=True)},
        maxlen=CTL_STREAM_MAXLEN,
        approximate=True,
    )
    return cmd.req_id


def parse_ctl(raw: bytes | str) -> CtlCommand:
    return CtlCommand.model_validate(json.loads(raw))


def _s(v: bytes | str) -> str:
    return v.decode() if isinstance(v, bytes) else v
