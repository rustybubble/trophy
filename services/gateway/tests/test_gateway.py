import json
import struct

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from trophy.framebus import pack_header
from trophy.timebase import now_ms

from gateway.app import create_app
from gateway.config import Settings
from gateway.tokens import TokenError, mint, normalize_role, verify

SECRET = "test-secret-0123456789"


def make_jpeg(w=1280, h=720):
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, h, w, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + sof0 + b"\xff\xda\x00\x02" + b"\x00" * 16 + b"\xff\xd9"


class Upstream:
    """Fake Cartesia / adapter / rules / Spacetime behind one httpx.MockTransport."""

    def __init__(self):
        self.adapter_up = False
        self.calls = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        url = str(req.url)
        if url == "https://api.cartesia.ai/access-token":
            assert req.headers["authorization"] == "Bearer sk_test"
            assert json.loads(req.content)["grants"] == {"tts": True, "stt": True}
            return httpx.Response(200, json={"token": "ct_short_lived"})
        if url.endswith(":8050/calibrate"):
            if not self.adapter_up:
                raise httpx.ConnectError("down")
            return httpx.Response(200, json={"schema": "trophy.calibration.v1", "solver": "adapter"})
        if url.endswith(":8100/ask"):
            body = json.loads(req.content)
            return httpx.Response(
                200,
                json={
                    "answer": f"[test] {body['question']}",
                    "speech": "x",
                    "kind": "check",
                    "check": "in_out",
                    "p": 0.82,
                    "calibrated": False,
                    "citations": [{"rule_id": "T-1", "title": "t", "url": "https://example.invalid", "quote": "q"}],
                    "moss_ms": 12.0,
                    "latency_ms": 900.0,
                },
            )
        if url.endswith("/v1/identity"):
            return httpx.Response(200, json={"identity": "ab", "token": "stdb_anon"})
        if "/sql" in url:
            elements = [{"name": {"some": "created_at_ms"}}, {"name": {"some": "t_game_s"}}]
            return httpx.Response(200, json=[{"schema": {"elements": elements}, "rows": [[now_ms() - 500, 1.0]]}])
        return httpx.Response(404)


@pytest.fixture
def env(tmp_path):
    r = fakeredis.FakeAsyncRedis()
    up = Upstream()
    st = Settings(token_secret=SECRET, cartesia_api_key="sk_test", data_dir=tmp_path)
    app = create_app(st, r=r, http=httpx.AsyncClient(transport=httpx.MockTransport(up)))
    with TestClient(app) as client:
        yield client, r, up


def ctl_cmds(client, r):
    rows = client.portal.call(r.xrange, "ctl:engine")
    return [json.loads(f[b"json"]) for _, f in rows]


def new_game(client, role="cam"):
    g = client.post("/api/games", json={"sport": "table_tennis"}).json()
    j = client.post(
        f"/api/games/{g['game_id']}/join", json={"join_key": g["join_key"], "label": "side", "role": role}
    ).json()
    return g, j


# ---------------------------------------------------------------- tokens
def test_tokens_roundtrip_tamper_expiry():
    tok, exp = mint(SECRET, "g_abcdefgh", "c_abcdef", "cam,judge", 60)
    c = verify(SECRET, tok)
    assert (c.game_id, c.cam_id, c.has("judge"), c.has("display")) == ("g_abcdefgh", "c_abcdef", True, False)
    body, mac = tok.split(".")
    with pytest.raises(TokenError):
        verify(SECRET, body + "." + mac[:-2] + ("AA" if mac[-2:] != "AA" else "BB"))
    with pytest.raises(TokenError):
        verify("other-secret-0123456789", tok)
    with pytest.raises(TokenError):
        verify(SECRET, tok, now_ms=exp + 1)
    assert normalize_role("judge, cam") == "cam,judge"
    with pytest.raises(TokenError):
        normalize_role("service")


