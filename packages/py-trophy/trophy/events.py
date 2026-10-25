"""Building, serialising and parsing trophy.event.v1 events (interfaces-v1 §7)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from .contracts import (
    AudioOnsetPayload,
    BallDeadPayload,
    BouncePayload,
    ContactPayload,
    Event,
    HeartbeatPayload,
    LineCrossPayload,
    NetPayload,
    PersonFeetPayload,
    PlayerContactPayload,
    ReachOverNetPayload,
    ServeHiddenPayload,
    ServePositionPayload,
    ServeTossPayload,
    ShotPayload,
    TouchPayload,
)
from .ids import new_ulid

PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "audio_onset": AudioOnsetPayload,
    "bounce": BouncePayload,
    "contact": ContactPayload,
    "net": NetPayload,
    "ball_dead": BallDeadPayload,
    "serve_toss": ServeTossPayload,
    "serve_hidden": ServeHiddenPayload,
    "serve_position": ServePositionPayload,
    "person_feet": PersonFeetPayload,
    "shot": ShotPayload,
    "line_cross": LineCrossPayload,
    "player_contact": PlayerContactPayload,
    "reach_over_net": ReachOverNetPayload,
    "touch": TouchPayload,
    "heartbeat": HeartbeatPayload,
}

# Types after which a rally is usually over; world writers flush these immediately.
RALLY_ENDING_TYPES = frozenset({"ball_dead"})


def make_event(
    *,
    game_id: str,
    t_game_s: float,
    sport: str,
    type: str,
    source: str,
    cams: list[str],
    conf: float,
    payload: BaseModel | Mapping[str, Any] | None = None,
    id: str | None = None,
    **fields: Any,
) -> Event:
    """Build and validate an Event. The payload is validated against its ``*Payload`` model."""
    if isinstance(payload, BaseModel):
        payload_d = payload.model_dump(by_alias=True, exclude_none=True)
    else:
        payload_d = dict(payload or {})
    model = PAYLOAD_MODELS.get(type)
    if model is not None:
        model.model_validate(payload_d)
    return Event.model_validate(
        {
            "schema": "trophy.event.v1",
            "id": id or new_ulid(),
            "game_id": game_id,
            "t_game_s": t_game_s,
            "sport": sport,
            "type": type,
            "source": source,
            "cams": cams,
            "conf": conf,
            "payload": payload_d,
            **fields,
        }
    )


def event_dict(ev: Event) -> dict[str, Any]:
    return ev.model_dump(by_alias=True, exclude_none=True, mode="json")


def event_json(ev: Event) -> str:
    return ev.model_dump_json(by_alias=True, exclude_none=True)


def parse_event(raw: bytes | str | Mapping[str, Any]) -> Event:
    data = raw if isinstance(raw, Mapping) else json.loads(raw)
    return Event.model_validate(data)


def payload_of(ev: Event) -> BaseModel | dict[str, Any]:
    """The event's payload as its typed model (or a plain dict for unknown types)."""
    model = PAYLOAD_MODELS.get(ev.type)
    return model.model_validate(ev.payload or {}) if model else dict(ev.payload or {})
