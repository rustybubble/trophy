# Ask-the-ref eval sets

Human-written questions per sport, one JSON object per line: `{question, expected_rule_ids: [...], notes}`.
`trophy-rules eval --sport <sport>` runs the full `/ask` pipeline (Moss → gate → Claude → grounding check) and
prints Moss hit@5, citation precision, `found` accuracy and p50/p95 latencies; results go to
`data/local/ask_eval/<date>.json` (gitignored). An empty `expected_rule_ids` means the question is outside the
rulebook and the right answer is `found: false` with no citations.

Rule ids are `<slug>:<number>` as the actor emits them (`ittf:2.6.2`, `usap:11.A`). **The numbers below were
written from memory of the laws on 2026-10-24 and are provisional until checked against the indexed text**; the
first eval run with keys prints the retrieved ids next to the expected ones, and any mismatch is corrected here with
the date. The first five table-tennis lines are the demo questions whose answers are also hand-checked (plan §5).
