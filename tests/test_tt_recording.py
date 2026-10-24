"""Known geometry, timestamp sync, conservative boundaries and durable review."""

import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/flight"))
sys.path.insert(0, str(ROOT / "tools"))
from evaluate_tt import evaluate  # noqa: E402
from flight.recording import estimate_sync, measure_toss, rally_candidates  # noqa: E402
from tt_demo import Demo, handler, synthetic_session  # noqa: E402


class RecordingTests(unittest.TestCase):
    def test_sync_sign_and_multiple_windows(self):
        rng = np.random.default_rng(23)
        a = rng.normal(0, 0.1, 8000 * 100)
        b = np.r_[np.zeros(800), a]
        result = estimate_sync(a, b)
        self.assertAlmostEqual(result["offset_s"], 0.1, places=3)
        self.assertFalse(result["verified"])
        self.assertGreaterEqual(result["uncertainty_s"], 1 / 60)

    def test_no_audio_evidence_does_not_verify_alignment(self):
        result = estimate_sync(np.zeros(80000), np.zeros(80000))
        self.assertFalse(result["verified"])
        self.assertIsNone(result["uncertainty_s"])

    def test_toss_boundaries_and_fall_exclusion(self):
        for height in [0.12, 0.16, 0.24]:
            for angle in [0, 30, 40]:
                x = height * np.tan(np.radians(angle))
                samples = [
                    dict(t_s=0, pos_m=[0, 0, 1]),
                    dict(t_s=1, pos_m=[x, 0, 1 + height]),
                    dict(t_s=2, pos_m=[10, 0, 0.5]),
                ]
                result = measure_toss(samples, 0, 1, 2, calibrated=True)
                self.assertAlmostEqual(result["height_m"], height)
                self.assertAlmostEqual(result["rise_angle_deg"], angle)
                self.assertFalse(result["fall_segment_used_for_angle"])

    def test_unknown_metric_and_release_stay_unavailable(self):
        self.assertEqual(measure_toss([], 0, 1)["status"], "unavailable")
        self.assertEqual(measure_toss([], 0, 1, calibrated=True)["status"], "unavailable")

    def test_disappearance_never_assigns_point(self):
        rows = [dict(t_game_s=i / 60, x=100, y=100) for i in range(120)]
        for p in rally_candidates(rows):
            self.assertIsNone(p["winner"])
            self.assertEqual(p["status"], "unresolved")

    def test_localization_is_not_coverage(self):
        labels = [dict(seq=0, status="visible", x=0, y=0), dict(seq=1, status="visible", x=0, y=0)]
        result = evaluate(labels, {0: dict(x=0, y=0), 1: dict(x=200, y=200)}, 5)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["localized_elsewhere"], 1)

    def test_synthetic_known_faults_score_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Demo(Path(tmp))
            first = d.advance("synthetic", 24)
            self.assertEqual(first["state"]["points"], {"A": 0, "B": 2})
            second = d.advance("synthetic", 24)
            self.assertEqual(second["newly_calls"], [])
            self.assertEqual(second["state"]["points"], {"A": 0, "B": 2})
            self.assertEqual(d.states["recorded"].snapshot()["points"], {"A": 0, "B": 0})

    def test_durable_manual_correction_and_separate_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            d = Demo(p)
            d.apply(dict(action="resolve", rally_id="r1", winner="A", event_id="request-a"))
            d.apply(dict(action="resolve", rally_id="r1", winner="A", event_id="request-a"))
            self.assertEqual(d.states["recorded"].snapshot()["points"], {"A": 1, "B": 0})
            d.apply(dict(action="resolve", rally_id="r1", winner="B", reason="Review correction"))
            after = Demo(p).states["recorded"].snapshot()
            self.assertEqual(after["points"], {"A": 0, "B": 1})
            self.assertEqual(len(after["history"]), 2)

    def test_fallback_ids_allow_return_to_previous_winner_and_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            d = Demo(p)
            for winner in ["A", "B", "A"]:
                d.apply(dict(action="resolve", rally_id="r1", winner=winner, reason="Review"))
            rows = [json.loads(line) for line in d.audit.read_text().splitlines()]
            self.assertEqual(len({row["event_id"] for row in rows}), 3)
            restored = Demo(p).states["recorded"].snapshot()
            self.assertEqual(restored["points"], {"A": 1, "B": 0})
            self.assertEqual(len(restored["history"]), 3)

    def test_duplicate_request_does_not_append_audit_or_change_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Demo(Path(tmp))
            row = dict(action="resolve", rally_id="r1", winner="A", event_id="same-id")
            d.apply(row)
            d.apply(row)
            self.assertEqual(len(d.audit.read_text().splitlines()), 1)
            with self.assertRaises(ValueError):
                d.apply({**row, "winner": "B"})
            self.assertEqual(d.reviews["r1"]["winner"], "A")
            self.assertEqual(d.states["recorded"].snapshot()["points"], {"A": 1, "B": 0})

    def test_challenge_retains_existing_point_and_marks_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            d = Demo(p)
            d.apply(dict(action="resolve", rally_id="r1", winner="A", event_id="resolved"))
            d.apply(dict(action="challenge", rally_id="r1", event_id="challenge"))
            self.assertEqual(d.states["recorded"].snapshot()["points"], {"A": 1, "B": 0})
            self.assertEqual(len(d.states["recorded"].snapshot()["history"]), 1)
            self.assertEqual(d.reviews["r1"]["review_status"], "requested")
            restored = Demo(p)
            self.assertEqual(restored.reviews["r1"]["review_status"], "requested")
            self.assertEqual(restored.states["recorded"].snapshot()["points"], {"A": 1, "B": 0})

    def test_persistence_failure_rolls_back_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Demo(Path(tmp))
            d.audit.mkdir()  # An unwritable audit target is a deterministic failure.
            with self.assertRaises(OSError):
                d.apply(dict(action="resolve", rally_id="r1", winner="A", event_id="write-failed"))
            self.assertEqual(d.states["recorded"].snapshot()["points"], {"A": 0, "B": 0})
            self.assertEqual(d.reviews, {})
            self.assertEqual(d.requests, {})

    def test_invalid_advance_does_not_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Demo(Path(tmp))
            for t in [True, -1, float("nan"), float("inf"), None]:
                with self.assertRaises(ValueError):
                    d.advance("synthetic", t)
            with self.assertRaises(ValueError):
                d.advance("missing", 24)
            self.assertEqual(d.states["synthetic"].snapshot()["points"], {"A": 0, "B": 0})

    def test_synthetic_boundary_passes_and_uncertainty_never_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Demo(Path(tmp))
            first = d.advance("synthetic", 3.5)
            self.assertEqual(first["state"]["points"], {"A": 0, "B": 1})
            for t in [7.5, 8, 3.5]:
                result = d.advance("synthetic", t)
                self.assertEqual(result["state"]["points"], {"A": 0, "B": 1})
            result = d.advance("synthetic", synthetic_session()["duration_s"])
            self.assertEqual(result["state"]["points"], {"A": 0, "B": 2})
            self.assertEqual(len(result["state"]["history"]), 2)
            self.assertTrue(
                all(c["evidence_refs"][0].startswith("synthetic_truth:") for c in result["state"]["history"])
            )

    def test_synthetic_uncertainty_not_fault(self):
        p = synthetic_session()["points"]
        self.assertEqual(p[1]["assessment"]["height"], "pass")
        self.assertEqual(p[3]["assessment"]["angle"], "pass")
        self.assertEqual(p[4]["assessment"]["status"], "review_needed")
        self.assertEqual(p[5]["assessment"]["status"], "unavailable")
        self.assertEqual(p[6]["assessment"]["angle"], "uncertain")
        self.assertEqual(p[6]["assessment"]["status"], "review_needed")


class LocalHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        (self.directory / "side.mp4").write_bytes(b"0123456789")
        self.demo = Demo(self.directory)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.demo))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_media_ranges_and_unsatisfiable_range(self):
        status, headers, data = self.request("GET", "/media/side.mp4", headers={"Range": "bytes=2-5"})
        self.assertEqual((status, data), (206, b"2345"))
        self.assertEqual(headers["Content-Range"], "bytes 2-5/10")
        for value in ["bytes=100-", "bytes=4-1", "bytes=", "bytes=0-1,3-4", "bytes=-0"]:
            status, headers, _ = self.request("GET", "/media/side.mp4", headers={"Range": value})
            self.assertEqual(status, 416)
            self.assertEqual(headers["Content-Range"], "bytes */10")
        status, _, data = self.request("GET", "/media/side.mp4", headers={"Range": "bytes=-3"})
        self.assertEqual((status, data), (206, b"789"))

    def test_non_object_and_bad_json_are_rejected(self):
        for body in ["[]", "null", "true", "1", "invalid-json"]:
            status, _, data = self.request("POST", "/api/resolve", body=body)
            self.assertEqual(status, 400, data)
        self.assertEqual(self.demo.states["recorded"].snapshot()["points"], {"A": 0, "B": 0})

    def test_origin_and_dns_rebinding_host_are_rejected(self):
        body = json.dumps(dict(dataset="synthetic", rally_id="synthetic-1", winner="A"))
        status, _, _ = self.request("POST", "/api/resolve", body, {"Origin": "https://example.com"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/api/state", headers={"Host": "example.com"})
        self.assertEqual(status, 403)

    def test_http_synthetic_retries_preserve_idempotence(self):
        row = dict(dataset="synthetic", rally_id="synthetic-1", winner="A", event_id="client-request")
        for _ in range(2):
            status, _, data = self.request("POST", "/api/resolve", json.dumps(row))
            self.assertEqual(status, 200, data)
            self.assertEqual(json.loads(data)["points"], {"A": 1, "B": 0})
        self.assertEqual(len(self.demo.audit.read_text().splitlines()), 1)
        row["winner"] = "B"
        status, _, _ = self.request("POST", "/api/resolve", json.dumps(row))
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
