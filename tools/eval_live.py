#!/usr/bin/env python3
"""Evaluate captured live-path output against independent labels. No tracker or rule changes.

Use `init`, `check-labels`, `capture`, then `score`. Reports never treat absent labels as success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

LABEL_SCHEMA = "trophy.eval_labels.v1"
PRED_SCHEMA = "trophy.eval_predictions.v1"
TASKS = ("rally", "edge", "serve")


def finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def metric(n: int, correct: int) -> dict:
    if not n:
        return {"n": 0, "correct": 0, "accuracy": None, "wilson_95": None}
    z = 1.959963984540054
    p = correct / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {"n": n, "correct": correct, "accuracy": p, "wilson_95": [max(0, center - radius), min(1, center + radius)]}


def validate_labels(labels: dict) -> None:
    if labels.get("schema") != LABEL_SCHEMA or not labels.get("game_id") or not labels.get("rule_profile"):
        raise ValueError("labels require schema, game_id and an explicit rule_profile")
    if labels.get("split") not in ("development", "held_out", "synthetic"):
        raise ValueError("split must be development, held_out or synthetic")
    ids = set()
    for category in ("rallies", "edges", "serves"):
        for row in labels.get(category, []):
            if not row.get("id") or row["id"] in ids:
                raise ValueError("label ids must be present and unique")
            ids.add(row["id"])
            if category == "rallies":
                if "winner_team_id" not in row:
                    raise ValueError("rallies require winner_team_id (use null for unknown truth)")
                if finite(row["t_end_s"], "end") <= finite(row["t_start_s"], "start"):
                    raise ValueError("rally boundaries must increase")
                if row.get("winner_team_id") is not None and not isinstance(row["winner_team_id"], str):
                    raise ValueError("winner must be a team id or null")
            else:
                if "outcome" not in row:
                    raise ValueError("event labels require outcome (use null for unknown truth)")
                finite(row["t_game_s"], "event time")
                if category == "edges" and row.get("outcome") not in ("edge_good", "side_fault", None):
                    raise ValueError("edge outcome must be edge_good, side_fault or null")
                if category == "serves" and row.get("outcome") not in (
                    "legal",
                    "illegal_toss_height",
                    "illegal_toss_angle",
                    "other_serve_fault",
                    None,
                ):
                    raise ValueError("invalid serve outcome")
                if "acceptable_outcomes" in row:
                    allowed = (
                        {"edge_good", "side_fault"}
                        if category == "edges"
                        else {"legal", "illegal_toss_height", "illegal_toss_angle", "other_serve_fault"}
                    )
                    values = row["acceptable_outcomes"]
                    if (
                        not isinstance(values, list)
                        or not values
                        or any(not isinstance(v, str) or v not in allowed for v in values)
                        or row["outcome"] not in values
                    ):
                        raise ValueError("acceptable_outcomes must include the primary outcome and only valid classes")
            for key in ("tolerance_s", "boundary_tolerance_s"):
                if key in row and finite(row[key], key) < 0:
                    raise ValueError("tolerances must be nonnegative")
    seen = set()
    for row in labels.get("no_ball_frames", []):
        key = (row["cam_id"], row["seq"])
        if key in seen or not isinstance(row["seq"], int) or isinstance(row["seq"], bool) or row["seq"] < 0:
            raise ValueError("negative frame labels require unique camera/sequence ids")
        seen.add(key)
    for row in labels.get("coverage", []):
        if finite(row["t1_s"], "coverage end") <= finite(row["t0_s"], "coverage start"):
            raise ValueError("coverage bounds must increase")
        if not row.get("tasks") or any(t not in TASKS for t in row["tasks"]):
            raise ValueError("coverage tasks must be rally, edge or serve")
        if not isinstance(row.get("complete"), bool):
            raise ValueError("coverage must explicitly state complete: true or false")


def ordered_match(labels: list[dict], predictions: list[dict], distance) -> tuple[dict[int, int], set[int]]:
    """Maximum-cardinality, minimum-time-error one-to-one association in temporal order.

    Outcome is never part of the association cost. Duplicate predictions cannot earn duplicate credit.
    """
    n, m = len(labels), len(predictions)
    if n * m > 2_000_000:
        raise ValueError("too many association pairs; evaluate shorter frozen game windows")
    score = [[(0, 0.0)] * (m + 1) for _ in range(n + 1)]
    back: dict[tuple[int, int], str] = {}
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best, step = score[i - 1][j], "label"
            if score[i][j - 1] > best:
                best, step = score[i][j - 1], "prediction"
            d = distance(labels[i - 1], predictions[j - 1])
            if d is not None:
                prev = score[i - 1][j - 1]
                candidate = (prev[0] + 1, prev[1] - d)
                if candidate > best:
                    best, step = candidate, "match"
            score[i][j], back[i, j] = best, step
    matches: dict[int, int] = {}
    i, j = n, m
    while i and j:
        step = back[i, j]
        if step == "match":
            matches[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif step == "label":
            i -= 1
        else:
            j -= 1
    return matches, set(matches.values())


def time_of(row: dict) -> float:
    return finite(row.get("t_end_s", row.get("t_game_s")), "prediction time")


def in_coverage(row: dict, task: str, labels: dict) -> bool:
    t = time_of(row)
    return any(c["complete"] and task in c["tasks"] and c["t0_s"] <= t <= c["t1_s"] for c in labels.get("coverage", []))


def cameras(row: dict) -> set[str]:
    return (
        {e["cam_id"] for e in row.get("evidence", [])}
        | set(row.get("cams", []))
        | ({row["cam_id"]} if row.get("cam_id") else set())
    )


def event_distance(label: dict, prediction: dict) -> float | None:
    # No camera provenance means an event cannot be matched to a camera-specific label.
    if label.get("cam_id") and label["cam_id"] not in cameras(prediction):
        return None
    distance = abs(time_of(label) - time_of(prediction))
    return distance if distance <= label.get("tolerance_s", 0.25) else None


def score_events(task: str, truth: list[dict], predictions: list[dict], labels: dict) -> dict:
    truth = sorted(truth, key=time_of)
    predictions = sorted(predictions, key=time_of)
    matches, used = ordered_match(truth, predictions, event_distance)
    assessed = [(i, row) for i, row in enumerate(truth) if row.get("outcome") is not None]
    correct, missing, errors = 0, 0, []
    false_faults = 0
    confusion: dict[str, dict[str, int]] = {}
    for i, row in assessed:
        prediction = predictions[matches[i]] if i in matches else None
        outcome = prediction.get("outcome") if prediction else None
        acceptable = row.get("acceptable_outcomes") or [row["outcome"]]
        good = outcome in acceptable
        outcomes = confusion.setdefault(row["outcome"], {})
        predicted = outcome or "missing"
        outcomes[predicted] = outcomes.get(predicted, 0) + 1
        false_faults += task == "serve" and row["outcome"] == "legal" and outcome not in (None, "legal")
        correct += good
        missing += prediction is None
        if not good:
            errors.append({"label_id": row["id"], "truth": acceptable, "prediction": outcome})
    extras = [p for i, p in enumerate(predictions) if i not in used]
    false_positives = [p for p in extras if in_coverage(p, task, labels)]
    return {
        **metric(len(assessed), correct),
        "excluded_unknown": len(truth) - len(assessed),
        "missed": missing,
        "false_positive_calls": len(false_positives),
        "unscored_predictions": len(extras) - len(false_positives),
        "errors": errors,
        "confusion": confusion,
        **({"false_fault_calls_on_legal_serves": false_faults} if task == "serve" else {}),
        "false_positive_ids": [p.get("id") for p in false_positives],
    }


def score_rallies(truth: list[dict], predictions: list[dict], labels: dict) -> dict:
    truth = sorted(truth, key=time_of)
    predictions = sorted([p for p in predictions if p.get("t_end_s") is not None], key=time_of)

    def distance(label: dict, prediction: dict) -> float | None:
        d = abs(label["t_end_s"] - prediction["t_end_s"])
        return d if d <= label.get("tolerance_s", 1.0) else None

    matches, used = ordered_match(truth, predictions, distance)
    assessed = [(i, row) for i, row in enumerate(truth) if row.get("winner_team_id") is not None]
    correct = sum(
        i in matches and predictions[matches[i]].get("winner_team_id") == row["winner_team_id"] for i, row in assessed
    )
    bad_boundaries = []
    for i, row in enumerate(truth):
        if i not in matches:
            continue
        p = predictions[matches[i]]
        tolerance = row.get("boundary_tolerance_s", 0.2)
        start_error, end_error = p["t_start_s"] - row["t_start_s"], p["t_end_s"] - row["t_end_s"]
        if max(abs(start_error), abs(end_error)) > tolerance:
            bad_boundaries.append(
                {
                    "label_id": row["id"],
                    "rally_no": p.get("rally_no"),
                    "start_error_s": start_error,
                    "end_error_s": end_error,
                }
            )
    extras = [p for i, p in enumerate(predictions) if i not in used]
    spurious = [p for p in extras if in_coverage(p, "rally", labels)]
    missed = len(truth) - len(matches)
    return {
        **metric(len(assessed), correct),
        "excluded_unknown": len(truth) - len(assessed),
        "boundaries": {
            **metric(len(truth), len(matches) - len(bad_boundaries)),
            "wrong_matched": len(bad_boundaries),
            "missed": missed,
            "spurious": len(spurious),
            "unscored_predictions": len(extras) - len(spurious),
            "errors": bad_boundaries,
        },
        "spurious_rally_numbers": [p.get("rally_no") for p in spurious],
    }


def evaluate(labels: dict, predictions: dict) -> dict:
    validate_labels(labels)
    if predictions.get("schema") != PRED_SCHEMA:
        raise ValueError("unsupported prediction schema")
    for key in ("game_id", "rule_profile"):
        if labels[key] != predictions.get(key):
            raise ValueError(f"prediction/label {key} mismatch")
    if labels.get("sources") and predictions.get("sources") != labels["sources"]:
        raise ValueError("source frame-index hashes mismatch")
    calls = predictions.get("calls", [])
    automatic = [c for c in calls if c.get("p_source") != "manual"]
    edges = [c for c in automatic if c.get("kind") == "edge_call" or c.get("rule_id") == "edge_ball"]
    serves = [
        c
        for c in automatic
        if c.get("rule_id", "").startswith("serve_") or c.get("outcome", "").startswith("illegal_toss_")
    ]
    serves += [c for c in predictions.get("serve_evaluations", []) if c.get("p_source") != "manual"]
    # Normalize the current engine's height/angle outcomes without deriving new calls from measurements.
    serves = [
        {
            **c,
            "outcome": c["outcome"]
            if c["outcome"] in ("legal", "illegal_toss_height", "illegal_toss_angle")
            else "other_serve_fault",
        }
        for c in serves
    ]
    by_frame: dict[tuple[str, int], list[dict]] = {}
    for sample in predictions.get("tracks", []):
        if "px" not in sample or (
            sample["px"] is not None
            and (
                not isinstance(sample["px"], list)
                or len(sample["px"]) != 2
                or any(not math.isfinite(finite(v, "pixel")) for v in sample["px"])
            )
        ):
            raise ValueError("track samples require explicit px: [x,y] or null")
        by_frame.setdefault((sample["cam_id"], sample["seq"]), []).append(sample)
    negatives = labels.get("no_ball_frames", [])
    evaluated = [row for row in negatives if (row["cam_id"], row["seq"]) in by_frame]
    fp = [
        row for row in evaluated if any(sample.get("px") is not None for sample in by_frame[row["cam_id"], row["seq"]])
    ]
    fp_metric = metric(len(evaluated), len(fp))
    warnings = []
    if predictions.get("source") == "state_snapshot":
        warnings.append(
            "State snapshot: freeze before human review; this is not an immutable pre-review live-call log."
        )
    reviewed = sum(c.get("status") in ("upheld", "overturned", "voided") for c in calls)
    if reviewed:
        warnings.append(
            "Reviewed/voided calls are present. They remain in the report; do not call this pre-review live accuracy."
        )
    if not labels.get("coverage"):
        warnings.append("No exhaustive coverage intervals: unmatched calls are unscored, not assumed false positives.")
    if not negatives:
        warnings.append("No no-ball frame labels: detector false-positive rate is unknown.")
    return {
        "schema": "trophy.eval_report.v1",
        "game_id": labels["game_id"],
        "rule_profile": labels["rule_profile"],
        "split": labels["split"],
        "synthetic": labels["split"] == "synthetic",
        "prediction_source": predictions.get("source"),
        "rally_outcomes": score_rallies(labels.get("rallies", []), predictions.get("rallies", []), labels),
        "edge_vs_side": score_events("edge", labels.get("edges", []), edges, labels),
        "serve_faults": score_events("serve", labels.get("serves", []), serves, labels),
        "no_ball_false_positives": {
            "labelled_n": len(negatives),
            "evaluated_n": len(evaluated),
            "missing_samples": len(negatives) - len(evaluated),
            "false_positives": len(fp),
            "rate": fp_metric["accuracy"],
            "wilson_95": fp_metric["wilson_95"],
            "frames": fp,
        },
        "manual_calls_excluded": len(calls) - len(automatic),
        "reviewed_calls": reviewed,
        "warnings": warnings,
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def init_labels(recording: Path, profile: str) -> dict:
    sources = []
    for path in sorted(recording.glob("*/index.jsonl")):
        sources.append({"cam_id": path.parent.name, "index_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if not sources:
        raise ValueError("recording must be a game directory containing camera index.jsonl files")
    return {
        "schema": LABEL_SCHEMA,
        "game_id": recording.name,
        "rule_profile": profile,
        "split": "development",
        "labeller": "",
        "reviewer": "",
        "sources": sources,
        "coverage": [],
        "rallies": [],
        "edges": [],
        "serves": [],
        "no_ball_frames": [],
    }


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.split("#", 1)[0].strip()
    return {**values, **os.environ}


def capture(recording: Path, profile: str, uri: str, module: str, env_file: Path) -> dict:
    gid = recording.name
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", gid):
        raise ValueError("invalid game id")
    env = read_env(env_file)
    token = env.get("SPACETIME_ENGINE_TOKEN", "")
    if not token:
        raise ValueError("SPACETIME_ENGINE_TOKEN is required for capture")
    tables = {}
    for table in ("game", "call", "rally", "observation"):
        req = urllib.request.Request(
            f"{uri.rstrip('/')}/v1/database/{module}/sql",
            data=f"SELECT * FROM {table} WHERE game_id = '{gid}'".encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.load(response)[0]
        names = [
            c["name"].get("some") if isinstance(c["name"], dict) else c["name"] for c in result["schema"]["elements"]
        ]
        tables[table] = [json.loads(dict(zip(names, row, strict=True))["json"]) for row in result["rows"]]
    tracks = []
    sources = init_labels(recording, profile)["sources"]
    for path in sorted(recording.glob("*/tracks_ball.jsonl")):
        for line in path.read_text().splitlines():
            tracks.append({**json.loads(line), "cam_id": path.parent.name})
    return {
        "schema": PRED_SCHEMA,
        "game_id": gid,
        "rule_profile": profile,
        "source": "state_snapshot",
        "sources": sources,
        "game": tables["game"],
        "calls": tables["call"],
        "rallies": tables["rally"],
        "observations": tables["observation"],
        "tracks": tracks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "capture"):
        p = sub.add_parser(command)
        p.add_argument("--recording", type=Path, required=True, help="local game archive directory")
        p.add_argument("--profile", required=True, help="actual pack/profile/version under test")
        p.add_argument("--output", type=Path, required=True)
        if command == "capture":
            p.add_argument("--uri", default="http://127.0.0.1:3000")
            p.add_argument("--module", default="trophy")
            p.add_argument("--env-file", type=Path, default=Path(".env"))
    p = sub.add_parser("check-labels")
    p.add_argument("labels", type=Path)
    p = sub.add_parser("score")
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            if args.output.exists():
                raise ValueError("label file exists; refusing to overwrite human work")
            write_json(args.output, init_labels(args.recording, args.profile))
        elif args.command == "capture":
            if args.output.exists():
                raise ValueError("capture file exists; choose a new immutable snapshot name")
            write_json(args.output, capture(args.recording, args.profile, args.uri, args.module, args.env_file))
        elif args.command == "check-labels":
            validate_labels(json.loads(args.labels.read_text()))
            print("labels validated; validation does not certify their ground truth")
        else:
            labels, predictions = json.loads(args.labels.read_text()), json.loads(args.predictions.read_text())
            report = evaluate(labels, predictions)
            write_json(args.output, report)
            print(
                json.dumps(
                    {
                        k: report[k]
                        for k in (
                            "rally_outcomes",
                            "edge_vs_side",
                            "serve_faults",
                            "no_ball_false_positives",
                            "warnings",
                        )
                    },
                    indent=2,
                )
            )
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
