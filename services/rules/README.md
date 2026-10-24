# Rules: ask the ref (Agent 3, Part 2)
**py3.11, FastAPI on port 8100** (`8100 + PORT_OFFSET`). Contract: `docs/plan/interfaces-v1.md` §17; brief: `docs/plan/prompts/agent-3-part-2-rulebook.md`; status: `docs/status/a3-rulebook.md`.

```
actors/rulebook-scraper (Apify)  ──one dataset item per numbered clause──▶  trophy-rules dataset export  ──▶  data/local/rulebooks/<sport>.jsonl
trophy-rules index build  ──▶  ONE Moss index `trophy-rules-v1` for every sport, `sport` metadata filter (D-30)
POST /ask {question ≤ 300, sport}  ──▶  Moss top-5 (alpha 0.8; +alpha 0.3 when the question names a clause)  ──▶  score gate
   ──▶  Claude (claude-opus-5-5, effort low, structured output, cached system prompt) answers ONLY from those clauses
   ──▶  server-side grounding check: cited id ∈ retrieved, quote verbatim ≤ 25 words, else the citation is DROPPED
   ◀──  {answer, speech, citations: [{rule_id, title, url, quote}], found, moss_ms, llm_ms, latency_ms, model, top_score, retrieved}
POST /rule_ref {sport, rule_ref?: "ITTF 2.6.2", rule_id?: "ittf:2.6.2", text?}  ──▶  {rule_id, title, url, quote, score, how: exact|search} | 404
GET  /clauses?sport=&q=&k=8  ──▶  Markdown, the top-k clauses with ids, titles and links (the Droid workspace's context/clauses.md)
GET  /healthz  ──▶  {ok, index, doc_count, model, loaded_ms, ask_model, effort}
```

## No keys, no run
`trophy-rules serve` (and `index`, `eval`, `check-pack`) **exit 3 with one line** unless `ANTHROPIC_API_KEY`, `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` are set (environment, or the repo's `.env` / `.env.local`). Startup loads the Moss index and fails fast if it isn't built (the message names the command). There is **no keyword fallback, no mock index and no canned answer**: a weak retrieval (top score below `ASK_MIN_SCORE`) or an answer with no verifiable citation returns `found: false` and "I couldn't find that rule in the ITTF laws." without inventing anything, and the weak-retrieval case never calls Claude.

## Run
```sh
cd services/rules && uv sync
# 1. scrape (local, no Apify credit): see actors/rulebook-scraper/README.md, then
uv run trophy-rules dataset export                       # actors/rulebook-scraper/storage -> data/local/rulebooks/<sport>.jsonl
uv run trophy-rules index build                          # -> Moss `trophy-rules-v1` (wait=True); `index refresh` upserts; `index status`
uv run trophy-rules serve                                # 127.0.0.1:8100 (+PORT_OFFSET)
curl -s localhost:8100/ask -H 'content-type: application/json' -d '{"question":"Does the ball have to go up 16 cm on a serve?","sport":"table_tennis"}'
uv run trophy-rules eval --sport table_tennis            # evals/ask/table_tennis.jsonl -> hit@5, citation precision, found accuracy, p50/p95
uv run trophy-rules check-pack ../../sports/table_tennis/rules.yaml   # resolves every rule_ref (read-only)
```
Through the gateway: `POST /api/ask` with a cam token proxies here and publishes `ask_logged` on `ctl:engine`.

## Config (`.env.example`, rulebooks block)
`MOSS_INDEX=trophy-rules-v1`, `MOSS_MODEL=moss-minilm`, `MOSS_CACHE_PATH`, `ASK_MODEL=claude-opus-5-5`, `ASK_EFFORT=low`, `ASK_MIN_SCORE=0.35` (tuned on the eval set; see the status file), `ASK_TOP_K=5`, `APIFY_RULEBOOK_ACTOR`, `APIFY_TOKEN` (platform pulls and `apify push` only).

## Tests
`uv run pytest -q -rs`. Pure parts run without keys against doubles at the SDK boundary (`tests/conftest.py`: a one-index fake Moss with the real `moss` result types, honouring the `sport` filter and `get_docs`; a fake Anthropic client returning real `anthropic.types.Message`s). **`tests/live/`** calls Moss and Claude for real (the P0 spikes and measurements) and is **skipped with a printed reason** when the keys are absent; `-rs` shows the skips.

## Logging
JSON lines on stderr: `{"svc": "rules", "msg": "ask", "sport", "found", "moss_ms", "llm_ms", "latency_ms", "top_score", "citations"}`, `moss query`, `claude` (with `cache_read_input_tokens`), `rule_ref`, `clauses`. Never a key, never the full prompt.

## Track evidence
- **Moss** (`moss==1.21`): one cloud-built index, loaded locally (`load_index`) so queries run in-process; hybrid `alpha`; `filter={"sport": {"$eq": …}}`; `get_docs(doc_ids=…)` for exact `rule_ref`s; `moss_ms` is returned on every answer so Moss is visibly in the loop.
- **Apify**: the index is built only from our "Sports Rulebook Scraper" actor's dataset (`actors/rulebook-scraper/`).
- **Anthropic** (`anthropic==2.3`, `claude-opus-5-5`): `output_config={"effort", "format": json_schema}`, no `temperature`, no prefill, no forced `tool_choice`; the system prompt is cached (`cache_control`); `stop_reason == "refusal"` raises; the model's citations are verified server-side and never trusted.
