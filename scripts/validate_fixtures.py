"""Validate versioned fixtures and rule packs against packages/contracts (CI "fixture validation").

- packages/state-client/fixtures/*.json (MockScripts): every row against its table's schema; must be synthetic.
- rulepacks/*.yaml and rulepacks/house/**/*.yaml (except sports.yaml) against rulepack.schema.json.
- evals/fixtures/**/*.jsonl event logs: each line against event.schema.json; *.l1.jsonl layer-1 logs: each line is an
  L1Record (scene.schema.json) whose row is a state Camera or a tracks BallTrackSample; *.labels.json / scene.json
  against SampleLabels / SceneDescriptor, and every fixture must be labelled synthetic.
- sports/*/config.yaml against sportmodule.schema.json and sports/*/rules.yaml against rulepack.schema.json.

Run: uv run --project packages/py-trophy python scripts/validate_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts"


def load_schemas() -> tuple[dict[str, dict], Registry]:
    schemas = {
        p.name.removesuffix(".schema.json"): json.loads(p.read_text("utf8")) for p in CONTRACTS.glob("*.schema.json")
    }
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    return schemas, registry


def validator(schema: dict, registry: Registry, ref: str | None = None) -> Draft202012Validator:
    target = {"$ref": f"{schema['$id']}#/$defs/{ref}"} if ref else schema
    return Draft202012Validator(target, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)


def main() -> int:
    schemas, reg = load_schemas()
    for name, s in schemas.items():
        Draft202012Validator.check_schema(s)
        if not s["$id"].endswith(f"/{name}.schema.json"):
            print(f"{name}: $id does not match the file name")
            return 1
    state = schemas["state"]
    table_validators = {
        "call": validator(schemas["call"], reg),
        "observation": validator(schemas["event"], reg),
        **{
            t: validator(state, reg, d)
            for t, d in {
                "game": "Game",
                "camera": "Camera",
                "rally": "Rally",
                "score": "Score",
                "challenge": "Challenge",
                "house_rule": "HouseRule",
                "ai_vote": "AiVote",
                "track_sample": "TrackSample",
                "ask": "Ask",
            }.items()
        },
    }
    errors: list[str] = []
    checked = 0

    for f in sorted((ROOT / "packages/state-client/fixtures").glob("*.json")):
        script = json.loads(f.read_text("utf8"))
        if script.get("synthetic") is not True or "SYNTHETIC" not in script.get("label", ""):
            errors.append(f"{f.name}: mock scripts must be labelled synthetic")
        for i, step in enumerate(script["steps"]):
            v = table_validators.get(step["table"])
            if v is None:
                errors.append(f"{f.name} step {i}: unknown table {step['table']}")
                continue
            errors += [f"{f.name} step {i} ({step['table']}): {e.message}" for e in v.iter_errors(step["row"])]
            checked += 1

    pack_v = validator(schemas["rulepack"], reg)
    for f in sorted((ROOT / "rulepacks").rglob("*.yaml")) + sorted((ROOT / "sports").glob("*/rules.yaml")):
        if f.name == "sports.yaml":
            continue
        errors += [
            f"{f.relative_to(ROOT)}: {e.message}" for e in pack_v.iter_errors(yaml.safe_load(f.read_text("utf8")))
        ]
        checked += 1
    config_v = validator(schemas["sportmodule"], reg)
    for f in sorted((ROOT / "sports").glob("*/config.yaml")):
        cfg = yaml.safe_load(f.read_text("utf8"))
        errors += [f"{f.relative_to(ROOT)}: {e.message}" for e in config_v.iter_errors(cfg)]
        checked += 1

    ev_v = table_validators["observation"]
    l1_v = validator(schemas["scene"], reg, "L1Record")
    l1_rows = {"camera": table_validators["camera"], "ball_sample": validator(schemas["tracks"], reg)}
    track3d_v = validator(schemas["track3d"], reg)
    for f in sorted((ROOT / "evals/fixtures").rglob("*.jsonl")):
        is_l1 = f.name.endswith(".l1.jsonl")
        is_3d = f.name.endswith(".track3d.jsonl")
        for n, line in enumerate(f.read_text("utf8").splitlines(), 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            if is_3d:
                errors += [f"{f.relative_to(ROOT)}:{n}: {e.message}" for e in track3d_v.iter_errors(rec)]
            elif is_l1:
                errs = list(l1_v.iter_errors(rec))
                if not errs:
                    errs = list(l1_rows[rec["table"]].iter_errors(rec["row"]))
                errors += [f"{f.relative_to(ROOT)}:{n}: {e.message}" for e in errs]
            else:
                errors += [f"{f.relative_to(ROOT)}:{n}: {e.message}" for e in ev_v.iter_errors(rec)]
            checked += 1
    labels_v = validator(schemas["scene"], reg, "SampleLabels")
    scene_v = validator(schemas["scene"], reg)
    labels3d_v = validator(schemas["track3d"], reg, "Track3DLabels")
    field_v = validator(schemas["track3d"], reg, "Field")
    for f in sorted((ROOT / "evals/fixtures").rglob("*.json")):
        obj = json.loads(f.read_text("utf8"))
        v = (
            scene_v
            if f.name == "scene.json"
            else field_v
            if f.name == "field.json"
            else labels_v
            if f.name.endswith(".labels.json")
            else labels3d_v
            if f.name.endswith(".labels3d.json")
            else None
        )
        if v is None:
            continue
        errors += [f"{f.relative_to(ROOT)}: {e.message}" for e in v.iter_errors(obj)]
        if "synthetic" in str(f) and (obj.get("synthetic") is not True or "SYNTHETIC" not in obj.get("label", "")):
            errors.append(f"{f.relative_to(ROOT)}: synthetic fixtures must set synthetic: true and a SYNTHETIC label")
        checked += 1

    for e in errors[:50]:
        print(e)
    print(f"validated {checked} rows/files against {len(schemas)} schemas: {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
