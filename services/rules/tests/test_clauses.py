def test_clauses_markdown_lists_ids_titles_and_links(client_factory):
    client, _ = client_factory()
    r = client.get("/clauses", params={"sport": "paddle_pong", "q": "serve toss palm", "k": 3})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    md = r.text
    assert md.startswith("# Official clauses: paddle pong") and "## [ttl:2.6.2] 2.6 The Service" in md
    assert "Source: TTL <https://example.test/trophy-test-laws.pdf>" in md and "kb:7.A" not in md
    assert md.count("## [") <= 3


def test_clauses_empty(client_factory):
    client, _ = client_factory()
    assert "_No clause matched._" in client.get("/clauses", params={"sport": "paddle_pong", "q": "zebra"}).text
