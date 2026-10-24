# Rules: ask the ref (Agent 3)
**py3.11, FastAPI on port 8100** (`8100 + PORT_OFFSET`). Contracts: `docs/plan/interfaces-v1.md` §17 (ask the ref) and §19 (`/search_moments`, `/coach`).

## Flow
```
actors/rulebook-scraper (Apify)  ──dataset: one item per rule──▶  rules index build  ──▶  Moss index per sport (rules-<sport>)
POST /ask {question, sport}  ──▶  Moss query(top_k=5), moss_ms logged  ──▶  Claude answers ONLY from those clauses (structured output)
                             ◀──  {answer, speech, citations: [{rule_id, title, url, quote ≤ 25 words}], moss_ms, latency_ms, found, top_score}
GET  /rule_ref?sport=&q=     ──▶  the closest clause {rule_id, title, url, quote, score}  (verdicts, house-rule diffs, the Droid)
POST /moments/index          ──▶  upsert moments into moments-<game_id>;  POST /search_moments {game_id, q} → {hits: [{moment_id, score}], mode: "semantic"}
POST /coach {game_id, sport, side, stats}  ──▶  Claude writes 2–3 tips from the stats alone → grounding validator → {tips: [{text, facts, source}], validated}
GET  /healthz                ──▶  {ok, keys: {anthropic, moss, apify}}  (presence booleans only)
```

- **Weak retrieval**: when there is no hit or the top Moss score is below `RULES_MIN_SCORE` (default 0.35; Moss scores are 0–1 relevance, hybrid `alpha` 0.8), `/ask` answers "I couldn't find that rule." without calling Claude. Claude can also return `found=false`, which gives the same answer.
- **Citations are verified**: a cited `rule_id` must be one of the retrieved clauses (others are dropped), and the quote must occur verbatim in that clause (else the clause's first 25 words are quoted). `speech` has rule ids stripped so Cartesia never reads "2.6.2" aloud.
- **Coach grounding** (`rules/grounding.py`, adapted from Replay's `narrate/grounding.py` @ `2db92c0`, MIT): every number, number word or ordinal in a tip must be a number in the stats; every capitalised word must be a side, a stat word or ordinary English; injuries, seasons, coaches, pronouns and other invented facts are rejected. A rejected tip is replaced by a **template** tip (`source: "template"`, with the `violations`) and `validated` becomes `false`. That template is the only fallback in this service, and it is a product behaviour required by §19.
- **No keyless mode.** Each client is built lazily and raises `ConfigError` without its credential: `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY` (Moss), `ANTHROPIC_API_KEY` (Claude), `APIFY_TOKEN` (pulling the actor's dataset). The app still imports and serves `/healthz`; `/ask`, `/rule_ref`, `/moments/*`, `/search_moments`, `/coach` return **503** `{"error": "not_configured", "detail": "<which key>"}`. Secrets are `repr=False` and never logged.

## Run
```sh
cp .env.example .env            # fill ANTHROPIC_API_KEY, MOSS_PROJECT_ID, MOSS_PROJECT_KEY, APIFY_TOKEN
cd services/rules && uv sync
uv run rules index build --sport table_tennis          # the actor's last SUCCEEDED run (APIFY_RULEBOOK_ACTOR) → Moss
uv run rules index build --dataset <datasetId>         # or a specific dataset id
uv run rules index load-local data/local/rules.jsonl   # or a local JSON/JSONL export of the dataset (still Moss)
uv run rules serve                                     # or: uv run uvicorn rules.app:app --port 8100
curl -s localhost:8100/ask -H 'content-type: application/json' -d '{"question":"How high must the serve toss rise?","sport":"table_tennis"}'
```
Moss indexes build in the cloud and are queried from a local snapshot (`MOSS_CACHE_PATH`, default `data/local/moss`, gitignored). The store reloads a snapshot after every mutation.

## Logging (measured, per request)
`moss query index=… moss_ms=…`, `claude ask claude_ms=… in=… out=…`, `ask … moss_ms claude_ms latency_ms`, `coach … validated claude_ms latency_ms`. Put the numbers you measure in `docs/progress.md`; nothing here is a benchmark until it has been run with keys.

## Track evidence
- **Moss**: `moss==1.21` (`MossClient(project_id, project_key, cache_path=)`, `create_index(name, docs, "moss-minilm")`, `add_docs(…, MutationOptions(upsert=True))`, `load_index`, `query(…, QueryOptions(top_k=5))`; hits carry `id, text, metadata, score`). One index per sport plus one per game for moments; `moss_ms` is returned to the UI so Moss is visibly in the loop.
- **Apify**: the dataset of our "Sports Rulebook Scraper" actor feeds the index (`apify-client==3.3`, `actor(...).last_run(status="SUCCEEDED").dataset().iterate_items(clean=True)`).
- **Anthropic**: `anthropic==2.3`, `claude-opus-5-5`, `messages.create(output_config={"effort": "low", "format": {"type": "json_schema", "schema": …}})`; thinking stays on (the default), no `temperature`, no forced `tool_choice` (both rejected on this model). A `refusal` stop reason raises instead of being hidden.

## Tests
`uv run pytest -q` — fakes are injected at the SDK boundary through FastAPI `dependency_overrides`: a fake Moss client that returns real `moss.SearchResult` objects and a fake Anthropic client whose `messages.create` returns a real `anthropic.types.Message` in the recorded structured-output shape. Covered: `/ask` with citations, quote verification, weak retrieval (no Claude call), `found=false`, `/rule_ref`, `/moments/index` + `/search_moments` (create, upsert, snapshot reload), `/coach` grounding (an absent number → template tip, `validated: false`), 503 without keys, the CLI with and without keys.

## Not verified (no live calls were made)
- No request has been sent to Moss, Anthropic or Apify from this service; the SDK call shapes were checked against the installed packages and the vendors' docs on 2026-10-24, not against live responses. Moss error codes on a missing index (we catch `MossError` from `get_index`) and the exact `last_run(status=…)` behaviour are unexercised.
- The score threshold 0.35 is a guess until measured on the real index; tune `RULES_MIN_SCORE`.
- The actor has not been run on Apify, so no dataset exists yet (see `actors/rulebook-scraper/README.md`).
