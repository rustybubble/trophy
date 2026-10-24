import pytest

from rules.rule_ref import parse_rule_ref


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("ITTF 2.6.2", "ittf:2.6.2"),
        ("ittf 2.10.1.4", "ittf:2.10.1.4"),
        ("ittf:2.6.2", "ittf:2.6.2"),
        ("USA Pickleball 11.A", "usap:11.A"),
        ("USAP 7.A", "usap:7.A"),
        ("FIBA 12.1.1", "fiba:12.1.1"),
        ("TTE 2.1.2", "ittf:2.1.2"),
        ("just words", None),
        ("", None),
    ],
)
def test_parse_rule_ref(ref, expected):
    assert parse_rule_ref(ref) == expected


def test_exact_resolution_by_rule_ref(client_factory, moss):
    client, _ = client_factory()
    r = client.post("/rule_ref", json={"sport": "paddle_pong", "rule_ref": "TTL 2.6.2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rule_id"] == "ttl:2.6.2" and body["how"] == "exact" and body["score"] == 1.0
    assert body["title"] == "2.6 The Service" and body["url"] and len(body["quote"].rstrip("…").split()) <= 25
    assert any(c.startswith("get_docs:") for c in moss.calls)


def test_exact_resolution_respects_the_sport(client_factory):
    client, _ = client_factory()
    assert client.post("/rule_ref", json={"sport": "kitchen_ball", "rule_id": "ttl:2.6.2"}).status_code == 404


def test_search_resolution_by_text(client_factory, moss):
    client, _ = client_factory()
    r = client.post(
        "/rule_ref",
        json={"sport": "paddle_pong", "rule_ref": "TTL 9.9.9", "text": "ball resting freely on the open palm"},
    )
    assert r.status_code == 200 and r.json()["rule_id"] == "ttl:2.6.1" and r.json()["how"] == "search"
    assert any(c.endswith("alpha=0.5") for c in moss.calls)


def test_404_and_422(client_factory):
    client, _ = client_factory()
    assert client.post("/rule_ref", json={"sport": "paddle_pong", "text": "zebra"}).status_code == 404
    assert client.post("/rule_ref", json={"sport": "paddle_pong"}).status_code == 422
