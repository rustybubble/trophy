"""Local replay archive shared by recorder and gateway; never publishes video."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageOps

ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def safe_id(value: str) -> str:
    if not ID.fullmatch(value):
        raise ValueError("invalid archive identifier")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".metadata-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(value, f, allow_nan=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def ffmpeg_binary() -> str:
    path = os.environ.get("TROPHY_FFMPEG") or shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is required; set TROPHY_FFMPEG to an installed binary")
    return str(path)


def select_encoder(ffmpeg: str, requested: str = "auto") -> str:
    """Test actual encoding, not just a compiled-in hardware encoder's presence."""
    candidates = ["libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"]
    if requested != "auto":
        if requested not in candidates:
            raise ValueError("unsupported H.264 encoder")
        candidates = [requested]
    for encoder in candidates:
        result = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=size=64x64:rate=30",
                "-frames:v",
                "1",
                "-c:v",
                encoder,
                "-pix_fmt",
                "yuv420p",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0:
            return encoder
    raise RuntimeError("no working H.264 encoder; install libx264 or configure a tested hardware encoder")


def live_snapshot(playlist_text: str) -> str:
    """A live HLS playlist closed with ENDLIST, so ffmpeg reads the segments written so far and stops."""
    text = playlist_text.rstrip("\n")
    return text + "\n" if "#EXT-X-ENDLIST" in text else text + "\n#EXT-X-ENDLIST\n"


class RecordingStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def camera(self, game: str, cam: str) -> Path:
        path = (self.root / safe_id(game) / safe_id(cam)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("archive path escapes root")
        return path

    def asset(self, game: str, cam: str, name: str) -> Path:
        if not re.fullmatch(r"(?:index\.m3u8|init\.mp4|seg_\d{6}\.m4s|sprite_\d+\.jpg|sprite\.json)", name):
            raise FileNotFoundError("no such recording asset")
        base = self.camera(game, cam)
        path = (base / name).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise FileNotFoundError("no such recording asset")
        return path

    def meta(self, game: str, cam: str) -> dict:
        return json.loads((self.camera(game, cam) / "meta.json").read_text())

    def rows(self, game: str, cam: str, name: str, t0: float = -math.inf, t1: float = math.inf) -> list[dict]:
        path = self.camera(game, cam) / name
        if not path.exists():
            return []
        result = []
        # Only newline-terminated records are committed; ignore an in-progress last write.
        with path.open(encoding="utf8") as f:
            for line in f:
                if not line.endswith("\n"):
                    break
                row = json.loads(line)
                if t0 <= row["t_game_s"] <= t1:
                    result.append(row)
        return result

    def window(self, game: str, cam: str, t0: float, t1: float) -> tuple[dict, list[dict]]:
        if not math.isfinite(t0) or not math.isfinite(t1) or t1 <= t0 or t1 - t0 > 30:
            raise ValueError("window must be finite, increasing and at most 30 seconds")
        meta = self.meta(game, cam)
        rows = self.rows(game, cam, "index.jsonl", t0, t1)
        if not rows:
            raise FileNotFoundError("no recorded frames in this window")
        return meta, rows

    def jpeg(self, game: str, cam: str, row: dict) -> bytes:
        name = row["file"]
        if not re.fullmatch(r"frames/\d{10}\.jpg", name):
            raise ValueError("invalid frame path")
        base = self.camera(game, cam)
        path = (base / name).resolve()
        if not path.is_relative_to(base):
            raise ValueError("frame path escapes archive")
        return path.read_bytes()

    def frames(self, game: str, cam: str, t0: float, t1: float, n: int, crop: tuple[int, int, int, int] | None) -> dict:
        if not 1 <= n <= 4:
            raise ValueError("n must be between 1 and 4")
        _, rows = self.window(game, cam, t0, t1)
        indices = sorted({round(i * (len(rows) - 1) / max(n - 1, 1)) for i in range(n)})
        frames = []
        for i in indices:
            row = rows[i]
            with Image.open(io.BytesIO(self.jpeg(game, cam, row))) as source:
                image = source.convert("RGB")
            if crop:
                x, y, w, h = crop
                if min(x, y) < 0 or min(w, h) <= 0 or x + w > image.width or y + h > image.height:
                    raise ValueError("crop must fit within the original frame")
                image = image.crop((x, y, x + w, y + h))
            image.thumbnail((1280, 1280))
            quality = 85
            while True:
                out = io.BytesIO()
                image.save(out, "JPEG", quality=quality)
                # Base64 payload also remains under 1 MB.
                if out.tell() < 740_000:
                    break
                image.thumbnail((max(1, image.width * 3 // 4), max(1, image.height * 3 // 4)))
                quality = max(40, quality - 10)
            frames.append(
                {"t_game_s": row["t_game_s"], "seq": row["seq"], "jpeg_b64": base64.b64encode(out.getvalue()).decode()}
            )
        return {"frames": frames}

    def clip(self, game: str, cam: str, t0: float, t1: float) -> Path:
        meta, rows = self.window(game, cam, t0, t1)
        base = self.camera(game, cam)
        # Use finalized HLS coverage only. The source JPEG endpoint is available sooner.
        playlist = base / "index.m3u8"
        if not playlist.exists():
            raise FileNotFoundError("HLS segments are not ready yet")
        start = max(t0, meta["t0_game_s"]) - meta["t0_game_s"]
        duration = min(t1, meta["last_t_game_s"] + 1 / meta["fps"]) - meta["t0_game_s"] - start
        text = playlist.read_text()
        coverage = sum(
            float(line.split(":", 1)[1].split(",", 1)[0]) for line in text.splitlines() if line.startswith("#EXTINF:")
        )
        if start + duration > coverage + 0.001:
            raise FileNotFoundError("requested HLS window is not finalized yet")
        key = hashlib.sha256(f"{start:.6f}:{duration:.6f}:{rows[-1]['seq']}".encode()).hexdigest()[:24]
        dest = base / "clips" / f"{key}.mp4"
        if dest.exists():
            return dest
        dest.parent.mkdir(exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".mp4", dir=dest.parent)
        os.close(fd)
        # Mid-game the playlist is still live (no ENDLIST), and ffmpeg would wait for segments that haven't been
        # written yet. Cut from a snapshot of the finalized segments instead, next to them so relative URIs resolve.
        source = playlist
        if "#EXT-X-ENDLIST" not in text:
            fd, snap = tempfile.mkstemp(suffix=".m3u8", prefix=".snapshot-", dir=base)
            with os.fdopen(fd, "w", encoding="utf8") as f:
                f.write(live_snapshot(text))
            source = Path(snap)
        try:
            subprocess.run(
                [
                    ffmpeg_binary(),
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-ss",
                    str(start),
                    "-t",
                    str(duration),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    tmp,
                ],
                capture_output=True,
                check=True,
                timeout=30,
            )
            if Path(tmp).stat().st_size < 1000:
                raise FileNotFoundError("requested HLS window is not finalized yet")
            os.replace(tmp, dest)
        finally:
            Path(tmp).unlink(missing_ok=True)
            if source != playlist:
                source.unlink(missing_ok=True)
        return dest

    def tracks(self, game: str, cam: str, kind: str, t0: float, t1: float) -> dict:
        if kind not in ("ball", "players"):
            raise ValueError("kind must be ball or players")
        meta = self.meta(game, cam)
        w, h = meta["w"], meta["h"]
        rows = self.rows(game, cam, f"tracks_{kind}.jsonl", t0, t1)
        frames = []
        for row in rows:
            people = []
            if kind == "ball" and row.get("px") is not None:
                x, y = row["px"]
                r = max(2.0, min(30.0, float(row.get("blur_len_px", 8)) / 2))
                people = [{"id": "ball", "bb": [(x - r) / w, (y - r) / h, 2 * r / w, 2 * r / h], "c": row["conf"]}]
                if row.get("pos_m"):
                    people[0]["ct"] = row["pos_m"][:2]
            elif kind == "players":
                for player in row.get("players", []):
                    x, y, bw, bh = player["bb_px"]
                    people.append({"id": player["track_id"], "bb": [x / w, y / h, bw / w, bh / h]})
                    if player.get("feet_m"):
                        people[-1]["ct"] = player["feet_m"][0][:2]
            for p in people:
                x, y, bw, bh = p["bb"]
                left, top = max(0, min(1, x)), max(0, min(1, y))
                right, bottom = max(left, min(1, x + bw)), max(top, min(1, y + bh))
                p["bb"] = [left, top, right - left, bottom - top]
            frames.append({"t": row["t_game_s"], "p": people})
        deltas = [b["t"] - a["t"] for a, b in zip(frames, frames[1:], strict=False) if b["t"] > a["t"]]
        return {
            "schema": "replay.tracks.v1",
            "t0": meta["t0_game_s"],
            "rate_hz": 1 / median(deltas) if deltas else 0,
            "frames": frames,
        }


def sprite_thumbnail(jpeg: bytes) -> Image.Image:
    with Image.open(io.BytesIO(jpeg)) as image:
        return ImageOps.pad(image.convert("RGB"), (160, 90))
