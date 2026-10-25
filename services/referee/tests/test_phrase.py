from conftest import CTX, EDGE_BETA, IN_OUT_OUT, SERVE_UNCAL, FakeLLM
from trophy.contracts import CheckResult

from referee.phrase import facts_for, numbers_ok, phrase_check, phrase_explain, score_line, template_check


def test_facts_are_in_spoken_units():
    f = facts_for(CheckResult.model_validate(IN_OUT_OUT), "was that out")
    assert f["margin_cm"] == "-3.2" and f["sigma_cm"] == "1.1" and f["confidence_percent"] == "97"
    assert f["line"] == "end B"


def test_numbers_guard():
    f = facts_for(CheckResult.model_validate(IN_OUT_OUT), "q")
    assert numbers_ok("Out by 3.2 centimetres, clear.", f)
    assert numbers_ok("Out, 97 percent.", f)
    assert not numbers_ok("Out by 5 centimetres.", f)


async def test_claude_line_is_used_when_its_numbers_match():
    llm = FakeLLM(
        {"phrase": [{"speech": "Out by 3.2 centimetres past the end line. Clear.", "answer": "Out (3.2 cm)"}]}
    )
    ph = await phrase_check(llm, "was that out", CheckResult.model_validate(IN_OUT_OUT))
    assert ph.by == "claude" and ph.speech.startswith("Out by 3.2")
    assert '"margin_cm":"-3.2"' in llm.calls[0]["user"]


async def test_invented_number_falls_back_to_the_template():
    llm = FakeLLM({"phrase": [{"speech": "Out by 9 centimetres.", "answer": "x"}]})
    ph = await phrase_check(llm, "was that out", CheckResult.model_validate(IN_OUT_OUT))
    assert ph.by == "template" and "3.2 centimetres" in ph.speech and "Clear" in ph.speech


def test_templates_say_confidence_and_calibration():
    t = template_check(CheckResult.model_validate(EDGE_BETA), None)
    assert t.speech == "Top edge, good ball. 71 percent."
    t = template_check(CheckResult.model_validate(SERVE_UNCAL), None)
    assert t.speech.startswith("Fault, toss too low: toss 12.1 centimetres, 12 degrees from vertical.")
    assert "uncalibrated" in t.speech


async def test_error_results_never_reach_claude():
    llm = FakeLLM()
    r = CheckResult(check="in_out", calibrated=False, error="no_data", latency_ms=1)
    ph = await phrase_check(llm, "q", r)
    assert ph.by == "template" and "didn't track" in ph.speech and llm.calls == []


async def test_explain_uses_the_call_facts():
    llm = FakeLLM(
        {"explain": [{"speech": "I called it out: it landed 3.2 centimetres past the end line.", "answer": "a"}]}
    )
    ph = await phrase_explain(llm, "why was that out", CTX["last_calls"][0])
    assert ph.by == "claude" and "97" in llm.calls[0]["user"]


def test_score_line():
    assert score_line(CTX).speech == "7 to 5, Team A leads. Team A to serve."
    tied = {**CTX, "scores": [{"team_id": "A", "points": 10}, {"team_id": "B", "points": 10}]}
    assert score_line(tied).speech == "10 all. Team A to serve."
    assert score_line({}).speech == "I don't have a score yet."
