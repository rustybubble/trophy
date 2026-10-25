# Scripts

- `dev.py`: `make dev` / `npm run dev`; (re)starts every `Procfile` line natively, waiting for each one's ports (`--stop` stops them).
- `e2e.py`: `make e2e`; streams the CC BY ping-pong clip as a phone and checks frames → recorder/replay → Spacetime observations + calls (C2).
- `gen-contracts.mjs`: `make contracts`; JSON Schema → TS (`@trophy/contracts`) + Pydantic (`py-trophy`).
- `validate_fixtures.py`: validates rule packs and synthetic fixtures against the schemas (CI).
- CC BY clips: `tools/fetch_clips.py` fetches the segments listed in `data/clips/clips.yaml` into `data/local/clips/` (ask the user before downloading).
