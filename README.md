# Trophy 🏆

> **Demo acceptance failed.** The current two-camera prototype has incorrect/teleporting ball detections, inadequate 3D presentation with no real 3D ball, and unreliable point segmentation with no automatic real point scoring. See the [comprehensive status report](docs/status/tt-demo-failure-report-2026-10-24.md). This reporting branch preserves the failing implementation without fixes.

**A universal AI referee for pickup games, built at Cal Hacks 13.0.**

A local recorded demo now runs on the two original recordings in `data/ttClips`:

```bash
make tt-demo
# Open http://127.0.0.1:8765/
```

It provides synchronized source playback, slow motion, original 4K evidence crops, ball tracks, estimated wireframe player replay, and persistent player/official score resolutions. A separate synthetic laboratory exercises deterministic toss thresholds and uncertainty. The server uses only Python's standard library; prepared local assets are already present on this machine.

**Automatic scoring, metric serve/edge adjudication, and live sponsor integrations have not passed validation on these phone clips.** Camera motion, calibration and timing uncertainty remain explicit. The official serve profile requires at least **16 cm** upward rise; the 30° review criterion applies to the upward toss, with an explicitly disclosed estimator. The real footage is local/private, and no model weights or recordings are included in git.

See [the demo guide](docs/tt-demo.md) for rebuilding, checks, measured results and remaining work. Live capture, Cartesia, shared Spacetime state, AI challenge votes, voice rule questions and the house-rule compiler remain the wider project plan in [three-agent-plan.md](docs/plan/three-agent-plan.md).

## Repo map
| Path | What |
|---|---|
| `apps/pwa` | Phone app: camera, calls, voice, challenge, replay |
| `apps/dashboard` | Judges' screen: score, calls, AI votes, Droid panel, ask-the-ref, live world state |
| `services/gateway`, `services/recorder`, `services/ingest` | Phone API, replay recording, optional WebRTC |
| `services/courtcam-adapter`, `services/flight` | Calibration and the ping-pong vision module |
| `services/engine`, `services/compiler`, `services/rules` | Rule engine + AI votes, Factory Droid house rules, ask the ref (Apify → Moss → Claude) |
| `services/players`, `services/possession` | Basketball (if time allows) |
| `spacetime/` | SpacetimeDB module: the shared world state (metadata only, no video) |
| `packages/` | Contracts (JSON Schema), generated types, shared Python lib, state client |
| `rulepacks/` | One YAML per sport |
| `docs/` | Plan, interfaces, decisions, progress, research; `docs/archive/` is superseded |

## Run it (macOS, M5 Pro)
`make dev` starts everything natively. Phones connect to `https://$TROPHY_DOMAIN/cam/`. Copy `.env.example` to `.env` and fill in the keys; never commit `.env`. Full setup instructions will land here once the services exist.

## Prize-track sections (filled in at submission)
- **Factory Droid:** where Droid runs, its trigger, its sandbox and what it can touch, and what the dashboard shows.
- **Cartesia:** the features used (Sonic WebSocket TTS, `context_id`, `cancel`, emotion, two voices, Ink-2 STT with turn detection) and known limitations.
- **Spacetime:** the shared world state (vision observations, game state, votes, house rules, ask log).
- **Anthropic:** our community and their problem, how Claude is used, and **where it could go wrong** and how we contain it.
- **Bitdeer AI Model Studio, Gemini:** each one's role as a challenge voter.
- **Moss, Apify:** the rulebook actor → Moss index → cited answers.
- **Meta:** how Trophy brings people closer.

## License
MIT (see [LICENSE](LICENSE)). Third-party code, models and media keep their own terms: see [docs/licenses.md](docs/licenses.md).
