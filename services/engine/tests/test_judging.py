"""The judging demo (D-42..D-44): feeds and viewers, who is at fault, and the automatic challenge verdict."""

from __future__ import annotations

from test_engine import GAME, floor, new_engine, point_call


def rally_point(eng):
    eng.feed(point_call(1.0, "A"))
    eng.feed(point_call(1.4, "B"))
    return eng.feed(floor(2.0, "A"))[-1]


def test_point_names_the_team_at_fault_and_says_it() -> None:
    eng, _ = new_engine()
    pt = rally_point(eng)
    assert pt["team_id"] == "A" and pt["at_fault"] == {"team_id": "B", "name": "Team B"}
    assert pt["speech"].endswith("Team B's fault.") and pt["source"] == "sensed"


def test_feed_schedule_resets_the_game_and_writes_feeds_and_viewers() -> None:
    eng, st = new_engine()
    rally_point(eng)
    teams = [{"team_id": "A", "name": "Mu"}, {"team_id": "B", "name": "Vedansh"}]
    eng.handle_ctl(
        {"cmd": "feed_schedule", "game_id": GAME, "args": {"sport": "table_tennis", "teams": teams, "reset": True}}
    )
    assert {r["team_id"]: r["points"] for r in st.rows("score")} == {"A": 0, "B": 0}
    g = eng.games[GAME]
    assert g.game["status"] == "live" and g.team("A")["name"] == "Mu" and g.game["t0_ms"] == 0
    feed = {"cam_id": "c_side01", "label": "Side", "status": "playing", "wall0_ms": 5000.0, "video_url": "/x.mp4"}
    eng.handle_ctl({"cmd": "feed_schedule", "game_id": GAME, "args": {"feeds": [feed]}})
    assert st.rows("feed")[0]["label"] == "Side" and st.rows("feed")[0]["game_id"] == GAME
    eng.handle_ctl(
        {
            "cmd": "viewer_status",
            "game_id": GAME,
            "by_cam_id": "c_phone1",
            "args": {"cam_id": "c_side01", "drift_ms": 12.34},
        }
    )
    v = st.rows("viewer")[0]
    assert v["viewer_id"] == "c_phone1" and v["cam_id"] == "c_side01" and v["drift_ms"] == 12.3


def test_challenge_without_a_voter_is_decided_by_geometry_with_an_explanation() -> None:
    eng, st = new_engine()
    pt = rally_point(eng)
    eng.handle_ctl({"cmd": "challenge", "game_id": GAME, "by_cam_id": "c_phone1", "args": {"call_id": pt["id"]}})
    assert eng.drain() == 1
    ch = st.rows("challenge")[0]
    assert ch["status"] == "resolved" and ch["result"] == "upheld" and ch["decided_by"] == "auto"
    assert ch["explanation"].startswith("The call stands") and "uncalibrated" in ch["explanation"]
    assert st.tables["call"][pt["id"]]["explanation"] == ch["explanation"]
    spoken = [c for c in st.rows("call") if c["rule_id"] == "challenge_verdict"]
    assert spoken and spoken[-1]["speech"] == ch["explanation"]


def test_challenge_with_a_voter_overturns_and_replays_the_point() -> None:
    class Rec:
        def __init__(self):
            self.reqs = []

        def submit(self, req):
            self.reqs.append(req)

    dec = Rec()
    eng, st = new_engine(decider=dec)
    pt = rally_point(eng)
    eng.handle_ctl({"cmd": "challenge", "game_id": GAME, "args": {"call_id": pt["id"]}})
    req = next(r for r in dec.reqs if r.get("challenge_id"))
    votes = [{"backend": "claude", "rationale": "The ball clearly lands on the table edge", "probs": {}}]
    eng.challenge_verdict(req, {"p_final": {req["original_option"]: 0.2}, "votes": votes})
    eng.drain()
    ch = st.rows("challenge")[0]
    assert ch["result"] == "overturned" and "Claude: The ball clearly lands" in ch["explanation"]
    rep = [c for c in st.rows("call") if c.get("supersedes") == pt["id"]]
    assert rep and rep[0]["outcome"] == "let" and "points" not in rep[0]
    assert {r["team_id"]: r["points"] for r in st.rows("score")} == {"A": 0, "B": 0}


def test_inconclusive_challenge_is_left_to_the_players() -> None:
    eng, st = new_engine()
    pt = rally_point(eng)
    g = eng.games[GAME]
    ch_cmd = {"cmd": "challenge", "game_id": GAME, "args": {"call_id": pt["id"]}}
    eng.handle_ctl(ch_cmd)
    eng.inbox.get_nowait()  # drop the geometry verdict; resolve as a voter would
    ch = next(iter(g.challenges.values()))
    eng.inbox.put(eng._verdict_cmd(g, ch, g.calls[0] if g.calls[0]["id"] == pt["id"] else pt, {pt["outcome"]: 0.5}, []))
    eng.drain()
    assert st.rows("challenge")[0]["result"] == "players_decide"
    assert st.tables["call"][pt["id"]]["status"] == "players_decide"
