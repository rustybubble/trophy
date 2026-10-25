"""Ask the ref over the stored 3D track: router rules, the check run, Claude phrasing through a recorded HTTP shape
(no live call), the pending-check queue, and the no-key / upstream-failure paths."""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from trophy_engine.ask import AskConfigError, AskUpstreamError, Phraser, TrackStore, make_app, route
from trophy_engine.checks.library import load_field, load_library

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "evals" / "fixtures" / "synthetic" / "table_tennis_3d"
CHECKS = ROOT / "sports" / "table_tennis" / "checks"

CLAUDE_BODY = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-haiku-5-5",
    "content": [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "answer": "In: 72.1 cm inside the right sideline, sigma 3.8 cm (BETA, uncalibrated).",
                    "speech": "In, by 72 centimetres, with a sigma of about 4 centimetres. Beta reading.",
                }
            ),
        }
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 10},
}


def claude_client(body=CLAUDE_BODY, status=200, capture: list | None = None) -> httpx2.Client:
    def handler(request):
        if capture is not None:
            capture.append(request)
        return httpx2.Response(status, json=body)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def filled_store() -> TrackStore:
    """The engine's side: load the golden library, set the field, push every row, set segments from `phases`."""
    lib = load_library(CHECKS)
    fld = load_field(FIXTURE / "field.json")
    store = TrackStore(lib)
    store.set_field(fld)
    for line in (FIXTURE / "game_01.track3d.jsonl").read_text("utf8").splitlines():
        if line.strip():
            store.push(json.loads(line))
    ph = lib.run("phases", store.track(), fld, None)
    store.set_segments(ph["verdict"]["segments"])
    return store


@pytest.fixture(scope="module")
def store() -> TrackStore:
    return filled_store()


@pytest.fixture(scope="module")
def truth(store: TrackStore) -> dict:
    """What the checks themselves say about the last rally (the fixture is regenerated, so no hard-coded times)."""
    segs = store.segments
    last = segs[-1]
    tr = store.track()
    t0 = float(last["t_start_s"])
    t1 = float(last["t_end_s"]) if last.get("t_end_s") is not None else tr.t1
    bn = store.library.run("bounces", tr, store.field, None, t0=t0, t1=t1)["verdict"]
    sv = store.library.run("serve_toss", tr, store.field, None, t_start=t0)
    return {
        "segments": segs,
        "last": last,
        "prev": segs[-2],
        "t0": t0,
        "t1": t1,
        "bounces": [b for b in bn if b["surface"] in ("table", "side_face")],
        "serve": sv,
    }


def client_for(store: TrackStore, tmp: Path | None = None, body=CLAUDE_BODY, status=200, capture=None) -> TestClient:
    ph = Phraser(api_key="k", http_client=claude_client(body, status, capture))
    return TestClient(make_app(store, ph, session_dir=tmp))


# ---------------------------------------------------------------- the hot path


