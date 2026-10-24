# Agent 3, Part 2 status: the rulebook capability (Apify actor → Moss → `/ask` with citations → `rule_ref`)

*Branch `claude/distracted-davinci-69e418` (worktree `.claude/worktrees/distracted-davinci-69e418`). Brief:
`docs/plan/prompts/agent-3-part-2-rulebook.md`. Newest entries first. Part 1 (the Droid compiler, PR #6) has its own
file, `docs/status/a3.md`.*

## Now (2026-10-24, evening)
- **Built, key-free parts done; blocked on keys for everything live.** None of `ANTHROPIC_API_KEY`,
  `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY` is set on this Mac (`.env.local` has the names, empty). Asked the user (through
  the Part 1 session, 2026-10-24) for: the keys / a Moss project, approval of `sources.json`, and the OK to run the
  actor against the three public PDFs. Until then: no Moss index, no measured `/ask`, no eval numbers, no spikes (a)
  and (b). Everything that measures is a `live` test that prints its skip reason.
- **Clash with PR #6, handled by building on it.** PR #6 (`a3/wk-rules-droid`, "stages 2–3") already carried a
  `services/rules` service and an actor at `actors/rulebook-scraper/` (fakes only, never run live) that the Part 2
  brief assumed would not exist. Writing a parallel service would collide at merge, so this branch **took PR #6's
  versions of `services/rules/**` and `actors/rulebook-scraper/**` as its base and reworked them to the brief**. The
  actor stays at `actors/rulebook-scraper/` (deviation from the brief's `services/rules/actors/…`) to keep the
  eventual merge small. Removed from `services/rules`: the moment index and `/coach` (Part 3 scope; the coach tip had
  a template fallback). When #6 merges, this branch rebases and keeps its versions of those paths, `.env.example`'s
  rulebooks block and the separate `rules:` CI job.

## Findings: where PR #6's rules service and actor deviate from the Part 2 brief (requested by the planning session, 2026-10-24)
Anchors are in `origin/a3/wk-rules-droid` @ `f819f87` (PR #6). "Fixed in #8" means this branch's rework already
addresses it; nothing here edits PR #6's branch.

| # | File:line (PR #6) | What | Why it matters | In #8 |
|---|---|---|---|---|
| 1 | `services/rules/rules/search.py:56-57, 150` | One Moss index **per sport** (`rules-<sport>`), plus one per game for moments | The free Developer plan allows 3 indexes; 3 sports + any moment index exceeds it. The brief's design is one index with a `sport` filter | one index `trophy-rules-v1` + filter (D-30) |
| 2 | `services/rules/rules/app.py:30, 49, 113-114`; `cli.py:65` | No startup key check: the app boots keyless, `/healthz` answers `ok: true`, routes return 503 `not_configured`; `serve` runs uvicorn without checking keys | The brief and the user's rule: refuse to start without the 3 keys (exit 3, one line). The gateway's health probe would show `rules` healthy while every `/ask` fails | `require_keys()` at startup, exit 3; index load fails fast |
| 3 | `services/rules/rules/ask.py:75-80` | `verified_quote` **replaces** a non-verbatim quote with the clause's first 25 words | A fabricated or wrong quote is silently swapped for a generic one, so the citation looks verified when the model's claim wasn't; the brief says drop failing citations and return `found: false` when none survive | citations dropped; zero survivors → not found |
| 4 | `services/rules/rules/search.py:140` | `QueryOptions(top_k=top_k)` only: no `sport` filter, no `alpha`, no clause-number keyword pass | Needed for one index; hybrid tuning and "law 2.6.2" questions | filter + alpha 0.8 / 0.3 merge |
| 5 | `services/rules/rules/app.py:152` | `GET /rule_ref?sport&q` = top-1 search only; no exact resolution of the pack's `"ITTF 2.6.2"` strings, no gate | Part 1's `rules.yaml` refs must resolve exactly; a search-only ref can point at the wrong clause with no signal | `POST /rule_ref` exact via `get_docs`, else gated search, `how` field |
| 6 | `actors/rulebook-scraper/src/rulebook_scraper/splitter.py:146` | `rule_id` is the bare number (`2.6.2`) with no source slug | Ids collide across sources (ITTF 2.1 vs FIBA 2.1) and can't be looked up by `get_docs` in one index | `"<slug>:<number>"` |
| 7 | `actors/rulebook-scraper/src/rulebook_scraper/sources.json:6, 13` | Sources include `ittf.com/handbook/` (403 on 2026-10-24) and a 2025 USA Pickleball URL (404'd) | A run would skip table tennis entirely; the brief names the TTE and Pickleball Canada PDFs | proposed list (awaiting approval) |
| 8 | `actors/rulebook-scraper/src/rulebook_scraper/main.py:52-55` | `max_request_retries=2`, default concurrency, the HTTP client's default browser-impersonation headers, no `max_pages` input | The brief's crawl policy: no retry on 403/429, one request at a time, a descriptive UA with contact, a hard cap | retries 0, concurrency 1, named UA, `max_pages`, 403/429 skipped |
| 9 | `actors/rulebook-scraper/tests/test_splitter.py:11, 35`; `services/rules/tests/conftest.py` (`RULES`) | Verbatim ITTF clauses (> 25 words) committed as test fixtures | CLAUDE.md / brief: no real rulebook text in the repo beyond ≤ 25-word quotes | synthetic "Trophy Test Laws" fixtures |
| 10 | `services/rules/rules/app.py:168-176`, `rules/coach.py:2, 52, 68` | `/moments/index`, `/search_moments`, `/coach` with **template tips** as a fallback | Part 3 scope; the template tip is a keyless fallback path the user ruled out | removed |
| 11 | `services/rules/rules/llm.py:29-32` | `system=` as a plain string, no `cache_control`; `max_tokens=2048`; no usage/cache logging | Every ask pays the full system prompt; the brief asks for a cached prefix and `cache_read_input_tokens` checks | cached system block, 600 tokens, usage logged |
| 12 | `services/rules/rules/config.py:45, 53` | Model from `CLAUDE_MODEL`, threshold `RULES_MIN_SCORE`; no `ASK_EFFORT`, `ASK_TOP_K`, `MOSS_INDEX` | The brief's knobs are `ASK_MODEL`, `ASK_EFFORT`, `ASK_MIN_SCORE`, `ASK_TOP_K`, `MOSS_INDEX`, and switching the model is a user decision | the brief's names, in the rulebooks block |
| 13 | `.github/workflows/ci.yml:37, 45` (PR #6) | Rules and actor steps inside the `python` job | The brief wants a separate `rules:` job so the rebase is clean | separate job |
| 14 | missing | No `/clauses`, `eval`, `check-pack`, `dataset export`, `index status/refresh`, no `evals/ask/*.jsonl`, no live tests, no `latency` numbers | The brief's acceptance list needs them | all present; numbers await keys |
| — | `actors/rulebook-scraper/` | Location at the repo root, not `services/rules/actors/` | Fine (planning session, 2026-10-24); recorded as a deviation from the brief | kept |

## What is built (2026-10-24)
| Piece | Where | Checked by |
|---|---|---|
| **Actor "Sports Rulebook Scraper"**: PDF/HTML → one dataset item per numbered clause `{sport, rule_id: "<slug>:<number>", number, title, text, url, source, section_path, license_note, fetched_at, content_hash}`; headings → `title`/`section_path`; contents lines, page numbers, byelaw boxes (`skip_patterns`) dropped; wrapped measurements and out-of-order numbers not mistaken for clauses; > 2000-char clauses split into `#2…`; robots.txt respected, one request at a time, descriptive UA, **no retry on 403/429**, hard `max_pages`; `SUMMARY` in the KV store | `actors/rulebook-scraper/` | 15 pytest on the synthetic fixtures; **`apify run` end to end** (below) |
| Synthetic fixtures: invented "Trophy Test Laws of Paddle Pong" (`.txt`) and a 2-page PDF generated without a PDF library (9.4 KB) | `evals/fixtures/rulebooks/`, `actors/rulebook-scraper/tools/make_synthetic_pdf.py` | the PDF splits identically to the text (test); CI regenerates it and diffs |
| **`services/rules`**: startup requires the 3 keys (exit 3, one line) and loads **one Moss index `trophy-rules-v1`** with a `sport` filter (D-30); `POST /ask` = Moss top-5 (alpha 0.8, + alpha 0.3 when the question names a clause) → score gate (`ASK_MIN_SCORE`, no Claude call below it) → Claude `claude-opus-5-5` effort low, structured output, cached system prompt → **server-side grounding check** (cited id ∈ retrieved, quote verbatim ≤ 25 words, otherwise **dropped**; zero survivors → `found: false`) → `{answer, speech, citations, found, moss_ms, llm_ms, latency_ms, model, top_score, retrieved}`; `POST /rule_ref` ("ITTF 2.6.2" → `ittf:2.6.2` via `get_docs`, else search alpha 0.5 top-1 with the same gate); `GET /clauses` (Markdown for the Droid); `GET /healthz` | `services/rules/rules/` | 39 pytest (doubles at the SDK boundary) + 2 `live` tests skipped without keys |
| CLI `trophy-rules serve | index build/refresh/status | dataset export | eval | check-pack` | `rules/cli.py` | exit-3 tests; eval + check-pack tests on the doubles |
| Eval sets: 17 table-tennis questions (the 5 demo ones first, 2 out-of-rulebook) and 7 pickleball; expected ids **provisional** until checked against the indexed text | `evals/ask/` | run needs keys |
| CI job `rules:` (service + actor lint/tests, fixture regeneration diff, `apify validate-schema`) | `.github/workflows/ci.yml` | on this PR |
| Env knobs inside the rulebooks block; `.env.local` now gitignored (it was not) | `.env.example`, `.gitignore` | |

### Measured (2026-10-24, this Mac, M-series, single runs)
| What | Value | Method |
|---|---|---|
| Actor local run (`npx apify-cli@1.10.0 run --purge`, `apify 4.1.0`, `crawlee 1.11.0`, `pypdf 6.21.2`) | **25 items** from the 2-page synthetic PDF; the 403 source skipped, not retried; the robots-disallowed path **never requested**; the configured UA on all 3 requests; **3 s** wall | a local `http.server` with `laws.pdf`, `forbidden.pdf` (403) and `robots.txt` (`Disallow: /private/`); access log checked |
| Moss: create (≈ 50 docs, 2 sports) / cold `load_index` / per-query ms / filter isolation | **not measured: no keys** | `tests/live/test_live_spikes.py::test_moss_spike` writes `data/local/spikes/moss-spike.json` |
| Claude: one `/ask`-shaped structured call at effort low; second call's `cache_read_input_tokens` | **not measured: no keys** | `tests/live/test_live_spikes.py::test_claude_spike` |
| `/ask` p50/p95, hit@5, citation precision, `found` accuracy; `ASK_MIN_SCORE` tuning; the 5 demo answers hand-checked | **not measured: no keys, no index** | `trophy-rules eval --sport table_tennis` |
| `check-pack sports/table_tennis/rules.yaml` | **not run: no index** (and the pack is on PR #6's branch) | `trophy-rules check-pack` |

## Sources (proposed, awaiting approval)
`actors/rulebook-scraper/src/rulebook_scraper/sources.json`: table tennis = Table Tennis England's "Laws of Table
Tennis 2026-27" PDF (the ITTF Laws, chapter 2; national byelaw boxes skipped; slug `ittf`); pickleball = the 2026 USA
Pickleball Official Rulebook PDF as hosted by Pickleball Canada (slug `usap`); basketball = FIBA Official Basketball
Rules 2024 PDF (slug `fiba`). `ittf.com/handbook` answered 403 on 2026-10-24 and is **not** used. Doc counts per
sport: **none yet** (the actor has not been run on real sources). Store publish: **not published, awaiting the user**.

## Requests
- **To the user** (sent 2026-10-24 via the Part 1 session): keys + Moss project; approve the sources; OK the local run.
- **To the Part 1 session:** please stop editing `services/rules/**` and `actors/**`; if this branch lands first, #6
  resolves those paths by taking `main`. The two engine seams (brief §D) and the `rule_ref` notes go to them once
  `check-pack` has run against the real index.
- **To Agent 1:** add `rules: cd services/rules && uv run trophy-rules serve` to the `Procfile`; `/api/healthz` can
  now read `doc_count` and `loaded_ms` from `rules`.

## Deviations from interfaces-v1 / the brief
- **D-30 (to record in `docs/decisions.md` after #6 merges): one Moss index with a `sport` metadata filter** instead
  of one index per sport (§17), because the free Developer plan allows 3 indexes and Part 3's per-game moment index
  needs one. (The brief called this D-28; PR #6 took D-28 and D-29.)
- `/rule_ref` is `POST` with `{sport, rule_ref?, rule_id?, text?}` (§17 said `GET`); `/clauses` and `check-pack` are
  additions; `rule_id`s carry a source slug (`ittf:2.6.2`), so the Part 1 pack's `"ITTF 2.6.2"` strings resolve.
- The actor lives at `actors/rulebook-scraper/` (PR #6's location), not `services/rules/actors/`.

## Checks run / not run (2026-10-24)
- Run: `services/rules` ruff + 39 pytest (2 live skipped, reason printed); `actors/rulebook-scraper` ruff + 15 pytest;
  `apify validate-schema`; the local `apify run` above; `uv sync --frozen` lockfiles regenerated.
- Not run (no keys): `tests/live/*` (Moss spike, Claude spike), `trophy-rules index build`, `serve`, `eval`,
  `check-pack`, the gateway round trip (`/api/ask` → `ask_logged` on `ctl:engine`; also needs Redis + the gateway up).

## Upstream code and licenses
`moss 1.21.0`, `anthropic 2.3.0`, `apify-client 3.3`, `apify 4.1.0`, `crawlee 1.11.0`, `pypdf 6.21.2`, `fastapi
0.162`, `pyyaml 6` (rows in `docs/licenses.md`). Rulebook text: ITTF / Table Tennis England, USA Pickleball, FIBA,
each publisher's terms; scraped from public PDFs only, full text kept in `data/local/` (gitignored), quotes ≤ 25
words with a link. No real rulebook text is in the repo (PR #6's test fixtures with verbatim ITTF clauses were
replaced by the synthetic laws).

## Known demo risks and fallbacks
- No fallback by design: without keys or an index the service does not start; the judge then sees the PWA's "the
  rules service is unavailable" (the gateway's 503), never a made-up answer. Rehearse with the index built and loaded
  before the demo (`index status` prints the load time).
- An out-of-date mirror: the Table Tennis England PDF is the 2026-27 Laws; re-run the actor if the ITTF changes a
  number. English-only STT (Ink-2). A `found: false` is spoken as "I couldn't find that rule in the ITTF laws."
- Latency: C3 wants speech to start ≤ 3 s after the question; `/ask` has ≈ 1.5 s p50. If Opus 5.5 at effort low misses
  it on the eval set, the user decides on `ASK_MODEL=claude-haiku-5-5` (not changed silently).
