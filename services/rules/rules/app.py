"""Trophy rules service (port 8100 + PORT_OFFSET): ask the ref, rule_ref, clauses, healthz (interfaces-v1 §17).

Startup validates the three keys, builds the Moss client, loads the one rules index (fails fast if it isn't built)
and constructs the Claude client with no warm-up call. There is no keyless mode: a ConfigError at startup is printed
as one line and the process exits 3 (uvicorn's startup-failure code).
"""

from __future__ import annotations

import contextlib
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import rule_ref as RR
from .clauses import render_markdown
from .clients import anthropic_client, moss_client
from .config import Settings
from .errors import ConfigError
from .llm import ClaudeJSON
from .log import jlog
from .models import AskIn, AskOut, RuleRefIn, RuleRefOut
from .pipeline import AskPipeline
from .search import RuleStore


async def boot(settings: Settings) -> tuple[RuleStore, ClaudeJSON]:
    """Keys -> Moss client -> load the index -> Claude client. Raises ConfigError with a one-line reason."""
    settings.require_keys()
    store = RuleStore(moss_client(settings), index=settings.moss_index, model_id=settings.moss_model)
    await store.load()
    with contextlib.suppress(Exception):  # the cloud status call is informational; a loaded index is what matters
        await store.status()
    llm = ClaudeJSON(anthropic_client(settings), model=settings.ask_model, effort=settings.ask_effort)
    return store, llm


def create_app(settings: Settings | None = None, *, pipeline: AskPipeline | None = None) -> FastAPI:
    """`pipeline` is injected by tests; the real app boots from the environment in its lifespan."""

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        s = settings or Settings.from_env()
        app.state.settings = s
        if pipeline is not None:
            app.state.pipeline = pipeline
        else:
            try:
                store, llm = await boot(s)
            except ConfigError as e:
                print(str(e), file=sys.stderr)
                sys.exit(3)
            app.state.pipeline = AskPipeline(store, llm, s)
        app.state.started_ms = int(time.time() * 1000)
        jlog("rules up", port=s.port, index=s.moss_index, ask_model=s.ask_model, effort=s.ask_effort)
        yield

    app = FastAPI(title="Trophy rules", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(ConfigError)
    async def _config_error(_, exc: ConfigError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": "not_configured", "detail": str(exc)})

    def pl(request: Request) -> AskPipeline:
        return request.app.state.pipeline

    @app.get("/healthz")
    async def healthz(request: Request) -> dict[str, Any]:
        p = pl(request)
        info = p.store.info or {}
        return {
            "ok": True,
            "service": "rules",
            "index": p.store.index,
            "doc_count": info.get("doc_count"),
            "model": info.get("model", p.store.model_id),
            "loaded_ms": round(p.store.loaded_ms, 1) if p.store.loaded_ms is not None else None,
            "ask_model": p.llm.model,
            "effort": p.llm.effort,
        }

    @app.post("/ask", response_model=AskOut)
    async def ask(body: AskIn, request: Request) -> AskOut:
        return await pl(request).ask(body.question, body.sport)

    @app.post("/rule_ref", response_model=RuleRefOut)
    async def rule_ref(body: RuleRefIn, request: Request) -> RuleRefOut:
        if not (body.rule_ref or body.rule_id or body.text):
            raise HTTPException(422, "give rule_ref, rule_id or text")
        p = pl(request)
        out = await RR.resolve(
            p.store, sport=body.sport, rule_ref=body.rule_ref, rule_id=body.rule_id, text=body.text,
            min_score=p.s.ask_min_score,
        )  # fmt: skip
        if out is None:
            raise HTTPException(404, "no clause matched")
        jlog("rule_ref", sport=body.sport, rule_ref=body.rule_ref, rule_id=out.rule_id, how=out.how, score=out.score)
        return out

    @app.get("/clauses", response_class=PlainTextResponse)
    async def clauses(
        request: Request,
        sport: str = Query(min_length=1, max_length=40),
        q: str = Query(min_length=1, max_length=2000),
        k: int = Query(8, ge=1, le=20),
    ) -> PlainTextResponse:
        p = pl(request)
        hits, moss_ms = await p.store.search(sport, q, k, alpha=0.8)
        jlog("clauses", sport=sport, k=k, hits=len(hits), moss_ms=round(moss_ms, 1))
        return PlainTextResponse(render_markdown(hits, sport=sport, q=q, moss_ms=moss_ms), media_type="text/markdown")

    return app


app = create_app()
