import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from trophy.events import make_event
from trophy.tracks import BallTrackWriter, Downsampler, read_ball_track
from trophy.world import ObservationWriter, RecordingClient, SpacetimeClient, TrackSampleWriter

GAME = "g_abcdefgh"


def ev(type_="heartbeat", t=1.0, payload=None):
    return make_event(
        game_id=GAME,
        t_game_s=t,
        sport="table_tennis",
        type=type_,
        source="flight",
        cams=["c_abcdef"],
        conf=1.0,
        payload=payload or {"service": "flight"},
    )


def test_observations_are_batched():
    rc = RecordingClient()
    with ObservationWriter(rc, flush_interval_s=0.2) as w:
        for i in range(5):
            w.post(ev(t=i))
        assert rc.calls == []  # still inside the batching window
        assert w.flush()
    assert len(rc.calls) == 1
    reducer, (batch_json,) = rc.calls[0]
    assert reducer == "post_observations"
    rows = json.loads(batch_json)
    assert [r["t_game_s"] for r in rows] == [0, 1, 2, 3, 4] and rows[0]["schema"] == "trophy.event.v1"


def test_rally_ending_flushes_immediately():
    rc = RecordingClient()
    w = ObservationWriter(rc, flush_interval_s=10)
    w.post(ev("ball_dead", payload={"reason": "floor", "last_side": "A"}))
    deadline = time.monotonic() + 1
    while not rc.calls and time.monotonic() < deadline:
        time.sleep(0.005)
    w.close()
    assert rc.rows("post_observations")[0]["type"] == "ball_dead"


def test_writer_survives_spacetime_down():
    errors = []
    w = ObservationWriter(SpacetimeClient(uri="http://127.0.0.1:9", timeout_s=0.2), on_error=errors.append)
    w.post(ev())
    w.flush()
    w.close()
    assert w.dropped == 1 and errors


def test_spacetime_client_http_shape():
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    SpacetimeClient(uri=f"http://127.0.0.1:{srv.server_port}", module="trophy", token="tok").call(
        "post_observations", "[]"
    )
    srv.server_close()
    assert seen == {
        "path": "/v1/database/trophy/call/post_observations",
        "auth": "Bearer tok",
        "body": ["[]"],
    }


def test_track_samples_downsampled_to_10hz():
    rc = RecordingClient()
    with TrackSampleWriter(rc) as w:
        kept = sum(w.post(GAME, "c_abcdef", i / 30, pos_m=(0, 0, 0.1), conf=0.9) for i in range(90))
        w.flush()
    assert kept == 30
    rows = rc.rows("post_track_samples")
    assert len(rows) == 30 and rows[0]["object"] == "ball" and rows[0]["px"] is None


def test_downsampler_resets_on_time_jump():
    d = Downsampler(10)
    assert d.accept(100.0) and not d.accept(100.05) and d.accept(100.1)
    assert d.accept(0.0)  # clip restarted


def test_ball_track_roundtrip(r):
    w = BallTrackWriter(r, "c_abcdef")
    for i in range(30):
        w.write({"t_game_s": i / 10, "seq": i, "px": [i, i] if i % 2 else None, "conf": 0.5})
    got = read_ball_track(r, "c_abcdef", 1.0, 1.5)
    assert [s.seq for s in got] == [10, 11, 12, 13, 14, 15]
    assert got[0].px is None and got[1].px == [11, 11]
