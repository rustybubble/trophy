import asyncio
import json

from conftest import CTX, FakeLLM
from trophy.streams import CTL_ENGINE

from referee.service import PENDING_FAILED, PENDING_SPEECH, AskRequest, Referee


def _ctl(r):
    async def read():
        out = []
        for _id, f in await r.xrange(CTL_ENGINE):
            out.append(json.loads(f[b"json"]))
        return out

    return read


async def test_check_question_runs_in_the_engine_and_is_phrased(settings, redis_client, engine):
    llm = FakeLLM({"phrase": [{"speech": "Out by 3.2 centimetres. Clear.", "answer": "Out by 3.2 cm (97%)"}]})
    ref = Referee(settings, r=redis_client, llm=llm)
    out = await ref.ask(AskRequest("g1", "Trophy, was that out?", by_cam_id="cam1", context=CTX))
    assert out["kind"] == "check" and out["check"] == "in_out" and out["verdict"] == "out" and out["p"] == 0.97
    assert out["speech"] == "Out by 3.2 centimetres. Clear." and out["phrased_by"] == "claude"
    assert out["citations"][0]["rule_id"] == "check:in_out" and "margin -3.2 cm" in out["citations"][0]["quote"]
    assert out["route_source"] == "regex" and out["route_ms"] == 0.0 and out["check_ms"] > 0
    sent = engine.seen[0]
    assert sent["cmd"] == "run_check" and sent["by_cam_id"] == "cam1"
    assert sent["args"]["check"] == "in_out" and sent["args"]["args"]["t_game_s"] == 61.42
    assert sent["args"]["reply_to"].startswith("reply:") and sent["args"]["question"].startswith("Trophy")
    assert (settings.data_dir / "referee" / "asks.jsonl").read_text().count("\n") == 1


async def test_score_and_explain_need_no_engine(settings, redis_client):
    llm = FakeLLM({"explain": [{"speech": "It landed 3.2 centimetres long.", "answer": "a"}]})
    ref = Referee(settings, r=redis_client, llm=llm)
    s = await ref.ask(AskRequest("g1", "what's the score", context=CTX))
    assert s["kind"] == "score" and s["speech"].startswith("7 to 5") and s["phrased_by"] == "template"
    e = await ref.ask(AskRequest("g1", "why was that out", context=CTX))
    assert e["kind"] == "explain" and e["call_id"] == "01CALL" and e["phrased_by"] == "claude"
    none = await ref.ask(AskRequest("g1", "why was that out", context={}))
    assert none["speech"] == "I haven't made a call yet."


async def test_rules_question_is_grounded_in_the_pack_and_house_rules(settings, redis_client):
    llm = FakeLLM(
        {
            "route": [{"intent": "rule", "check": "", "hint": "", "reason": ""}],
            "rules": [
                {
                    "found": True,
                    "answer": "Yes: a serve that clips the net and lands in is a let (house_rule_1).",
                    "speech": "Yes. A serve that clips the net and lands in is replayed as a let.",
                    "citations": [
                        {"rule_id": "house_rule_1", "quote": "A serve that clips the net and lands in is a let."},
                        {"rule_id": "made_up", "quote": "nope"},
                    ],
                }
            ],
        }
    )
    ref = Referee(settings, r=redis_client, llm=llm)
    out = await ref.ask(AskRequest("g1", "is a net serve a let?", context=CTX))
    assert out["kind"] == "rule" and out["found"] is True
    assert [c["rule_id"] for c in out["citations"]] == ["house_rule_1"]
    prompt = llm.calls[1]["user"]
    assert "[edge_ball]" in prompt and "[house_rule_1]" in prompt and "points to win 11" in prompt


async def test_missing_rule_pack_is_an_error_not_an_answer(settings, redis_client):
    llm = FakeLLM({"route": [{"intent": "rule", "check": "", "hint": "", "reason": ""}]})
    ref = Referee(settings, r=redis_client, llm=llm)
    out = await ref.ask(AskRequest("g1", "what about lets", sport="pickleball", context={}))
    assert out["error"] == "no_rule_pack" and "pickleball rule pack" in out["speech"]


async def test_no_matching_check_says_give_me_a_moment_then_answers_late(settings, redis_client, engine):
    engine.droid_result = {
        "check": "ball_speed",
        "verdict": "fast",
        "p": 0.9,
        "evidence": {"speed_max_mps": 18.2},
        "calibrated": True,
        "latency_ms": 2.0,
    }
    llm = FakeLLM(
        {
            "route": [{"intent": "check", "check": "new", "hint": "ball_speed(rally) -> max m/s", "reason": ""}],
            "phrase": [{"speech": "Fastest ball 66 kilometres an hour.", "answer": "66 km/h"}],
        }
    )
    ref = Referee(settings, r=redis_client, llm=llm)
    out = await ref.ask(AskRequest("g1", "how hard was that hit", by_cam_id="judge1", context=CTX))
    assert out["kind"] == "pending" and out["speech"] == PENDING_SPEECH and out["reply_to"].startswith("reply:")
    assert out["hint"] == "ball_speed(rally) -> max m/s"
    await asyncio.wait_for(ref.pending[out["reply_to"]], 3)
    late = ref.late_answers[0]
    assert late["check"] == "ball_speed" and late["speech"] == "Fastest ball 66 kilometres an hour."
    cmds = await _ctl(redis_client)()
    req = [c for c in cmds if c["cmd"] == "request_check"][0]
    assert (
        req["args"]["check_hint"] == "ball_speed(rally) -> max m/s"
        and req["args"]["question"] == "how hard was that hit"
    )
    logged = [c for c in cmds if c["cmd"] == "ask_logged"][0]
    assert (
        logged["args"]["answer"] == "66 km/h"
        and logged["args"]["kind"] == "check"
        and logged["args"]["check"] == "ball_speed"
    )
    assert logged["by_cam_id"] == "judge1" and logged["args"]["speech"].startswith("Fastest")


async def test_session_without_a_catalog_check_goes_to_the_droid_too(settings, redis_client, engine):
    llm = FakeLLM()
    ref = Referee(settings, r=redis_client, llm=llm)
    out = await ref.ask(AskRequest("g1", "did it touch the net", context=CTX))  # fake engine has no net_touch
    assert out["kind"] == "pending" and out["check"] == "net_touch" and out["hint"] == "net_touch(window)"
    await asyncio.wait_for(ref.pending[out["reply_to"]], 3)
    assert ref.late_answers[0]["speech"] == PENDING_FAILED and ref.late_answers[0]["kind"] == "none"


async def test_engine_timeout_is_reported(settings, redis_client):
    ref = Referee(settings, r=redis_client, llm=FakeLLM())  # nobody consumes ctl:engine
    out = await ref.ask(AskRequest("g1", "was that out", context=CTX))
    assert out["kind"] == "check" and out["error"] == "timeout" and "didn't come back" in out["speech"]
    assert 400 < out["check_ms"] < 1500


async def test_uncalibrated_result_is_said(settings, redis_client, engine):
    ref = Referee(settings, r=redis_client, llm=None)
    out = await ref.ask(AskRequest("g1", "was that serve legal", context=CTX))
    assert out["calibrated"] is False and "uncalibrated" in out["speech"] and out["phrased_by"] == "template"
    assert "uncalibrated" in out["citations"][0]["quote"]
