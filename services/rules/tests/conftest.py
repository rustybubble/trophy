"""Test doubles at the SDK boundary, for the pure parts of the pipeline (no network, no keys).

`FakeMoss` keeps one index in memory with the real `moss` result types, honours the `sport` `$eq` filter and
`get_docs(doc_ids=…)`; its scores are a deterministic word overlap, so the tests exercise OUR logic (the gate, the
grounding check, routing), never Moss's ranking. Anything that measures Moss or Claude lives under `tests/live/`.
The clauses are from the invented "Trophy Test Laws" (`evals/fixtures/rulebooks/synthetic_laws.txt`).
"""

from __future__ import annotations

import json
import re

import pytest
from anthropic.types import Message, TextBlock, Usage
from fastapi.testclient import TestClient
from moss import MossError, QueryResultDocumentInfo, SearchResult

from rules.app import create_app
from rules.config import Settings
from rules.llm import ClaudeJSON
from rules.models import RuleDoc
from rules.pipeline import AskPipeline
from rules.search import RuleStore

URL = "https://example.test/trophy-test-laws.pdf"
DOCS = [
    RuleDoc(sport="paddle_pong", rule_id="ttl:2.6.1", number="2.6.1", title="2.6 The Service", url=URL, source="TTL",
            text="Service shall start with the ball resting freely on the open palm of the server's stationary free "
            "hand, held still for at least one second."),
    RuleDoc(sport="paddle_pong", rule_id="ttl:2.6.2", number="2.6.2", title="2.6 The Service", url=URL, source="TTL",
            text="The server shall then project the ball near vertically upwards, without imparting spin, so that it "
            "rises at least 20 cm after leaving the palm of the free hand and then falls without touching anything "
            "before being struck."),
    RuleDoc(sport="paddle_pong", rule_id="ttl:2.9.1", number="2.9.1", title="2.9 A Let", url=URL, source="TTL",
            text="The rally shall be a let if in service the ball, in passing over or around the net assembly, "
            "touches it, provided the service is otherwise correct or the ball is obstructed by the receiver."),
    RuleDoc(sport="paddle_pong", rule_id="ttl:2.10.5", number="2.10.5", title="2.10 A Point", url=URL, source="TTL",
            text="Unless the rally is a let, a player shall score a point if the opponent's free hand touches the "
            "playing surface during the rally."),
    RuleDoc(sport="paddle_pong", rule_id="ttl:2.11.1", number="2.11.1", title="2.11 A Game", url=URL, source="TTL",
            text="A game shall be won by the player or pair first scoring 15 points unless both players or pairs "
            "score 14 points, when the game shall be won by the first player or pair subsequently gaining a lead of "
            "2 points."),
    RuleDoc(sport="kitchen_ball", rule_id="kb:7.A", number="7.A", title="7 Faults", url=URL, source="KB",
            text="It is a fault to volley the ball while any part of the player touches the kitchen, the zone within "
            "two metres of the net, during the rally."),
]  # fmt: skip


