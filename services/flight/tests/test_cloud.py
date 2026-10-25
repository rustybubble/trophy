"""The CLI end to end on a small synthetic dataset (no video rendering: caches only)."""

import json
from pathlib import Path

from flight import cloud
from flight.calib import camera_looking_at, solve_pose
from flight.field import field_json
from flight.synth import DEFAULT_CAMERAS, blurball_like_json, sample_frames, simulate


def test_cli_run_and_eval(tmp_path: Path):
    sim = simulate(seed=2, shots=4)
    cams = {cid: camera_looking_at(cid, **spec) for cid, spec in DEFAULT_CAMERAS.items()}
    per = {cid: sample_frames(sim, cam, 30.0, {"side": 0.0, "diag": 0.012}[cid]) for cid, cam in cams.items()}
    for cid in cams:
        blurball_like_json(per[cid], tmp_path / f"{cid}.json", noise_px=1.5, miss_p=0.05, false_p=0.03, seed=2)
    fj = field_json([solve_pose(cid, per[cid]["corners_px"], 1280, 720).to_json() for cid in cams])
    (tmp_path / "field.json").write_text(json.dumps(fj))
    truth = {
        "synthetic": True,
        "track": sim["track"][::6],
        "bounces": sim["bounces"],
        "hits": sim["hits"],
        "serve": sim["serve"],
    }
    (tmp_path / "truth.json").write_text(json.dumps(truth))
    out = tmp_path / "out"
    cloud.main(
        [
            "run",
            "--field",
            str(tmp_path / "field.json"),
            "--cam",
            f"side={tmp_path / 'side.json'}",
            "--cam",
            f"diag={tmp_path / 'diag.json'}",
            "--out",
            str(out),
        ]
    )
    assert (out / "track3d.jsonl").exists() and (out / "viewer.html").exists()
    rows = [json.loads(line) for line in (out / "track3d.jsonl").read_text().splitlines()]
    assert rows and all({"t_s", "xyz_m", "cov_m2", "conf", "n_views", "sigma_m"} <= set(r) for r in rows)
    assert "const DATA = " in (out / "viewer.html").read_text()
    cloud.main(["eval", "--out", str(out), "--truth", str(tmp_path / "truth.json")])
    rep = json.loads((out / "eval.json").read_text())
    assert rep["synthetic"] is True
    assert rep["track3d_err_m"]["median"] < 0.05
    assert rep["bounces"]["matched_within_80ms"] >= rep["bounces"]["truth"] - 1
