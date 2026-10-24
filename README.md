# Trophy 🏆

**A universal AI referee and post-game analyzer for casual sports.** Open a link on 2–4 phones, point them at any pickup game, and Trophy referees it:
- live calls with honest confidence;
- challenges with multi-angle replays;
- a spoken voice referee;
- house rules compiled on the fly.

After the game, **Trophy Watch** turns it into a broadcast you can replay in any browser.

Built at **Cal Hacks 13.0** (Oct 23–25, 2026).

## Repo map
| Path | What |
|---|---|
| `apps/pwa` | Phone capture PWA (join by QR, stream, record, beep/flash, challenge) |
| `apps/dashboard` | Live dashboard: scoreboard, calls, challenges, sport wall, Droid compiler view |
| `apps/watch` | **Trophy Watch** post-game web app |
| `services/*` | Backend services (see each README) |
| `spacetime/` | SpacetimeDB module (live game state) |
| `packages/contracts` | JSON Schemas: Event, Call, Decide, RulePack |
| `rulepacks/` | One YAML per sport + `sports.yaml` catalog |
| `infra/` | GCP VM, Vultr, Caddy, Remotion Lambda setup |
| `data/clips` | Clip manifest + credits (no footage in git) |
| `evals/` | Labelled calls and accuracy reports |
| `docs/` | Plan, research, decisions, progress, compliance |

## Prior work disclosure
See [docs/rules-compliance.md](docs/rules-compliance.md). Trophy depends on **courtcam** (MIT), a computer-vision library published by a teammate before the event. Everything else in this repo was built during Cal Hacks 13.0.

## Quick start (on the GCP dev VM, not a laptop)
```bash
cp .env.example .env          # fill in keys; never commit .env
docker compose up -d redis spacetimedb gateway
```
Per-service instructions are in each `services/*/README.md`.

## License
MIT (see [LICENSE](LICENSE)). Third-party models keep their own licenses: [docs/licenses.md](docs/licenses.md).
