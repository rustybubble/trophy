import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("eval_live", Path(__file__).resolve().parents[1] / "tools/eval_live.py")
eval_live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_live)


def labels():
    return {
        "schema": eval_live.LABEL_SCHEMA,
        "game_id": "g1",
        "rule_profile": "synthetic-v1",
        "split": "synthetic",
        "coverage": [{"t0_s": 0, "t1_s": 20, "tasks": ["rally", "edge", "serve"], "complete": True}],
        "rallies": [{"id": "r1", "t_start_s": 1, "t_end_s": 5, "winner_team_id": "A"}],
        "edges": [{"id": "e1", "t_game_s": 3, "cam_id": "c1", "outcome": "edge_good"}],
        "serves": [{"id": "s1", "t_game_s": 1, "outcome": "illegal_toss_height"}],
        "no_ball_frames": [{"cam_id": "c1", "seq": 1}, {"cam_id": "c1", "seq": 2}, {"cam_id": "c1", "seq": 3}],
    }


def predictions():
    return {
        "schema": eval_live.PRED_SCHEMA,
        "game_id": "g1",
        "rule_profile": "synthetic-v1",
        "source": "synthetic",
        "rallies": [{"rally_no": 1, "t_start_s": 1, "t_end_s": 5, "winner_team_id": "A"}],
        "calls": [
            {"id": "edge1", "kind": "edge_call", "t_game_s": 3, "outcome": "edge_good", "evidence": [{"cam_id": "c1"}]},
            {"id": "serve1", "rule_id": "serve_toss_too_low", "t_game_s": 1, "outcome": "illegal_toss_height"},
        ],
        "tracks": [{"cam_id": "c1", "seq": 1, "px": None}, {"cam_id": "c1", "seq": 2, "px": [40, 50]}],
    }


def test_known_metrics_include_false_positives_missing_samples_and_wilson():
    report = eval_live.evaluate(labels(), predictions())
    for key in ("rally_outcomes", "edge_vs_side", "serve_faults"):
        assert report[key]["n"] == 1 and report[key]["correct"] == 1
        assert report[key]["wilson_95"] == pytest.approx([0.2065493144, 1])
    fp = report["no_ball_false_positives"]
    assert fp["labelled_n"] == 3 and fp["evaluated_n"] == 2 and fp["missing_samples"] == 1
    assert fp["false_positives"] == 1 and fp["rate"] == 0.5


def test_missing_labels_or_predictions_are_not_a_success():
    empty = {**labels(), "rallies": [], "edges": [], "serves": [], "no_ball_frames": [], "coverage": []}
    report = eval_live.evaluate(empty, predictions())
    assert report["edge_vs_side"]["accuracy"] is None and report["edge_vs_side"]["wilson_95"] is None
    assert report["edge_vs_side"]["unscored_predictions"] == 1
    assert report["no_ball_false_positives"]["rate"] is None
    missing = eval_live.evaluate(labels(), {**predictions(), "rallies": [], "calls": [], "tracks": []})
    assert missing["rally_outcomes"]["correct"] == 0 and missing["serve_faults"]["missed"] == 1
    assert missing["no_ball_false_positives"]["missing_samples"] == 3


def test_duplicate_predictions_and_phantom_rallies_count_as_false_positives():
    p = predictions()
    p["calls"].append({**p["calls"][0], "id": "edge-duplicate"})
    p["rallies"].append({"rally_no": 2, "t_start_s": 5.1, "t_end_s": 6, "winner_team_id": "B"})
    report = eval_live.evaluate(labels(), p)
    assert report["edge_vs_side"]["correct"] == 1 and report["edge_vs_side"]["false_positive_calls"] == 1
    assert report["rally_outcomes"]["boundaries"]["spurious"] == 1