# ---------------------------------------------------------------- games, join, ctl
def test_create_join_and_ctl_allowlist(env):
    client, r, _ = env
    g, j = new_game(client)
    assert g["join_url"] == f"https://trophy.photo/cam/?g={g['game_id']}&k={g['join_key']}"
    assert j["frame"]["w"] == 1280 and j["stdb"]["uri"] == "wss://trophy.photo/stdb"
    pub = client.get(f"/api/games/{g['game_id']}/public").json()
    assert pub["sport"] == "table_tennis" and "join_key" not in pub
    # rejoin with the stored cam_id keeps it
    j2 = client.post(
        f"/api/games/{g['game_id']}/join", json={"join_key": g["join_key"], "role": "cam", "cam_id": j["cam_id"]}
    ).json()
    assert j2["cam_id"] == j["cam_id"]
    assert client.post(f"/api/games/{g['game_id']}/join", json={"join_key": "x" * 22}).status_code == 403
    assert (
        client.post(f"/api/games/{g['game_id']}/join", json={"join_key": g["join_key"], "role": "god"}).status_code
        == 422
    )

    cam = {"Authorization": f"Bearer {j['cam_token']}"}
    assert (
        client.post("/api/ctl", json={"cmd": "challenge", "args": {"call_id": "01JABC"}}, headers=cam).status_code
        == 202
    )
    assert client.post("/api/ctl", json={"cmd": "end_game"}, headers=cam).status_code == 403
    assert client.post("/api/ctl", json={"cmd": "create_game"}, headers=cam).status_code == 403
    assert client.post("/api/ctl", json={"cmd": "challenge"}).status_code == 401
    _, judge = new_game(client, role="judge")
    jh = {"Authorization": f"Bearer {judge['cam_token']}"}
    bad = client.post(
        "/api/ctl", json={"cmd": "resolve_challenge", "args": {"challenge_id": "x", "result": "maybe"}}, headers=jh
    )
    assert bad.status_code == 422
    ok = client.post(
        "/api/ctl", json={"cmd": "submit_house_rule", "args": {"text": "first to 7", "source": "typed"}}, headers=jh
    )
    assert ok.status_code == 202
    cmds = ctl_cmds(client, r)
    assert [c["cmd"] for c in cmds].count("create_game") == 2
    ch = next(c for c in cmds if c["cmd"] == "challenge")
    assert ch["by_cam_id"] == j["cam_id"] and ch["schema"] == "trophy.ctl.v1" and ch["args"] == {"call_id": "01JABC"}


# ---------------------------------------------------------------- frames + clock
def test_frames_ws_writes_bus_and_still(env):
    client, r, _ = env
    g, j = new_game(client)
    jpeg = make_jpeg()
    with client.websocket_connect(f"/api/ws/frames?token={j['cam_token']}") as ws:
        for seq in range(3):
            ws.send_bytes(pack_header(seq, now_ms()) + jpeg)
        ws.send_bytes(b"garbage")  # ignored, connection survives
        ws.send_bytes(pack_header(3, now_ms()) + jpeg)
    rows = client.portal.call(r.xrange, f"frames:{j['cam_id']}")
    assert len(rows) == 4
    f = rows[-1][1]
    assert f[b"seq"] == b"3" and f[b"w"] == b"1280" and f[b"source"] == b"ws" and f[b"data"] == jpeg
    assert float(f[b"sync_err_ms"]) == 1000.0  # no clock fit yet: arrival time, flagged
    assert 0 <= float(f[b"t_game_s"]) < 5
    still = client.get(f"/api/cams/{j['cam_id']}/still", headers={"Authorization": f"Bearer {j['cam_token']}"})
    assert still.status_code == 200 and still.content == jpeg and still.headers["x-seq"] == "3"
    assert "x-crop" not in still.headers
    health = [c for c in ctl_cmds(client, r) if c["cmd"] == "camera_health"]
    assert health and health[-1]["args"]["connected"] is False


