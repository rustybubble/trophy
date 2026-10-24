"""Decode a recorded clip into BGR frames at a working size, keeping every source frame and its time."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ClipInfo:
    path: Path
    w: int
    h: int
    fps: float
    duration_s: float
    n_frames: int


def probe(path: Path) -> ClipInfo:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_read_packets:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    d = json.loads(out)
    s = d["streams"][0]
    num, den = (int(x) for x in s["avg_frame_rate"].split("/"))
    return ClipInfo(
        path, int(s["width"]), int(s["height"]), num / den, float(d["format"]["duration"]), int(s["nb_read_packets"])
    )


def frames(
    path: Path,
    w: int = 1280,
    h: int = 720,
    start_s: float = 0.0,
    seconds: float | None = None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """(source frame index, source time s, BGR frame) for every decoded frame from start_s.

    Frame indices count from the start of the file (assumes constant frame rate, which phone clips have)."""
    info = probe(path)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start_s}", "-i", str(path)]
    if seconds is not None:
        cmd += ["-t", f"{seconds}"]
    cmd += ["-vf", f"scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=w * h * 3 * 4)
    first = round(start_s * info.fps)
    n = 0
    size = w * h * 3
    assert proc.stdout
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            idx = first + n
            yield idx, idx / info.fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            n += 1
    finally:
        proc.stdout.close()
        proc.wait()
