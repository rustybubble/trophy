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


def mark(t: float, z: float, x: float = -1.5) -> dict:
    return {
        "t_s": t,
        "t0_s": t - 0.017,
        "t1_s": t + 0.017,
        "sigma_t_s": 0.01,
        "pos_m": {"x": x, "y": 0.2, "z": z},
        "sigma_m": 0.01,
    }


EST = {"name": "synthetic", "version": "0"}


def test_serve_toss_payload():
    p = ServeTossPayload.model_validate(
        {
            "server_side": "A",
            "release": mark(1.0, 0.0),
            "apex": mark(1.3, 0.2),
            "contact": mark(1.6, 0.05, -1.45),
            "height_m": 0.2,
            "sigma_height_m": 0.01,
            "angle_from_vertical_rad": 0.05,
            "sigma_angle_rad": 0.05,
            "angle_segment": "rise",
            "struck_on_descent": True,
            "struck_on_descent_p": 0.97,
            "evidence_missing": ["spin"],
            "estimator": EST,
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
    assert ev.payload["height_m"] == 0.2 and ev.payload["angle_segment"] == "rise"
    with pytest.raises(ValidationError):  # the angle is on the rise only (ITTF Law 2.6.2, D-31)
        ServeTossPayload.model_validate({**p.model_dump(), "angle_segment": "hand_to_hit"})
    with pytest.raises(ValidationError):
        ServeTossPayload.model_validate({**p.model_dump(), "evidence_missing": ["vibes"]})


def test_serve_hidden_and_position_payloads():
    hidden = make_event(
        game_id=GAME,
        t_game_s=1.6,
        sport="table_tennis",
        type="serve_hidden",
        source="synthetic",
        cams=["c_abcdef"],
        conf=0.8,
        payload={
            "server_side": "A",
            "t0_s": 1.0,
            "t1_s": 1.6,
            "visible_fraction": 0.1,
            "sigma_visible_fraction": 0.1,
            "occluder": "free_arm",
            "cams_used": [{"cam_id": "c_abcdef", "view": "receiver_side", "visible_fraction": 0.1}],
            "evidence_missing": [],
            "estimator": EST,
        },
    )
    assert hidden.payload["occluder"] == "free_arm"
    pos = make_event(
        game_id=GAME,
        t_game_s=1.6,
        sport="table_tennis",
        type="serve_position",
        source="synthetic",
        cams=["c_abcdef"],
        conf=0.9,
        payload={
            "server_side": "A",
            "t0_s": 0.5,
            "t1_s": 1.6,
            "min_above_surface_m": 0.04,
            "min_behind_end_line_m": -0.05,
            "sigma_m": 0.02,
            "p_above": 0.98,
            "p_behind": 0.01,
            "evidence_missing": [],
            "estimator": EST,
        },
    )
    assert pos.payload["p_behind"] == 0.01
    net = make_event(
        game_id=GAME,
        t_game_s=1.7,
        sport="table_tennis",
        type="net",
        source="synthetic",
        cams=["c_abcdef"],
        conf=0.9,
        payload={"kind": "touch", "from_side": "A", "serve": True},
    )
    assert net.payload["serve"] is True


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


def test_consumer_acks_and_skips_malformed_entries_instead_of_raising():
    """Review blocker 6: one bad entry on ev:* must not stop the engine's consumer."""
    import fakeredis

    from trophy.streams import EV_FLIGHT, EventConsumer

    r = fakeredis.FakeRedis()
    c = EventConsumer(r, streams=[EV_FLIGHT], start="0")
    r.xadd(EV_FLIGHT, {"json": "{not json"})
    r.xadd(EV_FLIGHT, {"other": "no json field"})
    r.xadd(EV_FLIGHT, {"json": '{"schema": "trophy.event.v1"}'})
    assert c.read(block_ms=0) == []
    assert c.rejected == 3
    assert r.xpending(EV_FLIGHT, "engine")["pending"] == 0  # acked, so never redelivered
