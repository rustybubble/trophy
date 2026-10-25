"""Load a sport module directory and enforce what its ``events.py`` may do.

The Droid may edit three files in ``sports/<sport>/``. The runner enforces *which files* change; this loader enforces
*what the code can reach*: an AST walk refuses any import outside ``ALLOWED_IMPORTS`` and any of the escape hatches
(``exec``, ``eval``, ``__import__``, ``open``, dunder attribute access, ``globals``/``getattr`` tricks). It is a guard
against careless or runaway code, not a security boundary: the sandbox (a throwaway git worktree, no network beyond the
Factory API, a 90 s timeout and human approval) is the boundary.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .api import ModuleState, Observation

# typing, collections, dataclasses and enum are out (review blocker 2: e.g. typing.get_type_hints evaluates a string
# annotation, which the AST walk can't see); operator too (attrgetter("__class__") reaches dunders by string).
ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "__future__",
        "math",
        "statistics",
        "itertools",
        "functools",
        "bisect",
        "heapq",
        "trophy_engine.sportmod.api",
    }
)

API_MODULES = ("trophy_engine.sportmod.api",)


def _api_names() -> dict[str, frozenset[str]]:
    import importlib

    return {m: frozenset(importlib.import_module(m).__all__) for m in API_MODULES}


API_NAMES = _api_names()  # names module code may import from the engine's API modules
FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"exec", "eval", "compile", "__import__", "open", "input", "globals", "locals", "vars"}
    | {"getattr", "setattr", "delattr", "breakpoint", "exit", "quit"}
)
MODULE_FILES = ("config.yaml", "events.py", "rules.yaml")
# An annotated sport (D-44) has no perception: hand-marked events arrive as trophy.event.v1 with source "annotated",
# so its module is config.yaml + rules.yaml (+ RULES.md, the rulebook summary the Droid reads) and no events.py.
ANNOTATED_FILES = ("config.yaml", "rules.yaml")

CONTRACTS = Path(__file__).resolve().parents[4] / "packages" / "contracts"


class LoadError(Exception):
    """The module is malformed or violates the allowlist. ``errors`` lists every finding."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class SportModule:
    sport: str
    path: Path
    config: dict[str, Any]
    rules: dict[str, Any]
    events: Callable[[Iterable[Observation], ModuleState], Iterable[dict[str, Any]]]
    # True when the module has no events.py: its events are hand-annotated (D-44), never computed from layer 1
    annotated: bool = False

    def state(self, game_id: str, *, calib_trusted: bool = True) -> ModuleState:
        return ModuleState(
            game_id=game_id,
            sport=self.sport,
            config=self.config,
            field_lines=(self.rules.get("field") or {}).get("lines") or {},
            calib_trusted=calib_trusted,
        )


@lru_cache(maxsize=1)
def _validators() -> dict[str, Draft202012Validator]:
    schemas = {
        p.name.removesuffix(".schema.json"): json.loads(p.read_text("utf8")) for p in CONTRACTS.glob("*.schema.json")
    }
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    fc = Draft202012Validator.FORMAT_CHECKER
    return {
        "config": Draft202012Validator(schemas["sportmodule"], registry=registry, format_checker=fc),
        "rules": Draft202012Validator(schemas["rulepack"], registry=registry, format_checker=fc),
        "event": Draft202012Validator(schemas["event"], registry=registry, format_checker=fc),
        "labels": Draft202012Validator({"$ref": f"{schemas['scene']['$id']}#/$defs/SampleLabels"}, registry=registry),
        "scene": Draft202012Validator(schemas["scene"], registry=registry, format_checker=fc),
    }


def validate_against(kind: str, obj: Any) -> list[str]:
    errs = _validators()[kind].iter_errors(obj)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs]


def validate_event(ev: dict[str, Any]) -> list[str]:
    """Contract check for one event (schema + payload model)."""
    errs = validate_against("event", ev)
    if errs:
        return errs
    from trophy.events import PAYLOAD_MODELS  # py-trophy: the typed payload models

    model = PAYLOAD_MODELS.get(ev.get("type", ""))
    if model is not None:
        try:
            model.model_validate(ev.get("payload") or {})
        except Exception as e:  # pydantic ValidationError
            return [f"payload: {e}"]
    return []


# ---------------------------------------------------------------- AST allowlist


