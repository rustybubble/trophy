"""Clips as live cameras: the mode decision from the recordings' own timestamps, and the streamer's homography."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

from gateway.demo import plan

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stream_clips.py"


def _streamer():
    spec = importlib.util.spec_from_file_location("stream_clips", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["stream_clips"] = mod  # dataclasses look their module up
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def clip(uid: str, start_ms: float | None, dur: float) -> dict:
    return {"upload_id": uid, "recorded_at_ms": start_ms, "duration_s": dur}


def test_takes_that_do_not_overlap_play_back_to_back_in_recording_order():
    # the team's two takes: 16:22:09 for 26.1 s, then 16:23:15 for 39.2 s (uploaded in the other order)
    mode, clips, reason = plan([clip("u2", 66_000, 39.2), clip("u1", 0, 26.1)], "auto")
    assert mode == "sequential" and [c["upload_id"] for c in clips] == ["u1", "u2"]
    assert "don't overlap" in reason


def test_overlapping_recordings_are_angles_aligned_by_their_start_times():
    mode, clips, reason = plan([clip("a", 10_000, 30), clip("b", 12_500, 30), clip("c", 9_000, 40)], "auto")
    assert mode == "simultaneous" and "overlap" in reason
    assert {c["upload_id"]: c["auto_offset_s"] for c in clips} == {"a": 1.0, "b": 3.5, "c": 0.0}


def test_without_timestamps_the_clips_are_treated_as_angles_and_the_user_can_override():
    mode, _, reason = plan([clip("a", None, 10), clip("b", None, 10)], "auto")
    assert mode == "simultaneous" and "no recording timestamps" in reason
    mode, _, _ = plan([clip("a", 0, 10), clip("b", 1000, 10)], "sequential")
    assert mode == "sequential"


def test_streamer_homography_maps_the_tapped_corners_to_the_table():
    sc = _streamer()
    corners = [(0.2074, 0.7932), (0.7612, 0.7970), (0.6810, 0.7473), (0.2761, 0.7456)]  # take 1's detected table
    h9, err = sc.homography(corners)
    assert err < 1e-6
    hm = np.array(h9).reshape(3, 3)
    px = np.array([[x * sc.W, y * sc.H] for x, y in corners])
    assert np.allclose(sc.apply(hm, px), sc.CORNERS_M, atol=1e-6)


def test_library_presets_are_validated_and_bad_ones_are_listed_with_an_error(tmp_path: Path):
    from gateway.demo import load_presets

    good = tmp_path / "good"
    good.mkdir()
    (good / "side.mp4").write_bytes(b"x")
    (good / "preset.json").write_text(
        '{"title": "t", "mode": "simultaneous", "cameras": [{"label": "side", "video": "side.mp4", '
        '"corners_norm": [[0.1, 0.9], [0.9, 0.9], [0.8, 0.5], [0.2, 0.5]], "offset_s": 0}]}'
    )
    missing = tmp_path / "missing"
    missing.mkdir()
    (missing / "preset.json").write_text('{"cameras": [{"label": "a", "video": "nope.mp4", "corners_norm": []}]}')
    (tmp_path / "not-a-preset").mkdir()  # no preset.json: ignored
    out = {p["preset_id"]: p for p in load_presets(tmp_path)}
    assert set(out) == {"good", "missing"}
    assert "error" not in out["good"] and out["good"]["cameras"][0]["label"] == "side"
    assert "nope.mp4 is missing" in out["missing"]["error"]
    assert load_presets(tmp_path / "absent") == []


def test_the_stream_ends_the_game_once_every_camera_has_sent_its_last_frame():
    from gateway.demo import apply_stream_event

    live: dict = {"status": "starting", "cameras": {}}
    assert apply_stream_event(live, {"event": "joined", "label": "side", "cam_id": "c_1", "clips": ["a.mp4"]}) is None
    assert apply_stream_event(live, {"event": "start", "wall0_ms": 1.0}) is None
    assert live["status"] == "streaming" and live["cameras"]["side"]["cam_id"] == "c_1"
    assert apply_stream_event(live, {"event": "done", "label": "side", "frames": 30, "seconds": 1.0}) is None
    assert live["cameras"]["side"]["frames"] == 30
    assert apply_stream_event(live, {"event": "all_done", "cameras": {}}) == "end_game"
    live["ended"] = True
    assert apply_stream_event(live, {"event": "all_done", "cameras": {}}) is None  # never twice
