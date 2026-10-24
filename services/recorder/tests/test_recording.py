import io
import json
import subprocess
from dataclasses import replace

import fakeredis
import pytest
from PIL import Image
from trophy.framebus import Frame, FrameWriter
from trophy.recordings import RecordingStore, ffmpeg_binary, select_encoder

from recorder.service import CameraRecording, Recorder


def frame(seq=0, t=10, game="game1", cam="cam1"):
    out = io.BytesIO()
    Image.new("RGB", (64, 64), (seq % 255, 60, 90)).save(out, "JPEG")
    return Frame(str(seq + 1) + "-0", game, cam, seq, t * 1000, t * 1000, t, 1, 64, 64, "file", 0, out.getvalue())


@pytest.fixture
def ffmpeg():
    try:
        path = ffmpeg_binary()
    except RuntimeError:
        pytest.skip("set TROPHY_FFMPEG to run codec integration tests")
    assert select_encoder(path) == "libx264"  # this fixture expects the portable CPU build
    return path


def test_hls_source_index_sprites_and_missing_frames(tmp_path, ffmpeg):
    store = RecordingStore(tmp_path)
    rec = CameraRecording(store, frame(), 30, "libx264")
    try:
        for i in range(66):
            if i == 10:
                continue
            f = frame(i, 10 + i / 30)
            assert rec.add(f)
            assert not rec.add(f)
    finally:
        rec.close()
    meta = store.meta("game1", "cam1")
    assert meta["closed"] and meta["error"] is None
    assert meta["frame_count"] == 65 and meta["held_video_frames"] == 1 and meta["sequence_gaps"] == 1
    rows = store.rows("game1", "cam1", "index.jsonl")
    assert len(rows) == 65 and rows[10]["seq"] == 11 and rows[10]["held_frames_before"] == 1
    assert rows[10]["pts"] == pytest.approx(11 / 30)
    assert rows[-1]["seg"] == "seg_000001.m4s"
    playlist = (rec.path / "index.m3u8").read_text()
    assert "#EXT-X-ENDLIST" in playlist and "#EXTINF:2.000000" in playlist and 'URI="init.mp4"' in playlist
    with Image.open(rec.path / "sprite_0.jpg") as sprite:
        assert sprite.size == (1600, 900)
    assert json.loads((rec.path / "sprite.json").read_text())["count"] == 2
    clip = store.clip("game1", "cam1", 10.5, 11.5)
    result = subprocess.run([ffmpeg, "-v", "error", "-i", str(clip), "-f", "null", "-"], capture_output=True)
    assert result.returncode == 0 and clip.stat().st_size > 1000
    with pytest.raises(FileExistsError):
        CameraRecording(store, frame(), 30, "libx264")


