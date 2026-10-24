"""Trophy rules service (port 8100): ask the ref, rule_ref, moment search, grounded coach tips.

Clients are built lazily from the environment and only with their credentials (ConfigError ->
HTTP 503 with the missing key named). Tests override the `get_*` dependencies with fakes.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import ask as ask_mod
from . import coach as coach_mod
from .clients import anthropic_client, moss_client
from .config import Settings
from .errors import ConfigError
from .llm import ClaudeJSON
from .search import Moment, MomentHit, MossStore

log = logging.getLogger("rules")
app = FastAPI(title="Trophy rules", version="0.1.0")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache(maxsize=1)
def get_store() -> MossStore:
    s = get_settings()
    return MossStore(moss_client(s), model_id=s.moss_model)


@lru_cache(maxsize=1)
def get_llm() -> ClaudeJSON:
    s = get_settings()
    return ClaudeJSON(anthropic_client(s), model=s.claude_model)


@app.exception_handler(ConfigError)
async def _config_error(_, exc: ConfigError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "not_configured", "detail": str(exc)})


# --- models ---------------------------------------------------------------------------


class AskIn(BaseModel):
    question: str = Field(min_length=1)
    sport: str = Field(min_length=1)


class AskOut(BaseModel):
    answer: str
    speech: str
    citations: list[ask_mod.Citation]
    moss_ms: float
    latency_ms: float
    found: bool
    top_score: float | None


class RuleRefOut(BaseModel):
    rule_id: str
    title: str
    url: str
    quote: str
    score: float


class MomentsIn(BaseModel):
    game_id: str
    moments: list[Moment]


class SearchMomentsIn(BaseModel):
    game_id: str
    q: str = Field(min_length=1)
    top_k: int = 10


class SearchMomentsOut(BaseModel):
    hits: list[MomentHit]
    mode: str
    moss_ms: float


class CoachIn(BaseModel):
    game_id: str
    sport: str
    side: str
    stats: dict[str, float | int | str]
    sides: list[str] | None = None


class CoachOut(BaseModel):
    tips: list[coach_mod.Tip]
    validated: bool
    latency_ms: float


# --- routes ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz(s: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {"ok": True, "service": "rules", "keys": s.presence(), "model": s.claude_model}


@app.post("/ask", response_model=AskOut)
async def ask(
    body: AskIn,
    s: Settings = Depends(get_settings),
    store: MossStore = Depends(get_store),
    llm: ClaudeJSON = Depends(get_llm),
) -> AskOut:
    t0 = time.perf_counter()
    hits, moss_ms = await store.search(body.sport, body.question, s.top_k)
    top = hits[0].score if hits else None
    if top is None or top < s.min_score:
        res = ask_mod.not_found()
        log.info("ask sport=%s weak retrieval top=%s threshold=%.2f", body.sport, top, s.min_score)
    else:
        res = await ask_mod.answer(llm, body.question, body.sport, hits)
    latency = (time.perf_counter() - t0) * 1000
    log.info(
        "ask sport=%s found=%s moss_ms=%.1f claude_ms=%.0f latency_ms=%.0f",
        body.sport,
        res.found,
        moss_ms,
        res.claude_ms,
        latency,
    )
    return AskOut(
        answer=res.answer,
        speech=res.speech,
        citations=res.citations,
        moss_ms=round(moss_ms, 1),
        latency_ms=round(latency, 1),
        found=res.found,
        top_score=top,
    )


@app.get("/rule_ref", response_model=RuleRefOut | None)
async def rule_ref(
    sport: str = Query(min_length=1),
    q: str = Query(min_length=1),
    store: MossStore = Depends(get_store),
) -> RuleRefOut | JSONResponse:
    hits, moss_ms = await store.search(sport, q, 1)
    if not hits:
        return JSONResponse(
            status_code=404, content={"error": "no_rule", "detail": "no clause indexed for that sport/query"}
        )
    h = hits[0]
    log.info("rule_ref sport=%s rule_id=%s score=%.3f moss_ms=%.1f", sport, h.rule_id, h.score, moss_ms)
    return RuleRefOut(rule_id=h.rule_id, title=h.title, url=h.url, quote=ask_mod.clip_words(h.text), score=h.score)


@app.post("/moments/index")
async def moments_index(body: MomentsIn, store: MossStore = Depends(get_store)) -> dict[str, Any]:
    n = await store.upsert(body.game_id, body.moments)
    return {"game_id": body.game_id, "upserted": n}


@app.post("/search_moments", response_model=SearchMomentsOut)
async def search_moments(body: SearchMomentsIn, store: MossStore = Depends(get_store)) -> SearchMomentsOut:
    hits, moss_ms = await store.search_moments(body.game_id, body.q, body.top_k)
    return SearchMomentsOut(hits=hits, mode="semantic", moss_ms=round(moss_ms, 1))


@app.post("/coach", response_model=CoachOut)
async def coach(body: CoachIn, llm: ClaudeJSON = Depends(get_llm)) -> CoachOut:
    t0 = time.perf_counter()
    res = await coach_mod.coach(llm, sport=body.sport, side=body.side, stats=dict(body.stats), sides=body.sides)
    latency = (time.perf_counter() - t0) * 1000
    log.info(
        "coach game=%s side=%s validated=%s claude_ms=%.0f latency_ms=%.0f",
        body.game_id,
        body.side,
        res.validated,
        res.claude_ms,
        latency,
    )
    return CoachOut(tips=res.tips, validated=res.validated, latency_ms=round(latency, 1))
