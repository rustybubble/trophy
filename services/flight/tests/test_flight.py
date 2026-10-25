import cv2
import numpy as np
import pytest

from flight.balltrack import Detector, LumaDetector, Tracker
from flight.rally import Ev, events_for, referee
from flight.table import Table

W, H = 1280, 720


def ev(kind, side, t):
    return Ev(kind, t, int(t * 60), 0.0, 0.0, side, 0.9)


@pytest.mark.parametrize(
    ("seq", "winner", "why"),
    [
        # A serves: A-side bounce, B-side bounce; B returns into A's half; A never returns
        (
            [("hit", "A"), ("bounce", "A"), ("bounce", "B"), ("hit", "B"), ("bounce", "A"), ("dead", "A")],
            "B",
            "didn't return",
        ),
        # the toss counts as a hit by A: still one serve
        ([("hit", "A"), ("hit", "A"), ("bounce", "A"), ("bounce", "B"), ("dead", "B")], "A", "didn't return"),
        # B's return goes long: never lands on A's side
        ([("hit", "A"), ("bounce", "A"), ("bounce", "B"), ("hit", "B"), ("dead", "A")], "A", "didn't land"),
        # serve lands straight on the receiver's side
        ([("hit", "A"), ("bounce", "B"), ("dead", "B")], "B", "server's side first"),
        # second bounce on B's side
        ([("hit", "A"), ("bounce", "A"), ("bounce", "B"), ("bounce", "B"), ("dead", "B")], "A", "second bounce"),
        # B volleys A's return before it bounces
        (
            [("hit", "A"), ("bounce", "A"), ("bounce", "B"), ("hit", "B"), ("bounce", "A"), ("hit", "A"), ("hit", "B")],
            "A",
            "volley",
        ),
        # the serve hit was missed by the tracker: first bounce on A means A served
        ([("bounce", "A"), ("bounce", "B"), ("hit", "B"), ("bounce", "A"), ("dead", "A")], "B", "didn't return"),
        # A's shot lands on A's own side
        (
            [("hit", "B"), ("bounce", "B"), ("bounce", "A"), ("hit", "A"), ("bounce", "A"), ("dead", "A")],
            "B",
            "own side",
        ),
    ],
)
def test_referee_point_rules(seq, winner, why):
    events = [ev(k, s, i * 0.4) for i, (k, s) in enumerate(seq)]
    events[-1].why = "test"
    got, reason, _ = referee(events)
    assert got == winner and why in reason, reason


def test_referee_skips_a_detection_gap_when_play_continues():
    # a missed bounce makes B's return look like a volley, but A and B keep hitting: not a fault
    seq = [
        ("hit", "A"),
        ("bounce", "A"),
        ("bounce", "B"),
        ("hit", "B"),
        ("hit", "A"),
        ("bounce", "B"),
        ("hit", "B"),
        ("bounce", "A"),
        ("dead", "A"),
    ]
    events = [ev(k, s, i * 0.4) for i, (k, s) in enumerate(seq)]
    events[-1].why = "test"
    winner, reason, _ = referee(events)
    assert winner == "B" and "didn't return" in reason and "gap" in reason


def test_referee_undecided_without_hits():
    assert referee([ev("dead", "A", 1)])[0] is None


def test_referee_undecided_without_a_bounce():
    # hits alone: usually a ball being handled between points, never a decided point
    winner, reason, _ = referee([ev("hit", "B", 0.0), ev("hit", "B", 0.1), ev("dead", "B", 0.5)])
    assert winner is None and "no bounce" in reason


@pytest.mark.parametrize("fps", [60, 30])
def test_bounce_found_at_60_and_30_fps(fps):
    table = Table(300, 1000, 0.0, 400.0, 650, 20)
    rows = []
    for i in range(int(0.5 * fps)):
        t = i / fps
        rows.append({"seq": i, "t": t, "x": 400 + 600 * t, "y": 400 - 900 * abs(t - 0.25), "state": "observed"})
    evs = events_for(rows, lambda _seq: table, fps)
    assert [(e.kind, e.side) for e in evs] == [("bounce", "A")]
    assert abs(evs[0].t - 0.25) <= 1.5 / fps


