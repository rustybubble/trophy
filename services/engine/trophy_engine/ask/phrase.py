"""Claude phrases a check's result for the judge. It REQUIRES ``ANTHROPIC_API_KEY``: no template, no offline answer
(project rule: no fallback code without API keys). Structured output through ``output_config.format`` (no
``temperature``, no forced ``tool_choice``), the fast model by default, a short timeout; every API failure raises
``AskUpstreamError`` so the service answers 503 rather than inventing a line."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL = "claude-haiku-5-5"


class AskConfigError(RuntimeError):
    """The phraser cannot be built (no key)."""


class AskUpstreamError(RuntimeError):
    """Claude did not return a usable answer (network, HTTP, refusal, parse)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


PHRASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "at most 2 sentences for the dashboard"},
        "speech": {
            "type": "string",
            "description": "the same for text-to-speech: plain words, no symbols or units signs",
        },
    },
    "required": ["answer", "speech"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the voice of Trophy, an AI referee at a pickup game, answering the judge's question about a call. "
    "You are given the result(s) of geometry checks that already ran on the fused 3D ball track, plus a few facts. "
    "Phrase ONLY those results. Never compute, estimate or guess geometry, never add a measurement that is not in "
    "the result, and never decide a point or a score yourself. "
    "Rules for the answer: at most 2 sentences; state the verdict first; quote the numbers that justify it "
    "(margin to the line and sigma in centimetres, toss height in centimetres, angle in degrees, clearance, speed) "
    "with no more than one decimal; name the rally and time from the scope when it helps. "
    "If `calibrated` is false, say the reading is BETA (uncalibrated) in the same breath. "
    "If a result's verdict is 'no_bounce' or 'no_serve', or a list verdict is empty for a yes/no question, say "
    '"I don\'t have a measurement for that" and, briefly, why (for example: no bounce near that time). '
    "For a score or server question, answer only from the facts given; if they are missing, say you don't have "
    "that recorded. "
    "`speech` is the same answer for text-to-speech: plain words, numbers spelled as digits, no symbols, no "
    "abbreviations like cm or deg (say centimetres, degrees), no markdown."
)


def _user_prompt(question: str, results: list[dict[str, Any]], facts: dict[str, Any], sport: str, scope: str) -> str:
    slim = [{k: v for k, v in r.items() if k != "ms"} for r in results]
    body = {
        "sport": sport,
        "question": question,
        "scope": scope,
        "facts": facts,
        "check_results": slim,
        "units": "metres and radians in the results; answer in centimetres and degrees",
    }
    return json.dumps(body, separators=(",", ":"), default=str)[:12000]


@dataclass
class Phraser:
    api_key: str
    model: str = DEFAULT_MODEL
    http_client: Any = None  # an httpx2.Client (the anthropic SDK uses httpx2); tests inject a MockTransport
    timeout_s: float = 6.0
    max_tokens: int = 300

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kw: Any) -> Phraser:
        e = env if env is not None else os.environ
        key = e.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise AskConfigError("ANTHROPIC_API_KEY is not set: ask-the-ref phrasing needs Claude (no offline mode)")
        return cls(api_key=key, model=e.get("CLAUDE_FAST_MODEL") or DEFAULT_MODEL, **kw)

    def phrase(
        self,
        question: str,
        results: list[dict[str, Any]],
        facts: dict[str, Any],
        sport: str = "table_tennis",
        scope: str = "",
    ) -> dict[str, Any]:
        """-> {"answer", "speech", "model", "claude_ms"}; raises AskUpstreamError on any failure."""
        import anthropic

        t0 = time.perf_counter()
        client = anthropic.Anthropic(
            api_key=self.api_key, http_client=self.http_client, max_retries=0, timeout=self.timeout_s
        )
        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                output_config={"format": {"type": "json_schema", "schema": PHRASE_SCHEMA}, "effort": "low"},
                messages=[{"role": "user", "content": _user_prompt(question, results, facts, sport, scope)}],
            )
        except Exception as e:  # noqa: BLE001 - every upstream failure becomes one typed error for the service
            raise AskUpstreamError(_error_code(e), str(e)[:200]) from e
        if getattr(msg, "stop_reason", None) == "refusal":
            raise AskUpstreamError("refusal")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise AskUpstreamError("parse", text[:200]) from e
        answer = str(raw.get("answer", "")).strip()
        speech = str(raw.get("speech", "")).strip() or answer
        if not answer:
            raise AskUpstreamError("empty")
        return {
            "answer": answer,
            "speech": speech,
            "model": self.model,
            "claude_ms": round((time.perf_counter() - t0) * 1000, 1),
        }


def _error_code(e: Exception) -> str:
    status = getattr(e, "status_code", None)
    if isinstance(status, int):
        return f"http_{status}"
    name = type(e).__name__.lower()
    if "timeout" in name or "timed out" in str(e).lower():
        return "timeout"
    return f"error:{type(e).__name__}"
