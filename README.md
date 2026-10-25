# Trophy 🏆

**A universal AI referee for pickup games, built at Cal Hacks 13.0.**

Point a phone at a ping-pong table and Trophy referees the game:
- It **keeps score**.
- It **calls the edge rule and illegal serves**. Under the official ITTF law, the toss must rise at least 16 cm off the open palm, go up within 30° of vertical and be struck on the way down. Hidden serves and net-touch lets are called too.
- It **speaks every call** in a referee voice.
- Every call shows how sure it is: **AUTO** at p ≥ 0.90, **BETA** with its probability and open to challenge, or **PLAYERS DECIDE** when the cameras can't judge it.
- A **challenge** brings up an **instant replay** with a second opinion from Claude next to the geometry. The vote runs in the background and never holds up a call.
- Players can **ask the ref** by voice. Judgement questions ("was that on the edge?") are answered by a geometry check on the ball track; rules questions are answered from the sport's rule pack and the group's approved house rules.
- Players can **add their own house rule** in plain English, and a Factory Droid writes, tests and applies it.

> **Status (2026-10-24):** the platform is on `main`: capture, the gateway, replay, voice, the Spacetime world state, the judges' dashboard and Trophy Watch. The referee itself (rule engine, vision, Droid compiler, referee voice) is in review on rustybubble/trophy#19, so on `main` a game streams, records and replays, but nothing calls a point yet. Every number below is measured, with the device and method next to it; anything not measured yet says so.

