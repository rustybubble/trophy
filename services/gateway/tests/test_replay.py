import base64
import io
import json

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from trophy.recordings import atomic_json

from gateway.app import create_app
from gateway.config import Settings
from gateway.replay import project_mark
from gateway.tokens import mint

SECRET = "test-replay-secret-012345"


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "recordings" / "g1" / "c1"
    (path / "frames").mkdir(parents=True)
    atomic_json(
        path / "meta.json",
        {
            "game_id": "g1",
            "cam_id": "c1",
            "w": 100,
            "h": 100,
            "t0_game_s": 4,
            "last_t_game_s": 6,
            "duration_s": 2.1,
            "fps": 30,
            "closed": True,
        },
    )
    atomic_json(path.parent / "game.json", {"game_id": "g1", "sport": "table_tennis"})
    rows = []
    for i in range(3):
        name = f"frames/{i:010d}.jpg"
        Image.new("RGB", (100, 100), (i * 100, 20, 20)).save(path / name)
        rows.append({"seq": i, "t_game_s": 4 + i, "pts": i, "file": name, "seg": "seg_000000.m4s"})
    (path / "index.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (path / "tracks_ball.jsonl").write_text(
        json.dumps({"seq": 0, "t_game_s": 4, "px": [50, 50], "conf": 0.7})
        + "\n"
        + json.dumps({"seq": 1, "t_game_s": 5, "px": None, "conf": 0})
        + "\n"
    )
    (path / "index.m3u8").write_text('#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:2,\nseg_000000.m4s\n#EXT-X-ENDLIST\n')
    (path / "init.mp4").write_bytes(b"synthetic-init")
    (path / "seg_000000.m4s").write_bytes(b"synthetic-segment")
    atomic_json(
        path / "calibration.json",
        {
            "game_id": "g1",
            "cam_id": "c1",
            "trusted": True,
            "H_img_to_field": [0.01, 0, 0, 0, 0.02, 0, 0, 0, 1],
            "overlay_px": [[0, 0, 100, 0]],
        },
    )
    return tmp_path


@pytest.fixture
def client(archive):
    call = {
        "game_id": "g1",
        "id": "call1",
        "t_game_s": 5,
        "evidence": [{"cam_id": "c1"}],
        "overlay": {"bounce_marks": [{"pos_m": [0.5, 1, 0], "sigma_m": 0.01, "t_game_s": 5}]},
    }

    def upstream(request):
        if request.url.path.endswith("/v1/identity"):
            return httpx.Response(200, json={"token": "synthetic-read-token"})
        sql = request.content.decode()
        rows = [json.dumps(call)] if "FROM call " in sql else []
        return httpx.Response(
            200, json=[{"schema": {"elements": [{"name": {"some": "json"}}]}, "rows": [[r] for r in rows]}]
        )

    st = Settings(token_secret=SECRET, data_dir=archive)
    with TestClient(
        create_app(st, r=fakeredis.FakeAsyncRedis(), http=httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
    ) as c:
        yield c


def headers(role="display", game="g1"):
    token, _ = mint(SECRET, game, "c1", role, 600)
    return {"Authorization": f"Bearer {token}"}


def test_replay_requires_game_scoped_auth_and_service_crops(client):
    url = "/api/replay/g1/frames?cam=c1&t0=4&t1=6&n=4&crop=10,10,20,30"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(game="g2")).status_code == 403
    assert client.get(url, headers=headers()).status_code == 403
    response = client.get(url, headers=headers("service", "*"))
    assert response.status_code == 200, response.text
    frames = response.json()["frames"]
    assert [f["seq"] for f in frames] == [0, 1, 2]
    for f in frames:
        raw = base64.b64decode(f["jpeg_b64"])
        assert len(raw) < 1_000_000 and len(f["jpeg_b64"]) < 1_000_000
        with Image.open(io.BytesIO(raw)) as image:
            assert image.size == (20, 30)
    for query in ["n=5", "crop=-1,0,20,20", "crop=90,0,20,20", "crop=bad", "t0=nan", "t1=99"]:
        params = {"cam": "c1", "t0": 4, "t1": 6, "n": 4}
        key, value = query.split("=")
        params[key] = value
        assert client.get("/api/replay/g1/frames", params=params, headers=headers("service")).status_code == 422


def test_watch_manifest_playlists_segments_tracks_and_scope(client):
    response = client.get("/api/watch/g1/manifest", headers=headers())
    assert response.status_code == 200, response.text
    manifest = response.json()
    assert manifest["has_tracks"] == {"ball": True, "players": False}
    playlist_url = manifest["cams"][0]["hls_url"]
    playlist = client.get(playlist_url)
    assert playlist.status_code == 200 and "seg_000000.m4s?token=" in playlist.text
    assert 'URI="init.mp4?token=' in playlist.text
    token = playlist_url.split("?token=")[1]
    assert client.get("/api/watch/g1/hls/c1/init.mp4?token=" + token).content == b"synthetic-init"
    assert client.get("/api/watch/g1/hls/c1/seg_000000.m4s").status_code == 401
    assert client.get("/api/watch/g1/hls/c1/meta.json", headers=headers()).status_code == 404
    assert client.get("/api/watch/g1/hls/c1/seg_000000.m4s", headers=headers(game="g2")).status_code == 403
    tracks = client.get("/api/watch/g1/tracks?cam=c1&kind=ball&t0=4&t1=6", headers=headers()).json()
    assert tracks["schema"] == "replay.tracks.v1" and tracks["frames"][1]["p"] == []
    assert tracks["frames"][0]["p"][0]["bb"] == pytest.approx([0.46, 0.46, 0.08, 0.08])


def test_overlay_projects_mark_and_one_sigma_covariance(client):
    response = client.get("/api/replay/g1/overlay?cam=c1&t0=4&t1=6&call_id=call1", headers=headers())
    assert response.status_code == 200, response.text
    mark = response.json()["marks"][0]
    assert mark["px"] == pytest.approx([50, 50])
    assert [mark["ellipse_px"]["rx"], mark["ellipse_px"]["ry"]] == pytest.approx([1, 0.5])
    assert response.json()["frames"][1]["ball_px"] is None
    assert response.json()["warnings"] == []


def test_projection_handles_covariance_and_unobservable_height():
    cal = {"H_img_to_field": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
    mark = {"pos_m": [2, 3], "cov_m2": [4, 0, 0, 1]}
    out = project_mark(mark, cal, 1)
    assert out["ellipse_px"]["rx"] == 2
    assert out["ellipse_px"]["ry"] == 1
    assert project_mark({"pos_m": [2, 3, 1], "sigma_m": 1}, cal, 1) is None
    with pytest.raises(ValueError):
        project_mark({**mark, "cov_m2": [-1, 0, 0, 1]}, cal, 1)
    pinhole = {"K": [100, 0, 50, 0, 100, 50, 0, 0, 1], "rvec": [0, 0, 0], "tvec": [0, 0, 10]}
    out = project_mark({"pos_m": [1, 2, 1], "sigma_m": 0.1}, pinhole, 1)
    assert out["px"] == pytest.approx([50 + 100 / 11, 50 + 200 / 11])