def test_was_that_out_runs_in_out_and_phrases(store: TrackStore) -> None:
    seen: list = []
    c = client_for(store, capture=seen)
    r = c.post("/ask", json={"question": "Was that out?"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["found"] is True and out["check"] == "in_out"
    assert out["verdict"] in ("in", "out", "edge")
    assert 0.0 <= out["p"] <= 1.0
    assert out["answer"] and out["speech"] and out["citations"] == []
    assert out["calibrated"] is False  # the golden library is not specialised to a calibration
    assert out["scope"].startswith(f"rally {store.last_rally()['rally_no']}, the last bounce at ")
    for k in ("latency_ms", "check_ms", "claude_ms"):
        assert isinstance(out[k], int | float) and out[k] >= 0
    assert out["check_ms"] < 200  # the budget is 50 ms for fusion + check; this includes routing (bounces) too
    # the request Claude saw: the fast model, structured output, no temperature, the system prompt, only the results
    body = json.loads(seen[0].content)
    assert body["model"] == "claude-haiku-5-5" and body["max_tokens"] == 300
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in body and "tool_choice" not in body
    assert "Never compute" in body["system"]
    user = json.loads(body["messages"][0]["content"])
    assert user["question"] == "Was that out?" and user["check_results"][0]["check"] == "in_out"
    assert "ms" not in user["check_results"][0]


def test_was_the_serve_legal_runs_serve_toss(store: TrackStore, truth: dict) -> None:
    out = client_for(store).post("/ask", json={"question": "was the serve legal?"}).json()
    assert out["found"] and out["check"] == "serve_toss"
    v = out["verdict"]
    assert isinstance(v, dict) and {"legal", "height_m", "angle_deg"} <= set(v)
    assert out["t_s"] == truth["serve"]["t_s"] and out["verdict"] == truth["serve"]["verdict"]
    assert out["scope"] == f"rally {truth['last']['rally_no']}, serve at {truth['t0']:.1f} s"


def test_did_it_clip_the_net_runs_net_touch(store: TrackStore) -> None:
    out = client_for(store).post("/ask", json={"question": "Did it clip the net?"}).json()
    assert out["found"] and out["check"] == "net_touch"
    assert isinstance(out["verdict"], list)
    assert "overs" in out["evidence"]


def test_unknown_question_queues_a_pending_check(store: TrackStore, tmp_path: Path) -> None:
    sess = tmp_path / "session"
    out = client_for(store, tmp=sess).post("/ask", json={"question": "What's the weather like?"}).json()
    assert out["found"] is False
    assert out["answer"] == out["speech"] == "I don't have a check for that yet; give me a moment."
    assert out["citations"] == [] and "latency_ms" in out
    pc = out["pending_check"]
    assert pc["slug"] == "what_s_the_weather_like" and pc["question"] == "What's the weather like?"
    assert isinstance(pc["created_at_ms"], int)
    lines = (sess / "pending_checks.jsonl").read_text("utf8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["slug"] == pc["slug"] and row["sport"] == "table_tennis"


def test_no_key_means_no_phraser_and_503(store: TrackStore) -> None:
    with pytest.raises(AskConfigError):
        Phraser.from_env({})
    assert Phraser.from_env({"ANTHROPIC_API_KEY": "k"}).model == "claude-haiku-5-5"
    assert (
        Phraser.from_env({"ANTHROPIC_API_KEY": "k", "CLAUDE_FAST_MODEL": "claude-sonnet-5-5"}).model
        == "claude-sonnet-5-5"
    )
    c = TestClient(make_app(store, None))
    r = c.post("/ask", json={"question": "was that out?"})
    assert r.status_code == 503 and r.json()["error"] == "not_configured"
    assert c.get("/healthz").json()["phraser"] == "missing"


def test_claude_500_is_a_503_upstream_never_an_answer(store: TrackStore) -> None:
    err = {"type": "error", "error": {"type": "api_error", "message": "boom"}}
    r = client_for(store, body=err, status=500).post("/ask", json={"question": "was that out?"})
    assert r.status_code == 503
    assert r.json() == {"error": "upstream", "detail": "http_500", "check": "in_out"}
    bad = dict(CLAUDE_BODY)
    bad["content"] = [{"type": "text", "text": "not json"}]
    with pytest.raises(AskUpstreamError) as ei:
        Phraser(api_key="k", http_client=claude_client(bad)).phrase("q", [], {}, "table_tennis")
    assert ei.value.code == "parse"


def test_empty_store_reports_no_track_and_writes_nothing(tmp_path: Path) -> None:
    lib = load_library(CHECKS)
    empty = TrackStore(lib, load_field(FIXTURE / "field.json"))
    c = client_for(empty, tmp=tmp_path)
    out = c.post("/ask", json={"question": "was that out?"}).json()
    assert out == {
        "found": False,
        "answer": "",
        "speech": "",
        "reason": "no_track",
        "citations": [],
        "latency_ms": out["latency_ms"],
    }
    assert not (tmp_path / "pending_checks.jsonl").exists()
    h = c.get("/healthz").json()
    assert h["ok"] and h["samples"] == 0 and "in_out" in h["checks"] and h["phraser"] == "configured"


# ---------------------------------------------------------------- the router


def test_router_time_references(store: TrackStore, truth: dict) -> None:
    last_no, bounces = truth["last"]["rally_no"], truth["bounces"]
    assert len(bounces) == 2, "the last rally of game_01 is a served point with two table bounces"
    t_first, t_last = float(bounces[0]["t_s"]), float(bounces[-1]["t_s"])

    def t_of(question: str) -> float:
        q = route(question, store)
        assert q is not None and q.check == "in_out", question
        return q.checks[0].kwargs["t_s"]

    q = route("was that out?", store)
    assert q.intent == "in_out" and q.check == "in_out" and q.rally_no == last_no
    assert q.checks[0].kwargs["t_s"] == t_last and q.facts["bounce"] == "the last bounce"
    assert q.facts["n_table_bounces"] == 2 and q.facts["bounce_side"] == bounces[-1]["side"]
    assert t_of("was the last bounce in?") == t_last
    first = route("was the first bounce in?", store)
    assert first.checks[0].kwargs["t_s"] == t_first and first.facts["bounce"] == "bounce 1"
    assert t_of("did the second bounce land?") == t_last
    third = route("was the third bounce out?", store)
    assert third.facts["bounce"] == "no bounce 3"  # in_out then reports no_bounce; Claude says it has no measurement
    assert third.checks[0].kwargs["t_s"] == truth["t1"]
    serve_in = route("was the serve in?", store)
    assert serve_in.check == "in_out" and serve_in.facts["bounce"] == "the serve's first bounce"
    assert serve_in.checks[0].kwargs["t_s"] == t_first  # the serve's first bounce is the rally's first bounce
    assert truth["serve"]["verdict"] != "no_serve" and float(truth["serve"]["evidence"]["contact"]["t_s"]) < t_first
    assert route("did the serve hit the table?", store).check == "in_out"


def test_router_rally_references(store: TrackStore, truth: dict) -> None:
    prev_seg = truth["prev"]
    prev = route("was that out in the previous rally?", store)
    assert prev.rally_no == prev_seg["rally_no"] and prev.facts["t_start_s"] == round(prev_seg["t_start_s"], 3)
    assert prev.facts["t_end_s"] == round(prev_seg["t_end_s"], 3)
    seg3 = store.rally(3)
    r3 = route("was the serve legal in rally 3?", store)
    assert r3.check == "serve_toss" and r3.rally_no == 3 and r3.checks[0].kwargs["t_start"] == seg3["t_start_s"]
    assert r3.scope == f"rally 3, serve at {seg3['t_start_s']:.1f} s"
    assert route("was that serve ok?", store).check == "serve_toss"
    assert route("how high was the toss?", store).check == "serve_toss"
    assert route("was it a let?", store).check == "net_touch"
    assert route("did it bounce twice?", store).check == "bounces"
    assert route("how many bounces was that?", store).check == "bounces"
    stats = route("how long was that rally?", store)
    assert stats.intent == "rally_summary" and [c.name for c in stats.checks] == ["rally_summary", "contacts"]
    assert route("how fast was the hardest shot?", store).intent == "rally_summary"
    assert route("what's the score?", store).intent == "score" and route("what's the score?", store).checks == []
    who = route("who is serving?", store)
    assert who.intent == "server" and who.checks == [] and who.facts["server_side"] == store.last_rally()["server_side"]
    assert route("what's the weather like?", store) is None
    assert route("", store) is None


def test_router_without_segments_uses_the_whole_track() -> None:
    lib = load_library(CHECKS)
    fld = load_field(FIXTURE / "field.json")
    s = TrackStore(lib, fld)
    s.extend(json.loads(x) for x in (FIXTURE / "game_01.track3d.jsonl").read_text("utf8").splitlines() if x.strip())
    q = route("was that out?", store=s)
    assert q.rally_no is None and q.scope.startswith("the whole track")
    assert q.facts["t_start_s"] == 0.0 and q.facts["n_table_bounces"] > 2


def test_store_is_a_live_buffer() -> None:
    lib = load_library(CHECKS)
    s = TrackStore(lib, load_field(FIXTURE / "field.json"))
    assert len(s) == 0 and s.last_rally() is None and s.rally(1) is None
    s.push({"t_s": 1.0, "xyz_m": [0.0, 0.0, 0.3], "conf": 0.9})
    s.push({"t_s": 0.5, "xyz_m": [0.0, 0.0, 0.2], "conf": 0.9})  # late sample: the track still sorts
    assert [x.t for x in s.track()] == [0.5, 1.0] and s.track().calibrated is False  # no sigma on the rows
    s.set_segments(
        [
            {"rally_no": 2, "t_start_s": 5.0, "t_end_s": None, "server_side": "A"},
            {"rally_no": 1, "t_start_s": 0.0, "t_end_s": 4.0, "server_side": "B"},
        ]
    )
    assert s.last_rally()["rally_no"] == 2 and s.rally(1)["server_side"] == "B"
    s.add_call({"type": "point", "side": "A"})
    s.set_score({"A": 1, "B": 0})
    snap = s.snapshot()
    assert snap["recent_calls"] == [{"type": "point", "side": "A"}] and snap["score"] == {"A": 1, "B": 0}