## Repo map
| Path | What |
|---|---|
| `apps/pwa` | Phone app: camera, calls, voice, challenge, replay |
| `apps/dashboard` | Judges' screen: score, calls, AI votes, Droid panel, ask-the-ref, live world state |
| `apps/watch` | Trophy Watch: post-game recap, highlights, moments, replay, stats |
| `services/gateway`, `services/recorder` | Phone API and replay recording |
| `services/flight` | The ping-pong vision module (arriving with #19) |
| `services/engine`, `services/compiler`, `services/referee` | Rule engine + AI votes, Factory Droid house rules, the referee voice (arriving with #19) |
| `spacetime/` | SpacetimeDB module: the shared world state (metadata only, no video) |
| `packages/` | Contracts (JSON Schema), generated types, shared Python lib, state client |
| `infra/` | Caddy + Porkbun DNS for `https://trophy.photo` |
| `docs/` | Plan, interfaces, decisions, progress, agent briefs (`docs/plan/prompts/`), research |

## Setup
Everything runs natively on one Mac (we use an M5 Pro); there is no cloud backend (D-30). The phones and the Mac must be on the same Wi-Fi. Full walkthrough: [`docs/plan/prompts/mac-bringup.md`](docs/plan/prompts/mac-bringup.md).

**1. Tools.** `git`, Python 3.11, [`uv`](https://docs.astral.sh/uv/), Node 22 + npm, `ffmpeg`, Redis 7 (`brew install redis`, or Docker), the SpacetimeDB **2.13** CLI (`curl -sSf https://install.spacetimedb.com | sh`), and Caddy built with the Porkbun DNS module, at `~/.trophy/bin/caddy` (`xcaddy build --with github.com/caddy-dns/porkbun`).

**2. Code and secrets.**
```bash
git clone https://github.com/rustybubble/trophy && cd trophy
npm ci
cp .env.example .env
```
Fill in `.env` yourself and never commit it. It holds the Cartesia key, the Porkbun keys (for the certificate), the model keys, and `TROPHY_DOMAIN` (ours is `trophy.photo`).

**3. Spacetime.** With `spacetime start --listen-addr 127.0.0.1:3000 --non-interactive` running in another terminal:
```bash
make stdb-publish     # publish the module as `trophy`
make stdb-provision   # one identity per backend service (engine, vision, compiler) -> .env
make stdb-seed        # labelled-synthetic smoke test of every reducer
```
Then stop that `spacetime`: `make dev` starts its own.

**4. Run it.**
```bash
make dev
```
This (re)starts Redis, SpacetimeDB, the gateway, the recorder, the PWA, the dashboard, Trophy Watch and Caddy from the `Procfile`; `python3 scripts/dev.py --stop` stops them all. Check `curl -s http://127.0.0.1:8000/api/healthz`.

**5. Point the domain at the Mac.** `python3 infra/dns/porkbun_set_ip.py` sets the `trophy.photo` A record to the Mac's LAN IP. Caddy gets a Let's Encrypt certificate through Porkbun DNS-01, so nothing has to be reachable from the internet.

**6. Open it.**
| Who | URL |
|---|---|
| **Players' phones** (the camera) | **`https://trophy.photo/cam/`**: create or join a game, mount the phone side-on at the net line, landscape |
| Judges' dashboard | `https://trophy.photo/` (or `http://127.0.0.1:5174/?demo=table_tennis` for the labelled-synthetic demo) |
| Trophy Watch (post-game) | `https://trophy.photo/watch/` |

Phones need HTTPS for the camera and microphone, which is why the domain exists. On campus or guest Wi-Fi, check that phones can reach the Mac: client isolation or DNS-rebind filtering blocks it, and a travel router avoids both.

**Checks.** `make check` runs what CI runs (lint, types, tests, fixture validation, codegen staleness). `make e2e` plays the CC BY ping-pong clip into the running stack as a phone and checks every hop. Fetch the clip first with `python3 tools/fetch_clips.py --sport table_tennis`; it checks the license.

## Cartesia
Voice is how Trophy referees: every call is spoken, and players talk back to the ref.

**Features used**
- **Sonic TTS over one WebSocket** per phone (`sonic-3.6`, raw `pcm_f32le` at the device's sample rate, `max_buffer_delay_ms: 0`), opened when the game screen loads, so the first call doesn't pay for the handshake (`apps/pwa/src/lib/voice.ts`).
- **`context_id` per line plus `cancel`:** a new call cancels the line that's still playing, because a stale call is worse than none.
- **Inline emotion** (`<emotion value="excited"/>`) on game and match points only. Ordinary calls stay neutral.
- **Two voices:** `calls` for the referee's calls and `ref` for ask-the-ref answers (`CARTESIA_VOICE_CALLS`, `CARTESIA_VOICE_REF`).
- **Ink-2 STT with turn detection** (`wss://api.cartesia.ai/stt/turns/websocket`, `turn.update` / `turn.end`) for push-to-talk: voice intents ("challenge", "undo that call", "what's the score", a house rule) and ask-the-ref questions.
- **Short-lived access tokens:** the gateway mints them with `POST /access-token` (TTS + STT grants), and the phone passes `access_token` + `cartesia_version` as query parameters. The API key never leaves the Mac.
- Arriving with #19: server-side Sonic in `services/referee` for ask-the-ref answers.

**Measured**
| What | Value | Device / method |
|---|---|---|
| TTS first audio chunk | **112 ms** after the request, 234 ms after the tap | iPhone (iOS 18.7, Firefox for iOS = WebKit) through `https://trophy.photo`, campus Wi-Fi; single run |
| Ink-2 `turn.end` | **≤ 82 ms** after the button release, transcript exact | same iPhone; single runs |
| TTS first chunk (desktop) | 87–309 ms after the request | Windows PC, campus Wi-Fi, 3 runs |
| Ink-2 `turn.end` (desktop) | 768–1030 ms after speech ended | Windows PC, 3 runs |
| Access-token mint | 193–291 ms | Windows PC → Cartesia, 4 runs |
| Call posted → shown on the phone (`call_ack`) | 31.8 ms | test call via Spacetime, PWA in a desktop browser; single run |
| Call spoken ≤ 1.5 s after the rally ends (C3) | _not measured yet: needs the engine (#19) on the live stack_ | |

**Known limits**
- **Not yet tested in Safari itself**, only in WebKit through Firefox for iOS. iOS gives us no vibration, so a call is a beep, a flash and the voice.
- **The first call needs the TTS socket open.** If the token has expired (we refresh 30 s early) or the socket dropped, that call pays the reconnect (about 0.3 s).
- **Push-to-talk, not always listening:** a phone at a noisy table hears the ball and the players, so Ink-2 runs only while the button is held.
- **The onset microphone runs without echo cancellation** (it needs the transients), and push-to-talk reuses it, so the ref's own voice can bleed into a question asked while it's still speaking.
- **One language (English).**
- **Default voices:** both voices fall back to one stock Sonic voice until the two env vars are set.

## Spacetime
SpacetimeDB 2.13 is Trophy's shared world state (D-21): one module that every phone, the dashboard and Trophy Watch subscribe to, and that the backend services write to. Video never goes into it; frames stay on Redis and the local recorder.

**What's in it** (`spacetime/src/index.ts`, 17 tables, 25 reducers)
- **World state from vision:** `observation` (every event: game time, court-metre position, σ, confidence, camera) and `track_sample` (the ball at 10 Hz, pruned after 120 s).
- **Game state:** `game`, `camera`, `rally`, `call`, `score`, `challenge`, `ai_vote` (one row per call and voter, with an uncalibrated probability).
- **Agents and post-game:**
  - `house_rule` and `droid_run`: the Factory Droid's trigger, its streamed plan, steps, diff and gate results;
  - `sport_module`: the approved rule packs;
  - `ask`: the ask-the-ref transcript, with how it was answered, the check, p and whether it was calibrated;
  - `moment` and `commentary`, for Trophy Watch.
- **Each table has typed columns for filtering, plus `json`**, the full contract object from `packages/contracts/*.schema.json`. Clients read through `@trophy/state-client`, one typed API that also has a labelled-synthetic mock for UI work.

**How we use it**
- **Writers are backend services, checked by identity (D-25).** An unauthenticated HTTP call to SpacetimeDB gets a fresh random identity. So the module stores its publisher in `init`, the publisher registers one identity per service (vision, engine, compiler), and every writing reducer checks `ctx.sender` against its role. Phones never write: they talk to the gateway, which turns actions into engine commands.
- **One JSON-string argument per reducer**, so Python services call reducers with a plain HTTP POST (`["<json>"]`) and the module validates the payload itself.
- **Browsers only subscribe.** Caddy forwards just `/stdb/v1/{ping, identity, database/<db>/subscribe}` from the LAN; reducer calls, SQL and publishing stay on 127.0.0.1.
- The engine's house-rule approval and the compiler's Droid runs meet in Spacetime: the compiler can't approve its own run, and only a ready run with passing results and a pinned commit can be approved.

**Measured** (SpacetimeDB 2.13.0 local server; Windows 11 localhost, Core Ultra 5 125U, **not the Mac**; single runs)
| What | Value | Method |
|---|---|---|
| Reducer (Python HTTP) → TypeScript subscriber | **p50 3.4–5.0 ms, p95 5.1–7.6 ms**; 10-row batches p50 6.5 ms, p95 8.0 ms | 200 calls at 20 Hz, same host (`spikes/spacetime-latency/`) |
| HTTP reducer round trip | p50 4.4–5.9 ms, p95 5.7–8.1 ms | same |
| `post_call` → `SpacetimeState.onCall` | 7.3–14.4 ms | vitest integration, direct and through Caddy `wss://trophy.photo/stdb` |
| Vision writer flush | 31 observations + 10 track samples in 61 ms, 0 dropped | `trophy.world.ObservationWriter` |
| Synthetic demo seed | 97 reducer calls in 1.65–1.78 s | `spacetime/scripts/seed_demo.py --check` |
| Identity checks | 7 allowed and 8 rejected writes as expected | `provision.py --check-platform`, on the Mac (Agent 2) |
| Live-game numbers on the Mac | _not measured yet_ | |

## Meta: bringing people closer together
Pickup games are how strangers become regulars: a table in a dorm basement, a court after class. The thing that ends them is the argument. Was that on the edge? Was the toss high enough? Whose serve is it? With no referee, the loudest player wins the call, or people stop showing up.

**How Trophy keeps people playing together**
- **Anyone can join.** A phone on a mount is the camera; the next player scans a QR code to join the same game. Nobody needs an app, an account or special hardware.
- **Everyone hears the same call at the same moment.** The call is spoken aloud, not whispered to one player's screen.
- **It says when it isn't sure.** BETA calls show their probability and can be challenged. When the cameras can't see a call, Trophy says PLAYERS DECIDE and hands it back to the people at the table instead of pretending.
- **A challenge is a shared moment, not a fight:** the replay plays for everyone, and Claude gives a second opinion next to the geometry. The players (or the judge) decide.
- **Every group keeps its own rules.** "First to 7, win by 1", or "a serve that clips the net and lands in is good": say it, and the Droid writes it into the rule pack, tests it and applies it once the group approves.
- **Trophy Watch** turns the game into something to share afterwards: the recap, the moments, the ★ Play of the game.

**What players said** _[OPEN-8: quotes from real players at Cal Hacks go here, with their permission. None yet; we won't invent any.]_

## Factory Droid
_TODO (Agent 3, with #19): where the Droid runs, its trigger (`house_rule` row / `calibrate_checks`), the sandbox and exactly what it may touch, the `replay_test` / `check_test` gate, what the dashboard shows, and measured Droid-rule end-to-end time._

## Anthropic
_TODO (Agent 3, with #19): our community and its problem, how Claude is used (ask-the-ref phrasing grounded in `rules.yaml` + house rules, the challenge voter), **where it could go wrong** and how we contain it._

## License
MIT (see [LICENSE](LICENSE)). Third-party code, models and media keep their own terms: see [docs/licenses.md](docs/licenses.md).
