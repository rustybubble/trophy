"""Run a session check in the engine over Redis: `ctl:engine` run_check / request_check, reply on a per-request stream.

The engine (Agent 3) owns the check library and the track buffer; the referee never computes geometry. A cached check
answers in milliseconds, so `run` has a short timeout; `request` is the Droid path and is awaited in the background.
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from trophy.contracts import CheckReply
from trophy.ids import new_ulid
from trophy.streams import CTL_ENGINE, CTL_STREAM_MAXLEN, make_ctl

REPLY_TTL_S = 300


class CheckTimeout(TimeoutError):
    pass


@dataclass
class CheckOutcome:
    result: CheckReply | None
    latency_ms: float
    error: str | None = None
    reply_to: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class CheckBackend(Protocol):
    async def run(
        self, game_id: str, check: str, args: dict[str, Any], *, question: str, by_cam_id: str | None, timeout_s: float
    ) -> CheckOutcome: ...

    async def request(
        self, game_id: str, question: str, *, hint: str | None, args: dict[str, Any], by_cam_id: str | None
    ) -> str: ...

    async def wait(self, reply_to: str, timeout_s: float) -> CheckOutcome: ...


def parse_reply(fields: dict[Any, Any]) -> dict[str, Any]:
    raw = fields.get(b"json", fields.get("json"))
    if raw is None:
        return {}
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)


class RedisCheckBackend:
    """XADD a ctl command with `reply_to`, then XREAD that stream (blocking) for the one CheckReply."""

    def __init__(self, r: Any) -> None:
        self.r = r  # redis.asyncio.Redis (or fakeredis.FakeAsyncRedis)

    async def _send(self, cmd: str, game_id: str, args: dict[str, Any], by_cam_id: str | None) -> str:
        reply_to = f"reply:{new_ulid()}"
        ctl = make_ctl(cmd, game_id, {**args, "reply_to": reply_to}, by_cam_id=by_cam_id)
        await self.r.xadd(
            CTL_ENGINE, {"json": ctl.model_dump_json(by_alias=True)}, maxlen=CTL_STREAM_MAXLEN, approximate=True
        )
        return reply_to

    async def run(
        self, game_id: str, check: str, args: dict[str, Any], *, question: str, by_cam_id: str | None, timeout_s: float
    ) -> CheckOutcome:
        reply_to = await self._send(
            "run_check", game_id, {"check": check, "args": args, "question": question}, by_cam_id
        )
        return await self.wait(reply_to, timeout_s)

    async def request(
        self, game_id: str, question: str, *, hint: str | None, args: dict[str, Any], by_cam_id: str | None
    ) -> str:
        a: dict[str, Any] = {"question": question, "args": args}
        if hint:
            a["check_hint"] = hint
        return await self._send("request_check", game_id, a, by_cam_id)

    async def wait(self, reply_to: str, timeout_s: float) -> CheckOutcome:
        t0 = time.perf_counter()
        deadline = t0 + timeout_s
        last_id = "0-0"
        while True:
            remaining_ms = int((deadline - time.perf_counter()) * 1000)
            if remaining_ms <= 0:
                return CheckOutcome(None, (time.perf_counter() - t0) * 1000, "timeout", reply_to)
            resp = await self.r.xread({reply_to: last_id}, count=1, block=min(remaining_ms, 1000))
            if not resp:
                continue
            _stream, entries = resp[0]
            entry_id, fields = entries[0]
            last_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
            data = parse_reply(fields)
            if not data:
                continue
            with contextlib.suppress(Exception):  # housekeeping only
                await self.r.expire(reply_to, REPLY_TTL_S)
            ms = (time.perf_counter() - t0) * 1000
            try:
                result = CheckReply.model_validate(data)
            except Exception as e:  # noqa: BLE001 - a malformed reply is reported, not raised through the call
                return CheckOutcome(None, ms, f"bad_reply:{type(e).__name__}", reply_to, data)
            return CheckOutcome(result, ms, result.error, reply_to, data)
