# Trophy 🏆

**A universal AI referee for pickup games, built at Cal Hacks 13.0.**

Point a phone at a ping-pong table and Trophy referees the game:
- It **keeps score**.
- It **calls the edge rule**. Illegal serves follow the official ITTF law: the toss must rise at least 16 cm off the open palm, go up within 30° of vertical and be struck on the way down. Today that is **measured on recorded serves only**: the serve, hidden-serve and net-let rules are in the rule pack, but they don't fire live yet, because the live 2D pipeline doesn't emit serve-toss or net-touch events.
- It **speaks every call** in a referee voice.
- Every call shows how sure it is: **AUTO** at p ≥ 0.90, **BETA** with its probability and open to challenge, or **PLAYERS DECIDE** when the cameras can't judge it.
- A **challenge** brings up an **instant replay** with a second opinion from Claude next to the geometry. The vote runs in the background and never holds up a call.
- Players can **ask the ref** by voice. Judgement questions ("was that on the edge?") are answered by a geometry check on the ball track; rules questions are answered from the sport's rule pack and the group's approved house rules.
- Players can **add their own house rule** in plain English, and a Factory Droid writes, tests and applies it.

> **Status (2026-10-25, demo day):** the whole referee runs natively on one Mac from `make dev` (branch `demo/integration`, rustybubble/trophy#19). Phones, or recorded clips played as phones from the dashboard's library, stream to the gateway; BlurBall tracks the ball on every camera; the golden table-tennis module turns the tracks into bounces, nets and dead balls; a rule pack **written by the Factory Droid from the ITTF laws** (D-42) calls the points; every call is spoken on the Mac's speaker and on the phones; a challenge opens the instant replay from the referee's own recording on the dashboard and on the phone; a house rule typed or spoken on a phone is compiled, gated and approved live ("first to 7, win by 1": ready in 18.7 s on this Mac today); Trophy Watch opens on the ended game. Claude's background vote on challenged calls and ask-the-ref need `ANTHROPIC_API_KEY` (the referee service refuses to start without it, by design; set on the demo Mac on 2026-10-25). **No accuracy on real footage is claimed**: the calls on the preloaded clips are unlabelled. Every number below is measured, with the device and method next to it; anything not measured yet says so.

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

## Setup
Everything runs natively on one Mac (we use an M5 Pro); there is no cloud backend (D-30). The phones and the Mac must be on the same Wi-Fi. Full walkthrough: [`docs/plan/prompts/mac-bringup.md`](docs/plan/prompts/mac-bringup.md); the live-demo commands, step by step: [`docs/demo-runbook.md`](docs/demo-runbook.md).

**1. Tools.** `git`, Python 3.11, [`uv`](https://docs.astral.sh/uv/), Node 22 + npm, `ffmpeg`, Redis 7 (`brew install redis`, or Docker), the SpacetimeDB **2.13** CLI (`curl -sSf https://install.spacetimedb.com | sh`), and Caddy built with the Porkbun DNS module at `~/.trophy/bin/caddy`: download it from `https://caddyserver.com/api/download?os=darwin&arch=arm64&p=github.com%2Fcaddy-dns%2Fporkbun` (or `xcaddy build --with github.com/caddy-dns/porkbun`) and check `caddy list-modules | grep porkbun`.

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
This (re)starts Redis, SpacetimeDB, the gateway, the recorder, the engine, BlurBall (`flight`), the sport module (`live`), the announcer, the Droid compiler, the PWA, the dashboard, Trophy Watch and Caddy from the `Procfile`; `python3 scripts/dev.py --stop` stops them all, and `python3 scripts/dev.py engine compiler` restarts just those. Check `curl -s http://127.0.0.1:8000/api/healthz`. The `referee` entry (ask the ref) exits until `ANTHROPIC_API_KEY` is in `.env`; the engine turns Claude's vote on by itself once it is.

**5. Point the domain at the Mac.** `python3 infra/dns/porkbun_set_ip.py` sets the `trophy.photo` A record to the Mac's LAN IP (rerun it whenever DHCP changes the address). Caddy gets a Let's Encrypt certificate through Porkbun DNS-01, so nothing has to be reachable from the internet. Porkbun secret keys start with `sk1_` (lowercase): a capitalised prefix is rejected as "secret key does not match".

**6. Open it.**
| Who | URL |
|---|---|
| **Players' phones** (the camera) | **`https://trophy.photo/cam/`**: create or join a game, mount the phone side-on at the net line, landscape |
| Judges' dashboard | `https://trophy.photo/` or `http://127.0.0.1:5174/` on the Mac: **Start a game**, then **Play** a preloaded two-camera game or join phones; `?demo=table_tennis` shows the labelled-synthetic script |
| Trophy Watch (post-game) | `https://trophy.photo/watch/` |

Phones need HTTPS for the camera and microphone, which is why the domain exists. On campus or guest Wi-Fi, check that phones can reach the Mac: client isolation or DNS-rebind filtering blocks it, and a travel router avoids both.

**Checks.** `make check` runs what CI runs (lint, types, tests, fixture validation, codegen staleness). `make e2e` plays the CC BY ping-pong clip into the running stack as a phone and checks every hop. Fetch the clip first with `python3 tools/fetch_clips.py --sport table_tennis`; it checks the license.

## Cartesia
Voice is how Trophy referees: every call is spoken, and players talk back to the ref.
**Every call is spoken on the table speaker.** The engine appends each call to Redis `ev:calls`; `referee announce --speaker`
(the Procfile's `announcer`) speaks it through Sonic with the calls voice: first audio 83-321 ms after the call, measured
2026-10-24 on the Mac. The phones speak the same calls through their own Cartesia sockets.


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
A Factory Droid (`@factory/droid-sdk`, `services/compiler`) is how a judge changes the rules mid-game. It is never in
the per-call hot path.
- **Trigger:** a `house_rule` row with status `pending` in Spacetime (the judge typed or said "first to 7, win by 1").
  `trophy-droid watch` subscribes and starts a run. A second job, `calibrate_checks`, specialises the geometry check
  library to a camera setup (D-36).
- **The rules themselves are Droid-written, from the laws.** `trophy-droid compile-rules` gives the Droid the sport's laws
  (`sports/<sport>/laws.md`, ITTF clause ids), the engine's vocabulary rendered from code (`trophy_engine.vocabulary`: every
  event field, rally-state field and evidence parameter the engine can supply) and the labelled samples, and starts it from an
  **empty** `rules:` list; it must cite a clause per rule and declare what it could not encode. A judge's correction on the
  dashboard ("that was one rally, won by B") becomes a `correction` run: the engine fixes the score, exports the span as a
  labelled sample, and the Droid repairs the pack against it (D-42).
- **Sandbox:** a fresh git repository per run in `~/.trophy/droid_runs/<run_id>`, outside the repo, holding only the
  pack to edit, its schemas, labelled synthetic samples, the brief and one gate script. Three layers enforce it: a
  PreToolUse hook (`hooks/guard.py`) that allows edits to the job's allowlisted files, reads only inside the sandbox,
  and exactly one command, the bare `./replay_test` or `./check_test`; a git audit after each turn that fails the run if anything else changed (or
  nothing did); and the gate itself, which runs the Droid-written code with a clean environment, no network and no
  writes outside the sandbox (`sandbox-exec` on macOS).
- **Gate and approval:** `replay_test` replays the labelled fixtures through the candidate module and the rule engine
  (event counts, timing, the labelled rally winners). On `ready` the dashboard's Droid panel shows the plan, every
  step, the diff, the gate table and the calls that would change. The judge clicks Approve; the engine loads the pack
  **from the gated commit** (`git show`), never from the working tree, and hot-loads it.
- **Measured (this Mac, `claude-sonnet-5`, effort low, single runs):** "a serve that clips the net and lands in is a let"
  went pending → **ready in 27.5–30.6 s** (first attempt, gate 19/19 in 270 ms), **65.5 s** once under load; approve →
  hot-load in **0.5–0.8 s**. On the synthetic 3D fixtures, `calibrate_checks` was **ready in 86.9 s** (inside the 90 s cap, over the 60 s target), and a referee `new_check` ("how fast was the ball in that rally") was **ready in 37.2 s** with its answer gated on the session's own track.

## Anthropic
Pickup games have no referee, so close calls end in arguments or a replayed point. Trophy measures what sensors can
measure and lets the players decide the rest, honestly labelled.
- **How Claude is used:** the referee voice (`services/referee`) routes a spoken question and phrases the answer from a
  geometry check's numbers; rules questions are answered only from the sport's `rules.yaml` plus approved house rules;
  Claude is one of three background voters on a challenged BETA call (`decide()`), and writes post-game commentary
  from the moment's facts. The Factory Droid runs on a Claude model too.
- **Where it could go wrong, and the containment:**
  - *A made-up line call.* Claude never makes one: geometry decides, Claude only phrases, and a vote is shown next to
    the measurement, labelled uncalibrated.
  - *A wrong number in a spoken answer.* Every digit Claude says must be one it was given; otherwise the deterministic
    rendering of the same measurement is used, labelled `template`.
  - *A confident but unsupported rules answer.* Answers are grounded only in the pack the engine enforces; weak
    grounding says so instead of guessing.
  - *A house rule that does something else.* The Droid's sandbox, gate and the judge's approval of a visible diff.
- **Not yet measured:** no `ANTHROPIC_API_KEY` has been available on the demo Mac, so phrasing latency (budget
  0.5–1.5 s) and live votes have only been tested against recorded API response shapes.

## License
MIT (see [LICENSE](LICENSE)). Third-party code, models and media keep their own terms: see [docs/licenses.md](docs/licenses.md).
