"""The /ask pipeline, shared by the API and the eval runner: retrieve -> gate -> Claude -> verify -> answer."""

from __future__ import annotations

import time

from . import ask as A
from .config import Settings
from .llm import ClaudeJSON
from .log import jlog
from .models import AskOut
from .search import RuleStore


class AskPipeline:
    def __init__(self, store: RuleStore, llm: ClaudeJSON, settings: Settings) -> None:
        self.store, self.llm, self.s = store, llm, settings

    async def ask(self, question: str, sport: str) -> AskOut:
        t0 = time.perf_counter()
        hits, moss_ms = await self.store.retrieve(sport, question, self.s.ask_top_k)
        top = hits[0].score if hits else None
        base = {
            "moss_ms": round(moss_ms, 1),
            "model": self.llm.model,
            "top_score": top,
            "retrieved": [h.rule_id for h in hits],
        }

        def not_found(llm_ms: float, why: str) -> AskOut:
            text = A.not_found_text(hits, sport)
            out = AskOut(
                answer=text, speech=text, citations=[], found=False, llm_ms=round(llm_ms, 1), latency_ms=0, **base
            )
            out.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            jlog("ask", sport=sport, found=False, why=why, top_score=top, **_nums(out))
            return out

        if top is None or top < self.s.ask_min_score:
            return not_found(0.0, "weak retrieval")  # no Claude call
        data, llm_ms, _ = await self.llm.complete(
            system=A.SYSTEM, user=A.user_message(question, sport, hits), schema=A.ASK_SCHEMA, label="ask"
        )
        if not data.get("found") or not str(data.get("answer", "")).strip():
            return not_found(llm_ms, "model found=false")
        citations, dropped = A.verify_citations(data.get("citations", []), hits)
        if dropped:
            jlog("ask citations dropped", sport=sport, dropped=dropped)
        if not citations:
            return not_found(llm_ms, "no verifiable citation")
        out = AskOut(
            answer=str(data["answer"]).strip(),
            speech=A.strip_ids(str(data.get("speech") or data["answer"])),
            citations=citations,
            found=True,
            llm_ms=round(llm_ms, 1),
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            **base,
        )
        jlog("ask", sport=sport, found=True, citations=[c.rule_id for c in citations], top_score=top, **_nums(out))
        return out


def _nums(o: AskOut) -> dict[str, float]:
    return {"moss_ms": o.moss_ms, "llm_ms": o.llm_ms, "latency_ms": o.latency_ms}
