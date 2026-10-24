"""Record every retained frame-bus entry in order; gaps are explicit, never hidden by latest-frame reads."""

from __future__ import annotations

import io
import json
import math
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from PIL import Image
from trophy.framebus import Frame, _decode
from trophy.recordings import RecordingStore, atomic_json, ffmpeg_binary, sprite_thumbnail


def text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class CameraRecording:
    def __init__(self, store: RecordingStore, frame: Frame, fps: int, encoder: str) -> None:
        if not 1 <= fps <= 60:
            raise ValueError("recording fps must be 1..60")
        self.path = store.camera(frame.game_id, frame.cam_id)
        self.path.mkdir(parents=True, exist_ok=True)
        if (self.path / "meta.json").exists():
            raise FileExistsError(f"recording already exists: {frame.game_id}/{frame.cam_id}; refusing to overwrite")
        (self.path / "frames").mkdir(exist_ok=True)
        self.meta: dict[str, Any] = {
            "schema": "trophy.recording.v1",
            "game_id": frame.game_id,
            "cam_id": frame.cam_id,
            "t0_game_s": frame.t_game_s,
            "last_t_game_s": frame.t_game_s,
            "duration_s": 0,
            "fps": fps,
            "w": frame.w,
            "h": frame.h,
            "encoder": encoder,
            "frame_count": 0,
            "held_video_frames": 0,
            "sequence_gaps": 0,
            "closed": False,
            "timing": "CFR video; original frame times/seq in index.jsonl; capture gaps hold the previous image",
        }
        self.index = (self.path / "index.jsonl").open("x", encoding="utf8", buffering=1)
        self.stderr = (self.path / "ffmpeg.log").open("wb")
        self.sprite_page: Image.Image | None = None
        self.sprite_n = -1
        self.sprite_next = frame.t_game_s
        self.sprite_count = 0
        self.last: Frame | None = None
        self.slot = -1
        self.closed = False
        self.track_ids: dict[str, str] = {"ball": "0-0", "players": "0-0"}
        cmd = [
            ffmpeg_binary(),
            "-v",
            "warning",
            "-y",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            encoder,
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-g",
            str(2 * fps),
            "-keyint_min",
            str(2 * fps),
            "-force_key_frames",
            "expr:gte(t,n_forced*2)",
        ]
        if encoder == "libx264":
            cmd += ["-preset", "veryfast", "-crf", "20", "-sc_threshold", "0", "-tune", "zerolatency"]
        cmd += [
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "0",
            "-hls_playlist_type",
            "event",
            "-hls_segment_type",
            "fmp4",
            "-hls_fmp4_init_filename",
            "init.mp4",
            "-hls_flags",
            "independent_segments+temp_file",
            "-hls_segment_filename",
            "seg_%06d.m4s",
            "index.m3u8",
        ]
        self.proc = subprocess.Popen(
            cmd, cwd=self.path, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.stderr
        )
        atomic_json(self.path / "meta.json", self.meta)

    def add(self, frame: Frame) -> bool:
        if self.closed:
            raise RuntimeError("recording is closed")
        if (frame.game_id, frame.cam_id) != (self.meta["game_id"], self.meta["cam_id"]):
            raise ValueError("frame identity mismatch")
        if not math.isfinite(frame.t_game_s) or (frame.w, frame.h) != (self.meta["w"], self.meta["h"]):
            raise ValueError("invalid timestamp or camera size changed")
        if self.last and frame.seq == self.last.seq:
            return False
        if self.last and frame.t_game_s < self.last.t_game_s:
            raise ValueError("camera game time moved backwards")
        with Image.open(io.BytesIO(frame.data)) as image:
            if image.size != (frame.w, frame.h):
                raise ValueError("JPEG dimensions don't match the frame bus")
            image.verify()
        slot = round((frame.t_game_s - self.meta["t0_game_s"]) * self.meta["fps"])
        gap = max(0, slot - self.slot - 1)
        if gap > 30 * self.meta["fps"]:
            raise ValueError("capture gap exceeds 30 seconds; refusing to invent a long video interval")
        assert self.proc.stdin
        if self.proc.poll() is not None:
            raise RuntimeError("ffmpeg exited; inspect the local ffmpeg.log")
        if gap and self.last:
            for _ in range(gap):
                self.proc.stdin.write(self.last.data)
        if slot > self.slot:
            self.proc.stdin.write(frame.data)
            self.slot = slot
        self.proc.stdin.flush()
        count = self.meta["frame_count"]
        name = f"frames/{count:010d}.jpg"
        (self.path / name).write_bytes(frame.data)
        row = {
            "seq": frame.seq,
            "t_game_s": frame.t_game_s,
            "seg": f"seg_{max(0, slot) // (2 * self.meta['fps']):06d}.m4s",
            "pts": max(0, slot) / self.meta["fps"],
            "file": name,
            "sync_err_ms": frame.sync_err_ms,
            "source": frame.source,
            "held_frames_before": gap,
        }
        self.index.write(json.dumps(row, allow_nan=False) + "\n")
        if self.last:
            self.meta["sequence_gaps"] += max(0, frame.seq - self.last.seq - 1)
        self.last = frame
        self.meta.update(
            frame_count=count + 1,
            last_t_game_s=frame.t_game_s,
            duration_s=(self.slot + 1) / self.meta["fps"],
            held_video_frames=self.meta["held_video_frames"] + gap,
        )
        self._sprite(frame)
        atomic_json(self.path / "meta.json", self.meta)
        return True

    def _sprite(self, frame: Frame) -> None:
        if frame.t_game_s + 0.001 < self.sprite_next:
            return
        # Gaps stay blank in the storyboard instead of manufacturing an observation.
        sample = math.floor((frame.t_game_s - self.meta["t0_game_s"]) / 2 + 0.001)
        page, cell = divmod(sample, 100)
        if self.sprite_n != page:
            self.sprite_n = page
            self.sprite_page = Image.new("RGB", (1600, 900))
        assert self.sprite_page
        self.sprite_page.paste(sprite_thumbnail(frame.data), ((cell % 10) * 160, (cell // 10) * 90))
        out = io.BytesIO()
        self.sprite_page.save(out, "JPEG", quality=80)
        tmp = self.path / f".sprite_{page}.jpg"
        tmp.write_bytes(out.getvalue())
        tmp.replace(self.path / f"sprite_{page}.jpg")
        self.sprite_count = max(self.sprite_count, sample + 1)
        atomic_json(
            self.path / "sprite.json",
            {
                "url_template": "sprite_{n}.jpg",
                "cols": 10,
                "rows": 10,
                "every_s": 2,
                "w": 160,
                "h": 90,
                "count": self.sprite_count,
                "t0_game_s": self.meta["t0_game_s"],
            },
        )
        self.sprite_next = self.meta["t0_game_s"] + (sample + 1) * 2

    def copy_tracks(self, redis: Any) -> None:
        raw = redis.get(f"calib:{self.meta['cam_id']}")
        if raw:
            calibration = json.loads(raw)
            if calibration.get("game_id") == self.meta["game_id"] and calibration.get("cam_id") == self.meta["cam_id"]:
                atomic_json(self.path / "calibration.json", calibration)
        for kind in ("ball", "players"):
            entries = redis.xrange(f"trk:{kind}:{self.meta['cam_id']}", min=f"({self.track_ids[kind]}", count=2000)
            for entry_id, fields in entries:
                raw = fields.get(b"json", fields.get("json"))
                sample = json.loads(raw)
                if sample["t_game_s"] > self.meta["last_t_game_s"]:
                    break  # keep the cursor; this sample belongs to a frame still arriving
                self.track_ids[kind] = text(entry_id)
                if sample["t_game_s"] < self.meta["t0_game_s"]:
                    continue
                if sample.get("game_id", self.meta["game_id"]) != self.meta["game_id"]:
                    continue
                with (self.path / f"tracks_{kind}.jsonl").open("a", encoding="utf8") as out:
                    out.write(json.dumps({**sample, "_stream_id": text(entry_id)}, allow_nan=False) + "\n")

    def close(self, error: str | None = None) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.proc.stdin:
                with suppress(BrokenPipeError):
                    self.proc.stdin.close()
            try:
                code = self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
                code = -1
            if code:
                error = error or "ffmpeg failed; inspect ffmpeg.log"
        finally:
            self.index.close()
            self.stderr.close()
            self.meta.update(closed=True, error=error or self.meta.get("error"))
            atomic_json(self.path / "meta.json", self.meta)


class Recorder:
    def __init__(self, redis: Any, root: Path, fps: int, encoder: str) -> None:
        self.redis, self.store, self.fps, self.encoder = redis, RecordingStore(root), fps, encoder
        self.cursors: dict[str, str] = {}
        self.sessions: dict[str, CameraRecording] = {}
        self.finalized: set[tuple[str, str]] = set()
        self.ended_games: set[str] = set()
        self.ctl_cursor = "0-0"
        self.frames = 0

    def poll(self) -> int:
        for key in self.redis.scan_iter("frames:*"):
            self.cursors.setdefault(text(key), "0-0")
        batch = self.redis.xread({**self.cursors, "ctl:engine": self.ctl_cursor}, count=120, block=50)
        count = 0
        for key, entries in batch:
            for entry_id, fields in entries:
                if text(key) == "ctl:engine":
                    self.ctl_cursor = text(entry_id)
                    command = json.loads(fields.get(b"json", fields.get("json")))
                    if command.get("cmd") == "end_game":
                        self.ended_games.add(command["game_id"])
                    continue
                frame = _decode(entry_id, fields)
                self.cursors[text(key)] = text(entry_id)
                if (frame.game_id, frame.cam_id) in self.finalized:
                    continue
                session = self.sessions.get(frame.cam_id)
                if session and session.meta["game_id"] != frame.game_id:
                    session.copy_tracks(self.redis)
                    session.close()
                    session = None
                if not session:
                    session = CameraRecording(self.store, frame, self.fps, self.encoder)
                    self.sessions[frame.cam_id] = session
                    raw = self.redis.hgetall(f"game:{frame.game_id}")
                    game = {
                        text(k): text(v)
                        for k, v in raw.items()
                        if text(k) in ("sport", "t0_ms", "status", "teams_json")
                    }
                    atomic_json(session.path.parent / "game.json", {"game_id": frame.game_id, **game})
                count += int(session.add(frame))
        for cam, session in list(self.sessions.items()):
            session.copy_tracks(self.redis)
            status = self.redis.hget(f"game:{session.meta['game_id']}", "status")
            ended = session.meta["game_id"] in self.ended_games or (status and text(status) in ("ended", "finished"))
            tail = self.redis.xrevrange(f"frames:{cam}", count=1)
            drained = not tail or self.cursors.get(f"frames:{cam}") == text(tail[0][0])
            if ended and drained:
                session.close()
                self.finalized.add((session.meta["game_id"], cam))
                del self.sessions[cam]
        self.frames += count
        self.redis.set("recorder:heartbeat", str(time.time()), ex=5)
        return count

    def close(self) -> None:
        for session in self.sessions.values():
            try:
                session.copy_tracks(self.redis)
            finally:
                session.close()
        self.redis.delete("recorder:heartbeat")
