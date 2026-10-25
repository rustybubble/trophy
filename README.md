# Trophy 🏆

**A universal AI referee for pickup games, built at Cal Hacks 13.0.**

Point a phone at a ping-pong table and Trophy referees the game:
- It **keeps score**.
- It **calls the edge rule and illegal serves**: under the official ITTF law, the toss must rise at least 16 cm off the open palm, go up within 30° of vertical and be struck on the way down; hidden serves and net-touch lets are called too.
- It **speaks every call** in a referee voice.
- Close calls show their probability and can be **challenged**. A challenge brings an **instant replay** and a second opinion from three AI models.
- Players can **ask the ref** about any rule by voice and get an answer quoted from the official rulebook.
- Players can **add their own house rule** in plain English, and a Factory Droid compiles, tests and applies it.

> **Status:** under construction this weekend. The plan is in [`docs/plan/three-agent-plan.md`](docs/plan/three-agent-plan.md). Each prize-track section below gets filled in with what actually shipped and what was measured.

## Repo map
| Path | What |
|---|---|
| `apps/pwa` | Phone app: camera, calls, voice, challenge, replay |
| `apps/dashboard` | Judges' screen: score, calls, AI votes, Droid panel, ask-the-ref, live world state |
| `services/gateway`, `services/recorder`, `services/ingest` | Phone API, replay recording, optional WebRTC |
| `services/courtcam-adapter`, `services/flight` | Calibration and the ping-pong vision module |
| `services/engine`, `services/compiler`, `services/referee` | Rule engine + AI votes, Factory Droid house rules, the referee voice (ask the ref: checks → Claude phrasing → Cartesia) |
| `services/players`, `services/possession` | Basketball (if time allows) |
| `spacetime/` | SpacetimeDB module: the shared world state (metadata only, no video) |
| `packages/` | Contracts (JSON Schema), generated types, shared Python lib, state client |
| `rulepacks/` | One YAML per sport |
| `docs/` | Plan, interfaces, decisions, progress, research; `docs/archive/` is superseded |

## Run it (macOS, M5 Pro)
`make dev` starts everything natively. Phones connect to `https://$TROPHY_DOMAIN/cam/`. Copy `.env.example` to `.env` and fill in the keys; never commit `.env`. **The step-by-step demo (stack, a live synthetic game, a Droid house rule, the voice, the 3D map) is [`docs/demo.md`](docs/demo.md).**

## Prize-track sections (filled in at submission)
- **Factory Droid:** where Droid runs, its trigger, its sandbox and what it can touch, and what the dashboard shows.
- **Cartesia:** the features used (Sonic WebSocket TTS, `context_id`, `cancel`, emotion, two voices, Ink-2 STT with turn detection) and known limitations.
- **Spacetime:** the shared world state (vision observations, game state, votes, house rules, ask log).
- **Anthropic:** our community and their problem, how Claude is used, and **where it could go wrong** and how we contain it.
- **Bitdeer AI Model Studio, Gemini:** each one's role as a challenge voter.
- **Moss, Apify:** dropped (D-36); rules answers are grounded in the sport's own rule pack instead.
- **Meta:** how Trophy brings people closer.

## License
MIT (see [LICENSE](LICENSE)). Third-party code, models and media keep their own terms: see [docs/licenses.md](docs/licenses.md).
