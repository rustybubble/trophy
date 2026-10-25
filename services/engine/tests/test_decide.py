"""decide(): the Claude voter (D-41) through recorded HTTP shapes (no live calls), timeouts, the blend, and the key
requirement."""

from __future__ import annotations

import json
import threading
import time

import httpx
import httpx2
import pytest

from trophy_engine.decide import (
    BackgroundDecider,
    ClaudeVoter,
    VoterConfigError,
    blend,
    decide,
)

REQ = {
    "schema": "trophy.decide.v1",
    "req_id": "01JREQ000000000000000000AB",
    "game_id": "g_synth001",
    "call_id": "01JCALL00000000000000000AB",
    "question": "Top edge or side face?",
    "options": ["top_edge", "side_face"],
    "context": "bounce 1 cm inside end_B, σ 2 cm",
    "images": [],
    "observations": [{"type": "bounce"}],
    "p_geometry": {"top_edge": 0.6, "side_face": 0.4},
    "timeout_s": 2,
}

CLAUDE_BODY = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5-5",
    "content": [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "choice": "side_face",
                    "probs": {"top_edge": 0.3, "side_face": 0.7},
                    "rationale": "ball deflected sideways",
                }
            ),
        }
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 10},
}


def transport(body, status=200, delay=0.0, capture: list | None = None, lib=httpx):
    def handler(request):
        if capture is not None:
            capture.append(request)
        if delay:
            time.sleep(delay)
        return lib.Response(status, json=body)

    return lib.MockTransport(handler)


def claude_client(body, status=200, delay=0.0, capture: list | None = None):
    return httpx2.Client(transport=transport(body, status, delay, capture, lib=httpx2))


def test_voters_require_keys() -> None:
    with pytest.raises(VoterConfigError):
        ClaudeVoter.from_env({})


def test_claude_vote_uses_structured_output_and_maps_options() -> None:
    seen: list[httpx.Request] = []
    v = ClaudeVoter(api_key="k", http_client=claude_client(CLAUDE_BODY, capture=seen))
    out = v.vote(REQ, 2.0)
    assert (
        out["backend"] == "claude"
        and out["choice"] == "side_face"
        and out["probs"] == {"top_edge": 0.3, "side_face": 0.7}
    )
    body = json.loads(seen[0].content)
    assert (
        body["output_config"]["format"]["type"] == "json_schema"
        and "temperature" not in body
        and "tool_choice" not in body
    )
    assert body["model"] == "claude-opus-5-5"


def test_errors_are_recorded_not_raised() -> None:
    c = ClaudeVoter(api_key="k", http_client=claude_client({"type": "error", "error": {"type": "rate_limit_error",
                    "message": "x"}}, status=429))  # fmt: skip
    assert c.vote(REQ, 1.0)["error"] == "http_429"
    c = ClaudeVoter(
        api_key="k",
        http_client=claude_client({"type": "error", "error": {"type": "overloaded_error", "message": "x"}}, status=529),
    )
    assert c.vote(REQ, 1.0)["error"] == "http_529"
    bad = dict(CLAUDE_BODY)
    bad["content"] = [{"type": "text", "text": "not json"}]
    assert ClaudeVoter(api_key="k", http_client=claude_client(bad)).vote(REQ, 1.0)["error"] == "parse"


def test_a_timed_out_voter_leaves_geometry_and_never_waits() -> None:
    slow = ClaudeVoter(api_key="k", http_client=claude_client(CLAUDE_BODY, delay=1.5))
    t0 = time.perf_counter()
    res = decide({**REQ, "timeout_s": 0.5}, [slow])
    assert time.perf_counter() - t0 < 1.4
    assert res["votes"][0]["backend"] == "claude" and res["votes"][0]["error"] == "timeout"
    assert res["weights"] == {"geometry": 0.5} and res["p_final"] == REQ["p_geometry"]


def test_claudes_vote_is_blended_with_geometry() -> None:
    res = decide(REQ, [ClaudeVoter(api_key="k", http_client=claude_client(CLAUDE_BODY))])
    assert res["weights"] == {"geometry": 0.5, "claude": 0.5}
    assert res["calibrated"] is False and res["p_source"] == "decide:ensemble"
    assert abs(res["p_final"]["side_face"] - (0.5 * 0.4 + 0.5 * 0.7)) < 1e-6
    assert res["suggested"] == "side_face"


def test_blend_without_voters_is_geometry() -> None:
    b = blend(["a", "b"], {"a": 0.7, "b": 0.3}, [{"backend": "claude", "error": "timeout", "probs": {}}])
    assert b["p_final"] == {"a": 0.7, "b": 0.3} and b["weights"] == {"geometry": 0.5}


def test_background_decider_posts_one_vote_per_voter_and_never_blocks() -> None:
    posted = []
    results = []
    done = threading.Event()
    voters = [ClaudeVoter(api_key="k", http_client=claude_client(CLAUDE_BODY, delay=0.2))]
    dec = BackgroundDecider(
        voters, posted.append, lambda req, res: (results.append(res), done.set()), now_ms=lambda: 1.0
    )
    t0 = time.perf_counter()
    dec.submit(REQ)
    assert time.perf_counter() - t0 < 0.05  # submit returns immediately
    assert done.wait(5)
    assert [v["backend"] for v in posted] == ["claude"]
    assert all(v["call_id"] == REQ["call_id"] and v["created_at_ms"] == 1.0 for v in posted)
    from trophy.contracts import AiVote

    for v in posted:
        AiVote.model_validate(v)
