"""Run the voters in parallel (threads), each under the request's timeout, blend, and post one ai_vote row per voter.
The engine never waits on this: ``BackgroundDecider.submit`` returns immediately (D-23)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any

from .blend import blend
from .voters import Voter

log = logging.getLogger("trophy.decide")


def _timeout_vote(backend: str, model: str, t0: float) -> dict[str, Any]:
    return {
        "backend": backend,
        "model": model,
        "choice": None,
        "probs": {},
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "error": "timeout",
        "rationale": "",
    }


def decide(request: dict[str, Any], voters: Sequence[Voter], *, timeout_s: float | None = None) -> dict[str, Any]:
    """Fan out to every voter in parallel; a slow voter is cut off at the timeout and recorded as such."""
    timeout = float(timeout_s or request.get("timeout_s") or 4.0)
    options = list(request["options"])
    votes: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    if voters:
        pool = ThreadPoolExecutor(max_workers=len(voters), thread_name_prefix="voter")
        futs = {pool.submit(v.vote, request, timeout): v for v in voters}
        done, pending = wait(futs, timeout=timeout + 0.5)
        for f in done:
            try:
                votes.append(f.result())
            except Exception as e:  # noqa: BLE001
                v = futs[f]
                votes.append({**_timeout_vote(v.backend, v.model, t0), "error": f"error:{type(e).__name__}"})
        for f in pending:  # a voter past the deadline is recorded as a timeout; its thread is left to finish alone
            v = futs[f]
            votes.append(_timeout_vote(v.backend, v.model, t0))
            f.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
    votes.sort(key=lambda v: v["backend"])
    b = blend(options, request.get("p_geometry"), votes)
    return {"req_id": request["req_id"], "votes": votes, **b}


class BackgroundDecider:
    """Fire-and-forget: one thread per request; results go to ``post_vote`` (an ai_vote row) and ``on_result``."""

    def __init__(
        self,
        voters: Sequence[Voter],
        post_vote: Callable[[dict[str, Any]], None],
        on_result: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        now_ms: Callable[[], float] | None = None,
    ) -> None:
        self.voters = list(voters)
        self.post_vote = post_vote
        self.on_result = on_result
        self.now_ms = now_ms or (lambda: time.time() * 1000.0)
        self.threads: list[threading.Thread] = []

    def submit(self, request: dict[str, Any]) -> None:
        th = threading.Thread(target=self._run, args=(request,), name=f"decide-{request['req_id'][-6:]}", daemon=True)
        self.threads.append(th)
        th.start()

    def _run(self, request: dict[str, Any]) -> None:
        try:
            result = decide(request, self.voters)
        except Exception:  # noqa: BLE001
            log.exception("decide failed for %s", request.get("call_id"))
            return
        for v in result["votes"]:
            self.post_vote(
                {
                    "call_id": request["call_id"],
                    "challenge_id": request.get("challenge_id"),
                    "game_id": request["game_id"],
                    "backend": v["backend"],
                    "model": v["model"],
                    "choice": v.get("choice"),
                    "probs": v.get("probs") or {},
                    "latency_ms": v["latency_ms"],
                    "error": v.get("error"),
                    "rationale": v.get("rationale", ""),
                    "created_at_ms": self.now_ms(),
                }
            )
        if self.on_result is not None:
            self.on_result(request, result)

    def join(self, timeout_s: float = 10.0) -> None:
        for th in self.threads:
            th.join(timeout_s)
