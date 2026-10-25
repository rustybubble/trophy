"""SYNTHETIC: the live seam. Projected truth samples -> Analyzer (golden sport module + serve toss) -> ev:flight."""

import json
import time
from types import SimpleNamespace

import fakeredis
import numpy as np
import pytest

from flight import field as F
from flight.calib import camera_looking_at
from flight.live import REPO, Analyzer, View, calib_from_corners, calib_from_json
from flight.synth import DEFAULT_CAMERAS, sample_frames, simulate


def args(**kw):
    base = dict(module=REPO / "sports" / "table_tennis", fps=30.0, settle=0.2, toss_hold=1.5, fill_gaps=0.25)
    return SimpleNamespace(**{**base, **kw})


def taps(cam):
    """The PWA's tap order (A_left, A_right, B_right, B_left) from a camera that sees the table."""
    order = [3, 0, 1, 2]  # field.CORNERS_M is A-right, B-right, B-left, A-left
    return cam.project(F.CORNERS_M[order]).ravel().tolist()


@pytest.fixture(scope="module")
def run():
    sim = simulate(seed=3, shots=6)
    cam = camera_looking_at("c_side", **DEFAULT_CAMERAS["side"])
    frames = sample_frames(sim, cam, 30.0)["frames"]
    r = fakeredis.FakeRedis()
    r.hset("game:g_test0001", mapping={"t0_ms": repr(time.time() * 1000), "sport": "table_tennis"})
    an = Analyzer(r, "g_test0001", None, args())
    an.set_calib(calib_from_corners("c_side", taps(cam)))
    rng = np.random.default_rng(0)
    for seq, f in enumerate(frames):
        if f["xy_px"] is None:
            an.tick("c_side", f["t_s"], seq)
        else:
            u, v = np.asarray(f["xy_px"]) + rng.normal(0, 1.0, 2)
            an.add("c_side", f["t_s"], seq, float(u), float(v), 0.9)
        an.step()
    an.wall_last -= 10  # the phone stopped streaming: the open segment closes on the wall clock
    an.step()
    evs = [json.loads(fields[b"json"]) for _id, fields in r.xrange("ev:flight")]
    return sim, evs


def test_bounces_and_sides_match_truth(run):
    sim, evs = run
    bounces = [e for e in evs if e["type"] == "bounce"]
    truth = [(b["t_s"], b["side"]) for b in sim["bounces"]]
    matched = 0
    for t, side in truth:
        near = [b for b in bounces if abs(b["t_game_s"] - t) < 0.06]
        matched += bool(near) and near[0]["side"] == side
    assert matched >= len(truth) - 1, (matched, len(truth))
    assert len(bounces) <= len(truth) + 1
    assert all(b["payload"].get("calib_untrusted") for b in bounces)  # --corners / the stub are never trusted


def test_the_toss_is_a_serve_not_a_floor_bounce(run):
    sim, evs = run
    first_truth_bounce = min(b["t_s"] for b in sim["bounces"])
    early_dead = [e for e in evs if e["type"] == "ball_dead" and e["t_game_s"] < first_truth_bounce]
    assert not early_dead, early_dead
    toss = [e for e in evs if e["type"] == "serve_toss"]
    assert len(toss) == 1
    p = toss[0]["payload"]
    h_true = sim["serve"]["apex"]["xyz_m"][2] - sim["serve"]["release"]["xyz_m"][2]
    # one camera, plane-lifted: within 3 sigma (or 3 cm) of the truth
    assert abs(p["height_m"] - h_true) <= max(0.03, 3 * p["sigma_height_m"]), (p["height_m"], h_true)
    assert p["observable_plane"] == "xz" and "depth" in p["evidence_missing"]


def test_events_are_published_once(run):
    _sim, evs = run
    ids = [e["id"] for e in evs]
    assert len(ids) == len(set(ids))


def test_crop_maps_back_to_the_reference_view():
    v = View((0.25, 0.1, 0.5, 0.5), 1280, 720)  # a 2x zoom on part of the full view
    assert v.pt(0, 0) == pytest.approx((320.0, 72.0))
    assert v.pt(1280, 720) == pytest.approx((960.0, 432.0))
    assert View(None, 640, 360).pt(320, 180) == pytest.approx((640.0, 360.0))


def test_gateway_stub_calibration_gets_a_pose():
    cam = camera_looking_at("c_side", **DEFAULT_CAMERAS["side"])
    c0 = calib_from_corners("c_side", taps(cam))
    c = calib_from_json("c_side", {"H_img_to_field": list(c0.H), "image_size": {"w": 1280, "h": 720}, "trusted": False})
    assert c.pose is not None and not c.trusted
    assert np.linalg.norm(c.pose.centre_m - cam.centre_m) < 0.05
