# Live demo runbook: every command, in order

*2026-10-25, this Mac (`/Users/vedanshmannem/Desktop/trophy`, branch `demo/integration`). The design and the measured
numbers are in `docs/demo.md` and `docs/progress.md`; this file is only what to type and what you should see.*

## 0. Once, before the demo

| Check | Command | Expect |
|---|---|---|
| Keys in `.env` | `grep -E '^(CARTESIA_API_KEY\|FACTORY_API_KEY\|ANTHROPIC_API_KEY\|PORKBUN_API_KEY\|PORKBUN_SECRET_API_KEY)=' .env \| sed -E 's/=.+/=set/; s/=$/=EMPTY/'` | all `set`. `ANTHROPIC_API_KEY=EMPTY` means no Claude vote and no ask-the-ref until you add it |
| Domain → this Mac | `python3 infra/dns/porkbun_set_ip.py` then `dig +short trophy.photo A` | the answer equals `ipconfig getifaddr en0`. Rerun after any Wi-Fi change |
| Speaker | System Settings → Sound: the output the referee should use, volume up | the announcer plays on the default output |
| Phones on the same Wi-Fi | open `https://trophy.photo/cam/` on a phone | the join screen (client isolation or DNS-rebind filtering blocks it; a travel router avoids both) |

## 1. Start everything (terminal 1)

```bash
make dev
```

One coloured line per service. In order: `redis`, `spacetime` (local SpacetimeDB on :3000), `gateway` (:8000), `recorder`,
`engine` (rule engine), `flight` (BlurBall on MPS), `live` (the golden table-tennis module), `referee` (ask the ref: **exits
with "ANTHROPIC_API_KEY must be set" until the key is in `.env`**, by design), `announcer` (speaks every call on the Mac),
`compiler` (`trophy-droid watch`: the Factory Droid), `voice` (the P0 spike), `pwa` (:5173), `dashboard` (:5174), `watch`
(:5175), `caddy` (:443, `https://trophy.photo`). Ready when you see:

```
   engine | ... {"svc": "engine", "msg": "started", "state": "spacetime", "votes": false ...}
   flight | ... {"svc": "flight", "msg": "started", "detector": "blurball", "device": "mps" ...}
announcer | ... {"svc": "announce", "msg": "started", "stream": "ev:calls", "speaker": true}
 compiler | watching ws://127.0.0.1:3000 trophy for pending house rules (ctrl-c to stop)
    caddy | ... "msg":"certificate obtained successfully"   (or "loaded certificate": it is cached)
```

Health, from another terminal:

```bash
curl -s http://127.0.0.1:8000/api/healthz
```

`{"ok":true,"redis":true,"spacetime":true,"adapter":false,"rules":false,"recorder":true}`: `rules` turns true once the
referee service runs (Anthropic key); `adapter` stays false (the courtcam adapter is not part of this demo).

Stop everything, or restart a few entries (the engine keeps game state in memory, so restart it **between** games, never
during one):

```bash
python3 scripts/dev.py --stop
python3 scripts/dev.py engine compiler
```

After adding `ANTHROPIC_API_KEY` to `.env`: `python3 scripts/dev.py engine referee` (the engine then logs `"votes": true`).

## 2. Watch the data being generated (terminal 2)

`make dev` runs the local SpacetimeDB; the module is published as `trophy`. Every row the phones, the dashboard and Watch
subscribe to can be read with SQL (the CLI prints an "UNSTABLE" warning first; ignore it):

```bash
spacetime sql -s local trophy "SELECT game_id, status, rally_no FROM game"
```

```bash
spacetime sql -s local trophy "SELECT game_id, team_id, points FROM score"
```

```bash
spacetime sql -s local trophy "SELECT game_id, t_game_s, rule_id, text, tier, p, status FROM call"
```

```bash
spacetime sql -s local trophy "SELECT game_id, cam_id, t_game_s, type, conf FROM observation"
```

```bash
spacetime sql -s local trophy "SELECT game_id, cam_id, t_game_s FROM track_sample"
```

```bash
spacetime sql -s local trophy "SELECT game_id, cam_id, label, role, connected, fps_in, calib_trusted FROM camera"
```

```bash
spacetime sql -s local trophy "SELECT game_id, rule_version, status, text FROM house_rule"
```

```bash
spacetime sql -s local trophy "SELECT game_id, run_id, kind, status FROM droid_run"
```

