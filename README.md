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
| `apps/watch` | Trophy Watch: post-game recap, highlights, moments, replay, stats |
| `services/gateway`, `services/recorder` | Phone API, replay recording, the demo's clip upload + "stream as a phone" |
| `services/flight` | The ping-pong vision module: BlurBall live on every camera stream, N-camera 3D fusion |
| `services/engine`, `services/compiler`, `services/referee` | Rule engine + AI votes + 3D checks, Factory Droid house rules, the referee voice |
| `spikes/serve-analysis` | BlurBall adapter (vendored upstream + official weights), serve spotting, two-camera HMR2 replay, ball-track completion and toss evidence ([reproduce on another computer](spikes/serve-analysis/REPRODUCE.md)) |
| `spacetime/` | SpacetimeDB module: the shared world state (metadata only, no video) |
| `packages/` | Contracts (JSON Schema), generated types, shared Python lib, state client |
| `infra/` | Caddy + Porkbun DNS for `https://trophy.photo` |
| `docs/` | Plan, interfaces, decisions, progress, agent briefs (`docs/plan/prompts/`), research |

## Run it (macOS, M5 Pro)
`make dev` starts everything natively. Phones connect to `https://$TROPHY_DOMAIN/cam/`. Copy `.env.example` to `.env` and fill in the keys; never commit `.env`. Mac bring-up: [`docs/plan/prompts/mac-bringup.md`](docs/plan/prompts/mac-bringup.md).

## Prize-track sections (filled in at submission)
- **Factory Droid:** where Droid runs, its trigger, its sandbox and what it can touch, and what the dashboard shows.
- **Cartesia:** the features used (Sonic WebSocket TTS, `context_id`, `cancel`, emotion, two voices, Ink-2 STT with turn detection) and known limitations.
- **Spacetime:** the shared world state (vision observations, game state, votes, house rules, ask log).
- **Anthropic:** our community and their problem, how Claude is used, and **where it could go wrong** and how we contain it.
- **Bitdeer AI Model Studio, Gemini:** each one's role as a challenge voter.
- **Meta:** how Trophy brings people closer.

## License
MIT (see [LICENSE](LICENSE)). Third-party code, models and media keep their own terms: see [docs/licenses.md](docs/licenses.md).