def test_cropped_frames_carry_their_crop(env):
    client, r, _ = env
    g, j = new_game(client)
    jpeg = make_jpeg()
    with client.websocket_connect(f"/api/ws/frames?token={j['cam_token']}") as ws:
        ws.send_bytes(pack_header(0, now_ms(), 0, crop=(0.125, 0.25, 0.5, 0.5)) + jpeg)
    f = client.portal.call(r.xrange, f"frames:{j['cam_id']}")[-1][1]
    assert f[b"crop"] == b"0.125,0.25,0.5,0.5" and f[b"data"] == jpeg
    still = client.get(f"/api/cams/{j['cam_id']}/still", headers={"Authorization": f"Bearer {j['cam_token']}"})
    assert still.headers["x-crop"] == "0.125,0.25,0.5,0.5"


def test_frames_ws_rejects_bad_tokens_and_display_role(env):
    client, _, _ = env
    g, j = new_game(client, role="display")
    for url in ("/api/ws/frames", "/api/ws/frames?token=nope", f"/api/ws/frames?token={j['cam_token']}"):
        with pytest.raises(Exception), client.websocket_connect(url) as ws:  # noqa: B017
            ws.send_bytes(b"x")
            ws.receive_bytes()


def test_ctl_ws_clock_fit_then_onsets_and_acks(env, tmp_path):
    client, r, _ = env
    g, j = new_game(client)
    offset = 5000.0  # phone clock is 5 s behind the server
    with client.websocket_connect(f"/api/ws/ctl?token={j['cam_token']}") as ws:
        prev = None
        for _ in range(5):
            t0 = now_ms() - offset
            ws.send_json({"type": "ping", "t0": t0, **({"prev": prev} if prev else {})})
            pong = ws.receive_json()
            assert pong["type"] == "pong" and pong["t0"] == t0
            if prev:
                assert ws.receive_json()["type"] == "sync"
            prev = {"t0": t0, "t1": pong["t1"], "t2": pong["t2"], "t3": now_ms() - offset}
        ws.send_json({"type": "ping", "t0": now_ms() - offset, "prev": prev})
        ws.receive_json()
        sync = ws.receive_json()
        assert abs(sync["offset_ms"] - offset) < 50, sync
        t_onset_phone = now_ms() - offset
        ws.send_json({"type": "onset", "t_phone_ms": t_onset_phone, "peak": 0.8, "energy": 0.1})
        ws.send_json({"type": "call_ack", "call_id": "01JCALL0001", "t_phone_ms": now_ms() - offset})
        ws.send_json({"type": "health", "battery": 0.8, "thermal": "nominal", "evil": "x"})
        ws.send_json({"type": "ping", "t0": 1})  # round trip so the server has processed everything above
        ws.receive_json()
    onsets = client.portal.call(r.xrange, "ev:audio")
    ev = json.loads(onsets[0][1][b"json"])
    t0_ms = float(client.portal.call(r.hget, f"game:{g['game_id']}", "t0_ms"))
    assert ev["type"] == "audio_onset" and ev["payload"]["cam_id"] == j["cam_id"]
    assert abs(ev["t_game_s"] - ((t_onset_phone + offset) - t0_ms) / 1000) < 0.05
    cam = client.portal.call(r.hgetall, f"cam:{j['cam_id']}")
    assert cam[b"phone_battery"] == b"0.8" and b"phone_evil" not in cam and b"sync_err_ms" in cam
    import time

    for _ in range(50):  # the ack lookup runs as a background task
        p = tmp_path / "logs" / "call_ack.jsonl"
        if p.exists():
            break
        time.sleep(0.02)
    ack = json.loads((tmp_path / "logs" / "call_ack.jsonl").read_text().splitlines()[0])
    assert ack["call_id"] == "01JCALL0001" and 400 < ack["ack_latency_ms"] < 2000


