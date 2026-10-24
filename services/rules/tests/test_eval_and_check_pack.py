import json
from pathlib import Path

from conftest import DOCS, FakeAnthropic, message

from rules import check_pack as CP
from rules import evalrun
from rules.llm import ClaudeJSON
from rules.models import AskOut, Citation
from rules.pipeline import AskPipeline


def _out(retrieved, cited, found, moss=10.0, llm=0.0, total=12.0):
    return AskOut(answer="a", speech="a", citations=[Citation(rule_id=c, title="t", url="u", quote="q") for c in cited],
                  found=found, moss_ms=moss, llm_ms=llm, latency_ms=total, model="m",
                  top_score=0.9 if retrieved else None, retrieved=retrieved)  # fmt: skip


def test_summarize_metrics():
    cases = [
        {"question": "q1", "expected_rule_ids": ["a:1"]},
        {"question": "q2", "expected_rule_ids": ["a:2", "a:3"]},
        {"question": "q3", "expected_rule_ids": []},
    ]
    outs = [
        _out(["a:1", "a:9"], ["a:1"], True, llm=800, total=850),
        _out(["a:9", "a:8"], ["a:9"], True, llm=900, total=950),  # miss, wrong citation
        _out([], [], False),
    ]
    s = evalrun.summarize(cases, outs)
    assert s["hit_at_k"] == 0.5 and s["citation_precision"] == 0.5 and s["found_accuracy"] == 1.0
    assert s["llm_ms"]["p50"] == 850 and s["latency_ms"]["p95"] == 940 and s["moss_ms"]["p50"] == 10
    assert "| q2 |" in evalrun.table(cases, outs)


async def test_eval_run_writes_a_report(store, settings, tmp_path):
    cases = tmp_path / "paddle_pong.jsonl"
    cases.write_text(
        json.dumps({"question": "How high must the serve toss rise from the palm?", "expected_rule_ids": ["ttl:2.6.2"]})
        + "\n"
        + json.dumps({"question": "zebra kayak", "expected_rule_ids": []})
        + "\n"
    )
    reply = message({"found": True, "answer": "At least 20 cm [ttl:2.6.2].", "speech": "At least twenty centimetres.",
                     "citations": [{"rule_id": "ttl:2.6.2", "quote": "rises at least 20 cm"}]})  # fmt: skip
    pipeline = AskPipeline(store, ClaudeJSON(FakeAnthropic([reply])), settings)
    report = await evalrun.run(pipeline, "paddle_pong", path=cases, out_dir=tmp_path / "out")
    assert report["summary"]["hit_at_k"] == 1.0 and report["summary"]["found_accuracy"] == 1.0
    assert Path(report["path"]).exists() and report["cases"][0]["result"]["citations"][0]["rule_id"] == "ttl:2.6.2"


async def test_check_pack_resolves_refs_and_lists_unresolved(store, settings, tmp_path):
    pack = tmp_path / "rules.yaml"
    pack.write_text(
        "sport: paddle_pong\nrules:\n"
        "  - {id: toss_low, name: Toss too low, rule_ref: 'TTL 2.6.2', text: 'Fault: toss too low'}\n"
        "  - {id: by_text, name: Surface touch, rule_ref: 'TTL 9.9.9', "
        "text: 'touches the playing surface during the rally'}\n"
        "  - {id: nothing, name: Zebra, rule_ref: 'TTL 8.8.8', text: 'zebra kayak'}\n"
        "  - {id: no_ref, name: No ref}\n"
    )
    rows = await CP.check(store, CP.load_pack(pack), min_score=settings.ask_min_score)
    by = {r["rule"]: r for r in rows}
    assert by["toss_low"]["status"] == "exact" and by["toss_low"]["clause"] == "ttl:2.6.2"
    assert by["by_text"]["status"] == "search" and by["by_text"]["clause"] == "ttl:2.10.5"
    assert by["nothing"]["status"] == "unresolved" and by["no_ref"]["status"] == "no rule_ref"
    assert "| toss_low | TTL 2.6.2 | ttl:2.6.2 |" in CP.table(rows)
    assert len(DOCS) == 6
