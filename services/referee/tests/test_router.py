import pytest
from conftest import CTX, FakeLLM

from referee.router import route, route_regex


@pytest.mark.parametrize(
    "q,intent,check",
    [
        ("Trophy, was that out?", "check", "in_out"),
        ("in or out", "check", "in_out"),
        ("was that an edge ball", "check", "edge_hit"),
        ("did it clip the net?", "check", "net_touch"),
        ("was that serve legal", "check", "serve_toss"),
        ("did it bounce twice", "check", "double_bounce"),
        ("which side did it land on", "check", "bounce_side"),
        ("how long was that rally", "check", "rally_summary"),
        ("what's the score", "score", None),
        ("why was that out?", "explain", None),
    ],
)
def test_regex_routes(q, intent, check):
    r = route_regex(q, CTX)
    assert r is not None and r.intent == intent and r.check == check and r.source == "regex"


def test_time_args_come_from_the_newest_fresh_call():
    r = route_regex("was that out", CTX)
    assert r.args == {"t_game_s": 61.42, "ref": "call:01CALL"}
    stale = {**CTX, "t_game_s": 500.0}
    assert route_regex("was that out", stale).args == {"ref": "last"}
    assert route_regex("was that serve legal", CTX).args == {"ref": "last_rally", "rally_no": 9}
    w = route_regex("did it touch the net", CTX).args
    assert w["ref"] == "last_rally" and w["t0_s"] == 53.42 and w["t1_s"] == 61.92


async def test_claude_routes_the_rest():
    llm = FakeLLM({"route": [{"intent": "rule", "check": "", "hint": "", "reason": "general rules"}]})
    r, ms = await route("can I serve from the side of the table", CTX, llm)
    assert r.intent == "rule" and r.source == "claude" and ms == 42.0 and llm.calls[0]["fast"] is True
    assert "Catalog" in llm.calls[0]["system"] and "in_out(t)" in llm.calls[0]["system"]


async def test_claude_new_check_becomes_a_hint():
    llm = FakeLLM(
        {"route": [{"intent": "check", "check": "new", "hint": "ball_speed(rally) -> max m/s", "reason": ""}]}
    )
    r, _ = await route("how hard did she hit that", CTX, llm)
    assert r.intent == "check" and r.check is None and r.hint == "ball_speed(rally) -> max m/s"


async def test_unknown_catalog_name_from_claude_is_treated_as_new():
    llm = FakeLLM({"route": [{"intent": "check", "check": "spin_rate", "hint": "", "reason": ""}]})
    r, _ = await route("how much spin was on that", CTX, llm)
    assert r.check is None and r.hint.startswith("new_check")


async def test_no_router_model_falls_to_rules():
    r, ms = await route("tell me about lets", CTX, None)
    assert r.intent == "rule" and ms == 0.0
