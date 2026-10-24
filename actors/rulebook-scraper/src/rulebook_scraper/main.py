"""Sports Rulebook Scraper: official rulebook pages and PDFs -> one dataset item per rule.

Input ``{sources: [{sport, url, kind: "html"|"pdf", source?, license_note?}]}``; without
input the bundled ``sources.json`` is used. Public pages only; robots.txt is respected.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from apify import Actor
from crawlee import Request
from crawlee.crawlers import HttpCrawler, HttpCrawlingContext

from .splitter import html_to_text, pdf_to_text, rule_items

SOURCES_FILE = Path(__file__).with_name("sources.json")
KINDS = ("html", "pdf")


def default_sources() -> list[dict]:
    return json.loads(SOURCES_FILE.read_text("utf8"))["sources"]


def _validate(sources: list[dict]) -> list[dict]:
    out = []
    for s in sources:
        if not isinstance(s, dict) or not s.get("url") or not s.get("sport"):
            raise ValueError(f"each source needs sport and url: {s!r}")
        kind = (s.get("kind") or ("pdf" if s["url"].lower().endswith(".pdf") else "html")).lower()
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}: {s!r}")
        if not s["url"].lower().startswith(("http://", "https://")):
            raise ValueError(f"public http(s) URLs only: {s['url']}")
        out.append({**s, "kind": kind})
    return out


def _is_pdf(kind: str, content_type: str, body: bytes) -> bool:
    return kind == "pdf" or "application/pdf" in content_type or body[:5] == b"%PDF-"


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        sources = _validate(actor_input.get("sources") or default_sources())
        Actor.log.info("rulebook-scraper: %d source(s)", len(sources))
        totals: dict[str, int] = {}

        crawler = HttpCrawler(
            respect_robots_txt_file=True,
            max_requests_per_crawl=len(sources),
            max_request_retries=2,
        )

        @crawler.router.default_handler
        async def handle(context: HttpCrawlingContext) -> None:
            meta = dict(context.request.user_data)
            body = await context.http_response.read()
            content_type = str(context.http_response.headers.get("content-type", "")).lower()
            if _is_pdf(meta["kind"], content_type, body):
                text = pdf_to_text(body)
            else:
                text = html_to_text(body.decode("utf8", "replace"))
            items = rule_items(
                text,
                sport=meta["sport"],
                url=context.request.url,
                source=meta.get("source") or context.request.url.split("/")[2],
                license_note=meta.get("license_note") or "Official rulebook; public page; text © the governing body.",
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            if items:
                await context.push_data(items)
            totals[meta["sport"]] = totals.get(meta["sport"], 0) + len(items)
            context.log.info("%s: %d rule(s) from %s", meta["sport"], len(items), context.request.url)

        requests = [
            Request.from_url(
                s["url"],
                user_data={k: s.get(k) for k in ("sport", "kind", "source", "license_note")},
            )
            for s in sources
        ]
        await crawler.run(requests)
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(totals.items())) or "no rules extracted"
        await Actor.set_status_message(f"Done. Rules per sport: {summary}")
