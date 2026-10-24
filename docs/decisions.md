# Decisions

Record significant architecture changes: `D-n: decision. Why. Date/owner.` These are working defaults that agents may revise with evidence and updated consumers/docs.

- **D-1: Flexible compute, with a cloud deployment baseline.** GCP `g2-standard-8` (L4, us-west1) for live processing and Vultr L40S for post-game work are current defaults. Local development, tests, inference, training and rendering are allowed on capable hardware; providers may change within authorized resources and budget. Historical credit estimates must be checked before spending. Why: hardware and budgets change. (2026-10-23)
- **D-2: Capture is a PWA, not native.** It runs on any iPhone or Android. Consequences: about 30 fps on iOS, no vibration (beep + flash instead), no 120 fps (slow-mo comes from interpolation). (2026-10-22)
- **D-3: Three perception families × rule packs.** Flight, possession and resting-object pipelines; each sport is a YAML pack with CEL conditions. Why: share perception work across 28 sports. (2026-10-22)
- **D-4: Honest call tiers.** AUTO ≥ 0.90 / BETA (challengeable, shows uncertainty) / PLAYERS DECIDE. Line calls use P(in) = Φ(d/σ). Fouls get evidence mode only. (2026-10-22)
- **D-5: The decision chain is SubQ Snap → Gemini → Claude votes → geometry.** Probabilities are temperature-calibrated on labelled calls. Decision models never make raw visual line calls. (2026-10-22)
- **D-6: SpacetimeDB is the current live game backend** (tables + reducers; the TypeScript SDK on clients; the Python engine calls reducers over HTTP). Redis stays internal for high-rate events. Why: shared real-time state for phones, the engine and viewers. Alternatives remain open if they improve the product. (2026-10-23)
- **D-7: The house-rule compiler is a Factory Droid** (sandboxed, triggered by a SpacetimeDB row, replay-tested, plan/diff/tests visible, human approval). Fallback: Claude only. (2026-10-23)
- **D-8: Moss for rulebook lookup and play search.** Firecrawl → one index per sport. (2026-10-23)
- **D-9: Build on Replay and courtcam.** Agents may extend Replay's ideas and adapt, copy or vendor compatible licensed code across its app, render, service and infrastructure layers. Preserve required notices and record incorporated sources/revisions. Trophy Watch currently targets the web; other interfaces remain possible. Why: reuse useful work and spend effort on Trophy's improvements. (2026-10-23)
- **D-10: White table-tennis balls** (BlurBall is trained on white). (2026-10-22)
- **D-11: Agent autonomy with focused safeguards.** Plans, owners, branch conventions, version pins and schedules are adaptable. Agents can make routine reversible choices without approval; protect credentials, privacy, licenses, honest results, user work and authorized resource limits. Why: reduce unnecessary restrictions while preserving trust and control. (2026-10-23)
