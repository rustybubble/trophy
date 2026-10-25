"""Ball candidate sources. A candidate is where the ball MIGHT be in one frame; the tracker decides.

Every source yields {"frame": int, "t_s": float, "candidates": [{"xy_px": [x, y], "score": float, ...}]}.
Scores are detector ranking scores in [0, 1], not probabilities of being the ball.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

COLOUR_HSV = {
    # (lower, upper) inclusive HSV bounds (OpenCV ranges: H 0-179, S/V 0-255)
    "white": ((0, 0, 170), (179, 70, 255)),
    "orange": ((4, 120, 120), (28, 255, 255)),
}


def blurball_json_candidates(path: str | Path, t_offset_s: float = 0.0) -> Iterator[dict]:
    """The tracker branch's cache format: {"frames": [{seq, t_source_s, x, y, score, status, ...}]}."""
    data = json.loads(Path(path).read_text(encoding="utf8"))
    for r in data["frames"]:
        cands = []
        if r.get("x") is not None and r.get("y") is not None:
            cands.append(
                {
                    "xy_px": [float(r["x"]), float(r["y"])],
                    "score": float(min(1.0, r.get("score") or 0.5)),
                    "L_px": r.get("blur_length_px"),
                    "theta_deg": r.get("blur_angle_degrees"),
                }
            )
        yield {"frame": int(r["seq"]), "t_s": float(r["t_source_s"]) + t_offset_s, "candidates": cands}


def blurball_csv_candidates(path: str | Path, fps: float, t_offset_s: float = 0.0) -> Iterator[dict]:
    """BlurBall's own output: Frame, X, Y, Visibility, L, Theta (pixels in the source resolution)."""
    with open(path, newline="", encoding="utf8") as f:
        for row in csv.DictReader(f):
            frame = int(row["Frame"])
            vis = int(float(row.get("Visibility", 1)))
            cands = []
            if vis:
                cands.append(
                    {
                        "xy_px": [float(row["X"]), float(row["Y"])],
                        "score": 1.0,
                        "L_px": float(row["L"]) if row.get("L") not in (None, "") else None,
                        "theta_deg": float(row["Theta"]) if row.get("Theta") not in (None, "") else None,
                    }
                )
            yield {"frame": frame, "t_s": frame / fps + t_offset_s, "candidates": cands}


class ClassicalDetector:
    """Static-camera baseline: background subtraction, optional ball colour, blob size. CPU only."""

    def __init__(
        self,
        colour: str | None = "white",
        expected_radius_px: float | None = None,
        max_candidates: int = 5,
        history: int = 60,
        var_threshold: float = 16.0,
    ):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=history, varThreshold=var_threshold, detectShadows=False)
        self.colour = colour
        self.r = expected_radius_px
        self.k = max_candidates
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def __call__(self, bgr: np.ndarray) -> list[dict]:
        fg = self.bg.apply(bgr)
        fg = cv2.threshold(fg, 127, 255, cv2.THRESH_BINARY)[1]
        if self.colour:
            lo, hi = COLOUR_HSV[self.colour]
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            fg = cv2.bitwise_and(fg, cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8)))
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, self.kernel)
        n, _, stats, centres = cv2.connectedComponentsWithStats(fg, 8)
        if self.r:
            a_min, a_max = np.pi * (0.5 * self.r) ** 2, np.pi * (3.0 * self.r) ** 2 * 2  # blur streaks are long
        else:
            a_min, a_max = 3.0, 600.0
        cands = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if not (a_min <= area <= a_max):
                continue
            fill = area / max(1.0, float(w * h))
            elong = max(w, h) / max(1.0, float(min(w, h)))
            if elong > 8:  # a streak longer than 8x its width is not a 30 fps ball
                continue
            size = 1.0 if self.r is None else float(np.exp(-abs(np.log(np.sqrt(area / np.pi) / self.r))))
            score = float(np.clip(0.5 * fill + 0.5 * size, 0, 1))
            cands.append({"xy_px": [float(centres[i][0]), float(centres[i][1])], "score": score, "area_px": int(area)})
        cands.sort(key=lambda c: -c["score"])
        return cands[: self.k]


def video_candidates(
    path: str | Path,
    detector: ClassicalDetector,
    t_offset_s: float = 0.0,
    limit: int | None = None,
) -> Iterator[dict]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame = 0
    while True:
        ok, bgr = cap.read()
        if not ok or (limit is not None and frame >= limit):
            break
        yield {"frame": frame, "t_s": frame / fps + t_offset_s, "candidates": detector(bgr)}
        frame += 1
    cap.release()


def video_info(path: str | Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(path)
    info = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": float(cap.get(cv2.CAP_PROP_FPS) or 30.0),
        "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    return info


def first_frame(path: str | Path) -> np.ndarray:
    cap = cv2.VideoCapture(str(path))
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        raise FileNotFoundError(path)
    return bgr
