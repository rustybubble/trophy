# Trophy

**An AI referee for pickup games: every phone is a camera angle, every call is spoken, and it tells you how sure it is.**

## Inspiration
Every pickup game has the argument. Was that a let? Did it clip the line? Was the toss high enough? Our teammate Mu is a Team USA-ranked table tennis player, and even he can't always tell whether a ball clipped the net. Casual games have no referee, no replay, and no way to settle a close call except whoever argues loudest. We wanted the fairness of a pro broadcast for a Tuesday-night game, using only the phones people already have in their pockets.

## What it does
- **Phones become cameras.** Scan a QR code, type a name, and your phone joins the game as a camera angle. Two phones give two angles of the same rally, kept in sync to within milliseconds.
- **It makes the call.** The referee tracks the ball in every angle. Each sport's rules then decide what happened: a point, a fault, out, a let, a double bounce, an illegal serve.
- **Every call is spoken.** Every phone beeps, then says what happened and whose fault it was ("Out. Point, Mu. Vedansh's fault.").
- **It's honest about confidence.** Calls are AUTO when the referee is sure (p ≥ 0.90). Below that they're shown with their probability and can be challenged. When the sensors can't judge, it's PLAYERS DECIDE.
- **Challenge it.** Tap Challenge or just say "challenge". Every phone opens an instant replay of both angles. The geometry is re-checked, Claude gives a second opinion, and the verdict and its reason are read out loud, usually within about 4 seconds.
- **House rules, in plain English.** Say "a ball that clips the net and lands in is a let". A Factory Droid writes the rule in a locked-down sandbox and tests it against the plays already made. It then decides: it applies the rule, re-judges the game, and reports exactly which calls changed. One tap undoes it.
- **Any sport.** Ping pong runs on real ball tracking. For pickleball, volleyball and basketball, the Droid wrote each sport's let / out / fault rules from a rulebook summary and tested them against hand-marked plays.
- **Ask the ref.** Hold the mic and ask "what's the score?" or "why was that called?".

## How we built it
- **Phones** run a mobile-first web app (React + Vite). No install: open a link over HTTPS at trophy.photo.
- **SpacetimeDB is the shared world state.** Every device subscribes to the same tables:
  - each camera angle's playback schedule (`feed`);
  - every phone and its measured playback drift (`viewer`);
  - camera health, ball samples and observations;
  - calls, challenges and Claude's votes;
  - house rules and every Factory Droid run.

  The phones play their angle from one shared schedule and report their drift back, so every device can see every other device. Only backend services can write, and each writer's identity is checked.
- **The referee:**
  - BlurBall ball detection on the GPU (PyTorch) runs on every frame of every angle;
  - a sport module turns ball tracks into bounces, contacts and net events, merging cameras;
  - a rule engine (CEL rule packs per sport) decides the call, who's at fault and the confidence tier.

  It runs on a laptop on the same network. In the demo it replays our own two-phone recordings, plus Creative Commons clips for the other sports, as if they were live.
- **Cartesia:**
  - Sonic text-to-speech reads every call and verdict on the phones;
  - Ink-2 speech-to-text powers hold-to-talk: challenge, house rules, questions;
  - phones get short-lived tokens minted by our server, never the API key.
- **Claude:**
  - casts the second-opinion vote on a challenge (structured output, blended with geometry, labelled uncalibrated, never delaying a call);
  - phrases the explanations;
  - answers ask-the-ref questions from the rule pack.
- **Factory Droid:**
  - **Triggers:** a new sport coming into play (an event), "regenerate" (a user action), or a house rule spoken or typed (a Spacetime row).
  - **Sandbox:** each run gets a fresh git sandbox. A PreToolUse guard limits edits to that job's rule file, the only command it may run is the test gate, file reads stay inside the sandbox, and the gate runs with no network and no writes outside.
  - **Audit:** the runner checks `git status` after every turn and fails any run that touched anything else.
  - **Visibility:** the plan, live steps, the diff, the test table, blocked tool calls and the calls changed all stream to the phones and the dashboard.
- **Gateway** (FastAPI + Redis): game joins, clock sync, the frame bus, replay clips, and the Cloudflare tunnel fallback for venue Wi-Fi that isolates devices.

## Measured this weekend
- **Two angles in sync:** 30 fps per angle into the referee; ball found in 76–100 % of frames on our recording; phone playback within ±2–13 ms of the shared schedule (measured in a browser on the laptop's network).
- **Challenge → spoken verdict:** about 4 s, including a live Claude vote of about 3 s.
- **Factory Droid, live runs:**
  - interpreters written and gated in 44–66 s (pickleball 9/9 tests, volleyball 9/9, basketball 11/11);
  - house rules applied in 31–82 s, re-judging the game; Undo is instant.
- **Cartesia:** first audio about 112 ms after the request on an iPhone.

The ping-pong footage is unlabelled, so we don't claim an accuracy number. Claude's confidence is uncalibrated, and the app says so.

## Challenges we ran into
- **Venue Wi-Fi isolates devices,** so phones couldn't reach the laptop. We added a Cloudflare quick tunnel: phones join from any network, and the app hands out the reachable address automatically.
- **Two phones joining together picked the same angle,** because each saw the other's choice too late. Each phone now ranks itself among the game's phones.
- **A random join key starting with "-"** broke our clip streamer's argument parsing, failing about 1 game in 64. We found it while recording the demo video.
- **Sandboxing an AI agent is hard.** Our first runs produced a "ready" result with an empty diff, and a 90-second timeout. We enforce the sandbox with a hook, audit the git tree after every turn, and run the tests in a jail.
- **Structured output** rejected our vote schema (free-form maps aren't allowed), so the challenge vote silently failed until we switched to a list of options.

## Accomplishments we're proud of
- Two phones showing two angles of the same rally, in sync through SpacetimeDB, with every device seeing every other device's drift live.
- A Factory Droid that doesn't just write code: it decides, shows its work, and can be undone in one tap.
- A referee that says how sure it is, and that a player can argue with by voice.

## What we learned
- **Honest confidence is a feature.** Players accept "too close, you decide" far more easily than a confident wrong call.
- **Shared state beats messaging.** Once every device reads the same Spacetime tables, sync, replay, votes and Droid progress come for free on every screen.
- **For an agent you trust with real decisions,** the guardrails and the visible trail matter more than the model.

## What's next
- Real-time capture from the phones at a venue (the capture path exists).
- Perception for pickleball and volleyball.
- Calibrated confidence from labelled games.
- 3D reconstruction from multiple phones for line calls.
- Basketball fouls.

## Built with
SpacetimeDB · Factory Droid (droid CLI + SDK) · Cartesia (Sonic, Ink-2) · Claude (Anthropic API) · TypeScript · React · Vite · Python · FastAPI · Redis · PyTorch (BlurBall) · OpenCV · ffmpeg · CEL · Caddy · Cloudflare Tunnel · trophy.photo

## Credits (Creative Commons footage)
- **Pickleball:** "Pickleball Doubles Challenge Court in Melbourne, FL 06/09/2023 Game 1" by BT Pickleball, CC BY. https://www.youtube.com/watch?v=QhLECLlXU3c
- **Volleyball:** "Handymen vs AZIAN Mixed - Mixed Moscow Volleyball League (1st set)" by Almost Volleyball, CC BY. https://www.youtube.com/watch?v=kVpO4ypzPYU
- **Basketball:** "Fun Moderate to Intense 10 games Saturday run" by JaiArtHub, CC BY. https://www.youtube.com/watch?v=2NxcgKW7xFM

All three were trimmed and re-encoded. The ping-pong footage is our own team's recording.
