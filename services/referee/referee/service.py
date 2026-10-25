"""The referee: question in, spoken answer out, transcript logged (agent-3-droid-realtime.md §5).

question -> route -> [score | explain last call | rule pack Q&A | session check in the engine] -> Claude phrases
         -> {answer, speech, evidence}  (the gateway logs it with ask_logged; phones speak `speech`)
no matching check -> "give me a moment" + request_check -> wait for the Droid (<= 95 s) -> phrase -> ask_logged
                     (the ask row reaches the phones through Spacetime; the server speaker says it too)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trophy.contracts import CheckResult
from trophy.streams import CTL_ENGINE, CTL_STREAM_MAXLEN, make_ctl

from .catalog import CHECKS
from .checks import CheckBackend, CheckOutcome, RedisCheckBackend
from .config import Settings
from .llm import JSONCompleter
from .phrase import Phrased, fmt_num, phrase_check, phrase_explain, score_line, template_error
from .router import Route, route
from .rules_qa import answer_rules, clauses_from_pack, load_pack
from .tts import CartesiaTTS

log = logging.getLogger("referee")

PENDING_SPEECH = "Give me a moment. I don't have a check for that yet, so I'm writing one now."
PENDING_FAILED = "I couldn't write a check for that in time. Players decide."
NONE_SPEECH = "I can check the ball, explain a call, give the score, or answer a rules question."


@dataclass
class AskRequest:
    game_id: str
    question: str
    sport: str = "table_tennis"
    by_cam_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


def evidence_quote(result: CheckResult) -> str:
    bits: list[str] = []
    for k, v in (result.evidence or {}).items():
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int | float):
            if k.endswith("_m"):
                bits.append(f"{k[:-2]} {fmt_num(100 * v)} cm")
            elif k.endswith("_mps"):
                bits.append(f"{k[:-4]} {fmt_num(v)} m/s")
            else:
                bits.append(f"{k} {fmt_num(v, 2)}")
        elif isinstance(v, str):
            bits.append(f"{k} {v}")
    if result.p is not None:
        bits.append(f"p {fmt_num(result.p, 2)}")
    if not result.calibrated:
        bits.append("uncalibrated")
    return ", ".join(bits)[:200]


class Referee:
    def __init__(
        self,
        settings: Settings,
        *,
        r: Any = None,
        llm: JSONCompleter | None = None,
        checks: CheckBackend | None = None,
        tts: CartesiaTTS | None = None,
    ) -> None:
        self.st = settings
        self.r = r
        self.llm = llm
        self.checks: CheckBackend | None = checks or (RedisCheckBackend(r) if r is not None else None)
        self.tts = tts
        self.pending: dict[str, asyncio.Task[None]] = {}
        self.late_answers: list[dict[str, Any]] = []  # what the pending path produced (tests, /healthz)
        self.log_path: Path = settings.data_dir / "referee" / "asks.jsonl"

    # ---------------------------------------------------------------- the pipeline

    async def ask(self, req: AskRequest) -> dict[str, Any]:
        t0 = time.perf_counter()
        ctx = req.context or {}
        rt, route_ms = await route(req.question, ctx, self.llm)
        out: dict[str, Any] = {
            "question": req.question,
            "kind": rt.intent,
            "route_source": rt.source,
            "route_ms": round(route_ms, 1),
            "check_ms": 0.0,
            "phrase_ms": 0.0,
            "citations": [],
        }
        if rt.intent == "score":
            self._put(out, score_line(ctx))
        elif rt.intent == "explain":
            calls = ctx.get("last_calls") or []
            if not calls:
                self._put(out, Phrased("I haven't made a call yet.", "I haven't made a call yet.", "template"))
            else:
                self._put(out, await phrase_explain(self.llm, req.question, calls[0]))
                out["call_id"] = calls[0].get("id")
        elif rt.intent == "rule":
            await self._rules(req, out)
        elif rt.intent == "check":
            await self._check(req, rt, out)
        else:
            self._put(out, Phrased(NONE_SPEECH, NONE_SPEECH, "template"))
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._log({"game_id": req.game_id, "by_cam_id": req.by_cam_id, **out})
        return out

    async def _rules(self, req: AskRequest, out: dict[str, Any]) -> None:
        try:
            pack = load_pack(self.st.sports_dir, req.sport)
        except FileNotFoundError:
            s = f"I don't have the {req.sport.replace('_', ' ')} rule pack loaded, so I can't answer that."
            self._put(out, Phrased(s, s, "template"))
            out["error"] = "no_rule_pack"
            return
        if self.llm is None:
            s = "The rulebook model isn't available right now."
            self._put(out, Phrased(s, s, "template"))
            out["error"] = "no_llm"
            return
        clauses = clauses_from_pack(pack, (req.context or {}).get("house_rules"))
        ans = await answer_rules(self.llm, req.question, req.sport, clauses)
        out.update(
            answer=ans.answer,
            speech=ans.speech,
            citations=ans.citations,
            phrased_by="claude" if ans.found else "template",
            phrase_ms=round(ans.ms, 1),
            found=ans.found,
        )

    async def _check(self, req: AskRequest, rt: Route, out: dict[str, Any]) -> None:
        if self.checks is None:
            s = "The engine isn't connected, so I can't check that."
            self._put(out, Phrased(s, s, "template"))
            out["error"] = "no_engine"
            return
        if rt.check is None:
            await self._pending(req, rt, out)
            return
        oc = await self.checks.run(
            req.game_id,
            rt.check,
            rt.args,
            question=req.question,
            by_cam_id=req.by_cam_id,
            timeout_s=self.st.check_timeout_s,
        )
        out["check"] = rt.check
        out["inputs"] = rt.args
        out["check_ms"] = round(oc.latency_ms, 1)
        if oc.error == "no_such_check":
            await self._pending(req, rt, out)  # the session lacks it: the Droid writes it
            return
        if oc.result is None:
            res = CheckResult(check=rt.check, calibrated=False, error=oc.error or "timeout", latency_ms=oc.latency_ms)
            self._put(out, template_error(res))
            out["error"] = res.error
            return
        self._fill_check(out, oc.result, await phrase_check(self.llm, req.question, oc.result))

    def _fill_check(self, out: dict[str, Any], result: CheckResult, ph: Phrased) -> None:
        self._put(out, ph)
        out.update(
            kind="check",
            check=result.check,
            verdict=result.verdict,
            p=result.p,
            calibrated=result.calibrated,
            tier=result.tier,
            evidence=result.evidence or {},
            inputs=result.inputs or out.get("inputs") or {},
            error=result.error,
        )
        spec = CHECKS.get(result.check)
        out["citations"] = [
            {
                "rule_id": f"check:{result.check}",
                "title": f"{result.check}({', '.join(spec.args) if spec else ''})",
                "url": "",
                "quote": evidence_quote(result),
            }
        ]

    async def _pending(self, req: AskRequest, rt: Route, out: dict[str, Any]) -> None:
        assert self.checks is not None
        hint = rt.hint or (f"{rt.check}({', '.join(CHECKS[rt.check].args)})" if rt.check in CHECKS else None)
        reply_to = await self.checks.request(
            req.game_id, req.question, hint=hint, args=rt.args, by_cam_id=req.by_cam_id
        )
        out.update(kind="pending", reply_to=reply_to, hint=hint)
        self._put(out, Phrased(PENDING_SPEECH, PENDING_SPEECH, "template"))
        task = asyncio.create_task(self._finish_pending(req, out.get("check"), reply_to))
        self.pending[reply_to] = task
        task.add_done_callback(lambda _t: self.pending.pop(reply_to, None))

    async def _finish_pending(self, req: AskRequest, check: str | None, reply_to: str) -> None:
        assert self.checks is not None
        oc: CheckOutcome = await self.checks.wait(reply_to, self.st.pending_timeout_s)
        out: dict[str, Any] = {"question": req.question, "kind": "check", "citations": [], "reply_to": reply_to}
        if oc.result is None or oc.result.error:
            s = PENDING_FAILED
            self._put(out, Phrased(s, s, "template"))
            out["error"] = oc.error or (oc.result.error if oc.result else "timeout")
            out["kind"] = "none"
        else:
            self._fill_check(out, oc.result, await phrase_check(self.llm, req.question, oc.result))
        out["latency_ms"] = round(oc.latency_ms, 1)
        self.late_answers.append(out)
        self._log({"game_id": req.game_id, "by_cam_id": req.by_cam_id, "late": True, **out})
        await self.publish_ask_logged(req, out)
        if self.tts is not None:
            try:
                await self.tts.speak(out["speech"], voice="ref", interrupt=True)
            except Exception as e:  # noqa: BLE001 - the row still reaches the phones
                log.warning("late answer not spoken: %s", e)

    # ---------------------------------------------------------------- side effects

    async def publish_ask_logged(self, req: AskRequest, out: dict[str, Any]) -> None:
        """Late answers go to the ask table the same way the gateway logs immediate ones (engine posts the row)."""
        if self.r is None:
            return
        args: dict[str, Any] = {
            "question": req.question,
            "answer": out.get("answer", ""),
            "speech": out.get("speech", ""),
            "citations": out.get("citations", []),
            "latency_ms": float(out.get("latency_ms", 0.0)),
            "kind": out.get("kind", "none"),
        }
        for k in ("check", "p", "calibrated"):
            if out.get(k) is not None:
                args[k] = out[k]
        if req.by_cam_id:
            args["by_cam_id"] = req.by_cam_id
        ctl = make_ctl("ask_logged", req.game_id, args, by_cam_id=req.by_cam_id)
        await self.r.xadd(
            CTL_ENGINE, {"json": ctl.model_dump_json(by_alias=True)}, maxlen=CTL_STREAM_MAXLEN, approximate=True
        )

    @staticmethod
    def _put(out: dict[str, Any], ph: Phrased) -> None:
        out["answer"] = ph.answer
        out["speech"] = ph.speech
        out["phrased_by"] = ph.by
        out["phrase_ms"] = round(ph.ms, 1)

    def _log(self, row: dict[str, Any]) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf8") as f:
                f.write(json.dumps({"t_ms": int(time.time() * 1000), **row}, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("transcript log not written: %s", e)