def check_events_source(src: str, filename: str = "events.py") -> list[str]:
    """Return allowlist violations in ``events.py`` source (empty when clean)."""
    errors: list[str] = []
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError as e:
        return [f"{filename}:{e.lineno}: syntax error: {e.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    errors.append(f"{filename}:{node.lineno}: import {a.name!r} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not node.level and mod in API_NAMES:
                bad = [a.name for a in node.names if a.name == "*" or a.name not in API_NAMES[mod]]
                if bad:
                    errors.append(f"{filename}:{node.lineno}: {', '.join(bad)} not in {mod}.__all__")
            if node.level or mod not in ALLOWED_IMPORTS:
                errors.append(f"{filename}:{node.lineno}: from {mod!r} import is not allowed")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in FORBIDDEN_CALLS:
                errors.append(f"{filename}:{node.lineno}: call to {name}() is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            errors.append(f"{filename}:{node.lineno}: dunder attribute {node.attr!r} is not allowed")
        elif isinstance(node, ast.Name) and node.id in {"__builtins__", "__loader__", "__spec__"}:
            errors.append(f"{filename}:{node.lineno}: {node.id} is not allowed")
    errors += module_reach_errors(tree, filename, ALLOWED_IMPORTS)
    has_events = any(isinstance(n, ast.FunctionDef) and n.name == "events" for n in tree.body)
    if not has_events:
        errors.append(f"{filename}: no top-level `def events(observations, state)`")
    return errors


def module_reach_errors(tree: ast.AST, filename: str, allowed: frozenset[str]) -> list[str]:
    """What the import allowlist can't see by name alone (review blocker 2): allowed stdlib modules hold other modules
    (``statistics.sys``), and the engine's API modules import hashlib, dataclasses and typing. So: API modules only
    through ``from ... import`` of their ``__all__``; never a module object reached through an allowed module, by
    attribute or by from-import; and an imported module name may only be used as ``name.attr`` (no aliasing it away
    from that check)."""
    import contextlib
    import importlib
    import types

    errors: list[str] = []
    bound: dict[str, types.ModuleType] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in API_MODULES or a.name.startswith("trophy_engine"):
                    errors.append(f"{filename}:{node.lineno}: use `from {a.name} import ...` (names in its __all__)")
                elif a.name in allowed:
                    with contextlib.suppress(ImportError):
                        bound[(a.asname or a.name).split(".")[0]] = importlib.import_module(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module in allowed:
            if node.module in API_MODULES or node.module == "__future__":
                continue
            mod = importlib.import_module(node.module)
            for a in node.names:
                if isinstance(getattr(mod, a.name, None), types.ModuleType):
                    errors.append(f"{filename}:{node.lineno}: {node.module}.{a.name} is a module")
    parents = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in bound and isinstance(node.ctx, ast.Load):
            parent = parents.get(id(node))
            if not (isinstance(parent, ast.Attribute) and parent.value is node):
                errors.append(f"{filename}:{node.lineno}: module {node.id!r} may only be used as {node.id}.<name>")
            elif isinstance(getattr(bound[node.id], parent.attr, None), types.ModuleType):
                errors.append(f"{filename}:{node.lineno}: {node.id}.{parent.attr} is a module")
    return errors


def _import_events(path: Path, sport: str) -> Callable[..., Any]:
    name = f"trophy_sport_{sport}_{abs(hash(str(path))) & 0xFFFF:x}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LoadError([f"{path}: cannot import"])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise LoadError([f"{path}: import failed: {type(e).__name__}: {e}"]) from e
    fn = getattr(mod, "events", None)
    if not callable(fn):
        raise LoadError([f"{path}: `events` is not callable"])
    return fn


def load_module(path: str | Path, *, import_code: bool = True, rules_optional: bool = False) -> SportModule:
    """Load and validate ``sports/<sport>/``. Raises ``LoadError`` with every problem found.

    Without ``events.py`` the module is *annotated* (D-44): config.yaml only has to name the sport (no detector runs,
    so the detector parameters the schema requires are not needed) and ``events`` refuses to run. With
    ``rules_optional`` a missing rules.yaml loads as ``{}`` (a sport whose interpreter the Droid has not written yet).
    """
    p = Path(path)
    annotated = not (p / "events.py").is_file()
    errors: list[str] = []
    for f in ANNOTATED_FILES if annotated else MODULE_FILES:
        if f == "rules.yaml" and rules_optional:
            continue
        if not (p / f).is_file():
            errors.append(f"{p / f}: missing")
    if errors:
        raise LoadError(errors)
    try:
        config = yaml.safe_load((p / "config.yaml").read_text("utf8")) or {}
    except yaml.YAMLError as e:
        raise LoadError([f"config.yaml: {e}"]) from e
    rules: Any = {}
    if (p / "rules.yaml").is_file():
        try:
            rules = yaml.safe_load((p / "rules.yaml").read_text("utf8")) or {}
        except yaml.YAMLError as e:
            raise LoadError([f"rules.yaml: {e}"]) from e
        errors += [f"rules.yaml: {e}" for e in validate_against("rules", rules)]
    if annotated:
        if not isinstance(config, dict) or not isinstance(config.get("sport"), str):
            errors.append("config.yaml: must be a mapping with `sport`")
    else:
        errors += [f"config.yaml: {e}" for e in validate_against("config", config)]
    if isinstance(config, dict) and isinstance(rules, dict) and rules and config.get("sport") != rules.get("sport"):
        errors.append(f"config.yaml sport {config.get('sport')!r} != rules.yaml sport {rules.get('sport')!r}")
    if not annotated:
        errors += check_events_source((p / "events.py").read_text("utf8"), str(p / "events.py"))
    if errors:
        raise LoadError(errors)
    sport = str(config["sport"])
    if annotated:
        fn: Callable[..., Any] = _annotated_events
    else:
        fn = _import_events(p / "events.py", sport) if import_code else _not_imported
    return SportModule(sport=sport, path=p, config=config, rules=rules, events=fn, annotated=annotated)


def _annotated_events(*_a: Any, **_k: Any) -> Iterable[dict[str, Any]]:
    raise RuntimeError("an annotated module has no events.py: its events are hand-marked (source: annotated)")


def _not_imported(*_a: Any, **_k: Any) -> Iterable[dict[str, Any]]:
    raise RuntimeError("module loaded with import_code=False")
