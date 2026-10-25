"""SYNTHETIC: serve tosses rendered through a side-on camera at the net line; the estimator recovers height/angle."""

import math

import numpy as np
import pytest

from flight import field as F
from flight.calib import camera_looking_at, solve_pose
from flight.serve import estimate

G = 9.81


def side_cam():
    # 2.6 m from the table's centre line, at the net, 1.3 m up, looking across the table
    return camera_looking_at("side", [0.0, -2.6, 0.55], [0.0, 0.0, 0.1], f_px=1000.0)


def render(cam, height_m, angle_deg, *, fps=30.0, palm_s=0.5, y=0.1, noise_px=1.0, seed=0, strike=True):
    """Palm still at the A end, a toss of `height_m` leaning `angle_deg` toward the net (in x), struck while falling."""
    rng = np.random.default_rng(seed)
    palm = np.array([-F.LENGTH_M / 2 - 0.3, y, 0.15])
    vz = math.sqrt(2 * G * height_m)
    vx = vz * math.tan(math.radians(angle_deg))
    t_up = vz / G
    t_strike = 2 * t_up * 0.85  # struck at 85 % of the way back down (still above the palm)
    out = []
    t = 0.0
    dt = 1 / fps
    t_release = palm_s
    while t < palm_s + t_strike + 0.3:
        if t < t_release:
            p = palm
        else:
            s = t - t_release
            if s < t_strike or not strike:
                p = palm + np.array([vx * s, 0.0, vz * s - 0.5 * G * s * s])
            else:  # struck: 5 m/s toward the net
                s0 = t_strike
                p_hit = palm + np.array([vx * s0, 0.0, vz * s0 - 0.5 * G * s0 * s0])
                p = p_hit + np.array([5.0 * (s - s0), 0.0, -1.0 * (s - s0)])
        uv = cam.project(p[None])[0] + rng.normal(0, noise_px, 2)
        out.append((t, float(uv[0]), float(uv[1])))
        t += dt
    return out, t_release, t_release + t_up, t_release + t_strike


@pytest.mark.parametrize(
    "height,angle",
    [(0.25, 5.0), (0.10, 5.0), (0.30, 40.0)],
    ids=["legal", "too_low", "angled"],
)
def test_toss_recovered_with_honest_sigma(height, angle):
    cam = side_cam()
    samples, t_rel, t_apex, t_hit = render(cam, height, angle)
    got = estimate(samples, cam, server_side="A", calib_trusted=True)
    assert got is not None
    got.pop("_debug")
    assert got["server_side"] == "A"
    assert "release" not in got["evidence_missing"]
    assert got["palm_still_s"] >= 0.4
    assert abs(got["height_m"] - height) <= max(0.02, 3 * got["sigma_height_m"])
    sig_deg = math.degrees(got["sigma_angle_rad"])
    assert abs(math.degrees(got["angle_from_vertical_rad"]) - angle) <= max(4.0, 3 * sig_deg)
    assert abs(got["apex"]["t_s"] - t_apex) < 0.04
    assert got["struck_on_descent"] is True
    assert abs(got["contact"]["t_s"] - t_hit) < 0.05
    assert "depth" in got["evidence_missing"]  # the out-of-plane component is never observed by one camera


def test_unseen_palm_is_missing_evidence_not_a_measurement():
    cam = side_cam()
    samples, *_ = render(cam, 0.25, 5.0)
    rising = [s for s in samples if s[0] >= 0.5 + 1 / 30]  # the resting ball was never detected
    got = estimate(rising, cam, server_side="A", calib_trusted=True)
    assert got is not None
    assert {"release", "palm"} <= set(got["evidence_missing"])
    assert got["height_m"] < 0.25  # a lower bound


def test_pose_from_tapped_corners_lifts_the_same():
    cam = side_cam()
    corners = cam.project(F.CORNERS_M)
    solved = solve_pose("side", corners, 1280, 720)
    samples, *_ = render(cam, 0.25, 5.0, noise_px=0.0)
    got = estimate(samples, solved, server_side="A", calib_trusted=False)
    assert got is not None
    assert "calibration" in got["evidence_missing"] and got["calib_untrusted"] is True
    assert abs(got["height_m"] - 0.25) < 0.05


def test_no_toss_no_event():
    cam = side_cam()
    still = [(i / 30, 300.0, 400.0) for i in range(30)]
    assert estimate(still, cam, server_side="A") is None
