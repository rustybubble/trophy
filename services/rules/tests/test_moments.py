def test_moments_index_then_search(client_factory, moss):
    client, _ = client_factory()
    moments = [
        {
            "moment_id": "m1",
            "game_id": "g1",
            "kind": "point",
            "t_game_s": 12.5,
            "label": "Long rally won by Blue",
            "tags": ["rally"],
        },
        {
            "moment_id": "m2",
            "game_id": "g1",
            "kind": "serve_fault",
            "t_game_s": 40.0,
            "label": "Serve toss too low",
            "team_id": "red",
        },
        {
            "moment_id": "m3",
            "game_id": "g1",
            "kind": "edge",
            "t_game_s": 61.2,
            "label": "Edge ball called for Blue",
            "score_after": "7-5",
        },
        {"moment_id": "other", "game_id": "g2", "kind": "point", "t_game_s": 1.0, "label": "wrong game"},
    ]
    r = client.post("/moments/index", json={"game_id": "g1", "moments": moments})
    assert r.status_code == 200 and r.json() == {"game_id": "g1", "upserted": 3}
    assert "create_index:moments-g1:moss-minilm" in moss.calls
    assert moss.indexes["moments-g1"]["m2"]["metadata"]["team_id"] == "red"

    r = client.post("/search_moments", json={"game_id": "g1", "q": "serve toss low"})
    body = r.json()
    assert body["mode"] == "semantic" and body["hits"][0]["moment_id"] == "m2" and body["hits"][0]["score"] > 0

    # a second batch upserts (index exists) and the loaded snapshot is refreshed before the next query
    r = client.post(
        "/moments/index", json={"game_id": "g1", "moments": [{**moments[1], "label": "Serve toss low and angled"}]}
    )
    assert r.json()["upserted"] == 1 and any(c.startswith("add_docs:moments-g1:upsert=True") for c in moss.calls)
    r = client.post("/search_moments", json={"game_id": "g1", "q": "angled"})
    assert r.json()["hits"][0]["moment_id"] == "m2"
    assert moss.calls.count("load_index:moments-g1") == 2
