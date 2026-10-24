# Rules: ask the ref (Agent 3)
**py3.11, port 8100.**
- Our **Apify actor** (`actors/rulebook-scraper`) scrapes official rulebooks (ITTF first) into one-rule-per-document JSON.
- `index build` loads them into **Moss** (one index per sport).
- `POST /ask` → Moss top-k → Claude answers only from those clauses, with citations.
- `GET /rule_ref` supplies citations for verdicts and the Droid.
- Public pages only. Publishing the actor needs the user's OK.

Contracts: `docs/plan/interfaces-v1.md`. Plan and checkpoints: `docs/plan/three-agent-plan.md`. Record measured numbers in `docs/progress.md`.