# ---------------------------------------------------------------- calibration
def corners():
    return [
        {"name": "A_left", "px": [212.5, 470.0]},
        {"name": "A_right", "px": [190.0, 640.0]},
        {"name": "B_right", "px": [1100.0, 650.0]},
        {"name": "B_left", "px": [1050.0, 460.0]},
    ]


def test_calibrate_falls_back_to_untrusted_stub_then_saves(env):
    client, r, up = env
    g, j = new_game(client, role="cam,judge")
    h = {"Authorization": f"Bearer {j['cam_token']}"}
    req = {
        "schema": "trophy.calibration_request.v1",
        "game_id": g["game_id"],
        "cam_id": j["cam_id"],
        "sport": "table_tennis",
        "seq": 1,
        "image_size": {"w": 1280, "h": 720},
        "points": corners(),
    }
    cal = client.post("/api/calibrate", json=req, headers=h).json()
    assert cal["solver"] == "gateway-stub" and cal["trusted"] is False and cal["reproj_err_px"] < 1e-6
    hm = cal["H_img_to_field"]
    x, y = 212.5, 470.0  # A_left maps to (-1.37, +0.7625)
    d = hm[6] * x + hm[7] * y + hm[8]
    assert (
        abs((hm[0] * x + hm[1] * y + hm[2]) / d + 1.37) < 1e-6
        and abs((hm[3] * x + hm[4] * y + hm[5]) / d - 0.7625) < 1e-6
    )
    up.adapter_up = True
    assert client.post("/api/calibrate", json=req, headers=h).json()["solver"] == "adapter"
    assert client.post(f"/api/cams/{j['cam_id']}/calibration", json=cal, headers=h).json() == {
        "ok": True,
        "trusted": False,
    }
    assert json.loads(client.portal.call(r.get, f"calib:{j['cam_id']}"))["solver"] == "gateway-stub"
    assert any(c["cmd"] == "set_calibration" for c in ctl_cmds(client, r))
    other = client.post("/api/calibrate", json={**req, "game_id": "g_zzzzzzzz"}, headers=h)
    assert other.status_code == 403