def test_wrong_boundaries_are_separate_from_correct_winner():
    p = predictions()
    p["rallies"][0]["t_start_s"] = 0
    report = eval_live.evaluate(labels(), p)
    assert report["rally_outcomes"]["correct"] == 1
    assert report["rally_outcomes"]["boundaries"]["correct"] == 0
    assert report["rally_outcomes"]["boundaries"]["wrong_matched"] == 1


def test_unknown_labels_and_unlabelled_time_are_not_false_positives():
    truth, p = labels(), predictions()
    truth["edges"][0]["outcome"] = None
    p["calls"].append({**p["calls"][0], "id": "late", "t_game_s": 25})
    report = eval_live.evaluate(truth, p)
    assert report["edge_vs_side"]["n"] == 0 and report["edge_vs_side"]["excluded_unknown"] == 1
    assert report["edge_vs_side"]["false_positive_calls"] == 0 and report["edge_vs_side"]["unscored_predictions"] == 1


def test_matching_ignores_outcome_and_requires_camera_provenance():
    p = predictions()
    p["calls"][0]["outcome"] = "side_fault"
    assert eval_live.evaluate(labels(), p)["edge_vs_side"]["correct"] == 0
    p["calls"][0]["evidence"] = [{"cam_id": "other"}]
    assert eval_live.evaluate(labels(), p)["edge_vs_side"]["missed"] == 1


def test_no_fault_call_is_not_proof_that_the_engine_evaluated_a_legal_serve():
    truth = labels()
    truth["serves"][0]["outcome"] = "legal"
    p = predictions()
    p["calls"] = p["calls"][:1]
    report = eval_live.evaluate(truth, p)
    assert report["serve_faults"]["correct"] == 0 and report["serve_faults"]["missed"] == 1
    p["serve_evaluations"] = [{"id": "legal1", "outcome": "legal", "t_game_s": 1}]
    assert eval_live.evaluate(truth, p)["serve_faults"]["correct"] == 1


def test_manual_calls_and_review_contamination_are_explicit():
    p = predictions()
    p["source"] = "state_snapshot"
    p["calls"][0]["p_source"] = "manual"
    p["calls"][1]["status"] = "voided"
    report = eval_live.evaluate(labels(), p)
    assert report["manual_calls_excluded"] == 1 and report["reviewed_calls"] == 1
    assert report["serve_faults"]["correct"] == 1  # original automatic output is retained, including errors
    assert len(report["warnings"]) == 2


@pytest.mark.parametrize("change", ["game", "profile", "hash", "duplicate", "nan", "track"])
def test_invalid_or_mismatched_evidence_is_rejected(change):
    truth, p = labels(), predictions()
    if change == "game":
        p["game_id"] = "other"
    if change == "profile":
        p["rule_profile"] = "other"
    if change == "hash":
        truth["sources"] = [{"cam_id": "c1", "index_sha256": "different"}]
    if change == "duplicate":
        truth["edges"].append(copy.deepcopy(truth["edges"][0]))
    if change == "nan":
        truth["edges"][0]["t_game_s"] = float("nan")
    if change == "track":
        p["tracks"][0].pop("px")
    with pytest.raises(ValueError):
        eval_live.evaluate(truth, p)


def test_ordered_association_maximizes_count_before_time_error():
    truth = [{"t": 1}, {"t": 2}]
    preds = [{"t": 1.9}, {"t": 2.1}]
    matches, _ = eval_live.ordered_match(
        truth, preds, lambda label, pred: abs(label["t"] - pred["t"]) if abs(label["t"] - pred["t"]) <= 1 else None
    )
    assert matches == {0: 0, 1: 1}


def test_init_does_not_invent_labels(tmp_path):
    game = tmp_path / "g1"
    (game / "cam").mkdir(parents=True)
    (game / "cam" / "index.jsonl").write_text('{"seq":0,"t_game_s":0}\n')
    result = eval_live.init_labels(game, "profile1")
    assert result["rallies"] == [] and result["no_ball_frames"] == []
    assert result["sources"][0]["cam_id"] == "cam"
    eval_live.validate_labels(json.loads(json.dumps(result)))
