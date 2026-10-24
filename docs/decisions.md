# Decisions

Add an entry when you make an architecture choice: `D-n: decision. Why. Date/owner.`

- **D-1: Cloud only.** The live stack runs on a GCP `g2-standard-8` (L4, us-west1) and post-game work on a Vultr L40S. AWS ($100) is only for Remotion Lambda. Laptops only edit. Why: the budget, and no local GPUs. (2026-10-23)
- **D-2: Capture is a PWA, not native.** It runs on any iPhone or Android. Consequences: about 30 fps on iOS, no vibration (beep + flash instead), no 120 fps (slow-mo comes from interpolation). (2026-10-22)
- **D-3: Three perception families × rule packs.** Flight, possession and resting-object pipelines; each sport is a YAML pack with CEL conditions. Why: 28 sports in 36 hours. (2026-10-22)
- **D-4: Honest call tiers.** AUTO ≥ 0.90 / BETA (challengeable, shows uncertainty) / PLAYERS DECIDE. Line calls use P(in) = Φ(d/σ). Fouls get evidence mode only. (2026-10-22)
- **D-5: The decision chain is SubQ Snap → Gemini → Claude votes → geometry.** Probabilities are temperature-calibrated on labelled calls. Decision models never make raw visual line calls. (2026-10-22)
- **D-6: SpacetimeDB is the live game backend** (tables + reducers; the TypeScript SDK on clients; the Python engine calls reducers over HTTP). Redis stays internal for high-rate events. Supabase is dropped. Why: SpacetimeDB is the core real-time state, and it's a prize. (2026-10-23)
- **D-7: The house-rule compiler is a Factory Droid** (sandboxed, triggered by a SpacetimeDB row, replay-tested, plan/diff/tests visible, human approval). Fallback: Claude only. (2026-10-23)
- **D-8: Moss for rulebook lookup and play search.** Firecrawl → one index per sport. (2026-10-23)
- **D-9: Reuse only `courtcam` (MIT) from Replay**, as a disclosed dependency. Replay's app is rebuilt as the **Trophy Watch** web app (no Fire TV, no Alexa). Why: the Cal Hacks "all work during the event" rule. (2026-10-23)
- **D-10: White table-tennis balls** (BlurBall is trained on white). (2026-10-22)
