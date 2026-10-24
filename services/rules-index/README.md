# Rules index: Firecrawl → Moss (owner D)

**Env:** py3.11 · Firecrawl · Moss SDK (check package names at docs.moss.dev) · port 8100

## Responsibilities
- Scrape the official rules (USA Pickleball, BWF, ITTF, USA Football flag, the cornhole association, basketball streetball conventions…) → chunk **one rule per document** with {sport, rule_id, title, url} → one Moss index per sport (`moss-minilm`).
- `GET /rules/query?sport=&q=` → top-k clauses (hybrid alpha 0.6). Used by ask-the-ref (Deepgram → Moss → Claude, answering only from the retrieved clauses → Cartesia), by challenge verdicts (citing the rule) and by the Droid compiler.
- Also indexes **moments** after each game for Trophy Watch play search.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
