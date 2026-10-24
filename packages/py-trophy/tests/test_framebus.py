import pytest
from conftest import make_jpeg

from trophy.framebus import (
    FLAG_FIRST_AFTER_START,
    HEADER_SIZE,
    FrameReader,
    FrameWriter,
    jpeg_size,
    pack_header,
    parse_message,
)


def test_header_is_16_bytes_little_endian():
    h = pack_header(0x01020304, 1234.5, FLAG_FIRST_AFTER_START)
    assert len(h) == HEADER_SIZE == 16
    assert h[0] == 1 and h[1] == 2 and h[4:8] == b"\x04\x03\x02\x01"


def test_parse_message_roundtrip(jpeg):
    hdr, body = parse_message(pack_header(7, 1.7e12 + 0.25) + jpeg)
    assert (hdr.seq, hdr.t_capture_phone_ms, hdr.flags) == (7, 1.7e12 + 0.25, 0)
    assert body == jpeg


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"\x01" * 20,
        pack_header(1, 0) + b"notjpeg!",
        b"\x02" + pack_header(1, 0)[1:] + b"\xff\xd8\xff\xd9",
    ],
)
def test_parse_message_rejects(bad):
    with pytest.raises(ValueError):
        parse_message(bad)


def test_jpeg_size():
    assert jpeg_size(make_jpeg(1280, 720)) == (1280, 720)
    assert jpeg_size(make_jpeg(640, 360)) == (640, 360)


def _write(fw, seq, jpeg, cam="c_abcdef"):
    return fw.write(
        game_id="g_abcdefgh",
        cam_id=cam,
        seq=seq,
        t_phone_ms=1000.0 + seq,
        t_srv_ms=2000.0 + seq,
        t_game_s=seq / 30,
        sync_err_ms=3.0,
        jpeg=jpeg,
    )


def test_writer_fields_and_latest_reader(r, jpeg):
    fw = FrameWriter(r)
    rd = FrameReader(r, "c_abcdef", mode="latest")
    assert rd.read(block_ms=0) is None
    for s in range(5):
        _write(fw, s, jpeg)
    f = rd.read(block_ms=0)
    assert f.seq == 4 and (f.w, f.h) == (1280, 720) and f.data == jpeg and f.source == "ws"
    assert rd.read(block_ms=0) is None  # nothing new
    _write(fw, 5, jpeg)
    _write(fw, 6, jpeg)
    assert rd.read(block_ms=0).seq == 6  # skips 5: latest wins


def test_all_reader_consecutive_then_skips_backlog(r, jpeg):
    fw = FrameWriter(r)
    _write(fw, 0, jpeg)
    rd = FrameReader(r, "c_abcdef", mode="all", max_lag=3)
    assert rd.read(block_ms=0).seq == 0
    _write(fw, 1, jpeg)
    _write(fw, 1, jpeg)  # duplicate seq is dropped
    _write(fw, 2, jpeg)
    assert [rd.read(block_ms=0).seq, rd.read(block_ms=0).seq] == [1, 2]
    for s in range(3, 20):
        _write(fw, s, jpeg)
    assert rd.read(block_ms=0).seq == 19  # fell behind -> newest
    assert rd.skipped > 0


def test_all_reader_fetches_a_backlog_once(r, jpeg):
    fw = FrameWriter(r)
    _write(fw, 0, jpeg)
    rd = FrameReader(r, "c_abcdef", mode="all", max_lag=8)
    assert rd.read(block_ms=0).seq == 0
    for s in range(1, 7):
        _write(fw, s, jpeg)
    calls = []
    real = r.xread
    r.xread = lambda *a, **k: calls.append(1) or real(*a, **k)
    assert [rd.read(block_ms=0).seq for _ in range(6)] == [1, 2, 3, 4, 5, 6]
    assert len(calls) == 1  # not one XREAD (re-fetching the whole backlog) per frame
    assert rd.read(block_ms=0) is None


def test_stream_is_capped(r, jpeg):
    fw = FrameWriter(r, maxlen=10)
    for s in range(50):
        _write(fw, s, jpeg)
    assert r.xlen("frames:c_abcdef") < 50
