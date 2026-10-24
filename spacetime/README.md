# SpacetimeDB module: the shared world state (Agent 1)

**SpacetimeDB 2.13, TypeScript module** (`src/index.ts`), published locally as database `trophy` (`spacetime start`, :3000). Phones and the dashboard subscribe through `@trophy/state-client` (`SpacetimeState`) at `wss://trophy.photo/stdb`; backend services call reducers over HTTP on `http://127.0.0.1:3000`.

**What it holds: metadata only. Video frames never go in here** (D-21); they stay on Redis and in the local recorder.
- **World state:** `observation` (every vision event: time, position in court metres, σ, confidence, camera) and `track_sample` (the ball at 10 Hz; the module keeps the last 120 s per camera). Every phone, the dashboard and every agent see the same facts. Adding a camera adds rows, not schema.
- **Game state:** `game`, `camera`, `rally`, `call`, `score`, `challenge`, `ai_vote`.
- **Agents:** `house_rule` (the Factory Droid's trigger + streamed plan, steps, diff and results) and `ask` (ask-the-ref transcripts with citations).

## Design (D-25)
- **Every table has typed columns** for filtering and display (`game_id`, `status`, `t_game_s`, `p`, `tier`, …) **plus `json`: the full contract object** (`packages/contracts/*.schema.json`). `SpacetimeState` hands clients the parsed `json`, so contract growth needs no module change.
- **Every writing reducer takes one JSON string.** Over HTTP the body is the args array: `["<json text>"]`.
- **Writers are backend services, checked by identity.** The publisher (owner) registers one identity per service with a role. An unauthenticated HTTP call gets a random identity and is rejected (HTTP 530).

| Role | Reducers | Payload |
|---|---|---|
| owner | `register_service`, `unregister_service` | `{identity_hex, role, label?}` |
| **vision** | `post_observations` | JSON array of `Event` |
| | `post_track_samples` | JSON array of `TrackSample` (prunes > 120 s per camera) |
| **engine** | `upsert_game`, `upsert_camera` | a full `Game` / `Camera` |
| | `open_rally`, `close_rally` | a full `Rally` (also bumps `game.rally_no`) |
| | `post_call` | a full `Call` (same id replaces) |
| | `update_call_status` | `{call_id, status, suggested?}` |
| | `set_score` | JSON array of `Score` (one per team) |
| | `open_challenge` | a full `Challenge` (status `open`); also sets the call to `challenged` and links speculative votes |
| | `resolve_challenge` | a full `Challenge` (result `upheld`/`overturned`); also sets the call status |
| | `post_ai_vote` | a full `AiVote` (keyed by call + backend; `challenge_id` filled from an open challenge) |
| | `insert_house_rule` | a full `HouseRule` with status `pending` (**the Droid's trigger**) |
| | `set_house_rule_status` | `{rule_version, status: pending\|approved\|rejected\|failed, error?, pack_path?}` |
| | `post_ask` | a full `Ask` |
| | `prune_track_samples` | `{cam_id, before_t_game_s}` |
| **compiler** | `update_house_rule_progress` | `{rule_version, status?: compiling\|ready\|failed, plan_md?, steps?, append_steps?, diff?, results?, pack_path?, error?, backend?}`; refused once approved/rejected |

### Calling a reducer from Python (engine, compiler)
```python
import json, os
from trophy.world import SpacetimeClient
stdb = SpacetimeClient(token=os.environ["SPACETIME_ENGINE_TOKEN"])   # SPACETIME_URI / SPACETIME_MODULE from env
stdb.call("post_call", json.dumps(call.model_dump(by_alias=True, exclude_none=True, mode="json")))
```
Vision modules use `trophy.world.ObservationWriter` / `TrackSampleWriter` instead (batched, never blocking). The Node compiler can POST the same body: `fetch(\`${uri}/v1/database/trophy/call/update_house_rule_progress\`, {method: "POST", headers: {Authorization: \`Bearer ${token}\`, "Content-Type": "application/json"}, body: JSON.stringify([JSON.stringify(patch)])})`, or subscribe with the `spacetimedb` SDK to `SELECT * FROM house_rule WHERE status = 'pending'`.

## Run it (Windows PC; on a Mac drop `--root-dir`)
```bash
S="$HOME/.spacetimedb/spacetime.exe --root-dir=$HOME/.spacetimedb"   # see spikes/spacetime-latency/README.md
$S start --listen-addr 127.0.0.1:3000 --non-interactive               # keep running
$S publish -s local -p spacetime --yes=skip-login trophy               # add --delete-data=on-conflict for breaking changes
python spacetime/scripts/provision.py                                  # engine/vision/compiler identities -> .env
$S generate --lang typescript -p spacetime -o packages/state-client/src/bindings --no-config -y
python spacetime/scripts/seed_demo.py --check                          # labelled-synthetic demo game + smoke test
```
Caddy forwards only `/stdb/v1/{ping, identity, database/<db>/subscribe}` from the LAN; reducer calls, SQL and publishing are reachable only on 127.0.0.1.

## Tests
- `python spacetime/scripts/seed_demo.py --check`: every reducer through the right role, row counts and statuses, vote linking, scores, and six rejected calls (wrong role, anonymous, compiler approving, engine posting observations, engine registering a service, missing fields).
- `TROPHY_STDB_IT=1 npx vitest run --root packages/state-client`: `SpacetimeState` receives engine and vision writes live, filters by game, and replays state to a late subscriber. Add `TROPHY_STDB_WS=wss://trophy.photo/stdb` to go through Caddy.
- Neither runs in CI (CI has no Spacetime server); `tsc` on the module does.
