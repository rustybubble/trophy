# Rule packs
One YAML per sport, validated by `packages/contracts/rulepack.schema.json`. **Perception emits measurements; only packs decide** (D-18), so the Factory Droid changes rules by editing these files.
- `field:` (court template, landmarks in tap order, lines, zones; metres, z up) is owned by **Agent 2**. Everything else (teams, rules as CEL `when` + outcome + tier ceiling + `check: code|ensemble`, scoring template + params) is owned by **Agent 3**.
- House rules approved during a game are written to `rulepacks/house/{game_id}/{sport}.v{n}.yaml` (gitignored runtime output).
- Weekend packs: `table_tennis.yaml` (MUST), `basketball.yaml` (SHOULD). The catalog is `sports.yaml`.
