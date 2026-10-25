"""The live loop must not lose ctl commands that land while it reads events (seen at the demo, 2026-10-24)."""

from __future__ import annotations

import fakeredis
from trophy.streams import CTL_ENGINE, make_ctl, publish_ctl

from trophy_engine.loop import _read_ctl, _stream_tail


def test_tail_then_read_sees_every_command_added_after_start():
    r = fakeredis.FakeRedis()
    publish_ctl(r, make_ctl("create_game", "g_old", {"sport": "table_tennis", "t0_ms": 0}))
    last = _stream_tail(r, CTL_ENGINE)
    assert last != "$" and last != "0-0"
    # nothing new yet
    assert _read_ctl(r, last) == []
    # two commands land while the loop is elsewhere (reading ev:*); both must come back, in order
    publish_ctl(r, make_ctl("create_game", "g_new", {"sport": "table_tennis", "t0_ms": 1}))
    publish_ctl(r, make_ctl("start_game", "g_new", {"first_server": "A"}))
    got = _read_ctl(r, last)
    assert [f[b"json"] for _, f in got] and len(got) == 2
    assert b'"g_new"' in got[0][1][b"json"] and b"start_game" in got[1][1][b"json"]
    # and the old one before the tail is not replayed
    assert all(b"g_old" not in f[b"json"] for _, f in got)


def test_tail_of_an_empty_stream_reads_from_the_start():
    r = fakeredis.FakeRedis()
    assert _stream_tail(r, CTL_ENGINE) == "0-0"
    publish_ctl(r, make_ctl("create_game", "g_1", {"sport": "table_tennis", "t0_ms": 0}))
    assert len(_read_ctl(r, "0-0")) == 1
