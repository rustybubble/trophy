# Trophy demo: everything that is built, running together

*Branch `demo/integration` (2026-10-24): `main` (incl. the judges' dashboard #17 and the CC BY clip `make e2e` #18) + the
finished branches `mvp/tt-cloud` (flight: clips → fused 3D map), `a3/droid-checks` (rule engine, Factory Droid compiler,
golden table-tennis module, the Droid-written 3D check library and `calibrate_checks` job, synthetic fixtures) and
`voice/referee` (the referee voice service), plus the **upload-a-clip** path (§2). Not here: the engine's `run_check` /
`request_check` handlers for the referee, a live Droid `calibrate_checks` run, Trophy Watch, basketball, the GPU box (PR #16).*

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

## 2. Upload a clip and referee it (the demo site, localhost)
Open **http://127.0.0.1:5174/** (the judges' dashboard), click **Start a game**, then in the **Upload a clip** panel:
1. choose a clip (mp4 / mov / webm; one phone, side-on at the net line, white ball works best);
2. the first frame appears: tap the four table corners in the order shown (A end right, B end right, B end left, A end left);
3. pick the ball colour and the replay speed, click **Referee this clip**.

What happens (`services/gateway/gateway/demo.py`): the clip is stored under `data/local/uploads/<game>/`, flight extracts
the first frame; on run, `flight.clip2l1` tracks the ball (classical detector + gated tracker) and turns the corners into
the image→table homography, writing a layer-1 log; `trophy-play --samples` runs the golden `sports/table_tennis/events.py`
over it (bounces, contacts, dead ball), registers the camera with its **untrusted** calibration, and publishes the events
on Redis `ev:flight` paced by the clip's clock while mirroring the track into Spacetime. The live `trophy-engine` consumes
them like perception's events and posts calls, rallies and the score to Spacetime, so they appear in the **Calls** panel,
the **World state** view (ball trail + bounces) and on every joined phone (spoken through Cartesia). The video plays in
sync with the replay. Because the calibration is four tapped corners on one camera with no clock sync, the engine caps
every call at **BETA**; nothing here is a measurement of accuracy.

**Measured on this Mac (2026-10-24, single runs) with flight's rendered SYNTHETIC side clip** (`flight.cloud synth`,
1280×720, 196 frames): upload + first frame < 1 s; tracking **0.68–0.73 s** for 177 samples (90 % of frames);
11 events replayed at 2× in 5.0 s; 1 call (`off_table`, BETA) into Spacetime; 11 observations + 52 track samples mirrored;
the dashboard showed the call, the score and the trail live. No real clip was available on this machine.
Through the API: `POST /api/demo/uploads`, `POST /api/demo/runs`, `GET /api/demo/runs/<id>` (a judge/display token).

A clip to try without filming: `data/local/clips/synthetic/side-SYNTHETIC.mp4` (flight's rendered synthetic rally;
its true corners are in the `.corners.txt` next to it; regenerate both with `python -m flight.cloud synth`). It is
labelled SYNTHETIC everywhere.

Flight's two-camera 3D fusion (`services/flight`, §6) still needs two clips; a single upload goes through this 2D path.

## 3. The live game (synthetic rallies through the real pipeline)
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

## 4. A house rule, compiled by the Factory Droid, live
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
27.5 s** (interactive run) and **28.3 s** (`make e2e-synthetic`); approve → engine hot-load → status `approved` in **0.8 s**.
Note: the engine keeps game state in memory, so restart it *before* creating the game, not between the rule and the
approval.

## 4b. All of the above, headless
```bash
make e2e-synthetic   # scripts/e2e_synthetic.py: game via the gateway -> trophy-play -> calls/score/rallies/moments vs labels -> house rule -> ready -> approve
make e2e-synthetic PYTHON=python3   # (the default); add --no-droid through `python3 scripts/e2e_synthetic.py --no-droid` to skip the Factory run
```
Last result on this Mac: `E2E PASS` (2 fixtures in 3.6 s at ×4; Droid ready after 28.3 s; approved in 0.8 s).

## 5. The referee that talks (Cartesia; Claude needs its key)
```bash
uv run --directory services/referee --frozen referee speak "Edge ball. Good. Point, B." --voice calls --emotion excited --wav-dir /tmp/voice
# measured 2026-10-24, this Mac, real key, single run: socket open 1512 ms, first audio 174 ms, done 561 ms, 2.72 s of audio
```
With `ANTHROPIC_API_KEY` in `.env`, `referee serve` (:8100) answers `POST /api/ask` from the PWA's hold-to-talk: score
and last-call questions from the phone's context, rules questions grounded only in `sports/<sport>/rules.yaml` plus
approved house rules, and geometry questions through `run_check` once the engine's check handlers land (until then they
time out honestly after 1.5 s).

## 6. The 3D map (flight, synthetic two-camera rally)
```bash
cd services/flight
uv run --frozen python -m flight.cloud synth --out /tmp/synth0                       # renders two 1280×720 clips + truth (SYNTHETIC)
uv run --frozen python -m flight.cloud run --field /tmp/synth0/field.json --cam side=/tmp/synth0/side.mp4 --cam diag=/tmp/synth0/diag.mp4 --out /tmp/synth0/out
uv run --frozen python -m flight.cloud eval --out /tmp/synth0/out --truth /tmp/synth0/truth.json
open /tmp/synth0/out/viewer.html                                                       # browser point-cloud viewer
```
This produces the Droid brief's `field.json` + `track3d.jsonl` (+ `events.json`). It is not yet wired to the live
engine: that is the `track3d` adapter and check library in progress on `a3/droid-checks`.

## 7. What a judge sees
- **Scoreboard / Judge (PWA):** the synthetic label, the score, rally number, each call with its tier and p, Challenge
  (opens the replay + AI votes once voter keys exist), Hold to talk (needs the referee service), the menu with house rules.
- **Spacetime SQL** (`spacetime sql -s local trophy "SELECT … FROM call WHERE game_id = '…'"`) shows the same rows every
  client subscribes to: `game`, `score`, `rally`, `call`, `moment`, `house_rule`, `ask`.

## Known gaps on this branch
- The engine keeps game state in memory: restart it before creating a game, not during one.
- `services/gateway/tests/test_gateway.py::test_frames_ws_writes_bus_and_still` fails on this Mac on `main` too (3 rows instead of 4); untouched.
- The engine's `run_check` / `request_check` handlers (what the referee service asks for) are not built; `trophy-engine
  --field --ask` serves the 3D-check questions directly instead.
