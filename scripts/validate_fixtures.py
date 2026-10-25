"""Validate versioned fixtures and rule packs against packages/contracts (CI "fixture validation").

- packages/state-client/fixtures/*.json (MockScripts): every row against its table's schema; must be synthetic.
- rulepacks/*.yaml and rulepacks/house/**/*.yaml (except sports.yaml) against rulepack.schema.json.
- evals/fixtures/**/*.jsonl event logs: each line against event.schema.json.

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
                "moment": "Moment",
                "commentary": "Commentary",
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
    for f in sorted((ROOT / "rulepacks").rglob("*.yaml")):
        if f.name == "sports.yaml":
            continue
        errors += [
            f"{f.relative_to(ROOT)}: {e.message}" for e in pack_v.iter_errors(yaml.safe_load(f.read_text("utf8")))
        ]
        checked += 1

    ev_v = table_validators["observation"]
    for f in sorted((ROOT / "evals/fixtures").rglob("*.jsonl")):
        for n, line in enumerate(f.read_text("utf8").splitlines(), 1):
            if line.strip():
                errors += [f"{f.relative_to(ROOT)}:{n}: {e.message}" for e in ev_v.iter_errors(json.loads(line))]
                checked += 1

    for e in errors[:50]:
        print(e)
    print(f"validated {checked} rows/files against {len(schemas)} schemas: {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
