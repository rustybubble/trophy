"""The table-tennis field in the metric frame the Droid brief expects (docs/plan/prompts/agent-3-droid-realtime.md).

Origin: table centre on the surface. x along the length (+x = side B), y across, z up. Units: metres.
"""

from __future__ import annotations

import numpy as np

LENGTH_M = 2.74
WIDTH_M = 1.525
TABLE_HEIGHT_M = 0.76
NET_HEIGHT_M = 0.1525
NET_OVERHANG_M = 0.1525
BALL_DIAMETER_M = 0.040
BALL_RADIUS_M = BALL_DIAMETER_M / 2

# Corner order is fixed by the brief: A-right, B-right, B-left, A-left (counter-clockwise seen from above).
CORNERS_M = np.array(
    [
        [-LENGTH_M / 2, -WIDTH_M / 2, 0.0],
        [LENGTH_M / 2, -WIDTH_M / 2, 0.0],
        [LENGTH_M / 2, WIDTH_M / 2, 0.0],
        [-LENGTH_M / 2, WIDTH_M / 2, 0.0],
    ]
)

LINES_M = {
    "end_A": ((-LENGTH_M / 2, -WIDTH_M / 2), (-LENGTH_M / 2, WIDTH_M / 2)),
    "end_B": ((LENGTH_M / 2, -WIDTH_M / 2), (LENGTH_M / 2, WIDTH_M / 2)),
    "side_right": ((-LENGTH_M / 2, -WIDTH_M / 2), (LENGTH_M / 2, -WIDTH_M / 2)),
    "side_left": ((-LENGTH_M / 2, WIDTH_M / 2), (LENGTH_M / 2, WIDTH_M / 2)),
    "net": ((0.0, -WIDTH_M / 2), (0.0, WIDTH_M / 2)),
}


def side_of(x_m: float) -> str:
    return "A" if x_m < 0 else "B"


def signed_line_distances(x_m: float, y_m: float) -> dict[str, float]:
    """Signed distance to each table edge, positive = inside the table."""
    return {
        "end_A": x_m + LENGTH_M / 2,
        "end_B": LENGTH_M / 2 - x_m,
        "side_right": y_m + WIDTH_M / 2,
        "side_left": WIDTH_M / 2 - y_m,
    }


def on_table(x_m: float, y_m: float, margin_m: float = 0.0) -> bool:
    return all(d >= -margin_m for d in signed_line_distances(x_m, y_m).values())


def field_json(cameras: list[dict] | None = None, time: dict | None = None) -> dict:
    out = {
        "sport": "table_tennis",
        "frame": "field",
        "surface_z_m": 0.0,
        "table": {"length_m": LENGTH_M, "width_m": WIDTH_M, "height_m": TABLE_HEIGHT_M},
        "net": {"x_m": 0.0, "height_m": NET_HEIGHT_M, "overhang_m": NET_OVERHANG_M},
        "ball": {"diameter_m": BALL_DIAMETER_M},
        "corners_m": CORNERS_M.tolist(),
        "sides": {"A": "x<0", "B": "x>0"},
    }
    if cameras:
        out["cameras"] = cameras
    if time:
        out["time"] = time
    return out
