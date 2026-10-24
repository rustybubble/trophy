# Capture PWA (Agent 1)
Vite 7 + React 19 + strict TS, served at **`https://trophy.photo/cam/`** (Caddy → Vite on 127.0.0.1:5173). Game state comes only through `@trophy/state-client` (Spacetime subscriptions); writes go through the gateway.

```bash
npm run dev -w @trophy/pwa      # then open https://trophy.photo/cam/?g=<game>&k=<join key> on the phone (the dashboard's QR)
npm test -w @trophy/pwa         # pure libs: frame header, intents, onset detector, homography
```
URL flags: `?mock=1` plays the labelled-synthetic demo with no backend; `&fake=1` uses a synthetic test-pattern camera; `&test=1` opens device stats. On `http://127.0.0.1:5173` the dev server proxies `/api` and `/stdb` like Caddy does.

**What's in it (interfaces-v1 §5, §10, §13, §16):**
- **Join** by QR link (`g`, `k`), with a role: Camera, Camera + judge (the one-phone demo), Scoreboard, or Judge. The **Join tap** unlocks audio and takes the screen wake lock. `cam_id` is kept in `localStorage["trophy.cam." + game_id]`.
- **Camera:** the rear lens pinned by `deviceId` (the physical wide lens on iOS, not the auto-switching virtual one), 1280×720 at 30 fps. JPEG q 0.7 over `wss://…/api/ws/frames` with the 16-byte header, timestamped by `requestVideoFrameCallback` capture time. Latest frame wins: a frame is sent only when the socket has nothing buffered. Shows a rotate prompt in portrait.
- **Clock and onsets:** `/api/ws/ctl` pings (a burst of 20 at 50 ms, then every 2 s) feed the gateway's min-RTT fit. An AudioWorklet onset detector (1.5 kHz high-pass, energy over median + 6·MAD, 60 ms refractory) runs on the raw mic and sends `onset`.
- **Calls:** a banner with the tier badge and p, a beep, a team-colour flash, **Cartesia Sonic** speech of `call.speech` (a newer call cancels a stale line; `emotion` passes through), and a `call_ack` back to the gateway. Upheld/overturned calls are announced. There's a scoreboard and a recent-calls list, plus "read everything" (scores spoken too) and "speak calls" toggles.
- **Push-to-talk → Ink-2:** "challenge", "undo", "what's the score", "house rule: …", and anything else as an ask-the-ref question (answer spoken in the ref voice, citations shown).
- **Judge:** start game, uphold/overturn an open challenge, undo, score ±, submit and approve/reject house rules.
- **Calibration:** tap the 4 table corners on the latest still (team A's end first), drag to adjust, solve via `/api/calibrate`, see the projected outline and whether it's trusted, then confirm.
- **Not yet:** the replay viewer (with the recorder), the QR clock board, `audio_offset_ms` clap test.
