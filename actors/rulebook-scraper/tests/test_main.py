from pathlib import Path

import pytest

from rulebook_scraper.main import default_sources, is_pdf, items_from_response, validate_sources

FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "rulebooks"


def test_default_sources_are_public_pdfs_with_slugs():
    srcs = validate_sources(default_sources())
    assert {s["sport"] for s in srcs} == {"table_tennis", "pickleball", "basketball"}
    assert {s["slug"] for s in srcs} == {"ittf", "usap", "fiba"}
    assert all(s["url"].startswith("https://") and s["kind"] == "pdf" and s["license_note"] for s in srcs)
    assert all("ittf.com" not in s["url"] for s in srcs)  # 403 on 2026-10-24; never evaded


def test_validate_infers_kind_and_slug_and_rejects_bad_input():
    s = validate_sources([{"sport": "x", "url": "https://a/b.PDF", "source": "Test Laws 2026"}])[0]
    assert s["kind"] == "pdf" and s["slug"] == "testlaws2026" and s["skip_patterns"] == []
    for bad in (
        [{"sport": "x", "url": "ftp://a/b"}],
        [{"url": "https://a"}],
        [{"sport": "x", "url": "https://a", "slug": "Bad Slug"}],
        [{"sport": "x", "url": "https://a", "skip_patterns": ["("]}],
    ):
        with pytest.raises(Exception):  # noqa: B017 (ValueError or re.error)
            validate_sources(bad)


def test_pdf_detection():
    assert is_pdf("html", "application/pdf; charset=binary", b"")
    assert is_pdf("html", "", b"%PDF-1.7 ...")
    assert not is_pdf("html", "text/html", b"<html>")


def test_items_from_the_synthetic_pdf_response():
    meta = {"sport": "paddle_pong", "kind": "pdf", "slug": "ttl", "source": "Trophy Test Laws",
            "license_note": "synthetic", "skip_patterns": [r"^\s*National byelaw"]}  # fmt: skip
    items = items_from_response((FIXTURES / "synthetic_laws.pdf").read_bytes(), "application/pdf", meta,
                                "https://example.test/laws.pdf", "2026-10-24T00:00:00+00:00")  # fmt: skip
    assert len(items) == 25 and items[0]["rule_id"] == "ttl:2.1.1" and items[0]["url"].endswith("laws.pdf")
    assert all(i["sport"] == "paddle_pong" and i["source"] == "Trophy Test Laws" for i in items)
