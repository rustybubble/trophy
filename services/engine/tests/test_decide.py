"""decide(): three voters through recorded HTTP shapes (no live calls), timeouts, the blend, and key requirements."""

from __future__ import annotations

import json
import threading
import time

import httpx
import httpx2
import pytest

from trophy_engine.decide import (
    BackgroundDecider,
    BitdeerVoter,
    ClaudeVoter,
    GeminiVoter,
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
GEMINI_BODY = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "choice": "top_edge",
                                "probs": {"top_edge": 0.8, "side_face": 0.2},
                                "rationale": "trajectory continued",
                            }
                        )
                    }
                ],
            }
        }
    ]
}
BITDEER_BODY = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "Qwen/Qwen3.5-397B-A17B",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {"choice": "top_edge", "probs": {"top_edge": 0.55, "side_face": 0.45}, "rationale": "hard to tell"}
                ),
            },
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
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
    with pytest.raises(VoterConfigError):
        GeminiVoter.from_env({"GEMINI_API_KEY": "x"})
    with pytest.raises(VoterConfigError):
        BitdeerVoter.from_env({})


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


def test_gemini_and_bitdeer_votes() -> None:
    g = GeminiVoter(api_key="k", model="gemini-test", http_client=httpx.Client(transport=transport(GEMINI_BODY)))
    out = g.vote(REQ, 2.0)
    assert out["choice"] == "top_edge" and out["probs"]["top_edge"] == 0.8
    seen: list[httpx.Request] = []
    b = BitdeerVoter(
        api_key="k",
        model="Qwen/Qwen3.5-397B-A17B",
        http_client=httpx.Client(transport=transport(BITDEER_BODY, capture=seen)),
    )
    out = b.vote(REQ, 2.0)
    assert out["choice"] == "top_edge" and abs(out["probs"]["side_face"] - 0.45) < 1e-6
    assert seen[0].url.host == "api-inference.bitdeer.ai" and seen[0].url.path.endswith("/chat/completions")


def test_errors_are_recorded_not_raised() -> None:
    g = GeminiVoter(api_key="k", model="m", http_client=httpx.Client(transport=transport({"error": "x"}, status=429)))
    assert g.vote(REQ, 1.0)["error"] == "http_429"
    c = ClaudeVoter(
        api_key="k",
        http_client=claude_client({"type": "error", "error": {"type": "overloaded_error", "message": "x"}}, status=529),
    )
    assert c.vote(REQ, 1.0)["error"] == "http_529"
    bad = dict(CLAUDE_BODY)
    bad["content"] = [{"type": "text", "text": "not json"}]
    assert ClaudeVoter(api_key="k", http_client=claude_client(bad)).vote(REQ, 1.0)["error"] == "parse"


def test_parallel_fan_out_with_a_timed_out_voter() -> None:
    slow = GeminiVoter(api_key="k", model="m", http_client=httpx.Client(transport=transport(GEMINI_BODY, delay=1.5)))
    fast = BitdeerVoter(api_key="k", model="m", http_client=httpx.Client(transport=transport(BITDEER_BODY)))
    t0 = time.perf_counter()
    res = decide({**REQ, "timeout_s": 0.5}, [slow, fast])
    assert time.perf_counter() - t0 < 1.4
    by = {v["backend"]: v for v in res["votes"]}
    assert by["gemini"]["error"] == "timeout" and by["bitdeer"]["error"] is None
    assert res["weights"] == {"geometry": 0.5, "bitdeer": 0.5}
    assert res["calibrated"] is False and res["p_source"] == "decide:ensemble"
    assert abs(res["p_final"]["top_edge"] - (0.5 * 0.6 + 0.5 * 0.55)) < 1e-6
    assert res["suggested"] == "top_edge"


def test_blend_without_voters_is_geometry() -> None:
    b = blend(["a", "b"], {"a": 0.7, "b": 0.3}, [{"backend": "claude", "error": "timeout", "probs": {}}])
    assert b["p_final"] == {"a": 0.7, "b": 0.3} and b["weights"] == {"geometry": 0.5}


def test_background_decider_posts_one_vote_per_voter_and_never_blocks() -> None:
    posted = []
    results = []
    done = threading.Event()
    voters = [
        ClaudeVoter(api_key="k", http_client=claude_client(CLAUDE_BODY, delay=0.2)),
        GeminiVoter(api_key="k", model="m", http_client=httpx.Client(transport=transport(GEMINI_BODY))),
    ]
    dec = BackgroundDecider(
        voters, posted.append, lambda req, res: (results.append(res), done.set()), now_ms=lambda: 1.0
    )
    t0 = time.perf_counter()
    dec.submit(REQ)
    assert time.perf_counter() - t0 < 0.05  # submit returns immediately
    assert done.wait(5)
    assert {v["backend"] for v in posted} == {"claude", "gemini"}
    assert all(v["call_id"] == REQ["call_id"] and v["created_at_ms"] == 1.0 for v in posted)
    from trophy.contracts import AiVote

    for v in posted:
        AiVote.model_validate(v)
