import struct

import fakeredis
import pytest


@pytest.fixture
def r():
    return fakeredis.FakeRedis()


def make_jpeg(w: int = 1280, h: int = 720) -> bytes:
    """A minimal JPEG-shaped buffer: SOI, APP0, SOF0 with (h, w), SOS, EOI. Not decodable; enough for SOF parsing."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, h, w, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    sos = b"\xff\xda" + struct.pack(">H", 12) + b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    return b"\xff\xd8" + app0 + sof0 + sos + b"\x00" * 32 + b"\xff\xd9"


@pytest.fixture
def jpeg():
    return make_jpeg()