def scene(i: int, ball: tuple[float, float] | None) -> np.ndarray:
    """Synthetic side view: white wall, a static orange poster, and a skin-coloured hand moving across."""
    img = np.full((H, W, 3), (215, 228, 232), np.uint8)  # wall (BGR)
    cv2.rectangle(img, (1100, 120), (1140, 170), (40, 130, 230), -1)  # orange-ish poster, static
    hx = 300 + 6 * i
    cv2.circle(img, (hx, 420), 16, (120, 150, 200), -1)  # skin-coloured "hand", slow
    if ball is not None:
        cv2.circle(img, (int(ball[0]), int(ball[1])), 5, (75, 140, 250), -1)  # bright orange ball
    return img


@pytest.mark.parametrize("make", [Detector, LumaDetector])
def test_tracker_follows_the_ball_without_teleports(make):
    tr = Tracker(detector=make())
    pts = []
    for i in range(90):
        x = 200 + 12 * i
        y = 300 + 0.09 * (i - 45) ** 2  # an arc
        ball = (x, y) if not 40 <= i < 44 else None  # a 4-frame occlusion
        pts.append((i, ball, tr.step(i, i / 60, scene(i, ball))))
    obs = [(i, b, p) for i, b, p in pts if p.state == "observed"]
    assert len(obs) >= 75
    # <= 6 px: around i = 15 the ball passes ~10 px from the moving hand (the luma detector's blobs touch there)
    assert all(abs(p.x - b[0]) < 6 and abs(p.y - b[1]) < 6 for _, b, p in obs if b), "only the ball is observed"
    bridged = [p for i, b, p in pts if 40 <= i < 44]
    assert all(p.state in ("predicted", "none") for p in bridged), "occlusion is bridged, never 'observed'"
    steps = [abs(p1.x - p0.x) for (i0, _, p0), (i1, _, p1) in zip(obs, obs[1:], strict=False) if i1 - i0 == 1]
    assert max(steps) < 20, "no jumps between adjacent frames (the ball moves 12 px/frame)"
    assert len({p.track_id for _, _, p in obs}) == 1


@pytest.mark.parametrize("make", [Detector, LumaDetector])
def test_tracker_ignores_a_static_orange_object(make):
    tr = Tracker(detector=make())
    states = [tr.step(i, i / 60, scene(i, None)).state for i in range(60)]
    assert "observed" not in states


def test_tracker_does_not_bridge_dropped_frames():
    # a live reader that fell behind skips frames: the track restarts instead of extrapolating across the gap
    tr = Tracker()  # the default (colour) detector
    pts = []
    for i in list(range(30)) + list(range(45, 75)):
        ball = (200 + 12 * i, 300.0)
        pts.append((i, ball, tr.step(i, i / 60, scene(i, ball))))
    before = {p.track_id for i, _, p in pts if i < 30 and p.state == "observed"}
    after = {p.track_id for i, _, p in pts if i >= 45 and p.state == "observed"}
    assert before and after and not before & after
    assert all(abs(p.x - b[0]) < 4 for _, b, p in pts if p.state == "observed")


def test_view_maps_a_cropped_frame_to_reference_pixels():
    from flight.live import View

    # the phone streams the region x 0.25..0.75, y 0.25..0.75 of its view at 1280x720: a 2x zoom
    v = View((0.25, 0.25, 0.5, 0.5), 1280, 720)
    assert v.scale == 2.0
    assert v.pt(0, 0) == (320.0, 180.0) and v.pt(1280, 720) == (960.0, 540.0)
    t = v.table(Table(100, 1100, 0.05, 400.0, 600, 20))
    x = 700.0  # a point on the cropped table's top edge maps onto the mapped table's top edge
    rx, ry = v.pt(x, 0.05 * x + 400.0)
    assert abs(t.top_y(rx) - ry) < 1e-6 and t.thickness == 10 and t.net_x == v.pt(600, 0)[0]
    assert View(None, 1280, 720).pt(5, 6) == (5, 6)
