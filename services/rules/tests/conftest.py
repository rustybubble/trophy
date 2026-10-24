"""Fakes at the SDK boundary: a Moss client with the real `moss` result types and an Anthropic client
whose `messages.create` returns a real `anthropic.types.Message` (recorded shape). No network, no keys."""

from __future__ import annotations

import json
import re

import pytest
from anthropic.types import Message, TextBlock, Usage
from fastapi.testclient import TestClient
from moss import MossError, QueryResultDocumentInfo, SearchResult

from rules import app as app_mod
from rules.config import Settings
from rules.llm import ClaudeJSON
from rules.search import MossStore

RULES = [
    {
        "sport": "table_tennis",
        "rule_id": "2.6.2",
        "title": "2.6 The Service",
        "text": "The server shall then project the ball near vertically upwards, without imparting spin, so that it "
        "rises at least 16cm after leaving the palm of the free hand and then falls without touching anything before "
        "being struck.",
        "url": "https://www.ittf.com/handbook/",
    },
    {
        "sport": "table_tennis",
        "rule_id": "2.6.1",
        "title": "2.6 The Service",
        "text": "Service shall start with the ball resting freely on the open palm of the server's stationary free "
        "hand.",
        "url": "https://www.ittf.com/handbook/",
    },
    {
        "sport": "table_tennis",
        "rule_id": "2.10.1.3",
        "title": "2.10 A Point",
        "text": "Unless the rally is a let, a player shall score a point if an opponent fails to make a correct "
        "return.",
        "url": "https://www.ittf.com/handbook/",
    },
]


class FakeMoss:
    """Keyword overlap stands in for embeddings; scores are deterministic for the tests."""

    def __init__(self) -> None:
        self.indexes: dict[str, dict[str, dict]] = {}
        self.loaded: set[str] = set()
        self.calls: list[str] = []

    async def get_index(self, name):
        self.calls.append(f"get_index:{name}")
        if name not in self.indexes:
            e = MossError(f"Index '{name}' not found")
            e.code = "NOT_FOUND"
            raise e
        return {"name": name, "doc_count": len(self.indexes[name])}

    async def create_index(self, name, docs, model_id=None, **_):
        self.calls.append(f"create_index:{name}:{model_id}")
        self.indexes[name] = {d["id"]: d for d in docs}

    async def add_docs(self, name, docs, options=None, **_):
        self.calls.append(f"add_docs:{name}:upsert={getattr(options, 'upsert', None)}")
        self.indexes[name].update({d["id"]: d for d in docs})

    async def load_index(self, name, **_):
        self.calls.append(f"load_index:{name}")
        if name not in self.indexes:
            e = MossError(f"Index '{name}' not found")
            e.code = "NOT_FOUND"
            raise e
        self.loaded.add(name)
        return name

    async def query(self, name, query, options=None):
        assert name in self.loaded, "query before load_index"
        top_k = options.top_k if options and options.top_k is not None else 5
        qw = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored = []
        for d in self.indexes[name].values():
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


def message(payload: dict, *, stop_reason: str = "end_turn") -> Message:
    return Message(
        id="msg_01Fake",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=[TextBlock(type="text", text=json.dumps(payload))],
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=512, output_tokens=96),
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
def moss() -> FakeMoss:
    return FakeMoss()


@pytest.fixture
def store(moss: FakeMoss) -> MossStore:
    return MossStore(moss, model_id="moss-minilm")


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key="test-key", moss_project_id="p", moss_project_key="k", min_score=0.35)


@pytest.fixture
def client_factory(store: MossStore, settings: Settings):
    """A TestClient with the fakes injected; `replies` are the Claude Messages to return in order."""

    def make(replies: list[Message] | None = None) -> tuple[TestClient, FakeAnthropic]:
        fake = FakeAnthropic(replies or [])
        app_mod.app.dependency_overrides[app_mod.get_settings] = lambda: settings
        app_mod.app.dependency_overrides[app_mod.get_store] = lambda: store
        app_mod.app.dependency_overrides[app_mod.get_llm] = lambda: ClaudeJSON(fake, model="claude-opus-5-5")
        return TestClient(app_mod.app), fake

    yield make
    app_mod.app.dependency_overrides.clear()
