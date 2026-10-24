"""P0 spikes with real keys (brief §3 task 2): Moss index + load + 20 queries + filter; Claude parse + cache hit."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import pytest

from rules import ask as A
from rules.clients import anthropic_client, moss_client
from rules.config import ROOT
from rules.llm import ClaudeJSON
from rules.models import RuleDoc
from rules.search import RuleStore

pytestmark = pytest.mark.live
FIXTURE = ROOT / "evals" / "fixtures" / "rulebooks" / "synthetic_laws.txt"
SPIKE_INDEX = "trophy-rules-spike"
OUT = ROOT / "data" / "local" / "spikes"


def _synthetic_docs() -> list[RuleDoc]:
    """The synthetic laws split with the actor's splitter, indexed under two sports to test the filter."""
    import sys

    sys.path.insert(0, str(ROOT / "actors" / "rulebook-scraper" / "src"))
    from rulebook_scraper.splitter import rule_items

    text = FIXTURE.read_text("utf8")
    docs = []
    for sport, slug in (("paddle_pong", "ttl"), ("paddle_pong_b", "ttlb")):
        items = rule_items(text, sport=sport, slug=slug, url="https://example.test/laws.pdf", source="Trophy Test Laws",
                           license_note="synthetic", fetched_at="2026-10-24T00:00:00+00:00",
                           skip_patterns=[r"^\s*National byelaw"])  # fmt: skip
        for it in items:
            docs.append(RuleDoc.model_validate(it))
    return docs


QUESTIONS = [
    "how high must the serve toss rise", "what happens when the serve touches the net", "how many points wins a game",
    "can the free hand touch the table", "how often does the serve change", "how high is the net",
    "what is the playing surface", "is the edge of the table in play", "what if the ball hits the net post",
    "how heavy is the ball", "what is a let", "when is the receiver not ready", "does the ball rest on the palm",
    "what is the bounce height of the table", "what if the ball is hidden from the receiver",
    "what colour is the racket", "when does the serve rotate at deuce", "what about law 2.6.2",
    "is the vertical side of the table in", "can you strike the ball twice",
]  # fmt: skip


async def test_moss_spike(live_settings):
    """create (20+ docs, two sports) -> load (cold) -> 20 queries -> filter isolation -> get_docs; deletes the index."""
    client = moss_client(live_settings)
    store = RuleStore(client, index=SPIKE_INDEX, model_id=live_settings.moss_model)
    docs = _synthetic_docs()
    try:
        if await store.exists():
            await client.delete_index(SPIKE_INDEX)
        t0 = time.perf_counter()
        await store.build(docs)
        build_ms = (time.perf_counter() - t0) * 1000
        cold_ms = await store.load()
        info = await store.status()
        times = []
        for q in QUESTIONS:
            hits, ms = await store.search("paddle_pong", q, 5)
            times.append(ms)
            assert hits, q
            assert all(h.sport == "paddle_pong" and h.rule_id.startswith("ttl:") for h in hits), q  # the filter holds
            assert all(0.0 <= h.score <= 1.0 for h in hits) and hits[0].title, q
        hits_b, _ = await store.search("paddle_pong_b", "how high must the serve toss rise", 5)
        assert hits_b and all(h.rule_id.startswith("ttlb:") for h in hits_b)
        exact = await store.get_by_ids(["ttl:2.6.2"], sport="paddle_pong")
        assert len(exact) == 1 and exact[0].number == "2.6.2" and "20 cm" in exact[0].text
        toss, _ = await store.search("paddle_pong", "how high must the serve toss rise", 5)
        report = {
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "index": SPIKE_INDEX,
            "docs": len(docs),
            "doc_count": info["doc_count"],
            "model": info["model"],
            "build_ms": round(build_ms),
            "cold_load_ms": round(cold_ms),
            "query_ms": {"p50": round(statistics.median(times), 1), "max": round(max(times), 1), "n": len(times)},
            "toss_question_top3": [(h.rule_id, round(h.score, 3)) for h in toss[:3]],
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "moss-spike.json").write_text(json.dumps(report, indent=1))
        print("\nMOSS SPIKE", json.dumps(report))
        assert toss[0].rule_id in ("ttl:2.6.2", "ttl:2.6.1", "ttl:2.6.3")
    finally:
        try:
            await client.delete_index(SPIKE_INDEX)
        except Exception as e:  # noqa: BLE001
            print("spike index not deleted:", type(e).__name__)


async def test_claude_spike(live_settings):
    """One structured-output call at effort low on five synthetic clauses, then a second call for the cache hit."""
    llm = ClaudeJSON(anthropic_client(live_settings), model=live_settings.ask_model, effort=live_settings.ask_effort)
    docs = [d for d in _synthetic_docs() if d.sport == "paddle_pong"][:8]
    from rules.search import hit_from

    class _D:
        def __init__(self, d):
            self.id, self.text, self.metadata, self.score = d.rule_id, f"{d.number} {d.title}. {d.text}", {
                "sport": d.sport, "rule_id": d.rule_id, "number": d.number, "title": d.title, "url": d.url,
                "source": d.source}, 0.9  # fmt: skip

    hits = [hit_from(_D(d)) for d in docs if d.number.startswith("2.6")]
    user = A.user_message("How high must the ball be tossed on a serve?", "paddle_pong", hits)
    out1, ms1, u1 = await llm.complete(system=A.SYSTEM, user=user, schema=A.ASK_SCHEMA, label="spike-1")
    out2, ms2, u2 = await llm.complete(system=A.SYSTEM, user=user, schema=A.ASK_SCHEMA, label="spike-2")
    cites, dropped = A.verify_citations(out1.get("citations", []), hits)
    report = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": llm.model,
        "effort": llm.effort,
        "call1_ms": round(ms1),
        "call2_ms": round(ms2),
        "usage1": u1,
        "usage2": u2,
        "found": out1.get("found"),
        "answer": out1.get("answer"),
        "speech": out1.get("speech"),
        "citations_verified": [c.model_dump() for c in cites],
        "citations_dropped": dropped,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "claude-spike.json").write_text(json.dumps(report, indent=1))
    print("\nCLAUDE SPIKE", json.dumps(report))
    assert out1["found"] is True and cites and "20" in (out1["answer"] + out1["speech"])
    assert Path(OUT / "claude-spike.json").exists()
