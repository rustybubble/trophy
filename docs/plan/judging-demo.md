# The judging demo: phones as replayed cameras (D-42, D-43, D-44)

*2026-10-25. This supersedes live capture for judging. Real phones still join and act as cameras, but the picture is a recording replayed as if live.*

## Why
During judging we can't play a sport, and waiting for a real foul takes too long. Instead the Mac replays recordings as if they were live:
- our own ping-pong takes (two angles recorded at the same time);
- researched CC BY clips for pickleball, volleyball and basketball.

Each phone shows one angle as though it were filming it. The referee pipeline sees exactly the frames a phone would send. We tell judges this is how we demo. The UI shows a small "Replayed feed" chip; for CC BY footage it also shows the credit.

## Flow
1. **The host picks a scenario.** In the PWA (judge role) or on the dashboard, the host picks one: "Ping pong · 2 angles", "Pickleball", "Volleyball" or "Basketball".
2. **Phones join** with the game QR or link and land on an angle picker. Each phone takes the next free angle (Side, Diagonal, …) and can switch with one tap. A phone joins as role `display,judge`, so it can challenge and add house rules.
3. **Go live.** The gateway:
   - prepares the phone-playable files (720p H.264 + AAC, `+faststart`, cached);
   - starts `stream_clips.py`, which streams each angle into `frames:{cam_id}` for the referee;
   - schedules `wall0_ms = now + 4 s` on the server clock, and sends ctl `feed_schedule`. The engine then writes one Spacetime `feed` row per angle.
4. **Every phone plays its angle in sync.** It reads its `feed` row from Spacetime, shows a 3-2-1 countdown, and keeps `video.currentTime = offset_s + (server_now − wall0_ms)/1000`. `server_now = Date.now() + clock_offset`, from the gateway's `/api/ws/ctl` clock fit. If |drift| > 120 ms it seeks; smaller drift is corrected with `playbackRate` 0.97–1.03.
5. **Phones report drift.** Every 2 s each phone sends `viewer_status {cam_id, playing, drift_ms, name}`. The engine writes a `viewer` row, so every device sees every other device and its drift live.
6. **Annotated scenarios** (sports with no perception) also start the annotation feeder on the same `wall0`. It publishes each hand-marked event to `ev:flight` with `source: "annotated"` at its scheduled time, and the engine decides calls from those events with the sport's Droid-written `rules.yaml`.

## Timing
- **Clip time to game time.** Clip time `t` in an angle plays at server time `wall0_ms + (t − offset_s)·1000`. Its game time is `t_game0_s + (t − offset_s)`.
- **Where `t_game0_s` comes from.** The gateway computes it as `(wall0_ms − game.t0_ms)/1000`, the same mapping the frames WS uses for a phone with zero clock error.
- **Angles of one moment** share `wall0_ms`. They differ only by `offset_s`, which aligns recordings that started at different times.

## Spacetime tables (state.schema.json; module `spacetime/src/index.ts`)

**`feed`**: one row per angle. Fields: `cam_id`, `game_id`, `label`, `status` (scheduled|playing|ended|failed), `scenario_id`, `video_url`, `offset_s`, `duration_s`, `wall0_ms`, `t_game0_s`, `source` (team_recording|cc_by_online|synthetic), `credit`, `annotated`, `calibrated`. Written by the engine with `upsert_feed`.