def test_recorder_copies_tracks_and_calibration_without_dropping_backlog(tmp_path, ffmpeg):
    r = fakeredis.FakeRedis()
    writer = FrameWriter(r)
    for i in range(10):
        f = frame(i, 1 + i / 30)
        writer.write(
            game_id=f.game_id,
            cam_id=f.cam_id,
            seq=i,
            t_phone_ms=0,
            t_srv_ms=0,
            t_game_s=f.t_game_s,
            sync_err_ms=1,
            jpeg=f.data,
            source="file",
        )
    for t, px in [(1, [32, 30]), (1.1, None), (1.2, [40, 20])]:
        r.xadd("trk:ball:cam1", {"json": json.dumps({"t_game_s": t, "seq": 0, "px": px, "conf": 0.5})})
    cal = {"game_id": "game1", "cam_id": "cam1", "H_img_to_field": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
    r.set("calib:cam1", json.dumps(cal))
    rec = Recorder(r, tmp_path, 30, "libx264")
    try:
        assert rec.poll() == 10
        assert rec.poll() == 0
        assert r.exists("recorder:heartbeat")
    finally:
        rec.close()
    assert not r.exists("recorder:heartbeat")
    store = rec.store
    assert len(store.rows("game1", "cam1", "index.jsonl")) == 10
    assert len(store.rows("game1", "cam1", "tracks_ball.jsonl")) == 3
    assert json.loads((store.camera("game1", "cam1") / "calibration.json").read_text()) == cal
    tracks = store.tracks("game1", "cam1", "ball", 1, 2)
    assert tracks["schema"] == "replay.tracks.v1" and tracks["rate_hz"] == pytest.approx(10)
    assert tracks["frames"][1]["p"] == []
    assert tracks["frames"][0]["p"][0]["bb"][0] == pytest.approx(28 / 64)


def test_time_reversal_and_invalid_jpeg_do_not_get_recorded(tmp_path, ffmpeg):
    rec = CameraRecording(RecordingStore(tmp_path), frame(), 30, "libx264")
    try:
        rec.add(frame())
        with pytest.raises(ValueError, match="backwards"):
            rec.add(frame(1, 9))
        with pytest.raises(ValueError, match="size changed"):
            rec.add(replace(frame(1, 11), w=100))
        assert rec.meta["frame_count"] == 1
    finally:
        rec.close()


def test_archive_rejects_traversal_and_symlinks(tmp_path):
    store = RecordingStore(tmp_path / "archive")
    with pytest.raises(ValueError):
        store.camera("../game", "cam")
    (tmp_path / "archive" / "game").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    (tmp_path / "archive" / "game" / "cam").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError):
        store.camera("game", "cam")


def test_end_game_drains_pending_frames_before_finalizing(tmp_path, ffmpeg):
    r = fakeredis.FakeRedis()
    writer = FrameWriter(r)
    for i in range(140):
        f = frame(i, 1 + i / 30)
        writer.write(
            game_id=f.game_id,
            cam_id=f.cam_id,
            seq=i,
            t_phone_ms=0,
            t_srv_ms=0,
            t_game_s=f.t_game_s,
            sync_err_ms=1,
            jpeg=f.data,
            source="file",
        )
    r.xadd("ctl:engine", {"json": json.dumps({"cmd": "end_game", "game_id": "game1"})})
    rec = Recorder(r, tmp_path, 30, "libx264")
    try:
        assert rec.poll() == 120
        assert not rec.store.meta("game1", "cam1")["closed"]
        assert rec.poll() == 20
        assert rec.store.meta("game1", "cam1")["closed"]
        assert rec.poll() == 0
        assert rec.store.meta("game1", "cam1")["frame_count"] == 140
    finally:
        rec.close()


def test_spacetime_end_monitor_reads_status_with_anonymous_identity(monkeypatch):
    from recorder.state import GameEndMonitor

    calls = []

    def urlopen(request, timeout):
        calls.append(request)
        if request.full_url.endswith("/identity"):
            return io.BytesIO(b'{"token":"synthetic-reader"}')
        return io.BytesIO(
            json.dumps([{"schema": {"elements": [{"name": {"some": "status"}}]}, "rows": [["ended"]]}]).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monitor = GameEndMonitor("http://localhost:3100", "trophy-test")
    try:
        assert monitor._query({"game1"}) == {"game1"}
        assert calls[1].data == b"SELECT * FROM game WHERE game_id = 'game1'"
        assert calls[1].headers["Authorization"] == "Bearer synthetic-reader"
    finally:
        monitor.close()


def test_automatic_spacetime_end_finalizes_without_control_command(tmp_path, ffmpeg):
    class Monitor:
        def check(self, games):
            return {"game1"}

        def close(self):
            pass

    r = fakeredis.FakeRedis()
    f = frame()
    FrameWriter(r).write(
        game_id=f.game_id,
        cam_id=f.cam_id,
        seq=0,
        t_phone_ms=0,
        t_srv_ms=0,
        t_game_s=f.t_game_s,
        sync_err_ms=1,
        jpeg=f.data,
        source="file",
    )
    rec = Recorder(r, tmp_path, 30, "libx264", Monitor())
    try:
        assert rec.poll() == 1
        assert rec.store.meta("game1", "cam1")["closed"]
        assert not r.exists("ctl:engine")
    finally:
        rec.close()
