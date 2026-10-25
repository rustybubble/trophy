> **Superseded 2026-10-24** by `docs/plan/prompts/agent-3-droid-realtime.md` (D-31). Kept for history.

# Agent 3 prompt, Part 2: the rulebook capability (Apify actor → Moss → `/ask` with citations → `rule_ref`)

*Planned 2026-10-24 against `origin/main` @ `5645e75` and the open Part 1 PR [rustybubble/trophy#6](https://github.com/rustybubble/trophy/pull/6) (`a3/wk-rules-droid`). Part 1 is still being implemented, so §A below says exactly what Part 2 may and may not touch. Paste everything below the line into a fresh chat opened in the Trophy repository.*

---

You are **Agent 3 (rules and Droid), Part 2: the rulebook capability.** Trophy is a universal AI referee for pickup games, built for Cal Hacks 13.0. There is no fixed deadline (`docs/plan/three-agent-plan.md` → DEADLINE: we stop when the features are done); feature freeze is "once the MUSTs pass C3".

Part 1 (the Factory Droid sport-module compiler, the `replay_test` gate, the golden `sports/table_tennis/` module) is **in progress in another session**, on branch `a3/wk-rules-droid` in `../trophy-a3`, PR #6 open. Its status file is `docs/status/a3.md`. **Do not touch its files** (§A). The rule engine proper (CEL evaluation, scoring, the gate, the `ctl:engine` consumer) is **also not built yet**: the Part 1 session deferred it to its "stage 2". Part 2 depends on the engine only at two small seams (§D), which you hand to that session as requests, not code.

**What Part 2 delivers:** players ask the ref a rules question by voice; the answer comes **only from official rulebook clauses** that **our Apify actor** scraped, **Moss** retrieved, and **Claude** phrased, with citations; and every rule in a pack can carry a `rule_ref` to the clause it implements, so challenge verdicts and Droid diffs show the official text. Prize tracks: **Apify** (+ Best Actor), **Moss**, **Anthropic**, with Cartesia doing the voice on Agent 1's side.

## 0. Read first
1. `CLAUDE.md` (safeguards), then `docs/plan/three-agent-plan.md` §0 (the cut and the track table), §2, §5 (C2: "`/ask` returns a cited answer"; C3: "voice ask → spoken cited answer starts ≤ 3 s after the question ends").
2. `docs/plan/interfaces-v1.md` **§13** (the gateway's `POST /ask` proxy, already built), **§17** (ask the ref: the actor, the index, `/ask`), §9 (`ask_logged`), §10 (`Call.rule_ref`), §11 (the `ask` table and `post_ask`), §18 (the Droid workspace gets `context/clauses.md`).
3. What already exists for you on `main`:
   - `services/gateway/gateway/app.py` → `POST /api/ask`: proxies `{question, sport}` to `RULES_URL/ask` (`http://127.0.0.1:8100` + `PORT_OFFSET`), 8 s timeout, passes your JSON through to the phone, then publishes the `ask_logged` ctl command. `/api/healthz` probes `RULES_URL/healthz`.
   - Contracts: `packages/contracts/ctl.schema.json` → `AskLoggedArgs {question, answer, citations: [AskCitation {rule_id, title, url, quote ≤ 25 words}], latency_ms, moss_ms?}`; `state.schema.json` → `Ask` row + `Citation`; `call.schema.json` → `rule_ref: string` ("closest official clause (Moss)").
   - Spacetime: the `ask` table and the `post_ask` reducer (engine identity). `@trophy/state-client` has `onAsk`.
   - `services/rules/README.md` (a stub), `.env.example` (`APIFY_TOKEN`, `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `CLAUDE_FAST_MODEL`).
   - `docs/research/build-cards-platform-and-post-game.md` §5 (Claude API notes: no `temperature`, no prefill, `output_config.format`, caching).
   - Part 1's `sports/table_tennis/rules.yaml` (read-only for you): every rule already has a `rule_ref` string such as `"ITTF 2.6.2"`, `"ITTF 2.10.1.4"`, `"ITTF 2.1.2"`. Your `/rule_ref` must resolve those strings.

## A. Clash map: what Part 1 owns, what Part 2 owns
Part 1's PR touches (besides its own directories) `.env.example` (a Droid section appended at the end), `.github/workflows/ci.yml` (an engine step in the `python` job, uv in the `node` job), root `package.json` + `package-lock.json` (the compiler workspace), `packages/contracts/{droidrun,sportmodule,scene}.schema.json` + `state.schema.json` (`HouseRuleStep.kind`) + generated types, `scripts/validate_fixtures.py`, `evals/fixtures/synthetic/**`, `docs/decisions.md` (D-27), `docs/progress.md`, `docs/status/a3.md`.

| | Part 1 (hands off) | Part 2 (yours) |
|---|---|---|
| Directories | `services/engine/**`, `services/compiler/**`, `sports/**`, `evals/fixtures/synthetic/**` | `services/rules/**` (the service **and** the actor at `services/rules/actors/rulebook-scraper/`), `evals/ask/**`, `evals/fixtures/rulebooks/**` |
| Contracts | `droidrun`, `sportmodule`, `scene`, `state.HouseRuleStep` | **None needed.** `Ask`, `Citation`, `AskCitation`, `AskLoggedArgs`, `Call.rule_ref` already exist. If you must add a field, it is a `contracts/*` PR to Agent 1 after #6 merges, never a direct edit |
| `.env.example` | the `# --- Droid compiler` block at the end | add your knobs **inside the existing `# --- rulebooks (Apify actor -> Moss) ---` block** (lines 40–43), not at the end |
| CI | the engine step inside the `python` job | a **new job** `rules:` at the end of `ci.yml` (not a step inside `python`), so the rebase is clean |
| Status | `docs/status/a3.md` | **`docs/status/a3-rulebook.md`** (link it from `a3.md` only after #6 merges) |
| `docs/decisions.md` | D-27 | append your D-28+ **after** #6 merges, or in your final PR after rebasing |
| `docs/progress.md` | its rows | one row per measured number, added in your last PR after rebasing |
| Root `package.json` / npm | the compiler workspace | nothing: Part 2 is Python only |
| Engine seams | `services/engine/**` | §D requests to the Part 1 session; no code from you in that directory |

**Worktree:** `git worktree add ../trophy-a3b -b a3/wk-rulebook origin/main`. Rebase on `origin/main` before every PR. **When PR #6 merges, rebase immediately** and resolve the two small expected conflicts (`.env.example`, `ci.yml`).

## 1. Facts (verified 2026-10-24; recheck before pinning)
- **Moss** (docs.moss.dev, read today): `pip install moss` (Python ≥ 3.10; the PyPI name is `moss`, not `inferedge-moss`; npm is `@moss-js/moss`). `from moss import MossClient, DocumentInfo, QueryOptions`; `MossClient(project_id, project_key)` from `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY` (the Moss portal → API Keys). **The SDK is async.** `await client.create_index(name, docs, model_id="moss-minilm", wait=True)` → `MutationResult {job_id, doc_count}`; `await client.add_docs(name, docs, MutationOptions(upsert=True))`; **`await client.load_index(name)` before any query** (it downloads the index locally; queries then run in-process, "local queries: unlimited"); `await client.query(name, text, QueryOptions(top_k=5, alpha=0.8, filter={...}))` → `SearchResult.docs: [QueryResultDocumentInfo {id, text, metadata: dict[str,str] | None, score: float 0–1 (moss ≥ 1.14), payload?}]`. `alpha` 1.0 = semantic, 0.0 = keyword, default 0.8; lower it for exact identifiers. Metadata filters: `$eq $ne $gt $gte $lt $lte $in $nin`, `$and`/`$or`; metadata values are strings. Models: `moss-minilm` (default), `moss-mediumlm`. Chunks ≤ 2000 chars. **Free "Developer" plan: 3 indexes, 1 project, 500 MB storage, 50 MB ingest/month, 60 session minutes/month.** → §2 uses **one index with a `sport` filter**, not one index per sport.
- **Apify** (docs.apify.com + PyPI, read today): `apify` **4.1.0** (2026-10-08, Python ≥ 3.11), `crawlee` **1.11.0** (2026-10-15; `BeautifulSoupCrawler`, `PlaywrightCrawler`). Pattern: `async with Actor:` → `await Actor.get_input()` → `await Actor.push_data(item)`. Project layout: `.actor/actor.json` (`actorSpecification: 1`, `name`, `version "0.1"`, `title`, `input` → `.actor/input_schema.json` with `title`, `type: object`, `schemaVersion: 1`, `properties`; `storages.dataset` for the output schema), `Dockerfile`, `requirements.txt`, `README.md`. Local: `apify create`, `apify run` (writes `storage/datasets/default/*.json`; `--purge` clears), `apify push` to deploy (needs login / `APIFY_TOKEN`). **Publishing to the Store needs the user's OK.**
- **Claude** (`anthropic` Python SDK; pin the exact version you install): `claude-opus-5-5` is the default model; `claude-haiku-5-5` is the cheap/fast one. `temperature` is rejected and there is no prefill. Structured output: `client.messages.parse(model=..., max_tokens=..., system=[...], messages=[...], output_format=PydanticModel)` → `response.parsed_output`, or `output_config={"format": {"type": "json_schema", "schema": ...}}` on `create()` (flat schema, no recursion). Thinking is always on for Opus 5.5; control cost and latency with `output_config={"effort": "low"}`. Put the fixed system prompt first with `cache_control: {"type": "ephemeral"}` and check `usage.cache_read_input_tokens`. Check `stop_reason == "refusal"` before reading content.
- **Rulebook sources** (checked today; the user picks the final list, §2.1): `https://www.ittf.com/handbook/` returned **HTTP 403 to a plain fetch**, so assume ITTF's site blocks scrapers. **Never work around bot protection.** Public mirrors of the same Laws exist: Table Tennis England's "Laws of Table Tennis 2026–27" PDF (`https://www.tabletennisengland.co.uk/content/uploads/2026/07/Laws-of-Table-Tennis-2026-27.pdf`, reproduces the 2026 ITTF Statutes laws, with national byelaws in boxes to skip) and megaspin's ITTF Handbook mirrors (`https://cdn.megaspin.net/rules/pdf/2025/ittf-rules-2.pdf`). USA Pickleball's official-rules page 404'd today; Pickleball Canada hosts the "2026 USA Pickleball Official Rulebook" (`https://pickleballcanada.org/wp-content/uploads/2026/03/2026-Official-Rulebook-EN.pdf`; note the non-volley zone moved to Section 11 in 2026). Basketball: FIBA Official Basketball Rules PDF from fiba.basketball (verify the URL; NFHS is paywalled → no). Rulebook text is **copyrighted**: scrape public pages only, respect `robots.txt`, keep the full text in `data/local/` (gitignored), quote ≤ 25 words with a link, and record the source + license note on every document (`docs/licenses.md` has the "Rulebook text" row).
- **Not in Part 2:** Gemini, Bitdeer, the `decide()` voters, replay crops, Trophy Watch moments or moment search, the Claude-only Droid fallback, basketball perception. Don't install or stub them.
- **No keys, no run.** The service refuses to start without `ANTHROPIC_API_KEY`, `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`, with a one-line reason and exit code 3. **No keyword-search fallback, no canned answers, no in-memory "mock index".** Pure functions (the clause splitter, citation validation, prompt assembly) are unit-tested without keys; everything that calls Moss or Claude is a `live` test that is **skipped with a printed reason** when the keys are absent and listed under "checks not run". The Apify actor runs locally without a token (`apify run`); only `apify push` needs `APIFY_TOKEN`.

## 2. Design

### 2.1 The actor: `services/rules/actors/rulebook-scraper/` (Apify Python SDK + Crawlee + pypdf)
- **Input** (`.actor/input_schema.json`): `{sources: [{sport, url, kind: "html"|"pdf", source: "ITTF"|"USA Pickleball"|"FIBA"|…, license_note, skip_patterns?: [regex]}], max_pages: 25, user_agent}`; the default `prefill` is `sources.json` in the actor directory, the list the user approves.
- **Output dataset, one item per rule:** `RuleDoc = {sport, rule_id, number, title, text, url, source, section_path, license_note, fetched_at, content_hash}`. `rule_id = "<source-slug>:<number>"`, e.g. `ittf:2.6.2`, `usap:11.A`. `title` is the heading chain ("The Service"); `text` is the clause body (≤ 2000 chars, split long clauses into `…#2`).
- **Splitter** (`rulebook_scraper/split.py`, pure): hierarchical numbering `^(\d+(\.\d+)+)\s` with carry-over for wrapped PDF lines, heading detection, byelaw-box skipping via `skip_patterns`. PDF text via `pypdf`; HTML via `BeautifulSoupCrawler`. Unit-test it on **`evals/fixtures/rulebooks/synthetic_laws.txt`**: a small made-up rulebook ("Trophy Test Laws", labelled synthetic) in the ITTF numbering style, plus a two-page synthetic PDF generated by a script (≤ 100 KB). Never commit real rulebook text beyond ≤ 25-word quotes in tests.
- **Crawl policy:** honour `robots.txt` (Crawlee's option; verify its name in 1.11.0), one request at a time, a descriptive user agent with a contact, **no retry on 403/429**, and a hard `max_pages`. Nothing behind a login or paywall.
- **Run locally:** `apify run --purge` writes `storage/datasets/default/`; `trophy-rules dataset export --sport table_tennis` copies it to `data/local/rulebooks/<sport>.jsonl`. On the platform: `apify push` then run with the same input; the dataset is pulled with the Apify client using `APIFY_TOKEN`. The actor README is the **Best Actor** submission text: what it scrapes, the output schema, how Trophy uses it, limits.

### 2.2 The index (Moss)
- `trophy-rules index build --from data/local/rulebooks/*.jsonl` → **one index `trophy-rules-v1`** holding every sport, `DocumentInfo(id=rule_id, text=f"{number} {title}. {text}", metadata={sport, rule_id, number, title, url, source})` (strings only), `model_id="moss-minilm"`, `wait=True`. `index refresh` uses `add_docs(..., MutationOptions(upsert=True))`. Record this as **D-28: one Moss index with a `sport` metadata filter instead of one index per sport (interfaces §17), because the free tier allows 3 indexes and the per-game moment index (Part 3) will need one too.**
- `index status` prints `get_index` (doc count, model, status) and the local load time; `index eval` runs §2.5.

### 2.3 The service: `services/rules` (FastAPI, py3.11, port 8100 + `PORT_OFFSET`)
Startup: validate the three keys → `MossClient` → `load_index("trophy-rules-v1")` (fail fast if it isn't built; the message says which command builds it) → construct the Claude client (no warm-up call; don't spend on startup). Log JSON lines (`svc: rules`, `game_id`, `msg`), never a key, never the full prompt.

| Route | In → out |
|---|---|
| `POST /ask` | `{question ≤ 300 chars, sport}` → `{answer, speech, citations: [{rule_id, title, url, quote}], found, moss_ms, llm_ms, latency_ms, model}` |
| `POST /rule_ref` | `{sport, rule_ref?: "ITTF 2.6.2", rule_id?: "ittf:2.6.2", text?: "<rule name + text>"}` → `{rule_id, title, url, quote, score, how: "exact"|"search"}` or 404 |
| `GET /clauses?sport=&q=&k=8` | Markdown: the top-k clauses with ids, titles and links (the Droid workspace's `context/clauses.md`, §D) |
| `GET /healthz` | `{ok, index, doc_count, model, loaded_ms}` |

`/ask` pipeline:
1. **Retrieve:** `query("trophy-rules-v1", question, QueryOptions(top_k=5, alpha=0.8, filter={"sport": {"$eq": sport}}))`; if the question contains a clause number (`\d+\.\d+`), run with `alpha=0.3` as well and merge. Time it → `moss_ms`.
2. **Weak-retrieval gate:** if the best `score` is below `ASK_MIN_SCORE` (start at 0.35, **tune it on the eval set and record the number**), return `found: false`, `answer: "I couldn't find that rule in the <source> laws."`, `speech` the same, `citations: []`, and **no Claude call**.
3. **Answer:** `client.messages.parse(model=ASK_MODEL, max_tokens=400, output_config={"effort": "low"}, system=[{fixed rules-of-engagement, cache_control}], messages=[{clauses as numbered blocks + the question}], output_format=AskAnswer)`, with `AskAnswer = {answer: str, speech: str, citations: [{rule_id: str, quote: str}], found: bool}`. The system prompt: answer **only** from the clauses; ≤ 3 sentences; cite by `rule_id`; `speech` is the spoken form (≤ 2 sentences, numbers read naturally: "law two point six" not "ITTF 2.6.2"); if the clauses don't answer it, set `found: false`.
4. **Grounding check (server-side, not trusted to the model):** every cited `rule_id` must be in the retrieved set, and every `quote` must be a verbatim substring (whitespace-normalised) of that clause, ≤ 25 words; failing citations are dropped. An answer with **zero** surviving citations is returned as `found: false` with the "couldn't find" text. This is a gate, not a fallback: it makes the model's answer honest, it never invents one.
5. Return; the gateway adds `latency_ms` if missing and publishes `ask_logged` (`moss_ms` is optional there; always send it).

Config (in `.env.example`'s rulebooks block): `ASK_MODEL=claude-opus-5-5`, `ASK_EFFORT=low`, `ASK_MIN_SCORE=0.35`, `ASK_TOP_K=5`, `MOSS_INDEX=trophy-rules-v1`. **Latency decision (measure first):** C3 wants the spoken answer to start ≤ 3 s after the question ends, and Agent 1 measured Ink-2 turn end at ~0.8–1.0 s plus Cartesia first audio ~0.1–0.3 s, so `/ask` has about **1.5 s p50** end to end. Measure Opus 5.5 at `effort: low` on the eval set; if its p50 misses, **ask the user** whether to switch `ASK_MODEL` to `claude-haiku-5-5` (don't change the default silently). Report both numbers either way.

### 2.4 `rule_ref` resolution
- `POST /rule_ref` tries, in order: parse `rule_ref` ("ITTF 2.6.2" → `ittf:2.6.2`) and `get_docs` by id (`how: "exact"`); else `query` on `text` with `alpha=0.5`, `top_k=1`, same sport filter, and the same `ASK_MIN_SCORE` gate (`how: "search"`); else 404.
- `trophy-rules check-pack sports/table_tennis/rules.yaml` resolves every rule's `rule_ref` and prints a table (rule id → clause id, title, score). Run it against Part 1's golden pack **read-only** and put the table in your status file; if a `rule_ref` doesn't resolve, that is a note to the Part 1 session, not an edit by you.

### 2.5 Evaluation: `evals/ask/<sport>.jsonl`
Human-written, ≥ 10 questions for table tennis (the 5 demo questions first, e.g. "does the ball have to go up 16 cm on a serve?", "what if the ball hits the edge?", "net on a serve?", "can I touch the table with my free hand?", "how many serves each at 10–10?"), each `{question, expected_rule_ids: [...], notes}`; ≥ 5 for pickleball. `trophy-rules eval --sport table_tennis` runs the full `/ask` path and prints: Moss hit@5 (expected id ∈ retrieved), citation precision (every surviving citation ∈ expected), `found` accuracy, and p50/p95 for `moss_ms`, `llm_ms`, `latency_ms`, as a table and as JSON in `data/local/ask_eval/<date>.json`. **Correctness of the 5 demo answers is also checked by hand** (plan §5) and the hand check is written down with the date.

## 3. Tasks in priority order (small PRs, merge every ~2 h)

**P0 (first ~3 h)**
1. Worktree `../trophy-a3b` on `a3/wk-rulebook`; `docs/status/a3-rulebook.md`; `services/rules/pyproject.toml` (uv, py3.11, `trophy` as a path dep, ruff, pytest) and the actor's own `pyproject.toml` + `requirements.txt` + `Dockerfile` (Apify's Python 3.11 base image).
2. **Spikes, each recorded with numbers and date:** (a) Moss: create a 20-doc index from the synthetic laws, `load_index`, 20 queries → cold load time and per-query ms; confirm `score` and `metadata` come back and the `sport` filter works. (b) Claude: one `messages.parse` call with `AskAnswer` at `effort: low`, time to parsed output, cache hit on the second call. (c) Apify: `apify run` of a hello actor locally.
3. The splitter + synthetic fixtures + unit tests; the actor end to end on the synthetic PDF (`apify run`); `dataset export`.
4. **Ask the user** to approve `sources.json` (the ITTF mirror vs. waiting for ittf.com, USA Pickleball via the Canada mirror, FIBA) and to create the Moss project + key. Then run the actor on the real sources into `data/local/rulebooks/`, build the index, record doc counts.

**P1: the slice (C2 needs "`/ask` returns a cited answer")**
5. `services/rules`: config + key check, Moss client wrapper, `/ask` with the grounding gate, `/rule_ref`, `/clauses`, `/healthz`; `trophy-rules serve|index build|index refresh|index status|dataset export|eval|check-pack`. Tests: pure parts without keys; `live` tests with keys (skipped otherwise, with the reason printed).
6. `evals/ask/table_tennis.jsonl` + `pickleball.jsonl`; run `eval`; tune `ASK_MIN_SCORE`; write the numbers.
7. Through the gateway: `curl -X POST https://trophy.photo/api/ask` (or `localhost:8000` + `PORT_OFFSET`) with a cam token → the response and the `ask_logged` entry on `ctl:engine` (`redis-cli XREVRANGE ctl:engine + - COUNT 1`). Ask Agent 1 to add `rules:` to the `Procfile` and to try the voice path from the PWA once their push-to-talk lands (PR #5).
8. CI job `rules:` (ruff, pytest without keys, the actor's splitter tests, `apify`'s actor.json validated by `apify validate-schema` if available).

**P2: integration (after PR #6 merges; rebase first)**
9. Send the two §D requests to the Part 1 session with exact shapes; link `a3-rulebook.md` from `a3.md`; D-28 in `docs/decisions.md`.
10. The compiler's `context/clauses.md`: **one small PR in `services/compiler/src/sandbox.ts`** that, when `RULES_URL` is set and the service answers `/healthz`, writes `GET /clauses?sport&q=<house rule text>&k=8` into the sandbox before the Droid starts, and lists it in `TASK.md`'s "What you have". Coordinate the timing with the Part 1 session so you never both hold edits to that file.
11. Rehearse the C3 line: a judge says "Trophy, what's the rule on a serve that hits the net?" → spoken cited answer, with the transcript and Moss latency visible on the dashboard (Agent 1's panel; rows appear once the engine's `ask_logged` handler exists, §D).

**P3: freeze**
12. README sections (hand to Agent 1): **Apify** (what the actor scrapes, the output schema, how it feeds Moss, robots/terms policy, the Store listing), **Moss** (one index + sport filter, hybrid `alpha`, measured latency, where it is visible on screen), and the ask-the-ref part of **Anthropic** (Claude answers only from retrieved clauses; where it goes wrong: weak retrieval, a misquoted clause, an out-of-date mirror; containment: the score gate, the verbatim-quote check, citations shown, English only).
13. With the user's OK: `apify push` and publish the actor on the Apify Store.

## 4. Acceptance (Part 2)
- [ ] `apify run` on the approved sources produces ≥ 150 ITTF rule documents and ≥ 100 pickleball ones, one per numbered clause, each with `url`, `source`, `license_note`; the splitter's unit tests pass on the synthetic laws.
- [ ] The Moss index builds from the dataset; `index status` shows the doc count; the `sport` filter never returns another sport's clause (tested).
- [ ] `POST /ask` answers the 5 prepared table-tennis questions with correct ITTF citations (hand-checked, written down) and hit@5 ≥ 0.9 on `evals/ask/table_tennis.jsonl`; a question outside the rulebook ("what's the weather?") returns `found: false` with no citations and no fabricated answer.
- [ ] Every returned `quote` is a verbatim ≤ 25-word substring of the cited clause (tested).
- [ ] Measured and recorded: Moss cold load, `moss_ms` p50/p95, `llm_ms` p50/p95, `/ask` p50/p95, with method, device and date; the `ASK_MODEL` decision is recorded with the numbers.
- [ ] `check-pack` resolves every `rule_ref` in `sports/table_tennis/rules.yaml` (or lists the unresolved ones for Part 1).
- [ ] The gateway round trip works (`/api/ask` → JSON → `ask_logged` on `ctl:engine`).
- [ ] The service exits 3 with a clear message when any key is missing; there is no code path that answers without Moss and Claude.
- [ ] No key in the repo or the logs; no rulebook text in the repo beyond ≤ 25-word test quotes; the Store publish and every paid tier were approved by the user first.

## D. The two engine seams (requests to the Part 1 session, not your code)
1. **`ask_logged` → `post_ask`:** the engine's `ctl:engine` consumer (their stage 2) turns `AskLoggedArgs` into an `Ask` row: `ask_id = ulid()`, `game_id` from the command, `sport` from the game, `created_at_ms = t_srv_ms`, the rest copied (`moss_ms` optional). Until that exists, the dashboard transcript shows nothing live; say so in your status file rather than writing a consumer yourself (two consumers on one Redis group would race).
2. **`Call.rule_ref` population:** at pack load, resolve each rule's `rule_ref` string through `POST /rule_ref` once, cache `{rule_id → citation}`, and copy `citation.rule_id` into `Call.rule_ref` (and the clause title into the dashboard's verdict line). If the service is down, calls go out without `rule_ref`; it must never block a call.
Also note to them: `sports/table_tennis/rules.yaml` says `rule_ref: "ITTF 2.1.2"` for the edge ball; check against the 2026 laws whether the table-surface definition is 2.1.2 (it is the top edge rule) and keep the serve rules at 2.6.x.

## E. Completion report (`docs/status/a3-rulebook.md` + your final message)
1. What works, with PR links.
2. Measured numbers with method and date (§2.5 and the spikes), and the model decision.
3. The approved sources, doc counts per sport, the Store listing (or "not published: awaiting the user").
4. Checks run and checks not run (name the `live` tests that were skipped and why).
5. Deviations from interfaces-v1 (D-28; `/clauses` and `check-pack` are additions; `/rule_ref` is `POST` not `GET`).
6. Upstream code and licenses (`moss`, `apify`, `crawlee`, `pypdf`, `anthropic` versions; the rulebook publishers and their terms, one row each in `docs/licenses.md`).
7. Account actions and spend: the Moss project, Apify account/Store, Claude token usage from `usage`, each with the user's approval noted.
8. Known demo risks and fallbacks: an out-of-date mirror, Moss or Claude latency, English-only STT, what the judge sees if `/ask` returns `found: false`.

## F. Out of scope (Part 3, don't start)
`decide()` voters (Claude ‖ Gemini ‖ Bitdeer), challenge crops, the Claude-only Droid fallback, Trophy Watch moments/highlights/coach/commentary, the per-game moment index and `/search_moments`, basketball. Serve-toss rules stay with Part 1/3.
