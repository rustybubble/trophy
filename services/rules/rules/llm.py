"""Claude structured-output calls (anthropic 2.3, Messages API).

`output_config.format` with a JSON schema makes the first text block valid JSON (structured
outputs). Thinking is on by default on claude-opus-5-5 and `temperature` / forced `tool_choice`
are rejected there, so neither is sent; depth is set with `output_config.effort`.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("rules")


class ClaudeJSON:
    def __init__(self, client, *, model: str = "claude-opus-5-5", effort: str = "low", max_tokens: int = 2048) -> None:
        self.client = client  # anthropic.AsyncAnthropic, or a fake whose messages.create returns an anthropic Message
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    async def complete(
        self, *, system: str, user: str, schema: dict[str, Any], label: str
    ) -> tuple[dict[str, Any], float]:
        t0 = time.perf_counter()
        msg = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        ms = (time.perf_counter() - t0) * 1000
        if msg.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined the {label} request (stop_reason=refusal)")
        text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise RuntimeError(f"Claude returned no text block for {label} (stop_reason={msg.stop_reason})")
        usage = getattr(msg, "usage", None)
        log.info(
            "claude %s model=%s claude_ms=%.0f in=%s out=%s",
            label,
            msg.model,
            ms,
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )
        return json.loads(text), ms
