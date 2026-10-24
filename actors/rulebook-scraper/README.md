# Sports Rulebook Scraper (Apify actor)

Turns official sports rulebooks into **one dataset item per numbered rule clause**, the shape Trophy's ask-the-ref indexes into Moss (`docs/plan/interfaces-v1.md` §17):

```json
{"sport": "table_tennis", "rule_id": "2.6.2", "title": "2.6 The Service", "text": "The server shall then project the ball near vertically upwards …", "url": "https://www.ittf.com/handbook/", "source": "ITTF Handbook, chapter 2", "license_note": "© ITTF …", "fetched_at": "2026-10-24T18:00:00+00:00"}
```

**Input** `{sources: [{sport, url, kind: "html"|"pdf", source?, license_note?}]}`; with no input the bundled `src/rulebook_scraper/sources.json` is used (ITTF laws, USA Pickleball rulebook, FIBA official rules, BWF laws, FIVB rules). **Public pages only**, no login or paywall; the crawler respects `robots.txt` (`respect_robots_txt_file=True`) and skips what it may not fetch.

**Splitting** (`splitter.py`): a clause starts on a line that begins with a numbered heading such as `2.6.2`, `12.1.1` or `7.A.`; it runs until the next heading. Short top-level headings (`2.6 THE SERVICE`) become the `title` of the clauses under them. Dot-leader contents lines and page numbers are dropped; when an id appears twice (contents + body) the longer text wins; fragments under 20 characters are not rules. HTML is stripped of script/style/nav/header/footer with BeautifulSoup; PDFs are read with `pypdf`.

## Status: not run, not published
This actor has **not been run on Apify and has not been published to the Apify Store**: both need the user's OK (publishing is the Best Actor submission; a run spends Apify credit and fetches third-party pages). The ITTF and BWF sites answered 403 to our dev-box fetcher on 2026-10-24, so confirm those two URLs in `sources.json` before the first run. No rulebook text is checked into this repo.

## Run (once approved)
```sh
cd actors/rulebook-scraper
uv sync && uv run pytest -q              # unit tests on inline HTML/PDF-text fixtures (no network)
apify login                               # the user's account
apify run                                 # local run: input from storage/key_value_stores/default/INPUT.json; dataset in storage/datasets/default
apify push                                # build on the platform (the user's OK)
```
On the platform the run's default dataset is what `services/rules`' `rules index build --sport table_tennis` pulls (via `APIFY_TOKEN`).

## Files
`.actor/actor.json`, `.actor/input_schema.json` (Apify actor spec v1), `Dockerfile` (the Apify Python template, image `apify/actor-python:3.11`), `requirements.txt` (mirrors `pyproject.toml`), `src/rulebook_scraper/{main,splitter,sources.json}`, `tests/`.

**Pins** (verified against PyPI and docs.apify.com / crawlee.dev on 2026-10-24): `apify 4.1`, `crawlee[beautifulsoup] 1.11` (`HttpCrawler`, `HttpCrawlingContext.http_response.read()`, `Request.from_url(url, user_data=…)`, `context.push_data`), `beautifulsoup4 4.13+`, `pypdf 6`.
