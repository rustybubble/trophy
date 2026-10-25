"""Fakes at the boundaries: Claude (scripted JSON), the engine (a Redis consumer that answers run_check/request_check),
and Cartesia (a local websocket server). No test makes a live call."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from trophy.streams import CTL_ENGINE

from referee.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    """`complete()` pops the next scripted reply for its label; records every prompt."""

    def __init__(self, replies: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.replies = {k: list(v) for k, v in (replies or {}).items()}
        self.calls: list[dict[str, Any]] = []

    def script(self, label: str, *replies: dict[str, Any]) -> None:
        self.replies.setdefault(label, []).extend(replies)

    async def complete(self, *, system: str, user: str, schema: dict[str, Any], label: str, fast: bool = False):
        self.calls.append({"label": label, "system": system, "user": user, "fast": fast})
        queue = self.replies.get(label) or []
        if not queue:
            raise AssertionError(f"no scripted reply for {label}: {user[:120]}")
        return queue.pop(0), 42.0


class FakeEngine:
    """Consumes ctl:engine like the engine's loop; answers run_check from `results` and request_check after a delay."""

    def __init__(self, r: fakeredis.FakeAsyncRedis, results: dict[str, dict[str, Any]], droid_delay_s: float = 0.05):
        self.r = r
        self.results = results
        self.droid_delay_s = droid_delay_s
        self.seen: list[dict[str, Any]] = []
        self.droid_result: dict[str, Any] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        last = "0-0"
        while True:
            resp = await self.r.xread({CTL_ENGINE: last}, count=10, block=50)
            for _stream, entries in resp or []:
                for entry_id, fields in entries:
                    last = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    cmd = json.loads(fields[b"json"] if b"json" in fields else fields["json"])
                    self.seen.append(cmd)
                    await self._handle(cmd)

    async def _handle(self, cmd: dict[str, Any]) -> None:
        args = cmd["args"]
        if cmd["cmd"] == "run_check":
            res = self.results.get(args["check"]) or {
                "check": args["check"],
                "calibrated": False,
                "error": "no_such_check",
                "latency_ms": 0.3,
            }
            res = {**res, "check": args["check"], "inputs": args["args"]}
            await self.r.xadd(args["reply_to"], {"json": json.dumps(res)})
        elif cmd["cmd"] == "request_check":
            await asyncio.sleep(self.droid_delay_s)
            res = self.droid_result or {
                "check": "new_check",
                "calibrated": False,
                "error": "failed:droid",
                "latency_ms": 1,
            }
            await self.r.xadd(args["reply_to"], {"json": json.dumps(res)})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="sk-ant-test",
        cartesia_api_key="sk_car_test",
        sports_dir=FIXTURES / "sports",
        data_dir=tmp_path,
        check_timeout_s=0.5,
        pending_timeout_s=2.0,
    )


@pytest.fixture
def redis_client() -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis()


IN_OUT_OUT = {
    "check": "in_out",
    "verdict": "out",
    "p": 0.97,
    "evidence": {"line": "end_B", "margin_m": -0.032, "sigma_m": 0.011, "t_game_s": 61.42},
    "calibrated": True,
    "tier": "AUTO",
    "latency_ms": 0.8,
}
EDGE_BETA = {
    "check": "edge_hit",
    "verdict": "top_edge",
    "p": 0.71,
    "evidence": {"t_game_s": 61.42},
    "calibrated": True,
    "tier": "BETA",
    "latency_ms": 0.6,
}
SERVE_UNCAL = {
    "check": "serve_toss",
    "verdict": "too_low",
    "p": 0.84,
    "evidence": {"height_m": 0.121, "angle_deg": 12.0, "sigma_height_m": 0.02},
    "calibrated": False,
    "tier": "BETA",
    "latency_ms": 1.1,
}

CTX = {
    "t_game_s": 70.0,
    "rally_no": 9,
    "server_team_id": "A",
    "teams": [{"team_id": "A", "name": "Team A"}, {"team_id": "B", "name": "Team B"}],
    "scores": [{"team_id": "A", "points": 7}, {"team_id": "B", "points": 5}],
    "last_calls": [
        {
            "id": "01CALL",
            "kind": "point",
            "outcome": "out",
            "text": "Out. Point A",
            "why": "Bounce 3.2 cm past the end line on B's side.",
            "p": 0.97,
            "tier": "AUTO",
            "t_game_s": 61.42,
            "rally_no": 9,
            "status": "final",
            "rule_id": "off_table",
        }
    ],
    "house_rules": [{"text": "No lets: a serve that clips the net is played on.", "status": "approved"}],
}


@pytest.fixture
async def engine(redis_client: fakeredis.FakeAsyncRedis):
    e = FakeEngine(redis_client, {"in_out": IN_OUT_OUT, "edge_hit": EDGE_BETA, "serve_toss": SERVE_UNCAL})
    await e.start()
    yield e
    await e.stop()
