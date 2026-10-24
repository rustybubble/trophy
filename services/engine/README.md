# Engine (owner D)

**Env:** py3.11 · cel-python · transitions · redis

## Responsibilities
- Fuses `ev:*` (dedupes across cameras), runs rule packs (CEL conditions, scoring templates), applies the confidence gate (≥ 0.90 auto / 0.60–0.90 challengeable / < 0.60 replay), and auto-tags PLAYERS rules.
- **`decide()`**: SubQ Snap (`subq-snap-1.1`, `probabilities[choice]`, 2 s timeout, shuffled re-ask on borderline calls) → Gemini Flash → Claude votes (structured output, 5 shuffled votes) → geometry. Temperature calibration `softmax(log p / T)` from labelled calls. Trace everything in Langfuse.
- Writes calls through SpacetimeDB reducers (HTTP). Coach (F11): candidate generators + a Snap choice + Claude explanation.
- Tests: replay recorded event logs → expected calls.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
