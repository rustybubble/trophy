"""Layer-1 logs: JSONL of ``L1Record`` lines (scene.schema.json) -> ``Camera`` / ``BallSample`` observations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .api import BallSample, Camera, Observation


def camera_from_row(cam_id: str, row: dict[str, Any]) -> Camera:
    calib = row.get("calibration") or {}
    size = calib.get("image_size") or row.get("image_size") or {"w": 0, "h": 0}
    H = calib.get("H_img_to_field")
    if not H or len(H) != 9:
        raise ValueError(f"camera {cam_id}: calibration.H_img_to_field missing")
    return Camera(
        cam_id=cam_id,
        image_w=int(size["w"]),
        image_h=int(size["h"]),
        H_img_to_field=tuple(float(v) for v in H),
        trusted=bool(row.get("calib_trusted", calib.get("trusted", False))),
        reproj_err_px=float(calib.get("reproj_err_px", 0.0)),
        fps=float(row.get("fps_in", 0.0)),
    )


def sample_from_row(cam_id: str, row: dict[str, Any]) -> BallSample:
    px = row.get("px")
    return BallSample(
        cam_id=cam_id,
        t_s=float(row["t_game_s"]),
        seq=int(row["seq"]),
        px=(float(px[0]), float(px[1])) if px is not None else None,
        conf=float(row.get("conf", 0.0)),
    )


def parse_record(rec: dict[str, Any]) -> Observation:
    table = rec["table"]
    cam_id = rec["cam_id"]
    row = rec["row"]
    if table == "camera":
        return camera_from_row(cam_id, row)
    if table == "ball_sample":
        return sample_from_row(cam_id, row)
    raise ValueError(f"unknown layer-1 table {table!r}")


def read_l1(path: str | Path) -> list[Observation]:
    out: list[Observation] = []
    for n, line in enumerate(Path(path).read_text("utf8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(parse_record(json.loads(line)))
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"{path}:{n}: {e}") from e
    return out


def read_labels(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text("utf8"))