**`viewer`**: one row per phone. Fields: `viewer_id` (the phone's own cam_id), `game_id`, `cam_id` (the angle shown), `name`, `connected`, `playing`, `drift_ms`, `last_seen_ms`. Written by the engine with `upsert_viewer`.

**`droid_run`**: now also written for `interpreter`, `new_check` and `calibrate_checks` runs. The state client exposes `onFeeds`, `onViewers` and `onDroidRun`.

**What the Spacetime track shows** (the main track, so make it visible):
- **Synced playback across all phones.** A live drift readout appears on every phone, in the "Network" sheet.
- **Camera health per angle.** `camera` rows show fps in and connected.
- **Per-angle ball detections.** `track_sample` per cam, shown as a dot overlay on that angle's video.
- **Fused observations.** A bounce seen by two cameras shows `cams: [cam1, cam2]` and the fused σ. The mini world view marks which angle saw each bounce.
- **Calls, challenges, AI votes and Droid runs** appear on every device at the same moment.
- **The latency budget.** The PWA's `call_ack` shows engine → phone time.

## Calls: who is at fault, beep, speech (call.schema.json)
- **New call fields:**
  - `at_fault: {team_id, name} | null`;
  - `explanation: string | null`, the challenge verdict;
  - `source: sensed | annotated | manual`.
- **How the engine fills `at_fault`.** A rule may set `at_fault: "<CEL expr returning a team id>"`. The default is the team opposite `team` (the team the call favours) for point/violation/fault outcomes, and none for a let. `name` comes from `game.teams`.
- **Speech templates** can use `{at_fault}` (the team's name). Every point, fault, out or foul call is spoken as `<what> — <who>`, e.g. "Out. On Mu." or "Fault, toss too low. Vedansh."
- **The PWA beeps then speaks every call.** It plays `cue.beep`, then speaks `speech` with Cartesia (calls voice), interrupting any line still playing.

## Challenge: voice or button → replay → verdict
- **How a challenge starts.** A button, or saying "challenge" (Cartesia Ink-2 push-to-talk), challenges the newest non-info call, any tier.
- **Engine.** Opens the challenge, says "Challenge. Let's look at the replay.", and re-checks the play:
  1. It reads the call's events (geometry: p, σ, margins).
  2. It runs `decide()` (Claude, blended with geometry, labelled uncalibrated) for every challenged call, not only `check: ensemble` rules.
  3. Within ~5 s it resolves:
     - **upheld** if the blended p for the original outcome is ≥ 0.6;
     - **overturned** if it is ≤ 0.4, with a replacement call;
     - otherwise **"Players decide"**.
  4. It writes `explanation` (Claude phrases the measured facts; template fallback; numbers guarded) and speaks it with the referee voice.
  5. A judge can still override.
- **PWA replay.** On a challenge every phone opens the replay automatically: the recorder clip `GET /api/replay/{g}/clip?cam&t0&t1` for each angle, or the scenario file seeked to the evidence window. It shows angle tabs, the explanation, and the vote and verdict.

## Droid (D-43; Factory Droid track)

### Interpreters
The Droid writes, for each sport, the script that decides whether a play is a let, out or fault. That script is the sport's `rules.yaml`, plus `checks/*.py` where geometry is needed.
- **Job kind** `interpreter`.
- **Triggers:**
  - a `sport_module` request when a scenario's sport has no approved interpreter (an event);
  - "Regenerate interpreter" in the Droid sheet (a user action).
- **Gate.** The interpreter must reproduce `evals/fixtures/annotated/<sport>/*.labels.json` from `*.events.jsonl`.
- **Inputs.** The Droid gets the sport's `RULES.md` (a short rulebook summary with citations), `config.yaml`, the event vocabulary, and table tennis's golden `rules.yaml` as a reference.

### House rules: the Droid decides
- **Trigger.** A `house_rule` row inserted by voice or typing (an event, from a user action).
- **What the Droid does.** It writes the rule, runs the gate with this session's events as a baseline (so `calls_changed` is real), and emits a decision `{applies, rationale}`.
- **When the gate passes and `applies` is true,** the engine applies the rule without waiting for a judge:
  - it re-judges the session's recorded plays under the new pack, posting superseding calls and recomputing the score;
  - it sets status `applied` with `decision`;
  - it speaks "House rule applied: … 2 calls changed."
- **Undo.** One tap (`revert_house_rule`) restores the previous pack and calls.
- **Stacking.** Rules stack: each run starts from the last applied pack.

### Safety (unchanged and strengthened)
- a sandbox git workspace;
- a PreToolUse guard;
- a per-kind file allowlist;
- a jailed gate (no network, no outside writes, `env -i`);
- an import allowlist;
- a 3-attempt / 90 s cap;
- the git audit fails any run that touched an unlisted file;
- the engine only ever loads the gated commit.

### Visible work
The Droid sheet (PWA) and panel (dashboard) show, for every run:
- the trigger;
- the plan;
- live steps;
- the diff;
- the test table;
- calls that changed;
- blocked tool calls;
- timings.

## Annotated fixtures (other sports)
**Where they live:**
- `data/scenarios/<id>/scenario.yaml` is versioned metadata. Media stays in `data/local/scenarios/<id>/` (ignored).
- `evals/fixtures/annotated/<sport>/<clip>.events.jsonl` holds one trophy.event.v1 per line, with `source: "annotated"` and `t_game_s` = clip time from the segment start.
- `<clip>.labels.json` holds the expected calls: `{calls: [{t_s, rule_id?, outcome, team_id, at_fault}]}`.

```yaml
# data/scenarios/<id>/scenario.yaml
id: pickleball-rec-doubles
title: Pickleball · rec doubles
sport: pickleball
teams: [{team_id: A, name: Near team}, {team_id: B, name: Far team}]
source: cc_by_online            # team_recording | cc_by_online
credit: "BT Pickleball rec doubles — CC BY — youtube.com/watch?v=QhLECLlXU3c"
annotated: true
events: evals/fixtures/annotated/pickleball/rec-doubles.events.jsonl   # times relative to start_s
angles:
  - {label: Corner, file: data/local/scenarios/pickleball-rec-doubles/corner.mp4, start_s: 0, duration_s: 60, offset_s: 0}
```

Annotations are hand-marked by us from the footage. Calls from them are labelled `source: annotated`, and no perception accuracy is claimed for these sports.
