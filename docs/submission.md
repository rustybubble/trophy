# Submission: the 2-minute video and the Devpost writeup (draft)

*Agent 1, 2026-10-24. A draft to fill in after C3. Every `[[…]]` is a placeholder for a number that isn't measured yet or a quote we don't have yet. **Never fill one with an estimate or an invented quote**; if it isn't measured by submission time, cut the line or say "not measured".*

Rules for both:
- **Only measured numbers**, each with its device and method (see `docs/progress.md`). Label synthetic data, generated views and uncalibrated AI probabilities as such.
- **Player quotes are real** (OPEN-8): asked for this weekend, with the player's OK to publish their words and first name. Anyone on camera has consented (`docs/demo-setup.md`); blur anyone who hasn't.
- **Don't claim what isn't built.** Basketball fouls, pickleball, tennis, badminton, volleyball and two-hand touch are "coming next".

---

## 1. The 2-minute video (demo first)
Cartesia's format: **one complete flow first** (about 75 s, no slides), **then the problem and how it's built** (about 45 s). Film it live on the Mac stack with a fixed phone mount, side-on at the net line (`docs/demo-setup.md`). Record screen + room audio so the spoken calls are heard as they happened; don't dub them.

**Before filming:** three full rehearsals (C4); the phone charged and on the mount; the dashboard on a laptop in shot; a white ball; consent from both players; a house rule chosen that changes a visible call; the 5 Watch search queries prepared.

| Time | Shot | What happens (live) | Voice-over / on-screen text |
|---|---|---|---|
| 0:00–0:05 | Cold open: two players at the table, phone on a mount at the net | First serve. Trophy says the score. | Title card over the rally: **Trophy: an AI referee for pickup games** |
| 0:05–0:20 | Rally, then a ball off the end | **"Out. Point, [[player]]. [[score]]."** spoken from the phone; the call banner flashes; the dashboard score ticks | _(no voice-over: let the call speak)_ |
| 0:20–0:35 | A serve with a low toss | **"Fault: toss too low."** Banner shows **BETA, p [[0.xx]]**, the measured toss height [[x cm]] against 16 cm | Lower third: "ITTF law 2.6.2: the toss must rise at least 16 cm" |
| 0:35–0:55 | Close edge ball; the player says **"challenge"** (push-to-talk) | The replay opens on the phone: the ball's track and its σ ellipse at the edge. The dashboard shows three AI votes arriving (**Claude, Gemini, Bitdeer**) next to the geometry. The judge upholds or overturns; the score updates. | Lower third: "AI votes are a second opinion: uncalibrated, and they never delay a call" |
| 0:55–1:05 | A player asks: **"Was that last one on the edge?"** | The ref answers aloud from the geometry check, saying BETA when it's close. The dashboard shows the transcript with the check and p | — |
| 1:05–1:15 | A player says: **"House rule: [[rule]]"** | The dashboard's Droid panel streams the plan, the diff and the `replay_test` result; the judge approves; the next point is called under the new rule | Lower third: "A Factory Droid wrote, tested and applied the rule in [[x]] s" |
| 1:15–1:30 | **The problem.** Quick cuts of the table, the court, the dorm lounge | — | "Pickup games don't have referees. Every close call is an argument, and arguments end games. [[real player quote, with permission]]" |
| 1:30–1:50 | **How it's built:** the architecture diagram (README), the dashboard's live world-state panel | — | "Phones are the cameras. A Mac runs vision, the rule engine and the voice. SpacetimeDB keeps every phone, the dashboard and the replay in one shared world state. Cartesia speaks every call and hears every question. Calls are geometry first, with honest confidence: AUTO, BETA or PLAYERS DECIDE." |
| 1:50–2:00 | Trophy Watch: the recap and ★ Play of the game | Scroll the recap; play the best moment | "Trophy. [[one-line close]]" |

**Numbers that may appear on screen** (only once measured on the Mac; else cut them):
- call spoken after the rally ends: p50 [[ms]] (C3);
- challenge → replay: [[s]];
- three votes shown in [[s]];
- Droid rule end to end: [[s]];
- voice question → answer starts: [[s]];
- accuracy: rallies [[n correct / n]], staged edge balls [[n / n]], staged serves [[n / 12]], with their 95% CIs, from labelled runs only.

**Backup:** if the live stack misbehaves while filming, use the CC BY ping-pong clip as the backup demo (SHOULD) and **say on screen that it's a recorded clip**, with its CC BY credit (`data/clips/credits.json`).

---

## 2. Devpost writeup (outline)

### Tagline
An AI referee for pickup games: phones are the cameras, every call is spoken, and it tells you how sure it is.

### Inspiration
- The community: [[OPEN-8: confirm with the user; the plan says students who play pickup ping pong and basketball at Berkeley (RSF courts, dorm lounges)]].
- The problem in their words: [[2–3 real player quotes, with permission]].

