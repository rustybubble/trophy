"""trophy-live's sliding window over the golden module: each settled event once, a dead ball starts the next rally,
and fed sample by sample it agrees with the module run on the whole log (the batch path the Droid's gate uses)."""

from __future__ import annotations

from pathlib import Path

from trophy_engine.live import GameWindow, camera_from_calib
from trophy_engine.sportmod.api import BallSample, Camera
from trophy_engine.sportmod.l1 import read_l1
from trophy_engine.sportmod.loader import load_module

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis"


def _stream(log: Path):
    obs = read_l1(log)
    cams = {o.cam_id: o for o in obs if isinstance(o, Camera)}
    samples = sorted((o for o in obs if isinstance(o, BallSample)), key=lambda s: (s.t_s, s.cam_id))
    return cams, samples


def _live(log: Path, period: float = 0.25, lag: float = 0.35) -> list[dict]:
    mod = load_module(ROOT / "sports" / "table_tennis")
    cams, samples = _stream(log)
    g = GameWindow("g_live", mod, cams=dict(cams))
    out: list[dict] = []
    next_t = samples[0].t_s + period
    for s in samples:
        g.add(s)
        if s.t_s >= next_t:
            next_t += period
            out += g.settle(lag, 12.0)
    g.stream_t += 5.0  # the stream goes quiet: everything settles
    out += g.settle(lag, 12.0)
    return out


def test_live_window_matches_the_batch_module_on_the_fixtures():
    mod = load_module(ROOT / "sports" / "table_tennis")
    for log in sorted(FIX.glob("*.l1.jsonl")):
        batch = list(mod.events(iter(read_l1(log)), mod.state("g_live")))
        live = _live(log)
        key = lambda e: (e["type"], round(e["t_game_s"], 2))  # noqa: E731
        assert [key(e) for e in live] == [key(e) for e in batch], log.name


def test_each_event_is_published_once_however_often_the_window_runs():
    log = sorted(FIX.glob("*.l1.jsonl"))[0]
    fast = _live(log, period=0.05)
    slow = _live(log, period=0.5)
    ids = [e["id"] for e in fast]
    assert len(ids) == len(set(ids))
    assert [e["type"] for e in fast] == [e["type"] for e in slow]


def test_camera_from_calib_needs_a_homography():
    assert camera_from_calib("c", {"image_size": {"w": 1280, "h": 720}}) is None
    cam = camera_from_calib("c", {"H_img_to_field": [1, 0, 0, 0, 1, 0, 0, 0, 1], "image_size": {"w": 1280, "h": 720}})
    assert cam is not None and cam.trusted is False and cam.image_w == 1280
