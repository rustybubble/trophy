"""The annotation feeder (D-44) and the committed hand-annotated fixtures it replays."""

from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest
import yaml
from trophy.events import PAYLOAD_MODELS, parse_event
from trophy.ids import ULID_RE
from trophy.streams import EV_FLIGHT

from gateway.annotations import run_feeder

ROOT = Path(__file__).resolve().parents[3]
ANNOTATED = ROOT / "evals" / "fixtures" / "annotated"
GAME = "g_7k3m9q2x"


def line(t: float, type_: str = "bounce", **kw) -> str:
    payload = kw.pop("payload", {"surface": "court", "side": "B", "d_lines_m": {}, "p_in": 0.9, "in": True})
    return json.dumps(
        {
            "schema": "trophy.event.v1",
            "id": "01M5S0R78DA55E5DP77SK6QNHR",
            "game_id": "g_00000000",
            "t_game_s": t,
            "sport": "pickleball",
            "type": type_,
            "source": "annotated",
            "cams": [],
            "conf": 0.8,
            "side": "B",
            "payload": payload,
            **kw,
        }
    )


class Clock:
    """A fake server clock: sleep() advances it, so the schedule is checked without waiting."""

    def __init__(self, t: float) -> None:
        self.t = t
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


async def entries(r) -> list[dict]:
    return [json.loads(f[b"json"]) for _, f in await r.xrange(EV_FLIGHT)]


@pytest.fixture
def events_file(tmp_path: Path) -> Path:
    p = tmp_path / "clip.events.jsonl"
    # out of order on purpose, plus a blank line and a broken one
    p.write_text("\n".join([line(5.0), "", "{not json", line(1.5, "net", payload={"kind": "into", "from_side": "A"})]))
    return p


async def test_events_go_to_ev_flight_on_the_video_schedule_with_the_live_game_ids(events_file: Path):
    r = fakeredis.FakeAsyncRedis()
    clock = Clock(1_000.0)
    n = await run_feeder(
        r,
        game_id=GAME,
        sport="pickleball",
        events_path=events_file,
        wall0_ms=1_002_000.0,  # 2 s from now, as the gateway schedules wall0
        t_game0_s=30.0,
        cam_id="c_ab12cd",
        now=clock.now,
        sleep=clock.sleep,
    )
    assert n == 2
    got = await entries(r)
    assert [e["type"] for e in got] == ["net", "bounce"]
    assert [e["t_game_s"] for e in got] == [31.5, 35.0]  # t_game0 + clip time
    assert clock.slept == pytest.approx([3.5, 3.5])  # due at wall0 + 1.5 s, then wall0 + 5 s
    for e in got:
        ev = parse_event(e)
        assert ev.game_id == GAME and ev.source == "annotated" and ev.cams == ["c_ab12cd"]
        assert ULID_RE.match(ev.id) and ev.id != "01M5S0R78DA55E5DP77SK6QNHR"
    assert got[0]["id"] != got[1]["id"]


async def test_speed_start_and_late_starts(events_file: Path):
    r = fakeredis.FakeAsyncRedis()
    clock = Clock(1_000.0)
    # start_s skips the first event; at speed 2 the second is due (5 - 2)/2 = 1.5 s after wall0, which already passed
    n = await run_feeder(
        r,
        game_id=GAME,
        sport="pickleball",
        events_path=events_file,
        wall0_ms=990_000.0,
        t_game0_s=0.0,
        speed=2.0,
        start_s=2.0,
        now=clock.now,
        sleep=clock.sleep,
    )
    assert n == 1 and clock.slept == []
    (e,) = await entries(r)
    assert e["type"] == "bounce" and e["t_game_s"] == 3.0 and e["cams"] == []
    with pytest.raises(ValueError):
        await run_feeder(r, game_id=GAME, sport="pickleball", events_path=events_file, wall0_ms=0, t_game0_s=0, speed=0)


async def test_invalid_events_are_skipped_and_valid_ones_mirrored(tmp_path: Path):
    p = tmp_path / "bad.events.jsonl"
    p.write_text("\n".join([line(0.1, type_="teleport"), line(0.2)]))
    posted = []

    class World:
        def post(self, ev) -> None:
            posted.append(ev)

    r = fakeredis.FakeAsyncRedis()
    clock = Clock(5.0)
    n = await run_feeder(
        r,
        game_id=GAME,
        sport="pickleball",
        events_path=p,
        wall0_ms=0,
        t_game0_s=0,
        world=World(),
        now=clock.now,
        sleep=clock.sleep,
    )
    assert n == 1 and len(await entries(r)) == 1
    assert [ev.type for ev in posted] == ["bounce"]


# ---- the committed fixtures --------------------------------------------------------------------------------------
FIXTURES = sorted(ANNOTATED.glob("*/*.events.jsonl"))


def test_there_are_annotated_fixtures_for_the_three_demo_sports():
    assert {p.parent.name for p in FIXTURES} >= {"pickleball", "volleyball", "basketball"}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.parent.name)
def test_fixture_events_are_valid_annotated_events_and_labels_match(path: Path):
    events = [parse_event(json.loads(s)) for s in path.read_text("utf8").splitlines() if s.strip()]
    assert events and all(e.source == "annotated" and e.sport == path.parent.name for e in events)
    assert [e.t_game_s for e in events] == sorted(e.t_game_s for e in events)
    for e in events:
        model = PAYLOAD_MODELS.get(e.type)
        if model:
            model.model_validate(e.payload or {})
    labels = json.loads(path.with_name(path.name.replace(".events.jsonl", ".labels.json")).read_text("utf8"))
    assert labels["synthetic"] is False and "HAND-ANNOTATED" in labels["label"]
    times = [e.t_game_s for e in events]
    for c in labels["calls"]:
        assert c["team_id"] in ("A", "B") and c.get("at_fault") in ("A", "B", None)
        assert c["at_fault"] != c["team_id"]
        assert min(abs(c["t_s"] - t) for t in times) <= 1.5, f"call at {c['t_s']} has no event near it"


def test_scenarios_point_at_their_fixtures_and_local_media():
    scenarios = [
        yaml.safe_load(p.read_text("utf8")) for p in sorted((ROOT / "data" / "scenarios").glob("*/scenario.yaml"))
    ]
    assert {s["id"] for s in scenarios} >= {
        "pingpong-two-angle",
        "pickleball-rec-doubles",
        "volleyball-amateur-set",
        "basketball-halfcourt",
    }
    for s in scenarios:
        assert s["source"] in ("team_recording", "cc_by_online") and s["credit"]
        assert [t["team_id"] for t in s["teams"]] == ["A", "B"]
        for a in s["angles"]:
            assert a["file"].startswith(f"data/local/scenarios/{s['id']}/") and a["offset_s"] == 0
            assert a["duration_s"] > 0 and a["start_s"] >= 0
            if "corners_norm" in a:
                assert len(a["corners_norm"]) == 4 and all(0 <= v <= 1 for xy in a["corners_norm"] for v in xy)
        if s["annotated"]:
            assert (ROOT / s["events"]).exists() and s["events_angle"] in {a["label"] for a in s["angles"]}
            assert "CC BY" in s["credit"]
