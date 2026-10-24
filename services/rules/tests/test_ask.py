from conftest import message

from rules import ask as A
from rules.models import RuleHit

GOOD = {
    "found": True,
    "answer": "The toss must rise at least 20 cm after leaving the palm, near vertically and without spin [ttl:2.6.2].",
    "speech": "The toss must rise at least twenty centimetres from the palm, near vertically and without spin.",
    "citations": [
        {"rule_id": "ttl:2.6.2", "quote": "rises at least 20 cm after leaving the palm of the free hand"},
        {"rule_id": "ttl:9.9.9", "quote": "not a retrieved clause"},
    ],
}


def test_ask_answers_from_retrieved_clauses_with_verified_citations(client_factory, moss):
    client, fake = client_factory([message(GOOD)])
    r = client.post(
        "/ask", json={"question": "How high must the serve toss rise from the palm?", "sport": "paddle_pong"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] is True and "[ttl:2.6.2]" in body["answer"]
    assert "ttl:" not in body["speech"] and "[" not in body["speech"] and "twenty" in body["speech"]
    assert [c["rule_id"] for c in body["citations"]] == ["ttl:2.6.2"]  # the un-retrieved id was dropped
    c = body["citations"][0]
    assert c["title"] == "2.6 The Service" and c["url"].startswith("https://example.test")
    assert c["quote"] == "rises at least 20 cm after leaving the palm of the free hand"
    assert set(body) >= {"answer", "speech", "citations", "found", "moss_ms", "llm_ms", "latency_ms", "model"}
    assert (
        body["latency_ms"] >= body["moss_ms"]
        and body["model"] == "claude-opus-5-5"
        and "ttl:2.6.2" in body["retrieved"]
    )
    # the Claude request: cached system block first, structured output at effort low, no temperature / tool_choice
    req = fake.messages.requests[0]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"} and req["system"][0]["text"] == A.SYSTEM
    assert req["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": A.ASK_SCHEMA}}
    assert "temperature" not in req and "tool_choice" not in req
    assert "[ttl:2.6.2]" in req["messages"][0]["content"] and "20 cm" in req["messages"][0]["content"]
    assert any(c.startswith("query:trophy-rules-v1:alpha=0.8") for c in moss.calls)


def test_unverifiable_quote_is_dropped_not_replaced(client_factory):
    reply = {
        "found": True,
        "answer": "A point is scored if the free hand touches the playing surface [ttl:2.10.5].",
        "speech": "A point is scored if the free hand touches the playing surface.",
        "citations": [{"rule_id": "ttl:2.10.5", "quote": "this sentence was never in the clause at all"}],
    }
    client, _ = client_factory([message(reply)])
    r = client.post("/ask", json={"question": "free hand touches the playing surface point", "sport": "paddle_pong"})
    body = r.json()
    assert body["found"] is False and body["citations"] == []  # zero surviving citations -> not found, no rewrite
    assert body["answer"] == "I couldn't find that rule in the paddle pong laws." and body["speech"] == body["answer"]


def test_quote_over_25_words_is_dropped():
    hit = RuleHit(
        rule_id="x:1", sport="s", number="1", title="t", url="u", source="src", text=" ".join(["w"] * 40), score=1
    )
    cites, dropped = A.verify_citations([{"rule_id": "x:1", "quote": " ".join(["w"] * 26)}], [hit])
    assert cites == [] and dropped[0]["why"].startswith("quote not verbatim")
    cites, _ = A.verify_citations([{"rule_id": "x:1", "quote": " ".join(["w"] * 25)}], [hit])
    assert len(cites) == 1 and len(cites[0].quote.split()) == 25


def test_verify_quote_is_whitespace_and_case_tolerant_but_verbatim():
    clause = "The server shall then project   the ball\nnear vertically upwards, without imparting spin."
    assert (
        A.verify_quote("project the ball near vertically upwards", clause) == "project the ball near vertically upwards"
    )
    assert (
        A.verify_quote("Project the ball NEAR vertically upwards,", clause)
        == "project the ball near vertically upwards"
    )
    assert A.verify_quote("project the ball sideways", clause) is None
    assert A.verify_quote("", clause) is None


def test_weak_retrieval_says_not_found_without_calling_claude(client_factory):
    client, fake = client_factory([])  # any Claude call would raise
    r = client.post("/ask", json={"question": "zebra kayak", "sport": "paddle_pong"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is False and body["citations"] == [] and body["llm_ms"] == 0
    assert body["answer"] == "I couldn't find that rule in the paddle pong laws."
    assert fake.messages.requests == []


def test_sport_filter_never_returns_another_sports_clause(client_factory, store):
    client, fake = client_factory([])
    # "kitchen" only exists in the kitchen_ball clause; asked under paddle_pong, Moss returns nothing -> not found
    r = client.post("/ask", json={"question": "kitchen volley metres", "sport": "paddle_pong"})
    assert r.json()["found"] is False and r.json()["retrieved"] == [] and fake.messages.requests == []


def test_claude_found_false_is_not_found(client_factory):
    client, _ = client_factory([message({"found": False, "answer": "", "speech": "", "citations": []})])
    r = client.post("/ask", json={"question": "open palm free hand ball resting", "sport": "paddle_pong"})
    assert r.json()["found"] is False and r.json()["citations"] == []


def test_question_length_is_bounded(client_factory):
    client, _ = client_factory([])
    assert client.post("/ask", json={"question": "x" * 301, "sport": "paddle_pong"}).status_code == 422


def test_clause_number_in_question_adds_a_keyword_pass(client_factory, moss):
    client, _ = client_factory([message({"found": False, "answer": "", "speech": "", "citations": []})])
    client.post(
        "/ask", json={"question": "what does law 2.6.2 say about the ball and the palm", "sport": "paddle_pong"}
    )
    alphas = [c.split("alpha=")[1][:3] for c in moss.calls if c.startswith("query:")]  # moss stores alpha as float32
    assert alphas == ["0.8", "0.3"]


def test_strip_ids():
    assert A.strip_ids("See [ttl:2.6.2] and ittf:2.10.1.4 here.") == "See and here."


def test_healthz_reports_the_loaded_index(client_factory):
    client, _ = client_factory()
    body = client.get("/healthz").json()
    assert body["ok"] is True and body["index"] == "trophy-rules-v1" and body["doc_count"] == 6
    assert body["ask_model"] == "claude-opus-5-5" and body["loaded_ms"] is not None
    assert "test-key" not in client.get("/healthz").text
