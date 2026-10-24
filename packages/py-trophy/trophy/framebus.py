"""The frame bus (interfaces-v1 §5): the phone WS header, and Redis ``frames:{cam_id}``.

Writers: the gateway (JPEG-WS), aiortc ingest and Agent 2's clip player all use :class:`FrameWriter`.
Readers use :class:`FrameReader`, which never hands out a backlog: ``mode="latest"`` returns only the
newest frame; ``mode="all"`` returns consecutive frames but jumps to the newest when it falls behind.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Literal

import redis

from .streams import frames_key

HEADER = struct.Struct("<BBHId")  # version, flags, reserved, seq, t_capture_phone_ms
HEADER_SIZE = HEADER.size  # 16
VERSION = 1
FLAG_CALIB_STILL = 1 << 0
FLAG_FIRST_AFTER_START = 1 << 1
FRAMES_MAXLEN = 300

Source = Literal["ws", "webrtc", "file"]


@dataclass(frozen=True)
class FrameHeader:
    version: int
    flags: int
    seq: int
    t_capture_phone_ms: float


def pack_header(seq: int, t_capture_phone_ms: float, flags: int = 0) -> bytes:
    return HEADER.pack(VERSION, flags, 0, seq & 0xFFFFFFFF, t_capture_phone_ms)


def parse_message(buf: bytes) -> tuple[FrameHeader, bytes]:
    """Split a phone WS binary message into its header and JPEG bytes."""
    if len(buf) < HEADER_SIZE + 4:
        raise ValueError("frame message too short")
    version, flags, _reserved, seq, t_ms = HEADER.unpack_from(buf, 0)
    if version != VERSION:
        raise ValueError(f"unsupported frame header version {version}")
    jpeg = bytes(buf[HEADER_SIZE:])
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("payload is not a JPEG")
    return FrameHeader(version, flags, seq, t_ms), jpeg


_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(jpeg: bytes) -> tuple[int, int]:
    """(w, h) from the JPEG SOF marker, without decoding."""
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    i, n = 2, len(jpeg)
    while i + 4 <= n:
        if jpeg[i] != 0xFF:
            i += 1
            continue
        marker = jpeg[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack_from(">H", jpeg, i + 2)[0]
        if marker in _SOF:
            h, w = struct.unpack_from(">HH", jpeg, i + 5)
            return w, h
        if marker == 0xDA:  # start of scan before any SOF
            break
        i += 2 + seg_len
    raise ValueError("no SOF marker in JPEG")


@dataclass(frozen=True)
class Frame:
    entry_id: str
    game_id: str
    cam_id: str
    seq: int
    t_phone_ms: float
    t_srv_ms: float
    t_game_s: float
    sync_err_ms: float
    w: int
    h: int
    source: str
    flags: int
    data: bytes  # JPEG


class FrameWriter:
    def __init__(self, r: redis.Redis, maxlen: int = FRAMES_MAXLEN) -> None:
        self.r = r
        self.maxlen = maxlen

    def write(
        self,
        *,
        game_id: str,
        cam_id: str,
        seq: int,
        t_phone_ms: float,
        t_srv_ms: float,
        t_game_s: float,
        sync_err_ms: float,
        jpeg: bytes,
        source: Source = "ws",
        flags: int = 0,
        size: tuple[int, int] | None = None,
    ) -> str:
        w, h = size or jpeg_size(jpeg)
        entry_id = self.r.xadd(
            frames_key(cam_id),
            {
                "v": "1",
                "game_id": game_id,
                "cam_id": cam_id,
                "seq": str(seq),
                "t_phone_ms": repr(float(t_phone_ms)),
                "t_srv_ms": repr(float(t_srv_ms)),
                "t_game_s": repr(float(t_game_s)),
                "sync_err_ms": repr(float(sync_err_ms)),
                "w": str(w),
                "h": str(h),
                "fmt": "jpeg",
                "source": source,
                "flags": str(flags),
                "data": jpeg,
            },
            maxlen=self.maxlen,
            approximate=True,
        )
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id


def _decode(entry_id: bytes | str, fields: dict) -> Frame:
    def g(k: str) -> bytes:
        v = fields.get(k.encode(), fields.get(k))
        if v is None:
            raise KeyError(k)
        return v if isinstance(v, bytes) else str(v).encode()

    return Frame(
        entry_id=entry_id.decode() if isinstance(entry_id, bytes) else entry_id,
        game_id=g("game_id").decode(),
        cam_id=g("cam_id").decode(),
        seq=int(g("seq")),
        t_phone_ms=float(g("t_phone_ms")),
        t_srv_ms=float(g("t_srv_ms")),
        t_game_s=float(g("t_game_s")),
        sync_err_ms=float(g("sync_err_ms")),
        w=int(g("w")),
        h=int(g("h")),
        source=g("source").decode(),
        flags=int(fields.get(b"flags", fields.get("flags", b"0"))),
        data=g("data"),
    )


class FrameReader:
    """Reads ``frames:{cam_id}`` without ever processing a backlog.

    ``mode="latest"``: each :meth:`read` returns the newest frame not yet returned (or ``None``).
    ``mode="all"``: consecutive frames in order (for trackers that need every frame), but if more than
    ``max_lag`` frames are pending it skips to the newest. Frames repeating the previous ``seq`` are
    dropped (dedupe by seq). Use a ``decode_responses=False`` Redis client.
    """

    def __init__(
        self,
        r: redis.Redis,
        cam_id: str,
        mode: Literal["latest", "all"] = "latest",
        max_lag: int = 5,
    ) -> None:
        self.r = r
        self.key = frames_key(cam_id)
        self.mode = mode
        self.max_lag = max_lag
        self.last_id: str | None = None
        self.last_seq: int | None = None
        self.skipped = 0

    def _newest(self) -> Frame | None:
        got = self.r.xrevrange(self.key, count=1)
        return _decode(*got[0]) if got else None

    def read(self, block_ms: int = 50) -> Frame | None:
        if self.last_id is None:
            f = self._newest()
            if f is None and block_ms:
                got = self.r.xread({self.key: "$"}, count=1, block=block_ms)
                f = _decode(*got[0][1][-1]) if got else None
            return self._accept(f)

        if self.mode == "latest":
            f = self._newest()
            if f is not None and f.entry_id != self.last_id:
                return self._accept(f)
            if not block_ms:
                return None
            got = self.r.xread({self.key: self.last_id}, block=block_ms)
            if not got:
                return None
            f = self._newest()
            return self._accept(f) if f and f.entry_id != self.last_id else None

        got = self.r.xread({self.key: self.last_id}, count=self.max_lag + 1, block=block_ms or None)
        if not got:
            return None
        entries = got[0][1]
        if len(entries) > self.max_lag:
            newest = self._newest()
            self.skipped += len(entries)  # at least this many dropped
            return self._accept(newest)
        for entry in entries:
            f = _decode(*entry)
            self.last_id = f.entry_id
            if f.seq == self.last_seq:
                continue
            self.last_seq = f.seq
            return f
        return None

    def _accept(self, f: Frame | None) -> Frame | None:
        if f is None:
            return None
        self.last_id = f.entry_id
        if f.seq == self.last_seq and self.mode == "all":
            return None
        self.last_seq = f.seq
        return f
