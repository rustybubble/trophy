"""The import allowlist and module validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from trophy_engine.sportmod.loader import LoadError, check_events_source, load_module

ROOT = Path(__file__).resolve().parents[3]
TT = ROOT / "sports" / "table_tennis"


def test_golden_module_loads() -> None:
    mod = load_module(TT)
    assert mod.sport == "table_tennis"
    assert mod.config["court"]["length_m"] == 2.74
    assert any(r["id"] == "edge_ball" for r in mod.rules["rules"])


@pytest.mark.parametrize(
    "src,needle",
    [
        ("import os\ndef events(o, s):\n    return []\n", "import 'os' is not allowed"),
        ("import subprocess\ndef events(o, s):\n    return []\n", "'subprocess'"),
        ("from socket import socket\ndef events(o, s):\n    return []\n", "from 'socket' import"),
        ("def events(o, s):\n    return eval('1')\n", "eval()"),
        ("def events(o, s):\n    return open('x')\n", "open()"),
        ("def events(o, s):\n    return __import__('os')\n", "__import__()"),
        ("def events(o, s):\n    return ().__class__.__bases__\n", "dunder attribute"),
        ("from . import x\ndef events(o, s):\n    return []\n", "not allowed"),
        ("def run(o, s):\n    return []\n", "no top-level `def events"),
        ("def events(o, s:\n", "syntax error"),
    ],
)
def test_allowlist_rejects(src: str, needle: str) -> None:
    errs = check_events_source(src)
    assert errs, src
    assert any(needle in e for e in errs), errs


def test_allowlist_accepts_the_api() -> None:
    src = (
        "from __future__ import annotations\nimport math\nx = math.sqrt(2)\n"
        "from trophy_engine.sportmod.api import Iterable, bounce_event\n\ndef events(o, s):\n    return []\n"
    )
    assert check_events_source(src) == []


@pytest.mark.parametrize(
    "line",
    [
        "from typing import get_type_hints",  # evaluates string annotations, which the AST walk can't see
        "import collections",
        "from dataclasses import dataclass",
        "import enum",
        "from operator import attrgetter",  # attrgetter('__class__') reaches dunders by string
        "import statistics\nx = statistics.sys",  # a module reached through an allowed module
        "from statistics import sys",
        "import statistics\ny = statistics",  # aliased away from the attribute check
        "import trophy_engine.sportmod.api as a",  # a.hashlib ...
        "from trophy_engine.sportmod.api import hashlib",  # not in __all__
        "from trophy_engine.sportmod.api import *",
    ],
)
def test_allowlist_refuses_the_escapes_from_review(line: str) -> None:
    """Review blocker 2."""
    assert check_events_source(f"{line}\n\ndef events(o, s):\n    return []\n")


def test_missing_file_is_a_load_error(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("sport: x\n")
    with pytest.raises(LoadError) as e:
        load_module(tmp_path)
    # no events.py makes it an annotated module (D-44), which still needs rules.yaml
    assert any("rules.yaml: missing" in m for m in e.value.errors)


def test_annotated_module_loads_without_events_py(tmp_path: Path) -> None:
    """D-44: config.yaml + rules.yaml, no events.py; config only has to name the sport, events() refuses to run."""
    (tmp_path / "config.yaml").write_text("sport: table_tennis\nversion: 1\n")
    (tmp_path / "rules.yaml").write_text((TT / "rules.yaml").read_text())
    mod = load_module(tmp_path)
    assert mod.annotated and mod.sport == "table_tennis"
    with pytest.raises(RuntimeError, match="annotated"):
        list(mod.events([], mod.state("g_00000000")))
    assert not load_module(TT).annotated


def test_rules_optional_loads_a_sport_without_an_interpreter(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("sport: badminton\n")
    with pytest.raises(LoadError):
        load_module(tmp_path)
    mod = load_module(tmp_path, rules_optional=True)
    assert mod.rules == {} and mod.annotated


def test_schema_errors_are_collected(tmp_path: Path) -> None:
    for f in ("config.yaml", "events.py", "rules.yaml"):
        (tmp_path / f).write_text((TT / f).read_text())
    (tmp_path / "config.yaml").write_text("sport: table_tennis\nversion: 1\n")
    with pytest.raises(LoadError) as e:
        load_module(tmp_path)
    assert any("config.yaml" in m and "required" in m for m in e.value.errors)
