from conftest import message

from rules import grounding

STATS = {"points": 11, "serve_faults": 3, "longest_rally": 14, "serve_points_pct": "60%", "edge_balls": 1}


def test_grounding_accepts_stated_numbers_and_rejects_others():
    facts = grounding.build_facts(STATS, side="Blue", sides=["Blue", "Red"])
    assert grounding.check("Blue, you had 3 serve faults in 11 points; tighten the toss.", facts)["ok"]
    assert grounding.check("Sixty percent of your serve points is solid, Blue.", facts)["ok"]
    bad = grounding.check("You lost 7 points on serve faults, Blue.", facts)
    assert not bad["ok"] and bad["violations"][0] == {"kind": "absent_number", "detail": "7"}
    assert any(v["kind"] == "unknown_name" for v in grounding.check("Marcus should serve more.", facts)["violations"])
    assert any(
        v["kind"] == "invented_attribute" for v in grounding.check("He had 3 serve faults.", facts)["violations"]
    )
    assert any(
        v["kind"] == "invented_fact"
        for v in grounding.check("Your knees look tired after 11 points.", facts)["violations"]
    )


def test_coach_replaces_ungrounded_tip_with_template(client_factory):
    reply = message(
        {
            "tips": [
                {
                    "text": "Blue, 3 serve faults in 11 points is a lot: slow the toss down.",
                    "facts": ["serve_faults", "points"],
                },
                {"text": "Your longest rally went 14 shots, so your consistency is there.", "facts": ["longest_rally"]},
                {"text": "You dropped 7 points to the net cord, which cost you the set.", "facts": ["points"]},
            ]
        }
    )
    client, fake = client_factory([reply])
    r = client.post(
        "/coach",
        json={"game_id": "g1", "sport": "table_tennis", "side": "Blue", "stats": STATS, "sides": ["Blue", "Red"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["validated"] is False
    sources = [t["source"] for t in body["tips"]]
    assert sources == ["claude", "claude", "template"]
    assert body["tips"][2]["facts"] == ["points"] and "11" in body["tips"][2]["text"]
    assert body["tips"][2]["violations"][0]["kind"] == "absent_number"
    assert body["tips"][0]["facts"] == ["serve_faults", "points"]
    req = fake.messages.requests[0]
    assert (
        req["output_config"]["format"]["type"] == "json_schema" and "serve_faults: 3" in req["messages"][0]["content"]
    )


def test_coach_all_grounded_is_validated(client_factory):
    reply = message(
        {
            "tips": [
                {"text": "Blue, your 3 serve faults are the first thing to fix.", "facts": ["serve_faults"]},
                {"text": "A 14 shot longest rally shows you can stay in points.", "facts": ["longest_rally"]},
            ]
        }
    )
    client, _ = client_factory([reply])
    body = client.post("/coach", json={"game_id": "g1", "sport": "table_tennis", "side": "Blue", "stats": STATS}).json()
    assert body["validated"] is True and all(t["source"] == "claude" for t in body["tips"])
