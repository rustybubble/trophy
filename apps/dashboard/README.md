# Dashboard (Agent 1, with panels fed by Agent 3)
The judges' screen at `/`:
- create a game + QR;
- the scoreboard and call feed with tiers and replays;
- the **AI votes panel** (Claude next to the geometry; labelled uncalibrated);
- the **Factory Droid panel** (plan, steps, diff, tests, Approve);
- the **ask-the-ref transcript** with citations;
- the **live world-state view** (Spacetime observations + ball trail, no video);
- camera health;
- an honest sport wall (built vs. coming next).

## As built (2026-10-24, Agent 1)
- `npm run dev -w @trophy/dashboard` (port 5174, also in `make dev`); Caddy serves it at `/`. `/?demo=table_tennis` or `basketball` plays the labelled-synthetic MockState script; `/?g=<game>&k=<join key>` reopens a game.
- **Start a game** creates it (`POST /api/games`) and joins as `display,judge` so the dashboard can approve house rules and resolve challenges (`/api/ctl`). The join QR points phones at `/cam/?g=…&k=…`.
- Panels: scoreboard, call feed (tiers AUTO / BETA / PLAYERS DECIDE, p, status, Uphold / Overturn on open challenges), AI second opinion (labelled **uncalibrated**), Factory Droid (plan, streamed steps, diff, tests, calls that would change, Approve / Reject), ask-the-ref transcript with citations, world state (top-down table, 10 Hz ball trail, bounces with σ; badge "reconstructed from tracking, not video"), camera health, and the sport wall (built vs coming next).
- Synthetic data is always bannered (MockState, or a game whose `params.synthetic` is set).
- Verified on the Windows PC: the synthetic demo renders every panel; a live game through the local gateway + SpacetimeDB connected, and `seed_demo.py --game <id>` (97 reducer calls) appeared in every panel live. Not yet tested on a phone-sized screen or against the Vultr box.
