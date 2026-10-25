"""Synthetic end to end: BlurBall-like candidates -> tracker -> fuse -> events, measured against truth."""

import json

import numpy as np
import pytest

from flight.calib import camera_looking_at, solve_pose
from flight.detect import blurball_json_candidates
from flight.events import detect_bounces, detect_dead, detect_hits, serve_toss
from flight.lift import fuse
from flight.synth import DEFAULT_CAMERAS, blurball_like_json, sample_frames, simulate
from flight.track import Tracker


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    sim = simulate(seed=3, shots=6)
    cams = {cid: camera_looking_at(cid, **spec) for cid, spec in DEFAULT_CAMERAS.items()}
    skews = {"side": 0.0, "diag": 0.012}
    per = {cid: sample_frames(sim, cam, 30.0, skews[cid]) for cid, cam in cams.items()}
    for cid in cams:
        blurball_like_json(per[cid], d / f"{cid}.json", noise_px=1.5, miss_p=0.08, false_p=0.05, seed=1)
    return sim, cams, per, d


def test_tracks_follow_truth_despite_false_blobs(dataset):
    sim, cams, per, d = dataset
    for cid in cams:
        track = Tracker().run(blurball_json_candidates(d / f"{cid}.json"))
        truth = {f["frame"]: f["xy_px"] for f in per[cid]["frames"] if f["xy_px"] is not None}
        assert len(track) >= 0.8 * len(truth), (cid, len(track), len(truth))
        errs = [np.linalg.norm(np.array(s["xy_px"]) - truth[s["frame"]]) for s in track if s["frame"] in truth]
        assert len(errs) == len(track), "a tracked sample on a frame with no ball"
        assert np.percentile(errs, 95) < 6.0, np.percentile(errs, 95)


def test_fused_track_matches_truth_in_metres(dataset):
    sim, cams, per, d = dataset
    # calibrate from the projected corners, as a user would from taps
    solved = {cid: solve_pose(cid, per[cid]["corners_px"], 1280, 720) for cid in cams}
    tracks = {cid: Tracker().run(blurball_json_candidates(d / f"{cid}.json")) for cid in cams}
    t3 = fuse(tracks, solved, px_sigma=2.0, skew_sigma_s=0.012)
    assert len(t3) >= 0.7 * len(tracks["side"])
    errs = []
    for r in t3:
        i = int(round(r["t_s"] / sim["dt_s"]))
        truth = np.array(sim["track"][i]["xyz_m"])
        errs.append(np.linalg.norm(np.array(r["xyz_m"]) - truth))
    errs = np.array(errs)
    assert np.median(errs) < 0.04, np.median(errs)
    assert np.percentile(errs, 95) < 0.12, np.percentile(errs, 95)
    # σ should be an honest scale for the error: most errors within 3σ
    sig = np.array([r["sigma_m"] for r in t3])
    assert np.mean(errs < 3 * sig) > 0.9
    assert t3


def test_events_match_truth(dataset):
    sim, cams, per, d = dataset
    solved = {cid: solve_pose(cid, per[cid]["corners_px"], 1280, 720) for cid in cams}
    tracks = {cid: Tracker().run(blurball_json_candidates(d / f"{cid}.json")) for cid in cams}
    t3 = fuse(tracks, solved, px_sigma=2.0, skew_sigma_s=0.012)
    bounces = detect_bounces(t3, cams=solved, tracks2d=tracks)
    truth_b = sim["bounces"]
    matched = 0
    errs = []
    for tb in truth_b:
        near = [b for b in bounces if abs(b["t_s"] - tb["t_s"]) < 0.08]
        if near:
            b = near[0]
            assert b["side"] == tb["side"]
            errs.append(np.hypot(b["xyz_m"][0] - tb["xyz_m"][0], b["xyz_m"][1] - tb["xyz_m"][1]))
            matched += 1
    assert matched >= len(truth_b) - 1, (matched, len(truth_b), [round(b["t_s"], 2) for b in bounces])
    assert len(bounces) <= len(truth_b) + 1
    assert np.median(errs) < 0.04 and max(errs) < 0.15, errs
    hits = detect_hits(t3, bounces)
    truth_h = sim["hits"]
    hm = sum(any(abs(h["t_s"] - th["t_s"]) < 0.1 for h in hits) for th in truth_h)
    assert hm >= len(truth_h) - 2, (hm, len(truth_h))
    dead = detect_dead(t3)
    assert any(e["reason"] == "floor" for e in dead)
    st = serve_toss(t3, hits)
    assert st is not None
    true_h = sim["serve"]["apex"]["xyz_m"][2] - sim["serve"]["release"]["xyz_m"][2]
    assert abs(st["height_m"] - true_h) < 0.04, (st["height_m"], true_h)
    json.dumps({"t3": t3[:2], "bounces": bounces, "hits": hits, "serve": st})  # serialisable
