"""One Moss index for every sport (`trophy-rules-v1`), filtered by the `sport` metadata field (D-30).

moss 1.21: indexes are built in the cloud (`create_index` / `add_docs`), then `load_index` downloads a snapshot and
`query` / `get_docs` run in-process. Metadata values are strings; filters use `$eq` etc. `score` is vector
similarity in 0..1 and does not change with `alpha` (1.0 semantic, 0.0 keyword, default 0.8 hybrid).
"""

from __future__ import annotations

import re
import time
from typing import Any

from .errors import ConfigError
from .log import jlog
from .models import RuleDoc, RuleHit

_CLAUSE_NUMBER = re.compile(r"\b\d+\.\d+(?:\.\w+)*\b")


def doc_text(d: RuleDoc) -> str:
    head = " ".join(x for x in (d.number, d.title) if x)
    return f"{head}. {d.text}" if head else d.text


def to_moss(d: RuleDoc) -> dict[str, Any]:
    return {
        "id": d.rule_id,
        "text": doc_text(d),
        "metadata": {
            "sport": d.sport,
            "rule_id": d.rule_id,
            "number": d.number,
            "title": d.title,
            "url": d.url,
            "source": d.source,
        },
    }


def hit_from(doc: Any, score: float | None = None) -> RuleHit:
    """A RuleHit from a moss QueryResultDocumentInfo / DocumentInfo (metadata carries everything but the body)."""
    meta = doc.metadata or {}
    text = doc.text or ""
    head = " ".join(x for x in (meta.get("number", ""), meta.get("title", "")) if x)
    if head and text.startswith(head + ". "):
        text = text[len(head) + 2 :]
    return RuleHit(
        rule_id=meta.get("rule_id", doc.id),
        sport=meta.get("sport", ""),
        number=meta.get("number", ""),
        title=meta.get("title", ""),
        url=meta.get("url", ""),
        source=meta.get("source", ""),
        text=text,
        score=float(getattr(doc, "score", 0.0) if score is None else score),
    )


def mentions_clause_number(q: str) -> bool:
    return bool(_CLAUSE_NUMBER.search(q))


def merge_hits(primary: list[RuleHit], extra: list[RuleHit], top_k: int) -> list[RuleHit]:
    """Primary order first, then unseen extras; a repeated id keeps its best score."""
    out: dict[str, RuleHit] = {}
    for h in [*primary, *extra]:
        if h.rule_id in out:
            if h.score > out[h.rule_id].score:
                out[h.rule_id] = out[h.rule_id].model_copy(update={"score": h.score})
        else:
            out[h.rule_id] = h
    return list(out.values())[: max(top_k, len(primary))]


def _is_not_found(e: Exception) -> bool:
    return getattr(e, "code", None) == "NOT_FOUND" or "not found" in str(e).lower()


class RuleStore:
    """The rules index on one MossClient (`moss.MossClient`, or a test double with the same coroutines)."""

    def __init__(self, client, *, index: str = "trophy-rules-v1", model_id: str = "moss-minilm") -> None:
        self.client = client
        self.index = index
        self.model_id = model_id
        self.loaded_ms: float | None = None
        self.info: dict[str, Any] | None = None

    # ---- lifecycle
    async def exists(self) -> bool:
        from moss import MossError

        try:
            await self.client.get_index(self.index)
            return True
        except MossError as e:
            if _is_not_found(e):
                return False
            raise

    async def status(self) -> dict[str, Any]:
        info = await self.client.get_index(self.index)
        model = getattr(info, "model", None)
        self.info = {
            "index": self.index,
            "doc_count": int(getattr(info, "doc_count", 0)),
            "status": str(getattr(info, "status", "")),
            "model": getattr(model, "id", None) or str(model or self.model_id),
            "updated_at": getattr(info, "updated_at", None),
        }
        return self.info

    async def load(self) -> float:
        """`load_index` (downloads the snapshot; queries then run locally). Fails fast when the index isn't built."""
        from moss import MossError

        t0 = time.perf_counter()
        try:
            await self.client.load_index(self.index)
        except MossError as e:
            if _is_not_found(e):
                raise ConfigError(
                    f"Moss index {self.index!r} is not built; run `trophy-rules index build` "
                    f"(after `trophy-rules dataset export`)"
                ) from e
            raise
        self.loaded_ms = (time.perf_counter() - t0) * 1000
        jlog("moss index loaded", index=self.index, loaded_ms=round(self.loaded_ms, 1))
        return self.loaded_ms

    async def build(self, docs: list[RuleDoc], *, refresh: bool = False) -> dict[str, Any]:
        """Create the index (wait=True) or, with refresh, upsert into it. Returns {how, doc_count, job_id}."""
        from moss import MutationOptions

        payload = [to_moss(d) for d in docs]
        if not payload:
            raise ValueError("no rule documents to index")
        t0 = time.perf_counter()
        if await self.exists():
            if not refresh:
                raise ConfigError(f"Moss index {self.index!r} already exists; use `index refresh` to upsert into it")
            res = await self.client.add_docs(self.index, payload, MutationOptions(upsert=True))
            how = "refresh"
        else:
            res = await self.client.create_index(self.index, payload, self.model_id, wait=True)
            how = "create"
        ms = (time.perf_counter() - t0) * 1000
        out = {
            "how": how,
            "doc_count": int(getattr(res, "doc_count", len(payload))),
            "job_id": getattr(res, "job_id", None),
        }
        jlog("moss index built", index=self.index, build_ms=round(ms, 1), sent=len(payload), **out)
        return out

    # ---- retrieval
    def _filter(self, sport: str) -> dict[str, Any]:
        return {"sport": {"$eq": sport}}

    async def search(self, sport: str, q: str, top_k: int, alpha: float = 0.8) -> tuple[list[RuleHit], float]:
        from moss import QueryOptions

        t0 = time.perf_counter()
        res = await self.client.query(self.index, q, QueryOptions(top_k=top_k, alpha=alpha, filter=self._filter(sport)))
        ms = (time.perf_counter() - t0) * 1000
        hits = [hit_from(d) for d in res.docs if (d.metadata or {}).get("sport", sport) == sport]
        return hits, ms

    async def retrieve(self, sport: str, q: str, top_k: int) -> tuple[list[RuleHit], float]:
        """The /ask retrieval: hybrid at alpha 0.8, plus a keyword-leaning pass (alpha 0.3) when q names a clause."""
        hits, ms = await self.search(sport, q, top_k, alpha=0.8)
        if mentions_clause_number(q):
            extra, ms2 = await self.search(sport, q, top_k, alpha=0.3)
            hits, ms = merge_hits(hits, extra, top_k), ms + ms2
        jlog("moss query", index=self.index, sport=sport, top_k=top_k, hits=len(hits), moss_ms=round(ms, 1))
        return hits, ms

    async def get_by_ids(self, ids: list[str], sport: str | None = None) -> list[RuleHit]:
        from moss import GetDocumentsOptions

        docs = await self.client.get_docs(self.index, GetDocumentsOptions(doc_ids=ids))
        hits = [hit_from(d, score=1.0) for d in docs]
        return [h for h in hits if sport is None or h.sport == sport]
