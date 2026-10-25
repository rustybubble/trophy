"""Claude structured-output calls (anthropic >= 2.3, Messages API).

`output_config.format` with a JSON schema makes the first text block valid JSON. Thinking is adaptive by default on
these models and `temperature` / forced `tool_choice` are rejected, so neither is sent; depth is `output_config.effort`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Protocol

log = logging.getLogger("referee.llm")


class LLMError(RuntimeError):
    pass


class JSONCompleter(Protocol):
    async def complete(
        self, *, system: str, user: str, schema: dict[str, Any], label: str, fast: bool = False
    ) -> tuple[dict[str, Any], float]: ...


class ClaudeJSON:
    """Two models behind one call: `fast=True` picks the router model (Haiku), else the phrasing model."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-opus-5-5",
        fast_model: str = "claude-haiku-5-5",
        effort: str = "low",
        max_tokens: int = 1024,
        timeout_s: float = 6.0,
        client: Any = None,
    ) -> None:
        if client is None:
            import anthropic

            if not api_key:
                raise LLMError("ANTHROPIC_API_KEY is required")
            client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=1)
        self.client = client
        self.model = model
        self.fast_model = fast_model
        self.effort = effort
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    async def complete(
        self, *, system: str, user: str, schema: dict[str, Any], label: str, fast: bool = False
    ) -> tuple[dict[str, Any], float]:
        model = self.fast_model if fast else self.model
        t0 = time.perf_counter()
        try:
            msg = await asyncio.wait_for(
                self.client.messages.create(
                    model=model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                ),
                timeout=self.timeout_s,
            )
        except TimeoutError as e:
            raise LLMError(f"Claude {label} timed out after {self.timeout_s:.0f} s") from e
        ms = (time.perf_counter() - t0) * 1000
        if getattr(msg, "stop_reason", None) == "refusal":
            raise LLMError(f"Claude declined the {label} request (stop_reason=refusal)")
        text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise LLMError(f"Claude returned no text block for {label} (stop_reason={msg.stop_reason})")
        usage = getattr(msg, "usage", None)
        log.info(
            "claude %s model=%s ms=%.0f in=%s out=%s",
            label,
            getattr(msg, "model", model),
            ms,
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )
        try:
            return json.loads(text), ms
        except json.JSONDecodeError as e:
            raise LLMError(f"Claude {label} returned invalid JSON") from e
