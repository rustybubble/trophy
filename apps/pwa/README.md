# Phone PWA (Agent 1)
Vite 7 + React 19 + strict TS, served at **`https://trophy.photo/cam/`** (Caddy → Vite on 127.0.0.1:5173). Game state comes only through `@trophy/state-client` (Spacetime subscriptions); writes go through the gateway (`POST /api/ctl`).

```bash
npm run dev -w @trophy/pwa      # then open https://trophy.photo/cam/?g=<game>&k=<join key> on the phone (the dashboard's QR)
npm test -w @trophy/pwa         # pure libs: feed sync, angle pick, spoken lines, verdicts, frame header, intents, onsets
```

## The judging demo (default; D-42..D-44, `docs/plan/judging-demo.md`)
Phones are replayed cameras: the Mac replays a recording as if live and each phone shows one angle, in sync.
- **Join:** a name, then role `display,judge` (no role picker). The Join tap unlocks audio. Without `g`, the landing page can create a game (`POST /api/games`).
- **Host (⋯ menu):** pick a scenario (`GET /api/scenarios`), **Go live** (`POST /api/games/{g}/scenario {scenario_id}`), **Stop** (`POST /api/games/{g}/scenario/stop`), sound on/off, invite link, leave.
- **Angle view:** the `feed` row's `video_url?token=` plays at `offset_s + (serverNow − wall0_ms)/1000` (clock offset from `/api/ws/ctl`), with a 3-2-1 countdown, a seek past 120 ms of drift and `playbackRate` 0.97–1.03 below it; ctl `viewer_status` every 2 s. The phone takes the first angle no other phone shows; pills switch. A ball dot from this camera's `track_sample.px`. The banner shows the newest call with its tier and who is at fault (and "annotated").
- **Calls** beep, then speak `call.speech` (the at-fault name is appended if missing), interrupting a stale line. The engine's info calls (challenge, verdict) and a challenge's replacement call are spoken the same way, so explanations aren't spoken twice.
- **Challenge** (button or "challenge" by voice) targets the newest non-info call; every phone opens the **replay sheet** when the `challenge` row opens: angle tabs on the recorder clip (`/api/replay/{g}/clip?cam&t0&t1&token`), falling back to the scenario file seeked to the window, then the verdict, explanation and Claude's vote (uncalibrated).
- **Network sheet:** angles (feed + camera rows, ball seen), phones (viewer rows, drift), fused bounces with cams and σ, a top-down view.
- **Droid sheet:** submit a house rule (typed or held mic), and each `house_rule` / `droid_run`: trigger, progress, decision, plan, live steps, diff, tests, calls changed, blocked tool calls, timings; **Undo** (`revert_house_rule`) when applied, **Reject** only while `ready`.

URL flags: `?mock=1` runs the demo on labelled-synthetic rows (`src/mock/mockBackend.ts`) and generated test-pattern videos (`public/mock/*.mp4`, a dot over a drawn table; no people), `&idle=1` skips the automatic Go live. `?mode=camera` opens the original live-capture app below (`src/legacy/LegacyApp.tsx`).

## Live capture (`?mode=camera`, not the demo path)
URL flags: `?mode=camera&mock=1` plays the labelled-synthetic demo with no backend; `&fake=1` uses a synthetic test-pattern camera; `&test=1` opens device stats. On `http://127.0.0.1:5173` the dev server proxies `/api` and `/stdb` like Caddy does.

**What's in it (interfaces-v1 §5, §10, §13, §16):**
- **Join** by QR link (`g`, `k`), with a role: Camera, Camera + judge (the one-phone demo), Scoreboard, or Judge. The **Join tap** unlocks audio and takes the screen wake lock. `cam_id` is kept in `localStorage["trophy.cam." + game_id]`.
- **Camera:** the rear lens pinned by `deviceId` (the physical wide lens on iOS, not the auto-switching virtual one), 1280×720 at 30 fps. JPEG q 0.7 over `wss://…/api/ws/frames` with the 16-byte header, timestamped by `requestVideoFrameCallback` capture time. Latest frame wins: a frame is sent only when the socket has nothing buffered. Shows a rotate prompt in portrait.
- **Clock and onsets:** `/api/ws/ctl` pings (a burst of 20 at 50 ms, then every 2 s) feed the gateway's min-RTT fit. An AudioWorklet onset detector (1.5 kHz high-pass, energy over median + 6·MAD, 60 ms refractory) runs on the raw mic and sends `onset`.
- **Calls:** a banner with the tier badge and p, a beep, a team-colour flash, **Cartesia Sonic** speech of `call.speech` (a newer call cancels a stale line; `emotion` passes through), and a `call_ack` back to the gateway. Upheld/overturned calls are announced. There's a scoreboard and a recent-calls list, plus "read everything" (scores spoken too) and "speak calls" toggles.
- **Push-to-talk → Ink-2:** "challenge", "undo", "what's the score", "house rule: …", and anything else as an ask-the-ref question (answer spoken in the ref voice, citations shown).
- **Judge:** start game, uphold/overturn an open challenge, undo, score ±, submit and approve/reject house rules.
- **Calibration:** tap the 4 table corners on the latest still (team A's end first), drag to adjust, solve via `/api/calibrate`, see the projected outline and whether it's trusted, then confirm.
- **Challenge replay in high quality (D-27):** a camera phone captures at 1080p (default) or 4K (menu → Replay recording), streams 720p live, and records the full-quality track locally in rolling 6 s segments (last 5 kept). When a challenge opens, it uploads only the segments covering the call's evidence window ±1 s. "Watch replay" (judge) or "Replay last challenge" (menu) plays them at 1×, ½×, ¼× with frame steps.
- **Not yet:** the recorder-based replay with ball/bounce overlays (§12), the QR clock board, `audio_offset_ms` clap test.
