"""Commentary lines are grounded in the moment's facts or replaced by templates."""

from __future__ import annotations

import json

import httpx2
from trophy_engine.commentary import ClaudeCommentator, TemplateCommentator, commentary_rows, facts_for, grounded

MOMENT = {
    "moment_id": "m1",
    "game_id": "g_synth001",
    "kind": "point",
    "t_game_s": 12.0,
    "label": "Point Team A",
    "team_id": "A",
    "score_after": "7–5",
    "rally_no": 12,
    "tags": ["point", "shots:9"],
    "reasons": ["long rally (9 shots)", "scored from event features only (no crowd audio)"],
}
NAMES = {"A": "Team A", "B": "Team B"}


def test_grounding_rejects_numbers_and_names_not_in_the_facts() -> None:
    f = facts_for(MOMENT, NAMES)
    assert grounded("Point Team A, 7–5 after a 9-shot rally.", f)
    assert not grounded("Point Team A, 8–5.", f)
    assert not grounded("Team B folds under pressure.", f)
    assert not grounded("", f)


def test_template_rows_are_marked_template() -> None:
    rows = commentary_rows(MOMENT, NAMES, TemplateCommentator(), now_ms=1.0)
    assert [r["voice"] for r in rows] == ["pbp", "colour"]
    assert all(r["source"] == "template" and r["validated"] for r in rows)
    assert rows[0]["text"] == "Point, Team A. 7–5."


def test_claude_lines_pass_or_fall_back_per_line() -> None:
    body = {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {"pbp": "Team A takes the point, 7–5.", "colour": "Team B looked tired after 14 shots."}
                ),
            }
        ],
    }
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx2.Response(200, json=body)

    w = ClaudeCommentator(api_key="k", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    rows = commentary_rows(MOMENT, NAMES, w, now_ms=2.0)
    assert seen[0]["output_config"]["format"]["type"] == "json_schema" and "temperature" not in seen[0]
    pbp, colour = rows
    assert pbp["source"] == "claude" and pbp["validated"] and pbp["text"].startswith("Team A takes")
    assert colour["source"] == "template" and not colour["validated"]  # 14 is not a fact, Team B is not the team
    from trophy.contracts import Commentary

    for r in rows:
        Commentary.model_validate(r)


def test_writer_failure_is_template_not_an_exception() -> None:
    def handler(req):
        return httpx2.Response(500, json={"type": "error"})

    w = ClaudeCommentator(api_key="k", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    rows = commentary_rows(MOMENT, NAMES, w, now_ms=2.0)
    assert all(r["source"] == "template" for r in rows)