```bash
spacetime sql -s local trophy "SELECT game_id, call_id, status, result FROM challenge"
```

```bash
spacetime sql -s local trophy "SELECT game_id, call_id, backend, choice, latency_ms FROM ai_vote"
```

```bash
spacetime sql -s local trophy "SELECT game_id, label, t_game_s, highlight_score, is_best_play FROM moment"
```

```bash
spacetime sql -s local trophy "SELECT game_id, question, answer, kind, p, latency_ms FROM ask"
```

Add `WHERE game_id = 'g_…'` (the id is in the dashboard URL) to any of them. A live ticker of the calls, refreshed every 2 s:

```bash
while true; do clear; spacetime sql -s local trophy "SELECT game_id, t_game_s, rule_id, text, tier, status FROM call" 2>/dev/null | tail -25; sleep 2; done
```

The module's own log (reducer calls, rejected writers):

```bash
spacetime logs -s local trophy -f
```

The hot path before Spacetime is Redis: `redis-cli xlen ev:flight` (events from the module), `redis-cli xlen ev:calls` (what
the announcer speaks), `redis-cli xrevrange ev:calls + - COUNT 3`.

## 3. The dashboard: clips uploaded and processed

Open **http://127.0.0.1:5174/** on the Mac (or `https://trophy.photo/` from any device on the Wi-Fi once DNS is set).

1. **Start a game** (Ping pong). The URL becomes `/?g=<game_id>&k=<join_key>`: keep that tab, it is the game.
2. **Recorded clips as live cameras**:
   - **Preloaded games → Play** (TT3D game 00: 4 min, two angles; the 2015 Edmonton final: 20 min), or
   - **Choose Files** to upload clips (mp4/mov/webm, iPhone 4K fine; the table corners are detected automatically, tap to
     correct), then **Go live**.
3. What you see within ~5 s: each camera's live frame with BlurBall's green ring on the ball, `… frames sent`, the
   **LIVE** badge. Calls start after the first rally (~30 s into TT3D): the **Calls** feed (BETA, p, rule, why), the
   **score**, the **World state** bounces and dots, **Cameras** (`side`, `oblique`, calibration untrusted).
4. In terminal 1 at the same time: `live | … "msg": "event" … "type": "bounce"`, `engine | … "msg": "call" …`,
   `announcer | … "msg": "spoke", "text": "Point, double bounce. Team B. 2, 3." …`.

Every clip joins as a camera phone over the same WebSocket a phone uses; nothing downstream knows it is a file.

## 4. Phones

The dashboard's **Join with a phone** card shows the QR code and the link `https://trophy.photo/cam/?g=…&k=…`. Roles:
**Camera** (films; needs a fixed mount, side-on at the net line, landscape), **Camera + judge**, **Scoreboard** (shows and
speaks the calls), **Judge** (scoreboard plus uphold/overturn, undo, score ±, house rules). On the Mac itself:
`http://127.0.0.1:5173/cam/?g=<game_id>&k=<join_key>`. Menu → Connection details → **Test voice** speaks a line through
Cartesia on that phone.

## 5. A challenge and the replay

- Phone: **Challenge · NN%** (or hold to talk and say "challenge"). The announcer says "Challenge. Reviewing."; the judge
  sheet opens with **Uphold / Watch replay / Overturn**. **Watch replay** plays the window from the referee's own 720p
  recording (phone-recorded 1080p clips replace it when a real camera phone uploads them), per camera, ½× by default.
- Dashboard: the call shows **Challenged** with **Replay / Uphold / Overturn**. **Replay** opens the same window with the
  call's bounce marks and σ ellipses drawn on the frame. Any call has **Replay**, not only challenged ones.
- Uphold or overturn on either screen; the announcer says "Call stands." or the replacement call.
- With `ANTHROPIC_API_KEY`: Claude's vote appears in **AI second opinion** (uncalibrated) and in the `ai_vote` table.

## 6. A house rule: the Factory Droid, live

