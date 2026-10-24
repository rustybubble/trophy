import asyncio

from conftest import RULES, message

from rules.indexing import build, docs_from_items


def _index(store):
    return asyncio.run(build(store, docs_from_items(RULES)))


def test_ask_answers_from_retrieved_clauses_with_citations(client_factory, store, moss):
    counts = _index(store)
    assert counts == {"table_tennis": 3} and "create_index:rules-table_tennis:moss-minilm" in moss.calls
    reply = message(
        {
            "found": True,
            "answer": "The toss must rise at least 16 cm from the open palm, near vertically and without spin (2.6.2).",
            "speech": "The toss must rise at least sixteen centimetres from the open palm, near vertically and "
            "without spin.",
            "citations": [
                {"rule_id": "2.6.2", "quote": "rises at least 16cm after leaving the palm of the free hand"},
                {"rule_id": "9.9.9", "quote": "not a retrieved clause"},
            ],
        }
    )
    client, fake = client_factory([reply])
    r = client.post(
        "/ask", json={"question": "How high must the serve toss rise from the palm?", "sport": "table_tennis"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] is True and "(2.6.2)" in body["answer"]
    assert "2.6.2" not in body["speech"] and "sixteen" in body["speech"]
    assert [c["rule_id"] for c in body["citations"]] == ["2.6.2"]  # the un-retrieved id was dropped
    c = body["citations"][0]
    assert c["title"] == "2.6 The Service" and c["url"].startswith("https://www.ittf.com")
    assert c["quote"] == "rises at least 16cm after leaving the palm of the free hand"
    assert body["moss_ms"] >= 0 and body["latency_ms"] >= body["moss_ms"]
    # the Claude request was structured output, only the retrieved clauses, no temperature / tool_choice
    req = fake.messages.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in req and "tool_choice" not in req
    assert "[2.6.2]" in req["messages"][0]["content"] and "16cm" in req["messages"][0]["content"]


def test_quote_longer_than_25_words_or_not_in_clause_is_replaced(client_factory, store):
    _index(store)
    reply = message(
        {
            "found": True,
            "answer": "A point is scored when the opponent fails to make a correct return (2.10.1.3).",
            "speech": "A point is scored when the opponent fails to make a correct return.",
            "citations": [{"rule_id": "2.10.1.3", "quote": "this sentence was never in the clause at all"}],
        }
    )
    client, _ = client_factory([reply])
    r = client.post(
        "/ask", json={"question": "when does a player score a point correct return", "sport": "table_tennis"}
    )
    q = r.json()["citations"][0]["quote"]
    assert q.startswith("Unless the rally is a let") and len(q.rstrip("…").split()) <= 25


def test_weak_retrieval_says_not_found_without_calling_claude(client_factory, store):
    _index(store)
    client, fake = client_factory([])  # any Claude call would raise
    r = client.post("/ask", json={"question": "zebra kayak", "sport": "table_tennis"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "I couldn't find that rule." and body["citations"] == [] and body["found"] is False
    assert fake.messages.requests == []


def test_claude_found_false_is_not_found(client_factory, store):
    _index(store)
    reply = message({"found": False, "answer": "", "speech": "", "citations": []})
    client, _ = client_factory([reply])
    r = client.post("/ask", json={"question": "open palm free hand ball resting", "sport": "table_tennis"})
    assert r.json()["answer"] == "I couldn't find that rule." and r.json()["found"] is False


def test_rule_ref_returns_closest_clause(client_factory, store):
    _index(store)
    client, _ = client_factory()
    r = client.get("/rule_ref", params={"sport": "table_tennis", "q": "ball resting freely on the open palm"})
    assert r.status_code == 200
    body = r.json()
    assert body["rule_id"] == "2.6.1" and body["score"] > 0 and body["url"]
    assert len(body["quote"].rstrip("…").split()) <= 25
    assert client.get("/rule_ref", params={"sport": "table_tennis", "q": "zebra"}).status_code == 404


def test_healthz_reports_key_presence_only(client_factory):
    client, _ = client_factory()
    body = client.get("/healthz").json()
    assert body["ok"] is True and body["keys"] == {"anthropic": True, "moss": True, "apify": False}
    assert "test-key" not in client.get("/healthz").text
