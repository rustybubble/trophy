"""Moss indexes: one per sport for rules (`rules-<sport>`) and one per game for moments (`moments-<game_id>`).

Moss (1.21) builds indexes in the cloud and queries a locally loaded snapshot: `load_index` must
run before `query`, and after a mutation the snapshot is reloaded. Metadata values are strings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Protocol

from pydantic import BaseModel

log = logging.getLogger("rules")


class RuleDoc(BaseModel):
    sport: str
    rule_id: str
    title: str = ""
    text: str
    url: str = ""


class RuleHit(BaseModel):
    rule_id: str
    title: str
    url: str
    text: str
    score: float


class Moment(BaseModel):
    moment_id: str
    game_id: str
    kind: str
    t_game_s: float
    label: str
    team_id: str | None = None
    tags: list[str] = []
    score_after: str | None = None


class MomentHit(BaseModel):
    moment_id: str
    score: float


class Timed(BaseModel):
    ms: float


def rules_index(sport: str) -> str:
    return f"rules-{sport}"


def moments_index(game_id: str) -> str:
    return f"moments-{game_id}"


class RuleSearch(Protocol):
    async def search(self, sport: str, q: str, top_k: int) -> tuple[list[RuleHit], float]: ...


class MomentStore(Protocol):
    async def upsert(self, game_id: str, moments: list[Moment]) -> int: ...
    async def search(self, game_id: str, q: str, top_k: int) -> tuple[list[MomentHit], float]: ...


def rule_doc_to_moss(d: RuleDoc) -> dict[str, Any]:
    return {
        "id": d.rule_id,
        "text": f"{d.title}\n{d.text}" if d.title else d.text,
        "metadata": {"rule_id": d.rule_id, "title": d.title, "url": d.url, "sport": d.sport},
    }


def moment_to_moss(m: Moment) -> dict[str, Any]:
    tags = " ".join(m.tags)
    text = " · ".join(x for x in (m.kind.replace("_", " "), m.label, tags, m.score_after or "") if x)
    meta = {
        "moment_id": m.moment_id,
        "game_id": m.game_id,
        "kind": m.kind,
        "t_game_s": f"{m.t_game_s:.3f}",
        "label": m.label,
        "team_id": m.team_id or "",
        "tags": json.dumps(m.tags),
        "score_after": m.score_after or "",
    }
    return {"id": m.moment_id, "text": text, "metadata": meta}


class MossStore:
    """Rules + moments on one MossClient. `client` is a `moss.MossClient` or a fake with the same coroutines."""

    def __init__(self, client, *, model_id: str = "moss-minilm") -> None:
        self.client = client
        self.model_id = model_id
        self._loaded: set[str] = set()
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self, name: str) -> None:
        async with self._lock:
            if name in self._loaded:
                return
            await self.client.load_index(name)
            self._loaded.add(name)

    async def _invalidate(self, name: str) -> None:
        async with self._lock:
            self._loaded.discard(name)

    async def _exists(self, name: str) -> bool:
        from moss import MossError

        try:
            await self.client.get_index(name)
            return True
        except MossError:
            return False

    async def _create_or_upsert(self, name: str, docs: list[dict[str, Any]]) -> None:
        from moss import MutationOptions

        if await self._exists(name):
            await self.client.add_docs(name, docs, MutationOptions(upsert=True))
        else:
            await self.client.create_index(name, docs, self.model_id)
        await self._invalidate(name)

    async def _query(self, name: str, q: str, top_k: int):
        from moss import QueryOptions

        await self._ensure_loaded(name)
        t0 = time.perf_counter()
        res = await self.client.query(name, q, QueryOptions(top_k=top_k))
        ms = (time.perf_counter() - t0) * 1000
        log.info("moss query index=%s top_k=%d hits=%d moss_ms=%.1f", name, top_k, len(res.docs), ms)
        return res, ms

    # rules
    async def build_rules(self, sport: str, docs: list[RuleDoc]) -> int:
        payload = [rule_doc_to_moss(d) for d in docs if d.sport == sport]
        if not payload:
            raise ValueError(f"no rules for sport {sport!r}")
        await self._create_or_upsert(rules_index(sport), payload)
        return len(payload)

    async def search(self, sport: str, q: str, top_k: int) -> tuple[list[RuleHit], float]:
        res, ms = await self._query(rules_index(sport), q, top_k)
        hits = []
        for d in res.docs:
            meta = d.metadata or {}
            text = d.text
            title = meta.get("title", "")
            if title and text.startswith(title + "\n"):
                text = text[len(title) + 1 :]
            hits.append(
                RuleHit(
                    rule_id=meta.get("rule_id", d.id), title=title, url=meta.get("url", ""), text=text, score=d.score
                )
            )
        return hits, ms

    # moments
    async def upsert(self, game_id: str, moments: list[Moment]) -> int:
        payload = [moment_to_moss(m) for m in moments if m.game_id == game_id]
        if not payload:
            return 0
        await self._create_or_upsert(moments_index(game_id), payload)
        return len(payload)

    async def search_moments(self, game_id: str, q: str, top_k: int) -> tuple[list[MomentHit], float]:
        res, ms = await self._query(moments_index(game_id), q, top_k)
        return [MomentHit(moment_id=(d.metadata or {}).get("moment_id", d.id), score=d.score) for d in res.docs], ms