### What it does
- Live ping pong on one phone: rally scoring, the edge rule, illegal serves under ITTF law 2.6.2 (16 cm toss, within 30° of vertical on the rise, struck on the way down), hidden serves, net lets.
- The confidence tiers: AUTO at p ≥ 0.90, BETA with p and a challenge, PLAYERS DECIDE when the sensors can't judge; judgment fouls are capped at BETA.
- Every call spoken; push-to-talk to challenge, undo, ask the score, add a house rule or ask the ref.
- Challenge → instant replay with the track and its uncertainty, plus a background second opinion from Claude, Gemini and Bitdeer (uncalibrated, never delaying a call).
- Ask the ref: judge questions go to a geometry check; rules questions are answered from the rule pack and approved house rules.
- House rules in plain English: a Factory Droid edits the rule pack in a sandbox, gates it with `replay_test`, and the engine hot-loads it after approval.
- Trophy Watch after the game: recap, moments, highlights ending on ★ Play of the game, condensed game, replay, stats, moment search.
- Coming next (not built): basketball fouls, pickleball, tennis, badminton, volleyball, two-hand touch.

### How we built it
- The architecture diagram from `CLAUDE.md`. Phones stream 720p JPEG over WSS to a gateway on the Mac; flight (ball detection, track, events) and the engine (`rules.yaml`, CEL, the gate) run natively on an M5 Pro; SpacetimeDB is the shared world state; Caddy + Porkbun DNS-01 give the phones HTTPS at `trophy.photo`.
- Perception emits measurements; only rule packs decide (D-18). AI never makes a line call alone.
- Measured: [[the C1/C2/C3 table from docs/progress.md: device and method on every row]].

### Prize tracks (each with its evidence)
| Track | What we built for it | Evidence (link, file or number) |
|---|---|---|
| **Cartesia** | Spoken calls (Sonic WS, `context_id` + cancel, emotion on game point, two voices), Ink-2 push-to-talk, gateway-minted tokens | README "Cartesia"; measured iPhone TTS first chunk 112 ms after the request; the video |
| **Spacetime** | The shared world state: observations, track samples, game state, votes, house rules, Droid runs, asks, moments; identity-checked writers | README "Spacetime"; reducer → subscriber p50 3.4–5.0 ms (Windows localhost); [[Mac numbers]] |
| **Factory Droid SDK** | [[Agent 3: house rules + calibrate_checks, the sandbox, the gate]] | README "Factory Droid"; Droid rule end to end [[s]] |
| **Anthropic** | [[Agent 3: Claude in ask the ref + the challenge voter; where it could go wrong and how we contain it]] | README "Anthropic"; the named community and quotes above |
| **Bitdeer AI Model Studio** | [[Agent 3: challenge voter]] | README "Bitdeer"; vote latency [[ms]] |
| **Meta: bringing people closer** | Anyone joins with a phone and a QR code; everyone hears the same call; PLAYERS DECIDE hands close calls back; house rules keep each group's culture; Watch recap to share | README "Meta"; [[player quotes]]. The theme is enough; no Meta model needed (the user, 2026-10-24) |
| **MLH: Gemini API** | [[Agent 3: challenge voter]] | README "Gemini" |
| **MLH: GoDaddy Registry / .Tech** | `trophy.photo` (registered at Porkbun), serving the phones over HTTPS | The live URL `https://trophy.photo/cam/`; the user confirmed it qualifies (2026-10-24) |
| **MLH: Commit Fellowship** | [[the user: what this track needs]] | |
| **Cal Hacks overall** | The whole project | The video |

### Challenges we ran into (true stories from this weekend)
- Phones send 4:2:0 JPEG at q ≈ 0.7, so a 5–10 px ball loses its colour; detectors are tuned on frames that went through the phone path.
- Handheld footage breaks a one-time calibration, so the demo uses a fixed mount, side-on at the net line.
- Replay clips cut mid-game hung for 30 s, because ffmpeg waited on the live HLS playlist; cutting from a closed snapshot fixed it (0.7 s).
- A gateway test was flaky because Starlette's test client cancels the server task as soon as the socket closes; the test now waits for the handler to finish.
- The serve rule: "30° from vertical" is ITTF's review criterion, not law text; we call it on the rise only, and say so.
- [[Agent 2 and 3: add yours: BlurBall on MPS, the Droid sandbox, …]]

### Accomplishments we're proud of
[[after C3: the measured results]]

### What we learned
[[after the weekend]]

### What's next
Basketball 2s/3s and fouls, more sports from the same rule-pack + Droid flow, calibrated AI-vote probabilities, multi-camera 3D.

### Built with
[[final list; only what shipped: Python 3.11, FastAPI, Redis, SpacetimeDB 2.13, TypeScript, React 19, Vite, Cartesia Sonic + Ink-2, Claude, Gemini, Bitdeer Model Studio, Factory Droid SDK, OpenCV, ffmpeg, Caddy, …]]

### Licenses and media
Third-party code, models and media: `docs/licenses.md`. The CC BY clip is credited in `data/clips/credits.json`. BlurBall/WASB weights are used for the demo with the user's acceptance (D-30) and not redistributed.