class FakeMoss:
    """One index; word overlap stands in for embeddings; filter and get_docs behave like moss 1.21."""

    def __init__(self) -> None:
        self.indexes: dict[str, dict[str, dict]] = {}
        self.loaded: set[str] = set()
        self.calls: list[str] = []

    def _missing(self, name: str) -> MossError:
        e = MossError(f"Index '{name}' not found")
        e.code = "NOT_FOUND"
        return e

    async def get_index(self, name):
        self.calls.append(f"get_index:{name}")
        if name not in self.indexes:
            raise self._missing(name)
        return type(
            "Info", (), {"doc_count": len(self.indexes[name]), "status": "Ready", "model": None, "updated_at": ""}
        )()

    async def create_index(self, name, docs, model_id=None, **kw):
        self.calls.append(f"create_index:{name}:{model_id}:wait={kw.get('wait')}")
        self.indexes[name] = {d["id"]: d for d in docs}
        return type("Res", (), {"doc_count": len(docs), "job_id": "job_fake"})()

    async def add_docs(self, name, docs, options=None, **_):
        self.calls.append(f"add_docs:{name}:upsert={getattr(options, 'upsert', None)}")
        self.indexes[name].update({d["id"]: d for d in docs})
        return type("Res", (), {"doc_count": len(docs), "job_id": "job_fake2"})()

    async def load_index(self, name, **_):
        self.calls.append(f"load_index:{name}")
        if name not in self.indexes:
            raise self._missing(name)
        self.loaded.add(name)
        return name

    @staticmethod
    def _match(meta: dict, flt: dict | None) -> bool:
        for key, cond in (flt or {}).items():
            if isinstance(cond, dict):
                if "$eq" in cond and meta.get(key) != cond["$eq"]:
                    return False
                if "$in" in cond and meta.get(key) not in cond["$in"]:
                    return False
            elif meta.get(key) != cond:
                return False
        return True

    async def query(self, name, query, options=None):
        assert name in self.loaded, "query before load_index"
        self.calls.append(f"query:{name}:alpha={getattr(options, 'alpha', None)}")
        top_k = options.top_k if options and options.top_k is not None else 5
        qw = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored = []
        for d in self.indexes[name].values():
            if not self._match(d.get("metadata") or {}, getattr(options, "filter", None)):
                continue
            dw = set(re.findall(r"[a-z0-9]+", d["text"].lower()))
            score = min(1.0, len(qw & dw) / max(min(len(qw), 4), 1))
            scored.append((score, d))
        scored.sort(key=lambda x: -x[0])
        docs = [
            QueryResultDocumentInfo(id=d["id"], text=d["text"], metadata=d.get("metadata"), score=s)
            for s, d in scored[:top_k]
            if s > 0
        ]
        return SearchResult(docs=docs, query=query, index_name=name)

    async def get_docs(self, name, options=None):
        self.calls.append(f"get_docs:{name}")
        ids = list(getattr(options, "doc_ids", None) or [])
        return [
            QueryResultDocumentInfo(id=d["id"], text=d["text"], metadata=d.get("metadata"))
            for i in ids
            if (d := self.indexes[name].get(i))
        ]


def message(payload: dict, *, stop_reason: str = "end_turn", cache_read: int = 0) -> Message:
    return Message(
        id="msg_01Fake",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=[TextBlock(type="text", text=json.dumps(payload))],
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=512, output_tokens=96, cache_read_input_tokens=cache_read),
    )


class FakeMessages:
    def __init__(self, replies: list[Message]) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []

    async def create(self, **kw):
        self.requests.append(kw)
        if not self.replies:
            raise AssertionError("unexpected Claude call")
        return self.replies.pop(0)


class FakeAnthropic:
    def __init__(self, replies: list[Message]) -> None:
        self.messages = FakeMessages(replies)


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key="test-key", moss_project_id="p", moss_project_key="k", ask_min_score=0.35)


@pytest.fixture
def moss() -> FakeMoss:
    return FakeMoss()


@pytest.fixture
async def store(moss: FakeMoss, settings: Settings) -> RuleStore:
    s = RuleStore(moss, index=settings.moss_index, model_id=settings.moss_model)
    await s.build(DOCS)
    await s.load()
    await s.status()
    return s


@pytest.fixture
def client_factory(store: RuleStore, settings: Settings):
    """A TestClient over `create_app` with the pipeline injected; `replies` are the Claude Messages, in order."""

    def make(replies: list[Message] | None = None) -> tuple[TestClient, FakeAnthropic]:
        fake = FakeAnthropic(replies or [])
        pipeline = AskPipeline(store, ClaudeJSON(fake, model="claude-opus-5-5", effort="low"), settings)
        app = create_app(settings, pipeline=pipeline)
        client = TestClient(app)
        client.__enter__()  # run the lifespan so app.state.pipeline is set
        return client, fake

    return make
