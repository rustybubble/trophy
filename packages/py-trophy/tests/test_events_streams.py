import json

import pytest
from pydantic import ValidationError

from trophy.contracts import BouncePayload, ServeTossPayload
from trophy.events import event_json, make_event, parse_event, payload_of
from trophy.streams import (
    CTL_ENGINE,
    EV_FLIGHT,
    EventConsumer,
    make_ctl,
    parse_ctl,
    publish_ctl,
    publish_event,
    role_allows,
)

GAME = "g_abcdefgh"


def bounce(**kw):
    return make_event(
        game_id=GAME,
        t_game_s=12.34,
        sport="table_tennis",
        type="bounce",
        source="flight",
        cams=["c_abcdef"],
        conf=0.97,
        side="B",
        pos_m={"x": 1.36, "y": 0.75, "z": 0.0},
        sigma_m=0.018,
        payload={
            "surface": "table",
            "side": "B",
            "d_lines_m": {"end_B": 0.004, "side_left": 0.01},
            "p_in": 0.71,
            "edge": {"top_edge": 0.71, "side_face": 0.2, "surface": 0.09},
            "timing": "audio",
        },
        **kw,
    )


def test_event_json_uses_schema_key_and_roundtrips():
    ev = bounce()
    d = json.loads(event_json(ev))
    assert d["schema"] == "trophy.event.v1" and "schema_" not in d
    back = parse_event(event_json(ev))
    assert back == ev
    p = payload_of(back)
    assert isinstance(p, BouncePayload) and p.edge.top_edge == 0.71


def test_make_event_validates_payload():
    with pytest.raises(ValidationError):
        make_event(
            game_id=GAME,
            t_game_s=1,
            sport="table_tennis",
            type="bounce",
            source="flight",
            cams=["c_abcdef"],
            conf=1,
            payload={"surface": "table"},
        )
    with pytest.raises(ValidationError):
        make_event(
            game_id="nope",
            t_game_s=1,
            sport="table_tennis",
            type="heartbeat",
            source="flight",
            cams=[],
            conf=1,
            payload={"service": "flight"},
        )


def test_serve_toss_payload():
    p = ServeTossPayload.model_validate(
        {
            "server_side": "A",
            "release": {"t_s": 1.0, "pos_m": {"x": -1.5, "y": 0.2, "z": 0.0}},
            "apex": {"t_s": 1.3, "pos_m": {"x": -1.5, "y": 0.2, "z": 0.2}},
            "contact": {"t_s": 1.6, "pos_m": {"x": -1.45, "y": 0.2, "z": 0.05}},
            "height_m": 0.2,
            "sigma_height_m": 0.01,
            "rise_angle_rad": 0.0,
            "fall_angle_rad": 0.32,
            "angle_from_vertical_rad": 0.32,
            "sigma_angle_rad": 0.05,
            "observable_plane": "xz",
        }
    )
    ev = make_event(
        game_id=GAME,
        t_game_s=1.6,
        sport="table_tennis",
        type="serve_toss",
        source="synthetic",
        cams=["c_abcdef"],
        conf=0.9,
        payload=p,
    )
    assert ev.payload["height_m"] == 0.2


def test_publish_and_consume(r):
    c = EventConsumer(r, streams=[EV_FLIGHT], start="0")
    ev = bounce()
    publish_event(r, ev)
    got = c.read(block_ms=0)
    assert len(got) == 1 and got[0][0] == EV_FLIGHT and got[0][2].id == ev.id
    c.ack(EV_FLIGHT, got[0][1])
    assert c.read(block_ms=0) == []


def test_ctl_roundtrip_and_roles(r):
    cmd = make_ctl("challenge", GAME, {"call_id": "01J0000000000000000000000A"}, by_cam_id="c_abcdef")
    publish_ctl(r, cmd)
    ((_, fields),) = r.xrange(CTL_ENGINE)
    assert parse_ctl(fields[b"json"]) == cmd
    assert role_allows("cam", "challenge")
    assert not role_allows("cam", "resolve_challenge")
    assert role_allows("cam,judge", "approve_house_rule")
    assert not role_allows("judge", "create_game")  # gateway only
    assert not role_allows("judge", "ask_logged")


def test_watch_commands_survive_live_ctl_parsing():
    from trophy.streams import make_ctl, parse_ctl, role_allows

    for cmd, args in [
        ("bookmark", {"t_game_s": 1}),
        ("clip_that", {}),
        ("review_call", {"call_id": "call1", "result": "confirm"}),
    ]:
        wire = make_ctl(cmd, "g1", args).model_dump_json(by_alias=True)
        assert parse_ctl(wire).cmd == cmd
        assert role_allows("judge", cmd)
    assert role_allows("display", "bookmark")
    assert role_allows("cam", "clip_that")
    assert not role_allows("display", "review_call")
