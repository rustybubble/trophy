"""The synthetic generator is labelled, deterministic per seed, and produces contract-shaped rows."""

from __future__ import annotations

import json
from pathlib import Path

from trophy_engine.sportmod.l1 import read_l1
from trophy_engine.sportmod.loader import validate_against
from trophy_engine.synth.generate import generate


def test_generate_is_labelled_and_deterministic(tmp_path: Path) -> None:
    a = generate("table_tennis", tmp_path / "a", "r", 5, 4)
    b = generate("table_tennis", tmp_path / "b", "r", 5, 4)
    assert a == b
    assert (tmp_path / "a" / "r.l1.jsonl").read_text() == (tmp_path / "b" / "r.l1.jsonl").read_text()
    labels = json.loads((tmp_path / "a" / "r.labels.json").read_text())
    assert labels["synthetic"] is True and "SYNTHETIC" in labels["label"]
    assert validate_against("labels", labels) == []
    scene = json.loads((tmp_path / "a" / "scene.json").read_text())
    assert validate_against("scene", scene) == []
    obs = read_l1(tmp_path / "a" / "r.l1.jsonl")
    assert sum(1 for o in obs if type(o).__name__ == "Camera") == 2
    assert sum(1 for o in obs if type(o).__name__ == "BallSample") > 100


def test_pickleball_bounces_alternate(tmp_path: Path) -> None:
    generate("pickleball", tmp_path, "p", 2, 5)
    labels = json.loads((tmp_path / "p.labels.json").read_text())
    court = [b for b in labels["bounces"] if b["surface"] == "court"]
    assert len(court) == 5
    assert all(x["side"] != y["side"] for x, y in zip(court, court[1:], strict=False))