1. Phone (Judge) → Menu → **Judge controls** → type `first to 7, win by 1` → **Add rule** (or hold to talk: "house rule:
   first to 7, win by 1"). The announcer says "House rule added: …".
2. Dashboard **House rules · Factory Droid** panel: status `pending` → `running`, the plan, the streamed steps, the diff of
   `rules.yaml`, then **Gate: N/N checks passed** (expand it for the table) and **Approve / Reject**. Measured today:
   ready in **18.7 s**.
3. Terminal 1, `compiler |` lines: the run id, every tool call the Droid makes, the guard's verdicts, the gate result, and a
   JSON summary (`"status": "ready"`, `"attempts": 1`, `"commit": …`).
4. Every run is on disk: `ls -t ~/.trophy/droid_runs | head`, then inside a run: `job.json` (the brief),
   `run.jsonl` (every streamed step), `workspace/` (the sandbox git repository: `git -C ~/.trophy/droid_runs/<run>/workspace log --oneline`).
   A house-rule run streams into its `house_rule` row (plan, steps, diff, gate results: the dashboard panel is that row)
   and the row goes `pending → running → ready → approved`; the `droid_run` table holds the other jobs
   (`calibrate_checks`, `new_check`).
5. **Approve** on the dashboard or the phone: the engine loads the pack from the gated commit and hot-loads it (status
   `approved`, "0.5–0.8 s" measured). The next point is called under the new rule.

**Judge correction** (D-42): on the dashboard, **Judge: that was one rally, won by A / B** voids the span's points, posts the
judge's point (spoken), exports the span as a labelled sample under `data/local/labelled/table_tennis/` and files a
`correction` house rule; the Droid repairs the pack against every labelled sample. These runs take **minutes** (328 s
measured), so start one only when you can talk through it.

## 7. Ask the ref (needs `ANTHROPIC_API_KEY`)

Phone: **Hold to talk**, ask "what's the score?" (answered from the phone), "was that last one on the edge?" (a geometry
check over the ball track) or a rules question (answered only from `sports/table_tennis/rules.yaml` plus approved house
rules, with citations). The answer is spoken and appears in the dashboard's **Ask the ref** panel and the `ask` table.
Without the key the referee service is not running and the phone reports the error honestly.

## 8. End the game → Trophy Watch

The game ends by itself at 11 (deuce rules) or when a preset's last frame has gone; otherwise press **End game** in the
dashboard header (or the phone's judge sheet). Then **Open Trophy Watch ↗** (header, join card, clips panel), or go to
`http://127.0.0.1:5175/watch/?g=<game_id>&k=<join_key>` (`https://trophy.photo/watch/?…` on the Wi-Fi): recap with the
final score, **★ Play of the game**, **Highlights**, **Condensed**, the moments list with filters, the replay card (call,
votes, serve-toss trace when present), **Stats**, keyword search. Keys: Space, ←/→ 5 s, J/L moments, S slow-mo, `,` `.`
frames.

## 9. Headless checks (when nothing is live)

```bash
make e2e-synthetic
```

Creates a game through the gateway, plays the labelled synthetic rallies through the live engine, checks the calls and the
score against the labels, files a house rule, waits for the Droid (`ready`), approves it. Expect `E2E PASS`.

```bash
make check
```

Everything CI runs: ruff, pytest (py-trophy, referee), tsc, eslint, vitest, fixture validation, codegen staleness.

## 10. If something looks wrong

| Symptom | Look at | Fix |
|---|---|---|
| Frames but no calls | `flight \|` lines (`"detected": 0.5` = half the frames have a ball) and `live \|` events | the table corners: retap them on the clip; a white ball on a dark table detects best |
| No sound on the Mac | `announcer \|` lines: `"spoke"` with `"ttfa_ms"` means Cartesia answered | macOS output device / volume; `announcer` restart: `python3 scripts/dev.py announcer` |
| "Live state unavailable" on a page | `spacetime \|` lines; `curl -s http://127.0.0.1:3000/v1/ping` | `python3 scripts/dev.py spacetime gateway` then reload |
| House rule stuck `pending` | `compiler \|` lines ("watching …" must be there) | `python3 scripts/dev.py compiler`; the Droid needs `FACTORY_API_KEY` and the `droid` CLI |
| Approve does nothing | the engine was restarted during the game (it forgot the game) | start a new game; approve there |
| Phones can't open trophy.photo | `dig +short trophy.photo A` vs `ipconfig getifaddr en0` | `python3 infra/dns/porkbun_set_ip.py`; Caddy's cert is cached in `~/Library/Application Support/Caddy` |
| Ports held after a crash | `python3 scripts/dev.py --stop` reports what it stopped | it now recognises macOS full-path process names; rerun `make dev` |
