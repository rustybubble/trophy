"""The model voter behind the ``Voter`` interface: Claude only (D-41 cut Gemini and Bitdeer). It REQUIRES
its API key at construction; there is no offline or stub mode. Tests inject an ``httpx`` transport with recorded
response shapes so CI makes no live call.

- Claude: the ``anthropic`` SDK, ``claude-opus-5-5``, structured output through ``output_config.format``
  (no ``temperature``, no forced ``tool_choice``: both are rejected on this model).
Options are shuffled per voter to cancel position bias; the answer is mapped back to the canonical option names.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class VoterConfigError(RuntimeError):
    pass


class Voter(Protocol):
    backend: str
    model: str

    def vote(self, request: dict[str, Any], timeout_s: float) -> dict[str, Any]: ...


VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "choice": {"type": "string"},
        # structured output rejects free-form maps (additionalProperties must be false), so probabilities are a list
        "probs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"option": {"type": "string"}, "p": {"type": "number"}},
                "required": ["option", "p"],
                "additionalProperties": False,
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["choice", "probs", "rationale"],
    "additionalProperties": False,
}


def _prompt(request: dict[str, Any], options: list[str]) -> str:
    obs = json.dumps(request.get("observations") or [], separators=(",", ":"))[:4000]
    return (
        "You are the second-opinion voter for an AI referee at a pickup game. Answer only from the images, "
        "the measurements and the event facts below; the geometry already made a provisional call and your vote is "
        "advisory. Pick exactly one option and give a probability for every option (they sum to 1).\n\n"
        f"Question: {request['question']}\nOptions: {json.dumps(options)}\nFacts: {request.get('context', '')}\n"
        f"Observations (trophy.event.v1 rows): {obs}\n"
        'Reply as JSON {"choice": <option>, "probs": [{"option": <option>, "p": p}, ...], '
        '"rationale": <= 140 chars, plain words a player would understand}.'
    )


def _normalise(raw: dict[str, Any], options: list[str]) -> tuple[str | None, dict[str, float], str]:
    given = raw.get("probs") or {}
    if isinstance(given, list):  # [{"option": o, "p": p}] (the structured-output shape)
        given = {str(d.get("option")): d.get("p", 0.0) for d in given if isinstance(d, dict)}
    probs = {}
    for o in options:
        try:
            probs[o] = max(0.0, float(given.get(o, 0.0)))
        except (TypeError, ValueError):
            probs[o] = 0.0
    s = sum(probs.values())
    if s <= 0:
        choice = raw.get("choice") if raw.get("choice") in options else None
        probs = (
            {o: (1.0 if o == choice else 0.0) for o in options} if choice else {o: 1.0 / len(options) for o in options}
        )
    else:
        probs = {o: round(p / s, 4) for o, p in probs.items()}
    choice = raw.get("choice") if raw.get("choice") in options else max(probs, key=probs.get)  # type: ignore[arg-type]
    return choice, probs, str(raw.get("rationale", ""))[:140]


def _result(
    backend: str, model: str, t0: float, *, choice=None, probs=None, rationale="", error=None
) -> dict[str, Any]:
    return {
        "backend": backend,
        "model": model,
        "choice": choice,
        "probs": probs or {},
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "error": error,
        "rationale": rationale,
    }


def _shuffled(options: list[str], seed: str) -> list[str]:
    opts = list(options)
    random.Random(seed).shuffle(opts)
    return opts


def _http_error_code(e: Exception) -> str:
    if isinstance(e, httpx.TimeoutException):
        return "timeout"
    if isinstance(e, httpx.HTTPStatusError):
        return f"http_{e.response.status_code}"
    status = getattr(e, "status_code", None)
    if isinstance(status, int):
        return f"http_{status}"
    if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
        return "timeout"
    return f"error:{type(e).__name__}"


@dataclass
class ClaudeVoter:
    api_key: str
    model: str = "claude-opus-5-5"
    http_client: Any = None  # an httpx2.Client (the anthropic SDK uses httpx2); tests inject a MockTransport
    backend: str = "claude"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kw: Any) -> ClaudeVoter:
        e = env or os.environ
        key = e.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise VoterConfigError("ANTHROPIC_API_KEY is not set")
        return cls(api_key=key, model=e.get("CLAUDE_MODEL") or "claude-opus-5-5", **kw)

    def vote(self, request: dict[str, Any], timeout_s: float = 4.0) -> dict[str, Any]:
        import anthropic

        t0 = time.perf_counter()
        options = _shuffled(request["options"], f"claude:{request['req_id']}")
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img}}
            for img in (request.get("images") or [])[:4]
        ]
        content.append({"type": "text", "text": _prompt(request, options)})
        client = anthropic.Anthropic(
            api_key=self.api_key, http_client=self.http_client, max_retries=0, timeout=timeout_s
        )
        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=600,
                output_config={"format": {"type": "json_schema", "schema": VOTE_SCHEMA}, "effort": "low"},
                messages=[{"role": "user", "content": content}],
            )
        except Exception as e:  # noqa: BLE001 - every voter failure is recorded, never raised (D-23)
            return _result(self.backend, self.model, t0, error=_http_error_code(e))
        if getattr(msg, "stop_reason", None) == "refusal":
            return _result(self.backend, self.model, t0, error="refusal")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return _result(self.backend, self.model, t0, error="parse")
        choice, probs, rationale = _normalise(raw, request["options"])
        return _result(self.backend, self.model, t0, choice=choice, probs=probs, rationale=rationale)
