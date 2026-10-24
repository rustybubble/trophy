"""`trophy-rules eval`: run evals/ask/<sport>.jsonl through the real /ask pipeline and summarise (brief §2.5)."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ROOT
from .models import AskOut
from .pipeline import AskPipeline

EVALS = ROOT / "evals" / "ask"
OUT_DIR = ROOT / "data" / "local" / "ask_eval"


def load_cases(sport: str, path: Path | None = None) -> list[dict[str, Any]]:
    p = path or EVALS / f"{sport}.jsonl"
    return [json.loads(line) for line in p.read_text("utf8").splitlines() if line.strip()]


def pct(xs: list[float], q: float) -> float | None:
    """Linear-interpolation percentile (p50 of [800, 900] is 850)."""
    if not xs:
        return None
    xs = sorted(xs)
    pos = q * (len(xs) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo), 1)


def summarize(cases: list[dict[str, Any]], outs: list[AskOut]) -> dict[str, Any]:
    """hit@k (expected id among the retrieved ids), citation precision, found accuracy, latency percentiles."""
    in_book = [(c, o) for c, o in zip(cases, outs, strict=True) if c.get("expected_rule_ids")]
    hits = [any(e in o.retrieved for e in c["expected_rule_ids"]) for c, o in in_book]
    cites = [(cit.rule_id in c["expected_rule_ids"]) for c, o in in_book for cit in o.citations]
    found_ok = [o.found == bool(c.get("expected_rule_ids")) for c, o in zip(cases, outs, strict=True)]
    answered = [o for o in outs if o.llm_ms > 0]
    return {
        "n": len(cases),
        "n_in_rulebook": len(in_book),
        "hit_at_k": round(sum(hits) / len(hits), 3) if hits else None,
        "citation_precision": round(sum(cites) / len(cites), 3) if cites else None,
        "citations_total": len(cites),
        "found_accuracy": round(sum(found_ok) / len(found_ok), 3) if found_ok else None,
        "moss_ms": {"p50": pct([o.moss_ms for o in outs], 0.5), "p95": pct([o.moss_ms for o in outs], 0.95)},
        "llm_ms": {"p50": pct([o.llm_ms for o in answered], 0.5), "p95": pct([o.llm_ms for o in answered], 0.95)},
        "latency_ms": {"p50": pct([o.latency_ms for o in outs], 0.5), "p95": pct([o.latency_ms for o in outs], 0.95)},
        "latency_ms_answered": {
            "p50": pct([o.latency_ms for o in answered], 0.5),
            "p95": pct([o.latency_ms for o in answered], 0.95),
        },
        "top_score_mean": round(statistics.fmean([o.top_score for o in outs if o.top_score is not None]), 3)
        if any(o.top_score is not None for o in outs)
        else None,
    }


def table(cases: list[dict[str, Any]], outs: list[AskOut]) -> str:
    rows = [
        "| # | question | expected | retrieved (top score) | found | cited | moss | llm | total |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, (c, o) in enumerate(zip(cases, outs, strict=True), start=1):
        exp = ", ".join(c.get("expected_rule_ids") or []) or "(none)"
        ret = ", ".join(o.retrieved[:3]) + (f" ({o.top_score:.2f})" if o.top_score is not None else "")
        cited = ", ".join(x.rule_id for x in o.citations) or "-"
        ms = f"{o.moss_ms:.0f} | {o.llm_ms:.0f} | {o.latency_ms:.0f}"
        rows.append(f"| {i} | {c['question']} | {exp} | {ret} | {o.found} | {cited} | {ms} |")
    return "\n".join(rows)


async def run(
    pipeline: AskPipeline, sport: str, *, path: Path | None = None, out_dir: Path = OUT_DIR
) -> dict[str, Any]:
    cases = load_cases(sport, path)
    outs = [await pipeline.ask(c["question"], sport) for c in cases]
    summary = summarize(cases, outs)
    report = {
        "sport": sport,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": pipeline.llm.model,
        "effort": pipeline.llm.effort,
        "min_score": pipeline.s.ask_min_score,
        "top_k": pipeline.s.ask_top_k,
        "index": pipeline.store.index,
        "summary": summary,
        "cases": [
            {
                "question": c["question"],
                "expected_rule_ids": c.get("expected_rule_ids", []),
                "notes": c.get("notes", ""),
                "result": o.model_dump(),
            }
            for c, o in zip(cases, outs, strict=True)
        ],  # fmt: skip
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{datetime.now(UTC).strftime('%Y-%m-%dT%H%M%SZ')}-{sport}.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), "utf8")
    report["path"] = str(out)
    return report
