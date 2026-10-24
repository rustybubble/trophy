# Rule packs

One YAML file per sport, following `_template.yaml` and validated against `packages/contracts/rulepack.schema.json`. `sports.yaml` lists all 28 sports with their family, target badge and priority.

- **P0 packs (hand-written first):** `table_tennis.yaml`, `basketball.yaml`, `cornhole.yaml`.
- **P1 packs:** `pickleball.yaml`, `badminton.yaml`, `two_hand_touch.yaml`, `roundnet.yaml`.
- **The rest:** drafted by Claude from the official rules (Firecrawl), then reviewed.
- **Calls by tier for every sport** are in `docs/plan/concept-v3.md` §2. Any rule needing a signal we can't sense becomes `PLAYERS` automatically (engine).
- **House rules** are added by the Droid compiler (`services/compiler`) as `house_rule: true` entries, versioned.
