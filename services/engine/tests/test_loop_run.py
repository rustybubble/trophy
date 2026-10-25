"""The live loop end to end on a fake Redis (review blockers 4 and 6): a rally with trailing floor bounces and one
malformed entry go through `loop.run` exactly as the gateway and perception would publish them."""

from __future__ import annotations

import json
import threading
import time

import fakeredis
import pytest
from trophy.streams import CTL_ENGINE, EV_FLIGHT, make_ctl, publish_ctl

from trophy_engine import loop
from trophy_engine.state import MemoryState

GAME = "g_1007e5t2"


def bounce(t: float, side: str, surface: str = "table") -> dict:
    return {
        "schema": "trophy.event.v1",
        "id": f"lb{t}",
        "game_id": GAME,
        "t_game_s": t,
        "sport": "table_tennis",
        "type": "bounce",
        "source": "synthetic",
        "cams": ["c_syn001"],
        "conf": 0.95,
        "side": side,
        "payload": {"surface": surface, "side": side},
    }


@pytest.fixture
def redis_and_state(monkeypatch):
    server = fakeredis.FakeServer()
    r = fakeredis.FakeRedis(server=server)
    monkeypatch.setattr(
        loop.redis.Redis, "from_url", staticmethod(lambda *_a, **_k: fakeredis.FakeRedis(server=server))
    )
    states: list[MemoryState] = []

    class Capture(MemoryState):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            states.append(self)

    monkeypatch.setattr(loop, "MemoryState", Capture)
    return r, states


def test_loop_run_scores_one_point_and_survives_a_malformed_entry(redis_and_state):
    r, states = redis_and_state
    done: list[int] = []
    t = threading.Thread(
        target=lambda: done.append(loop.run(["--state", "memory", "--exit-when-idle", "1.0"])), daemon=True
    )
    t.start()
    time.sleep(0.4)  # the loop's ctl cursor starts after what is already on the stream
    publish_ctl(r, make_ctl("create_game", GAME, {"sport": "table_tennis", "t0_ms": 0}))
    publish_ctl(r, make_ctl("start_game", GAME, {"first_server": "A"}))
    time.sleep(0.3)
    r.xadd(EV_FLIGHT, {"json": "{not json"})  # a broken producer
    r.xadd(EV_FLIGHT, {"json": json.dumps({"schema": "trophy.event.v1", "id": "x"})})  # schema-invalid
    for ev in [bounce(1.0, "A"), bounce(1.4, "B"), bounce(2.0, "B", "floor"), bounce(2.3, "A", "floor"),
               bounce(2.6, "B", "floor")]:  # fmt: skip
        r.xadd(EV_FLIGHT, {"json": json.dumps(ev)})
    t.join(timeout=15)
    assert done == [0], "the loop died or never went idle"
    st = states[-1]
    scores = {row["team_id"]: row["points"] for row in st.rows("score") if row["game_id"] == GAME}
    assert scores == {"A": 1, "B": 0}
    assert r.xlen(CTL_ENGINE) == 2
