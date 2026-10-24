"""Sports Rulebook Scraper: official rulebook pages and PDFs -> one dataset item per numbered rule.

Input ``{sources: [{sport, url, kind: "html"|"pdf", source, slug, license_note, skip_patterns?}], max_pages,
user_agent}``; without input the bundled ``sources.json`` is used. Public pages only: robots.txt is respected,
one request at a time, a descriptive user agent, no retry on 403/429, and a hard ``max_pages``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apify import Actor
from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import HttpCrawler, HttpCrawlingContext
from crawlee.http_clients import ImpitHttpClient

from .splitter import html_to_text, pdf_to_text, rule_items

SOURCES_FILE = Path(__file__).with_name("sources.json")
KINDS = ("html", "pdf")
DEFAULT_MAX_PAGES = 25
DEFAULT_USER_AGENT = "TrophyRulebookScraper/0.1 (Cal Hacks 13.0 project; +https://github.com/rustybubble/trophy)"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,23}$")


def default_sources() -> list[dict]:
    return json.loads(SOURCES_FILE.read_text("utf8"))["sources"]


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())[:24] or "src"


def validate_sources(sources: list[dict]) -> list[dict]:
    """Normalise and check the input: public http(s) URLs, a kind, a slug per source, string patterns."""
    out = []
    for s in sources:
        if not isinstance(s, dict) or not s.get("url") or not s.get("sport"):
            raise ValueError(f"each source needs sport and url: {s!r}")
        kind = (s.get("kind") or ("pdf" if s["url"].lower().endswith(".pdf") else "html")).lower()
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}: {s!r}")
        if not s["url"].lower().startswith(("http://", "https://")):
            raise ValueError(f"public http(s) URLs only: {s['url']}")
        slug = s.get("slug") or _slugify(s.get("source") or s["url"].split("/")[2])
        if not _SLUG.match(slug):
            raise ValueError(f"slug must match {_SLUG.pattern}: {slug!r}")
        skips = s.get("skip_patterns") or []
        if not all(isinstance(p, str) for p in skips):
            raise ValueError(f"skip_patterns must be strings: {s!r}")
        for p in skips:
            re.compile(p)
        out.append(
            {
                "sport": s["sport"],
                "url": s["url"],
                "kind": kind,
                "source": s.get("source") or s["url"].split("/")[2],
                "slug": slug,
                "license_note": s.get("license_note")
                or "Official rulebook; public page; text (c) the governing body; quoted briefly with a link.",
                "skip_patterns": skips,
            }
        )
    return out


def is_pdf(kind: str, content_type: str, body: bytes) -> bool:
    return kind == "pdf" or "application/pdf" in content_type or body[:5] == b"%PDF-"


def items_from_response(body: bytes, content_type: str, meta: dict[str, Any], url: str, fetched_at: str) -> list[dict]:
    """The dataset items for one fetched source (pure: bytes in, items out)."""
    text = (
        pdf_to_text(body) if is_pdf(meta["kind"], content_type, body) else html_to_text(body.decode("utf8", "replace"))
    )
    return rule_items(
        text,
        sport=meta["sport"],
        slug=meta["slug"],
        url=url,
        source=meta["source"],
        license_note=meta["license_note"],
        fetched_at=fetched_at,
        skip_patterns=meta.get("skip_patterns"),
    )


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        sources = validate_sources(actor_input.get("sources") or default_sources())
        max_pages = int(actor_input.get("max_pages") or DEFAULT_MAX_PAGES)
        user_agent = str(actor_input.get("user_agent") or DEFAULT_USER_AGENT)
        Actor.log.info("rulebook-scraper: %d source(s), max_pages=%d", len(sources), max_pages)
        totals: dict[str, int] = {}
        skipped: list[str] = []

        crawler = HttpCrawler(
            http_client=ImpitHttpClient(browser=None, headers={"User-Agent": user_agent}),
            concurrency_settings=ConcurrencySettings(min_concurrency=1, max_concurrency=1, desired_concurrency=1),
            respect_robots_txt_file=True,
            max_requests_per_crawl=max_pages,
            max_request_retries=0,  # any error skips the source; we never hammer a publisher
            retry_on_blocked=False,
            ignore_http_error_status_codes={403, 429},  # handled below: logged and skipped, never retried
        )

        @crawler.router.default_handler
        async def handle(context: HttpCrawlingContext) -> None:
            meta = dict(context.request.user_data)
            status = context.http_response.status_code
            if status in (403, 429):
                skipped.append(f"{context.request.url} ({status})")
                context.log.warning("%s answered %d; skipped, not retried", context.request.url, status)
                return
            body = await context.http_response.read()
            content_type = str(context.http_response.headers.get("content-type", "")).lower()
            items = items_from_response(
                body, content_type, meta, context.request.url, datetime.now(UTC).isoformat(timespec="seconds")
            )
            if items:
                await context.push_data(items)
            totals[meta["sport"]] = totals.get(meta["sport"], 0) + len(items)
            context.log.info("%s: %d rule(s) from %s", meta["sport"], len(items), context.request.url)

        @crawler.failed_request_handler
        async def failed(context, error: Exception) -> None:
            skipped.append(f"{context.request.url} ({type(error).__name__})")
            context.log.warning("%s failed (%s); skipped", context.request.url, type(error).__name__)

        requests = [
            Request.from_url(
                s["url"],
                user_data={k: s[k] for k in ("sport", "kind", "source", "slug", "license_note", "skip_patterns")},
            )
            for s in sources
        ]
        await crawler.run(requests)
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(totals.items())) or "no rules extracted"
        if skipped:
            summary += f"; skipped: {', '.join(skipped)}"
        await Actor.set_value("SUMMARY", {"rules_per_sport": totals, "skipped": skipped})
        await Actor.set_status_message(f"Done. Rules per sport: {summary}")
