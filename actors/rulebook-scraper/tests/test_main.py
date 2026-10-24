import pytest

from rulebook_scraper.main import _is_pdf, _validate, default_sources


def test_default_sources_are_public_and_well_formed():
    srcs = _validate(default_sources())
    assert {s["sport"] for s in srcs} >= {"table_tennis", "pickleball", "basketball", "badminton", "volleyball"}
    assert all(s["url"].startswith("https://") and s["kind"] in ("html", "pdf") for s in srcs)


def test_validate_infers_kind_and_rejects_bad_input():
    assert _validate([{"sport": "x", "url": "https://a/b.PDF"}])[0]["kind"] == "pdf"
    with pytest.raises(ValueError):
        _validate([{"sport": "x", "url": "ftp://a/b"}])
    with pytest.raises(ValueError):
        _validate([{"url": "https://a"}])


def test_pdf_detection():
    assert _is_pdf("html", "application/pdf; charset=binary", b"")
    assert _is_pdf("html", "", b"%PDF-1.7 ...")
    assert not _is_pdf("html", "text/html", b"<html>")
