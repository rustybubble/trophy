"""The frame bus (interfaces-v1 §5): the phone WS header, and Redis ``frames:{cam_id}``.

Writers: the gateway (JPEG-WS), aiortc ingest and Agent 2's clip player all use :class:`FrameWriter`.
Readers use :class:`FrameReader`, which never hands out a backlog: ``mode="latest"`` returns only the
newest frame; ``mode="all"`` returns consecutive frames but jumps to the newest when it falls behind.
"""

from __future__ import annotations

import struct
from collections import deque
from dataclasses import dataclass
from typing import Literal

import redis

from .streams import frames_key

HEADER = struct.Struct("<BBHId")  # version, flags, reserved, seq, t_capture_phone_ms
HEADER_SIZE = HEADER.size  # 16
CROP = struct.Struct("<4f")  # x, y, w, h of the region sent, normalised to the camera's full view
VERSION = 1
FLAG_CALIB_STILL = 1 << 0
FLAG_FIRST_AFTER_START = 1 << 1
FLAG_CROP = 1 << 2  # the header is followed by CROP (16 bytes): the frame shows only that region of the view
FRAMES_MAXLEN = 300

Source = Literal["ws", "webrtc", "file"]
Crop = tuple[float, float, float, float]


@dataclass(frozen=True)
class FrameHeader:
    version: int
    flags: int
    seq: int
    t_capture_phone_ms: float
    crop: Crop | None = None


def pack_header(seq: int, t_capture_phone_ms: float, flags: int = 0, crop: Crop | None = None) -> bytes:
    if crop is None:
        return HEADER.pack(VERSION, flags & ~FLAG_CROP, 0, seq & 0xFFFFFFFF, t_capture_phone_ms)
    return HEADER.pack(VERSION, flags | FLAG_CROP, 0, seq & 0xFFFFFFFF, t_capture_phone_ms) + CROP.pack(*crop)


def _valid_crop(c: Crop) -> bool:
    x, y, w, h = c
    return 0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1.0001 and y + h <= 1.0001


def parse_message(buf: bytes) -> tuple[FrameHeader, bytes]:
    """Split a phone WS binary message into its header (with its crop, if flagged) and JPEG bytes."""
    if len(buf) < HEADER_SIZE + 4:
        raise ValueError("frame message too short")
    version, flags, _reserved, seq, t_ms = HEADER.unpack_from(buf, 0)
    if version != VERSION:
        raise ValueError(f"unsupported frame header version {version}")
    start, crop = HEADER_SIZE, None
    if flags & FLAG_CROP:
        if len(buf) < HEADER_SIZE + CROP.size + 4:
            raise ValueError("frame message too short for its crop")
        x, y, w, h = (round(v, 5) for v in CROP.unpack_from(buf, HEADER_SIZE))
        crop = (x, y, w, h)
        if not _valid_crop(crop):
            raise ValueError(f"bad crop {crop}")
        start += CROP.size
    jpeg = bytes(buf[start:])
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("payload is not a JPEG")
    return FrameHeader(version, flags, seq, t_ms, crop), jpeg


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
    crop: Crop | None = None  # the region of the camera's view this frame shows (normalised x, y, w, h)


def frame_fields(
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
    crop: Crop | None = None,
) -> dict[str, str | bytes]:
    """The fields of one ``frames:{cam}`` entry (§5.2). Async writers XADD these themselves."""
    w, h = size or jpeg_size(jpeg)
    extra = {"crop": ",".join(repr(float(v)) for v in crop)} if crop is not None else {}
    return {
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
        **extra,
        "data": jpeg,
    }


class FrameWriter:
    def __init__(self, r: redis.Redis, maxlen: int = FRAMES_MAXLEN) -> None:
        self.r = r
        self.maxlen = maxlen

    def write(self, *, cam_id: str, **kw) -> str:
        """Keyword args as :func:`frame_fields`. Returns the stream entry id."""
        entry_id = self.r.xadd(
            frames_key(cam_id), frame_fields(cam_id=cam_id, **kw), maxlen=self.maxlen, approximate=True
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
        crop=_crop(fields.get(b"crop", fields.get("crop"))),
    )


def _crop(v: bytes | str | None) -> Crop | None:
    if v is None:
        return None
    x, y, w, h = (float(p) for p in (v.decode() if isinstance(v, bytes) else v).split(","))
    return (x, y, w, h)


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
        self._pending: deque = deque()  # entries fetched in one XREAD and not yet returned ("all" mode)

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

        while True:
            while self._pending:  # serve what one XREAD fetched before fetching again (a backlog costs one read)
                f = _decode(*self._pending.popleft())
                self.last_id = f.entry_id
                if f.seq == self.last_seq:
                    continue
                self.last_seq = f.seq
                return f
            got = self.r.xread({self.key: self.last_id}, count=self.max_lag + 1, block=block_ms or None)
            if not got:
                return None
            entries = got[0][1]
            if len(entries) > self.max_lag:
                newest = self._newest()
                self.skipped += len(entries)  # at least this many dropped
                return self._accept(newest)
            self._pending.extend(entries)

    def _accept(self, f: Frame | None) -> Frame | None:
        if f is None:
            return None
        self.last_id = f.entry_id
        if f.seq == self.last_seq and self.mode == "all":
            return None
        self.last_seq = f.seq
        return f