# ---------------------------------------------------------------- voice + ask
def test_voice_token_never_leaks_the_key(env):
    client, _, _ = env
    _, j = new_game(client)
    resp = client.get("/api/voice/token", headers={"Authorization": f"Bearer {j['cam_token']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "ct_short_lived" and body["cartesia_version"] == "2026-08-14"
    assert "sk_test" not in resp.text
    assert client.get("/api/voice/token").status_code == 401


def test_ask_proxies_and_logs(env):
    client, r, _ = env
    _, j = new_game(client)
    out = client.post(
        "/api/ask",
        json={"question": "can the serve clip the net?"},
        headers={"Authorization": f"Bearer {j['cam_token']}"},
    )
    assert out.status_code == 200 and out.json()["answer"].startswith("[test]")
    logged = [c for c in ctl_cmds(client, r) if c["cmd"] == "ask_logged"][-1]
    assert logged["args"]["moss_ms"] == 12.0 and logged["args"]["citations"][0]["rule_id"] == "T-1"
    a = logged["args"]
    assert (a["speech"], a["kind"], a["check"], a["p"], a["calibrated"]) == ("x", "check", "in_out", 0.82, False)


def test_healthz(env):
    client, _, _ = env
    body = client.get("/api/healthz").json()
    assert body["redis"] is True and body["recorder"] is False


# ---------------------------------------------------------------- challenge clips
def sync_clock(client, token, offset=0.0):
    with client.websocket_connect(f"/api/ws/ctl?token={token}") as ws:
        prev = None
        for _ in range(4):
            t0 = now_ms() - offset
            ws.send_json({"type": "ping", "t0": t0, **({"prev": prev} if prev else {})})
            pong = ws.receive_json()
            if prev:
                ws.receive_json()
            prev = {"t0": t0, "t1": pong["t1"], "t2": pong["t2"], "t3": now_ms() - offset}


def test_clip_upload_list_and_ranged_get(env, tmp_path):
    client, _, _ = env
    g, j = new_game(client, role="cam,judge")
    h = {"Authorization": f"Bearer {j['cam_token']}", "Content-Type": "video/mp4"}
    q = "call_id=01JCALL0002&seg=7&t_start_phone_ms={}&t_end_phone_ms={}"
    body = b"\x00\x00\x00\x18ftypmp42" + b"x" * 5000
    t = now_ms() - 3000.0
    # no clock fit yet: refused, because the clip couldn't be placed on the game clock
    assert client.post("/api/clips?" + q.format(t, t + 6000), content=body, headers=h).status_code == 409
    sync_clock(client, j["cam_token"], offset=2000.0)
    r = client.post("/api/clips?" + q.format(t, t + 6000), content=body, headers=h)
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["name"] == f"{j['cam_id']}_00007.mp4" and meta["bytes"] == len(body)
    assert meta["t_game_end_s"] - meta["t_game_start_s"] == pytest.approx(6.0, abs=0.01)
    t0_ms = client.get(f"/api/games/{g['game_id']}/public").json()["t0_ms"]
    assert meta["t_game_start_s"] == pytest.approx((t + 2000.0 - t0_ms) / 1000, abs=0.05)  # phone clock is 2 s behind
    assert (
        client.post(
            "/api/clips?" + q.format(t, t + 6000), content=body, headers={**h, "Content-Type": "text/plain"}
        ).status_code
        == 415
    )

    listed = client.get(f"/api/clips/{g['game_id']}/01JCALL0002", headers={"Authorization": h["Authorization"]}).json()
    assert [c["name"] for c in listed["clips"]] == [meta["name"]]
    url = listed["clips"][0]["url"]
    assert client.get(url).status_code == 401
    full = client.get(f"{url}?token={j['cam_token']}")
    assert full.status_code == 200 and full.content == body and full.headers["content-type"] == "video/mp4"
    part = client.get(f"{url}?token={j['cam_token']}", headers={"Range": "bytes=0-15"})
    assert part.status_code == 206 and part.content == body[:16]
    assert (
        client.get(f"/api/clips/{g['game_id']}/01JCALL0002/..%2F..%2Fsecret.mp4?token={j['cam_token']}").status_code
        == 404
    )

    _, other = new_game(client)
    assert client.get(f"{url}?token={other['cam_token']}").status_code == 403
    _, display = new_game(client, role="display")
    dh = {"Authorization": f"Bearer {display['cam_token']}", "Content-Type": "video/mp4"}
    assert client.post("/api/clips?" + q.format(t, t + 6000), content=body, headers=dh).status_code == 403


def test_watch_ctl_commands_are_validated_and_review_is_judge_only(env):
    client, _, _ = env
    _, joined = new_game(client, role="display")
    auth = {"Authorization": f"Bearer {joined['cam_token']}"}
    for cmd, args in [("bookmark", {"t_game_s": 1.0, "label": "A point"}), ("clip_that", {})]:
        assert client.post("/api/ctl", json={"cmd": cmd, "args": args}, headers=auth).status_code == 202
    review = {"cmd": "review_call", "args": {"call_id": "call1", "result": "confirm"}}
    assert client.post("/api/ctl", json=review, headers=auth).status_code == 403
    _, judge = new_game(client, role="judge")
    auth = {"Authorization": f"Bearer {judge['cam_token']}"}
    assert client.post("/api/ctl", json=review, headers=auth).status_code == 202
    review["args"]["result"] = "correct"
    assert client.post("/api/ctl", json=review, headers=auth).status_code == 422
    review["args"]["replacement"] = {"outcome": "point_B", "team_id": "B"}
    assert client.post("/api/ctl", json=review, headers=auth).status_code == 202
    assert (
        client.post("/api/ctl", json={"cmd": "bookmark", "args": {"path": "hidden"}}, headers=auth).status_code == 422
    )
