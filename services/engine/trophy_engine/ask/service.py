"""The ask service the gateway proxies to (``RULES_URL``, default ``http://127.0.0.1:8100 + PORT_OFFSET``):
``POST /ask {question, sport?}`` -> route -> run the check(s) on the stored track -> Claude phrases -> answer.
The gateway reads ``answer``, ``citations`` (a list) and ``latency_ms`` and passes everything else through.
No matching check: ``found: false`` plus a pending check appended to ``<session_dir>/pending_checks.jsonl`` for the
Droid's ``new_check`` run. No phraser: 503 ``not_configured``. Claude down: 503 ``upstream``. Never a made-up answer."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..checks.library import LibraryError
from .phrase import AskUpstreamError, Phraser
from .router import Query, route
from .store import TrackStore

PENDING_FILE = "pending_checks.jsonl"
PENDING_ANSWER = "I don't have a check for that yet; give me a moment."
DEFAULT_PORT = 8100


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    sport: str | None = None


def slugify(question: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")
    return s[:n].rstrip("_") or "question"


def _append_pending(session_dir: Path, row: dict[str, Any]) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    with (session_dir / PENDING_FILE).open("a", encoding="utf8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _primary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return results[0] if results else {}


def make_app(
    store: TrackStore,
    phraser: Phraser | None,
    *,
    session_dir: Path | None = None,
    config_error: str | None = None,
) -> FastAPI:
    app = FastAPI(title="trophy-ask", version="0.1.0")
    app.state.store = store
    app.state.phraser = phraser
    app.state.session_dir = Path(session_dir) if session_dir else None
    app.state.config_error = config_error or ("ANTHROPIC_API_KEY is not set" if phraser is None else None)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "checks": store.library.names(),
            "samples": len(store),
            "segments": len(store.segments),
            "phraser": "configured" if app.state.phraser is not None else "missing",
        }

    @app.post("/ask")
    def ask(body: AskBody) -> Any:
        t_req = time.perf_counter()
        ph: Phraser | None = app.state.phraser
        if ph is None:
            return JSONResponse({"error": "not_configured", "detail": app.state.config_error}, status_code=503)
        sport = body.sport or store.sport
        if len(store) == 0 or store.field is None:
            return {
                "found": False,
                "answer": "",
                "speech": "",
                "reason": "no_track",
                "citations": [],
                "latency_ms": _ms(t_req),
            }

        t_chk = time.perf_counter()
        try:
            q: Query | None = route(body.question, store)
            results: list[dict[str, Any]] = []
            if q is not None:
                track = store.track()
                for call in q.checks:
                    results.append(store.library.run(call.name, track, store.field, None, **call.kwargs))
        except LibraryError as e:
            return JSONResponse({"error": "check_failed", "detail": str(e)[:300]}, status_code=500)
        check_ms = _ms(t_chk)

        if q is None:
            pending = {
                "slug": slugify(body.question),
                "question": body.question,
                "created_at_ms": int(time.time() * 1000),
            }
            if app.state.session_dir is not None:
                _append_pending(app.state.session_dir, {**pending, "sport": sport})
            return {
                "found": False,
                "answer": PENDING_ANSWER,
                "speech": PENDING_ANSWER,
                "citations": [],
                "pending_check": pending,
                "latency_ms": _ms(t_req),
            }

        try:
            said = ph.phrase(body.question, results, q.facts, sport, q.scope)
        except AskUpstreamError as e:
            return JSONResponse({"error": "upstream", "detail": e.code, "check": q.check}, status_code=503)

        prim = _primary(results)
        out: dict[str, Any] = {
            "found": True,
            "answer": said["answer"],
            "speech": said["speech"],
            "citations": [],
            "check": q.check,
            "intent": q.intent,
            "verdict": prim.get("verdict"),
            "p": prim.get("p"),
            "sigma_m": prim.get("sigma_m"),
            "t_s": prim.get("t_s"),
            "evidence": prim.get("evidence", {}) if results else q.facts,
            "text": prim.get("text", ""),
            "calibrated": bool(prim.get("calibrated", False)) if results else None,
            "scope": q.scope,
            "facts": q.facts,
            "results": results,
            "model": said["model"],
            "latency_ms": _ms(t_req),
            "check_ms": check_ms,
            "claude_ms": said["claude_ms"],
        }
        return out

    return app


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def default_port(env: dict[str, str] | None = None) -> int:
    e = env if env is not None else os.environ
    return DEFAULT_PORT + int(e.get("PORT_OFFSET") or 0)


def serve(app: FastAPI, port: int | None = None, host: str = "127.0.0.1") -> Any:
    """Run uvicorn in a daemon thread (the engine loop calls this). Returns the Server; ``should_exit`` stops it."""
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port if port is not None else default_port(), log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="trophy-ask", daemon=True)
    thread.start()
    server.thread = thread  # type: ignore[attr-defined]
    return server
