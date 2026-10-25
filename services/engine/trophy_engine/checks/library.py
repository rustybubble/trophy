"""Load a ``checks/`` directory and enforce what its code may do.

The compiler enforces *which files* the Droid changes; this loader enforces *what the code can reach*: an AST walk
refuses imports outside ``ALLOWED_IMPORTS`` and the usual escape hatches. The sandbox (throwaway git repo, hook
guard, timeout, human approval) is the security boundary; this is a guard against careless code.

``library.json`` next to the checks says whether they were specialised to a calibration (``calibrated: true`` only
after a Droid ``calibrate_checks`` run is approved; the handwritten golden library is ``false``).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .api import Field, Track

ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "__future__",
        "math",
        "statistics",
        "collections",
        "collections.abc",
        "dataclasses",
        "typing",
        "itertools",
        "functools",
        "bisect",
        "heapq",
        "enum",
        "operator",
        "trophy_engine.checks.api",
    }
)
FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"exec", "eval", "compile", "__import__", "open", "input", "globals", "locals", "vars"}
    | {"getattr", "setattr", "delattr", "breakpoint", "exit", "quit"}
)
CONTRACTS = Path(__file__).resolve().parents[4] / "packages" / "contracts"


class LibraryError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def check_source(src: str, filename: str) -> list[str]:
    """Allowlist violations in a check's source (empty when clean). Requires top-level ``check`` and ``PARAMS``."""
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
    if not any(isinstance(n, ast.FunctionDef) and n.name == "check" for n in tree.body):
        errors.append(f"{filename}: no top-level `def check(track, field, params=None, **q)`")
    if not any(
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMS" for t in n.targets)
        for n in tree.body
    ):
        errors.append(f"{filename}: no top-level `PARAMS = {{...}}`")
    return errors


@dataclass
class Check:
    name: str
    path: Path
    fn: Callable[..., dict[str, Any]]
    params: dict[str, Any]
    doc: str = ""


@dataclass
class CheckLibrary:
    path: Path
    checks: dict[str, Check]
    calibrated: bool
    meta: dict[str, Any] = field(default_factory=dict)

    def names(self) -> list[str]:
        return sorted(self.checks)

    def run(
        self,
        name: str,
        track: Track,
        fld: Field,
        params: Mapping[str, Any] | None = None,
        **q: Any,
    ) -> dict[str, Any]:
        """Run one check and validate its CheckResult. ``calibrated`` is false unless the library, the field and
        the track all are."""
        c = self.checks.get(name)
        if c is None:
            raise LibraryError([f"no check {name!r}; have {self.names()}"])
        t0 = time.perf_counter()
        res = c.fn(track, fld, params, **q)
        if not isinstance(res, dict):
            raise LibraryError([f"{name}: check() returned {type(res).__name__}, not a CheckResult dict"])
        res.setdefault("check", name)
        res["calibrated"] = (
            bool(res.get("calibrated", True)) and self.calibrated and fld.calibrated and track.calibrated
        )
        errs = validate_result(res)
        if errs:
            raise LibraryError([f"{name}: {e}" for e in errs])
        res["ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return res


@lru_cache(maxsize=1)
def _validators() -> dict[str, Draft202012Validator]:
    schema = json.loads((CONTRACTS / "track3d.schema.json").read_text("utf8"))
    defs = schema["$defs"]
    base = {"$schema": schema["$schema"], "$defs": defs}
    return {k: Draft202012Validator({**base, **defs[k]}) for k in ("CheckResult", "Field", "Track3DLabels")} | {
        "Track3DSample": Draft202012Validator(schema)
    }


def validate_against(kind: str, obj: Any) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in _validators()[kind].iter_errors(obj)
    ]


def validate_result(res: Mapping[str, Any]) -> list[str]:
    return validate_against("CheckResult", {k: v for k, v in res.items() if k != "ms"})


def _import(path: Path, name: str) -> Any:
    modname = f"trophy_check_{name}_{abs(hash(str(path))) & 0xFFFF:x}"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise LibraryError([f"{path}: cannot import"])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise LibraryError([f"{path}: import failed: {type(e).__name__}: {e}"]) from e
    return mod


def load_library(path: str | Path, *, import_code: bool = True) -> CheckLibrary:
    """Load ``<path>/*.py`` as checks (files starting with ``_`` are skipped). Raises LibraryError with every finding."""
    p = Path(path)
    if not p.is_dir():
        raise LibraryError([f"{p}: not a directory"])
    files = sorted(f for f in p.glob("*.py") if not f.name.startswith("_"))
    if not files:
        raise LibraryError([f"{p}: no checks (*.py)"])
    errors: list[str] = []
    for f in files:
        errors += check_source(f.read_text("utf8"), str(f))
    meta: dict[str, Any] = {}
    meta_path = p / "library.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text("utf8"))
        except json.JSONDecodeError as e:
            errors.append(f"{meta_path}: {e}")
    if errors:
        raise LibraryError(errors)
    checks: dict[str, Check] = {}
    for f in files:
        name = f.stem
        if import_code:
            mod = _import(f, name)
            fn = getattr(mod, "check", None)
            params = getattr(mod, "PARAMS", None)
            if not callable(fn) or not isinstance(params, dict):
                raise LibraryError([f"{f}: `check` must be callable and `PARAMS` a dict"])
            checks[name] = Check(name=name, path=f, fn=fn, params=dict(params), doc=(mod.__doc__ or "").strip())
        else:
            checks[name] = Check(name=name, path=f, fn=_not_imported, params={})
    return CheckLibrary(path=p, checks=checks, calibrated=bool(meta.get("calibrated", False)), meta=meta)


def _not_imported(*_a: Any, **_k: Any) -> dict[str, Any]:
    raise RuntimeError("library loaded with import_code=False")


def load_field(path: str | Path) -> Field:
    d = json.loads(Path(path).read_text("utf8"))
    errs = validate_against("Field", d)
    if errs:
        raise LibraryError([f"{path}: {e}" for e in errs])
    return Field.from_json(d)


def read_track(path: str | Path, fld: Field) -> Track:
    rows = []
    for n, line in enumerate(Path(path).read_text("utf8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise LibraryError([f"{path}:{n}: {e}"]) from e
    return Track.from_rows(rows, fld)
