"""Claude structured-output calls (anthropic 2.3, Messages API).

`output_config.format` with a JSON schema makes the first text block valid JSON. Thinking is on by default on
claude-opus-5-5; `temperature`, prefill and a forced `tool_choice` are rejected there, so none is sent; depth is
`output_config.effort`. The fixed system prompt goes first with `cache_control` so repeated asks hit the prompt cache.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .log import jlog


class ClaudeJSON:
    def __init__(self, client, *, model: str = "claude-opus-5-5", effort: str = "low", max_tokens: int = 600) -> None:
        self.client = client  # anthropic.AsyncAnthropic, or a double whose messages.create returns an anthropic Message
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    async def complete(
        self, *, system: str, user: str, schema: dict[str, Any], label: str
    ) -> tuple[dict[str, Any], float, dict[str, Any]]:
        """-> (parsed JSON, llm_ms, usage dict). Raises on refusal or a missing text block; never invents output."""
        t0 = time.perf_counter()
        msg = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        ms = (time.perf_counter() - t0) * 1000
        if msg.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined the {label} request (stop_reason=refusal)")
        text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise RuntimeError(f"Claude returned no text block for {label} (stop_reason={msg.stop_reason})")
        u = getattr(msg, "usage", None)
        usage = {
            "input_tokens": getattr(u, "input_tokens", None),
            "output_tokens": getattr(u, "output_tokens", None),
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
        }
        jlog("claude", label=label, model=getattr(msg, "model", self.model), llm_ms=round(ms, 1), **usage)
        return json.loads(text), ms, usage
