# Sports Rulebook Scraper (Apify actor)

Turns **official, public sports rulebooks** (PDFs or HTML pages) into **one dataset item per numbered rule clause**, the shape a retrieval index wants. Built for [Trophy](https://github.com/rustybubble/trophy), the universal AI referee for pickup games: Trophy indexes this actor's dataset in **Moss** and lets players *ask the ref* a rules question by voice; Claude answers **only** from the retrieved clauses, with citations that link back to the `url` below.

```json
{
  "sport": "table_tennis",
  "rule_id": "ittf:2.6.2",
  "number": "2.6.2",
  "title": "2.6 The Service",
  "text": "The server shall then project the ball near vertically upwards …",
  "url": "https://www.tabletennisengland.co.uk/…/Laws-of-Table-Tennis-2026-27.pdf",
  "source": "The Laws of Table Tennis 2026-27 (ITTF Laws, chapter 2 …)",
  "section_path": ["2 The Laws Of Table Tennis", "2.6 The Service"],
  "license_note": "(c) ITTF / Table Tennis England. Scraped from a public PDF; quoted <= 25 words with a link …",
  "fetched_at": "2026-10-24T22:10:03+00:00",
  "content_hash": "3f1c…"
}
```

## Input
`{sources: [{sport, url, kind: "html"|"pdf", source, slug, license_note, skip_patterns?: [regex]}], max_pages: 25, user_agent}`.
With no input the bundled [`src/rulebook_scraper/sources.json`](src/rulebook_scraper/sources.json) is used (a proposed list: ITTF Laws via Table Tennis England's PDF, the 2026 USA Pickleball rulebook via Pickleball Canada's PDF, FIBA Official Basketball Rules). `rule_id` is `"<slug>:<number>"` (`ittf:2.6.2`, `usap:11.A`), stable across runs so an index can be refreshed by id. `skip_patterns` drop paragraphs such as national byelaw boxes.

## Output
One dataset item per clause: `sport, rule_id, number, title, text, url, source, section_path, license_note, fetched_at, content_hash`. A clause longer than 2000 characters (the Moss chunk limit) is split at sentence ends into `<number>#2`, `#3`, …. The key-value store gets `SUMMARY` = `{rules_per_sport, skipped}`.

## How it splits (`splitter.py`, pure functions)
A clause starts on a line that begins with a hierarchical number (`2.6.2`, `12.1.1`, `7.A.`) and runs until the next one, so wrapped PDF lines carry over. A short numbered line that does not end a sentence (`2.6 THE SERVICE`) is a section heading and becomes the `title` / `section_path` of the clauses under it; an all-caps or `Art. 12` line is a chapter heading. Contents lines (dot leaders), page numbers and byelaw boxes are dropped; a wrapped measurement (`1.50 m wide`) or an out-of-order number is not mistaken for a clause. HTML loses script/style/nav/header/footer (BeautifulSoup); PDFs are read with pypdf.

## Crawl policy
Public pages only, nothing behind a login or paywall. `robots.txt` is respected (Crawlee `respect_robots_txt_file`), **one request at a time**, a descriptive user agent with a contact link, **no retry on 403/429** (the source is skipped and listed in `SUMMARY.skipped`; we never work around bot protection), and a hard `max_pages`. Rulebook text is copyrighted: Trophy keeps the full text locally, shows at most 25-word quotes with a link, and records `source` and `license_note` on every item.

## Run
```sh
cd actors/rulebook-scraper
uv sync && uv run pytest -q                 # splitter + input tests on the synthetic fixture (no network)
npx apify-cli run --purge                   # local run with the bundled sources -> storage/datasets/default/
npx apify-cli run --purge --input-file my-input.json
cd ../../services/rules && uv run trophy-rules dataset export   # -> data/local/rulebooks/<sport>.jsonl (gitignored)
```
`apify push` (build on the platform) and publishing on the Apify Store need the project owner's OK. On the platform, Trophy's `trophy-rules dataset export --actor <id>` pulls the last successful run's dataset with `APIFY_TOKEN`.

**Verified locally (2026-10-24, Apify CLI 1.10.0, `apify 4.1.0`, `crawlee 1.11.0`, `pypdf 6.21`):** a run against a local server with one allowed PDF (the synthetic laws), one URL answering 403 and one path disallowed by `robots.txt` produced 25 items, skipped the 403 without a retry, never requested the disallowed path, and sent the configured user agent on every request; wall time 3 s.

## Limits
- Numbering styles not yet covered: unnumbered bullet rulebooks, roman numerals, "Rule 4 Section 2" prose numbering.
- PDF text extraction depends on the publisher's PDF having a text layer (no OCR).
- The bundled sources are a proposal; confirm every URL and its terms before a run (`ittf.com/handbook` answered 403 on 2026-10-24 and is deliberately not used).

## Files
`.actor/actor.json`, `.actor/input_schema.json` (Apify actor spec v1), `Dockerfile` (`apify/actor-python:3.11`), `requirements.txt` (mirrors `pyproject.toml`), `src/__main__.py` (the CLI's `python -m src` entry), `src/rulebook_scraper/{main,splitter,sources.json}`, `tools/make_synthetic_pdf.py`, `tests/`. Fixtures: `evals/fixtures/rulebooks/synthetic_laws.{txt,pdf}` (invented "paddle pong" laws, labelled synthetic; no real rulebook text is committed).
