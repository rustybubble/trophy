# Judging-day runbook (D-42..D-44)

The demo replays recordings as if live: the Mac streams each angle to the referee, and every phone shows one angle in sync. Tell judges up front: "These are our recordings (and CC BY clips for other sports) replayed as live camera feeds; everything downstream runs exactly as it would with phones filming."

## Before judges arrive (once)
1. Stack on the Mac, from this checkout: `make dev`. Check `https://trophy.photo/api/healthz`: `redis`, `spacetime` and `recorder` must be true.
   - The phones need `trophy.photo` to resolve to the Mac's LAN IP (Porkbun A record), and they must be on the same Wi-Fi.
   - Engine with votes: the Procfile's `engine:` line needs `--votes` (Claude second opinion; `ANTHROPIC_API_KEY` in `.env`).
2. Prepare the media once, so Go live starts instantly: `curl -X POST -H "Authorization: Bearer <judge token>" https://trophy.photo/api/scenarios/<id>/prepare` for each scenario, or just press Go live once per scenario.
3. Droid time cap: set `DROID_TIMEOUT_S=150` in `.env` (live house-rule runs take 30–80 s; the default 90 s cap can cut one off).
4. Interpreters: each annotated sport needs its Droid-written `sports/<sport>/rules.yaml` (generated and gated in advance; see `docs/status/a3.md`).

### If phones can't reach the Mac (venue Wi-Fi isolates devices)
Symptom: the QR opens a blank page and the stack logs nothing. Run `make tunnel` (Cloudflare quick tunnel, installed with `brew install cloudflared`). It prints a `https://<words>.trycloudflare.com` address. While it runs, **new** games' join links and QR codes use that address automatically, phones on any network (venue Wi-Fi or cellular) can join, and Spacetime, the ctl socket and video all go through it. Start a new game after the tunnel is up (an older dashboard tab keeps its old QR). Anyone with the address can open the app while the tunnel runs; stop it with ctrl-c. `python3 infra/caddy/point_dns.py [--apply]` instead repoints trophy.photo at the Mac on a network that allows device-to-device traffic.

## The 3-minute demo
1. **Dashboard** (laptop, `https://trophy.photo/`): Start a game, which shows the join QR.
2. **Phones** scan the QR and tap Join. Each takes the next free angle (Side, Diagonal, …).
3. **Go live** with "Ping pong · 2 angles" (on the dashboard or the host phone). A 3-2-1 countdown appears, then every phone and the dashboard play their angle in sync.
   - **Spacetime story:** the dashboard's "Cameras in sync" panel and each phone's Network sheet show every phone's drift (ms), camera fps and per-angle ball detections live, all from the same Spacetime tables.
4. **Calls.** Every call beeps and is spoken with who's at fault ("Out. Point, Mu. Vedansh's fault.").
5. **Challenge.** Tap Challenge or hold the mic and say "challenge".
   - Every phone opens the replay with angle tabs.
   - About 4 s later the verdict is spoken: upheld, overturned (replay the point) or players decide. It gives the measured facts and Claude's second opinion, labelled uncalibrated.
6. **House rule** (Droid). Hold the mic: "house rule: a serve that clips the net is a let". The Droid sheet shows the trigger, plan, live steps, diff and tests. The Droid decides and applies the rule, re-judges earlier plays, and says how many calls changed. Undo is one tap.
7. **Other sports.** Go live with Pickleball, Volleyball or Basketball (CC BY clips, credited on screen). Their calls come from hand-annotated events, labelled "annotated", run through the Droid-written interpreter for that sport.

## What not to claim
- No accuracy numbers: the ping-pong takes are unlabelled. Annotated sports are marked events, not perception.
- Claude's vote is uncalibrated.
- Calibration is from tapped or suggested corners (untrusted), so sensed calls cap at BETA.
