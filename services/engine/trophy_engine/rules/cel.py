"""CEL conditions and expressions from rules.yaml, compiled once per pack.

Functions available inside expressions: ``opponent(side)``, ``phi(x)`` (the standard normal CDF) and ``has_side(s)``.
Activation: ``ev`` (the current event), ``rally`` (RallyState.view()), ``game`` (score/serve facts) and ``params``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import celpy
import celpy.celtypes as ct


class CelError(Exception):
    pass


def _opponent(side: Any) -> ct.StringType:
    s = str(side)
    return ct.StringType("B" if s == "A" else "A")


def _phi(x: Any) -> ct.DoubleType:
    return ct.DoubleType(0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0))))


def _has_side(s: Any) -> ct.BoolType:
    return ct.BoolType(str(s) in ("A", "B"))


FUNCTIONS = {"opponent": _opponent, "phi": _phi, "has_side": _has_side}

_ENV = celpy.Environment()


@dataclass
class CompiledRule:
    rule: dict[str, Any]
    when: celpy.Runner
    p: celpy.Runner | None
    team: celpy.Runner | None

    @property
    def id(self) -> str:
        return str(self.rule["id"])


@dataclass
class RuleSet:
    rules: list[CompiledRule] = field(default_factory=list)
    version: str = "1"

    def by_id(self, rule_id: str) -> CompiledRule | None:
        return next((r for r in self.rules if r.id == rule_id), None)


def _program(expr: str, where: str) -> celpy.Runner:
    try:
        ast = _ENV.compile(expr)
    except Exception as e:  # celpy raises CELParseError / CELSyntaxError
        raise CelError(f"{where}: cannot compile {expr!r}: {e}") from e
    return _ENV.program(ast, functions=FUNCTIONS)


def compile_rules(pack: dict[str, Any]) -> RuleSet:
    rs = RuleSet(version=str(pack.get("version", "1")))
    for r in pack.get("rules", []):
        rid = r.get("id", "?")
        rs.rules.append(
            CompiledRule(
                rule=r,
                when=_program(str(r["when"]), f"rule {rid} when"),
                p=_program(str(r["p"]), f"rule {rid} p") if r.get("p") else None,
                team=_program(str(r["team"]), f"rule {rid} team") if r.get("team") else None,
            )
        )
    return rs


def _to_cel(value: Any) -> Any:
    return celpy.json_to_cel(value)


def evaluate(runner: celpy.Runner, activation: dict[str, Any]) -> Any:
    """Evaluate a compiled expression; CEL errors (missing keys, type errors) become ``CelError``."""
    try:
        out = runner.evaluate({k: _to_cel(v) for k, v in activation.items()})
    except Exception as e:  # noqa: BLE001 - celpy raises CELEvalError and friends
        raise CelError(str(e)) from e
    if isinstance(out, ct.BoolType):
        return bool(out)
    if isinstance(out, ct.DoubleType | ct.IntType | ct.UintType):
        return float(out)
    if isinstance(out, ct.StringType):
        return str(out)
    return out


def when_true(cr: CompiledRule, activation: dict[str, Any]) -> bool:
    """A condition that errors (e.g. a missing payload key) is false, so one bad rule never stops the engine."""
    try:
        return bool(evaluate(cr.when, activation))
    except CelError:
        return False
