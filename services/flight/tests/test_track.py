import numpy as np

from flight.track import Tracker, TrackerParams


def parabola(n=60, fps=30.0):
    t = np.arange(n) / fps
    x = 200 + 600 * t
    y = 500 - 900 * t + 1800 * t**2
    return t, x, y


def test_tracker_ignores_teleports_and_bridges_gaps():
    t, x, y = parabola()
    rng = np.random.default_rng(1)
    frames = []
    for i in range(len(t)):
        cands = []
        if i not in (20, 21, 35):  # dropped detections
            cands.append({"xy_px": [x[i] + rng.normal(0, 1), y[i] + rng.normal(0, 1)], "score": 0.9})
        if i % 7 == 3:  # a strong wrong blob far away, like a hand
            cands.append({"xy_px": [rng.uniform(0, 1280), rng.uniform(0, 720)], "score": 1.0})
        frames.append({"frame": i, "t_s": float(t[i]), "candidates": cands})
    out = Tracker().run(frames)
    assert len(out) >= len(t) - 3 - 2  # birth needs 3 frames; 3 dropped
    err = [np.hypot(s["xy_px"][0] - x[s["frame"]], s["xy_px"][1] - y[s["frame"]]) for s in out]
    assert max(err) < 6.0, max(err)
    assert {s["track_id"] for s in out} == {out[0]["track_id"]}


def test_tracker_replaces_a_lost_track():
    t, x, y = parabola(80)
    frames = []
    for i in range(len(t)):
        if i < 30:
            cands = [{"xy_px": [x[i], y[i]], "score": 0.9}]
        elif i < 40:
            cands = []  # ball out of view
        else:
            cands = [{"xy_px": [1000 - 300 * (t[i] - t[40]), 300 + 200 * (t[i] - t[40])], "score": 0.9}]
        frames.append({"frame": i, "t_s": float(t[i]), "candidates": cands})
    out = Tracker(TrackerParams(max_miss=4)).run(frames)
    ids = sorted({s["track_id"] for s in out})
    assert len(ids) == 2
    assert not any(30 <= s["frame"] < 40 for s in out)
    assert sum(s["frame"] >= 40 for s in out) >= 38


def test_isolated_blobs_never_emitted():
    rng = np.random.default_rng(2)
    frames = [
        {"frame": i, "t_s": i / 30, "candidates": [{"xy_px": [rng.uniform(0, 1280), rng.uniform(0, 720)], "score": 1}]}
        for i in range(60)
    ]
    assert Tracker().run(frames) == []
