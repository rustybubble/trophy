# Trophy demo: everything that is built, running together

*Branch `demo/integration` (2026-10-24): `main` + the three finished branches `mvp/tt-cloud` (flight: clips → fused 3D
map), `a3/droid-checks` (rule engine, Factory Droid compiler, golden table-tennis module, synthetic fixtures) and
`voice/referee` (the referee voice service). What is in progress and not here: the 3D check library and
`calibrate_checks` runs (uncommitted on `a3/droid-checks`), the engine's `run_check` / `request_check` handlers, the
dashboard, Trophy Watch, basketball, the Vultr/AWS GPU box (PR #16, needs the user's OK).*

**Everything shown is labelled SYNTHETIC unless it comes from a phone.** The rallies in this demo are the labelled
synthetic fixtures (`evals/fixtures/synthetic/table_tennis`) run through the golden module's `events.py`, which is
exactly what the Droid's gate replays. No accuracy on real footage is claimed anywhere in this document.

## 0. Prerequisites (this Mac, measured 2026-10-24)
| What | How |
|---|---|
| Tools | `brew install redis ffmpeg`; `spacetime version upgrade` (2.13.0); `uv`, Node 24, the `droid` CLI |
| Env | `cp .env.local .env`; `TROPHY_TOKEN_SECRET` ≥ 16 chars (`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`); `SPACETIME_PUBLIC_URI=ws://127.0.0.1:5173/stdb` for a localhost demo (phones on `trophy.photo` need Caddy + the Porkbun keys instead) |
| Keys present | `CARTESIA_API_KEY` (calls are spoken), `FACTORY_API_KEY` (house rules compile) |
| Keys missing | `ANTHROPIC_API_KEY`: the referee service (`services/referee`, ask the ref) refuses to start without it, by design (no keyless mode); `GEMINI_API_KEY`, `BITDEER_API_KEY`: no AI votes (`trophy-engine --votes` refuses) |
| Deps | `npm ci`; `uv sync --frozen` in `packages/py-trophy`, `services/{gateway,recorder,engine,referee,flight}` |

## 1. Bring the stack up
```bash
make dev                      # redis, spacetime, gateway, recorder, engine, referee*, compiler, voice, pwa, caddy*
# or only what the localhost demo needs:
python3 scripts/dev.py redis spacetime gateway recorder engine compiler pwa
```
`*` referee needs `ANTHROPIC_API_KEY`; caddy needs the `caddy` binary with the Porkbun plugin and the Porkbun keys.
Then, once per fresh Spacetime data dir:
```bash
make stdb-publish && make stdb-provision        # publishes `trophy`, writes the three service tokens into .env
make stdb-seed                                   # smoke test: 97 reducer calls in 0.66 s on this Mac, 6 rejections as expected
```
Restart the engine and compiler after provisioning (they read the tokens at start): `python3 scripts/dev.py engine compiler`.

## 2. The live game (synthetic rallies through the real pipeline)
```bash
curl -s -X POST http://127.0.0.1:8000/api/games -H 'content-type: application/json' \
  -d '{"sport":"table_tennis","params":{"synthetic":true,"label":"SYNTHETIC demo: trophy-play fixtures"}}'
# -> {"game_id": "g_…", "join_key": "…", "join_url": "https://trophy.photo/cam/?g=…&k=…"}
```
Open the PWA on this machine at `http://127.0.0.1:5173/cam/?g=<game_id>&k=<join_key>` and join as **Scoreboard** (or
**Judge**: uphold/overturn, undo, house rules; **Camera + judge** needs a camera). Then:
```bash
uv run --directory services/engine --frozen trophy-play --game <game_id> [--speed 2] [--loop]
```
`trophy-play` sends `register_camera` + `start_game` (and `set_server` per fixture, to the fixture's labelled server),
then publishes the module's layer-2 events (`bounce`, `contact`, `ball_dead`) to Redis `ev:flight`, paced by
`t_game_s`. The live engine consumes them like perception's events, posts calls, rallies, scores and moments to
Spacetime, and every phone shows (and speaks, through Cartesia) each call.

**Measured on this Mac (2026-10-24, single runs):** 25 events / 2 fixtures → 2 point calls (`ball_dead_after_last_bounce`,
A then B, matching `rally_winner` in the labels), score 1–1, 2 closed rallies, 2 moments; engine event → `post_call`
through Spacetime 36–59 ms per call (engine log `ms`); the PWA scoreboard showed the label, score, rally number and the
BETA call list live through `ws://127.0.0.1:5173/stdb`. A bug found here and fixed: the engine's ctl reader re-armed at
`$` on every read and dropped `create_game`/`start_game` that arrived while it was reading events (`test_loop_ctl.py`).

## 3. A house rule, compiled by the Factory Droid, live
```bash
uv run --directory services/engine --frozen trophy-ctl submit_house_rule <game_id> --by judge \
  --args '{"text": "a serve that clips the net and lands in is a let: replay the point"}'
# the compiler (`trophy-droid watch`) sees the pending house_rule row in Spacetime, runs the Droid in a fresh sandbox
# (allowlist: sports/table_tennis/rules.yaml only; PreToolUse hook; git audit; replay_test gate; 90 s cap),
# streams plan/steps/diff/results into the row; when status = ready:
uv run --directory services/engine --frozen trophy-ctl approve_house_rule <game_id> --by judge \
  --args '{"rule_version": "<rule_version from the house_rule row>"}'
# -> the engine hot-loads the new pack (status approved); a serve net-let now replays the point.
```
The judge view of the PWA does the same from its House rules panel (typed or spoken).

**Measured on this Mac (2026-10-24, `claude-sonnet-5`, effort low, single runs):** pending row → sandbox → one edit of
`rules.yaml` (`net_let_on_serve`, placed before `net_into_own_side`) → `./replay_test` 19/19 in 270 ms → **ready in
27.5 s** (interactive run) and **28.3 s** (`make e2e`); approve → engine hot-load → status `approved` in **0.8 s**.
Note: the engine keeps game state in memory, so restart it *before* creating the game, not between the rule and the
approval.

## 3b. All of the above, headless
```bash
make e2e        # scripts/e2e.py: game via the gateway -> trophy-play -> calls/score/rallies/moments vs labels -> house rule -> ready -> approve
make e2e PYTHON=python3   # (the default); add --no-droid through `python3 scripts/e2e.py --no-droid` to skip the Factory run
```
Last result on this Mac: `E2E PASS` (2 fixtures in 3.6 s at ×4; Droid ready after 28.3 s; approved in 0.8 s).

## 4. The referee that talks (Cartesia; Claude needs its key)
```bash
uv run --directory services/referee --frozen referee speak "Edge ball. Good. Point, B." --voice calls --emotion excited --wav-dir /tmp/voice
# measured 2026-10-24, this Mac, real key, single run: socket open 1512 ms, first audio 174 ms, done 561 ms, 2.72 s of audio
```
With `ANTHROPIC_API_KEY` in `.env`, `referee serve` (:8100) answers `POST /api/ask` from the PWA's hold-to-talk: score
and last-call questions from the phone's context, rules questions grounded only in `sports/<sport>/rules.yaml` plus
approved house rules, and geometry questions through `run_check` once the engine's check handlers land (until then they
time out honestly after 1.5 s).

## 5. The 3D map (flight, synthetic two-camera rally)
```bash
cd services/flight
uv run --frozen python -m flight.cloud synth --out /tmp/synth0                       # renders two 1280×720 clips + truth (SYNTHETIC)
uv run --frozen python -m flight.cloud run --field /tmp/synth0/field.json --cam side=/tmp/synth0/side.mp4 --cam diag=/tmp/synth0/diag.mp4 --out /tmp/synth0/out
uv run --frozen python -m flight.cloud eval --out /tmp/synth0/out --truth /tmp/synth0/truth.json
open /tmp/synth0/out/viewer.html                                                       # browser point-cloud viewer
```
This produces the Droid brief's `field.json` + `track3d.jsonl` (+ `events.json`). It is not yet wired to the live
engine: that is the `track3d` adapter and check library in progress on `a3/droid-checks`.

## 6. What a judge sees
- **Scoreboard / Judge (PWA):** the synthetic label, the score, rally number, each call with its tier and p, Challenge
  (opens the replay + AI votes once voter keys exist), Hold to talk (needs the referee service), the menu with house rules.
- **Spacetime SQL** (`spacetime sql -s local trophy "SELECT … FROM call WHERE game_id = '…'"`) shows the same rows every
  client subscribes to: `game`, `score`, `rally`, `call`, `moment`, `house_rule`, `ask`.

## Known gaps on this branch
- No dashboard app yet (`apps/dashboard` is a README): the PWA's judge/scoreboard roles and Spacetime SQL stand in.
- `services/gateway/tests/test_gateway.py::test_frames_ws_writes_bus_and_still` fails on this Mac on `main` too (3 rows instead of 4); untouched.
- The Droid `calibrate_checks` job, the 3D check library and the engine's `run_check` handlers are being built on
  `a3/droid-checks` (uncommitted there at merge time) and are not on this branch.
