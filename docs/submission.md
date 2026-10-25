# Submission: the 3-minute video and the Devpost writeup (draft 2)

*2026-10-25 ~01:30 PDT. Rewritten from draft 1 against the code on `main`, rustybubble/trophy#19, #36 and #37, and the Devpost and Hive prize pages. Every `[[…]]` is a placeholder. **Never fill one with an estimate or an invented quote**; if it isn't measured or said by submission time, cut the line.*

**Hard deadline: Devpost submission Sun 10/25, 9:00 AM PDT** (Devpost page). Plan §0: feature freeze at 5:00, video locked at 7:00.

Rules for both:
- **Only measured numbers**, each with its device and method. Label synthetic data, recorded clips, sped-up footage and uncalibrated AI probabilities as such.
- **Player quotes are real** and said with permission. Everyone on camera has consented.
- **Don't claim what isn't built, or isn't live.** Live illegal-serve calls and live net lets don't fire yet (the 2D pipeline doesn't emit `serve_*` or net `touch` events). Basketball and every other sport are "coming next". No accuracy figure exists for real play.

---

## 1. The 3-minute video

**Why this shape:** Cartesia asks for **2 minutes, demo first** (one complete flow, then a brief problem + how it's built). The Devpost video is also what sponsors judge from on their own time. So **0:00–2:00 is a self-contained Cartesia cut**, and 2:00–3:00 adds the depth the other tracks score (Spacetime, Factory, Anthropic, technical complexity). Export the 2:00 cut separately and link it from the README's Cartesia section.

**Film it live on the Mac stack** with fixed phone mounts, side-on at the net line. Record the screen and room audio so the spoken calls are heard as they happened; don't dub them. If phones over HTTPS aren't verified by filming time, use "recorded clips as live cameras" (#19) and **say so on screen**.

| Time | Shot | What happens | On screen / voice-over |
|---|---|---|---|
| 0:00–0:10 | **Cold open, Mu Du** at the table: a fast rally, an edge ball, then Mu Du to camera | Not tracked; pure hook | Mu Du: "I've played internationally, and I still can't always tell if that clipped the edge." Lower third: Mu Du, [[exact ranking + federation]] |
| 0:10–0:15 | Title card | — | **Trophy.** A network of phones that referees your pickup games and settles the close calls. |
| 0:15–0:30 | Dashboard QR → a phone scans it → camera live; a second phone joins | Table corners found automatically | "Any phone is a camera. Scan, point, play." |
| 0:30–0:50 | A controlled rally (moderate pace) → point | **Trophy speaks the call and the score**; the banner shows the tier; the dashboard score ticks; the world view shows both cameras' ball dots | No voice-over: let the call speak |
| 0:50–1:05 | A close call → **Challenge** | Replay with the ball track and its σ ellipse; the geometry vote; **Claude's vote** next to it (only if it ran live, see gaps) | Lower third: "Claude is a second opinion: uncalibrated, never delays a call" |
| 1:05–1:25 | Trophy gets a rally wrong → judge taps **"one rally, won by A"** | Score fixed and spoken in < 3 s; a Droid `correction` run streams its plan, diff and gate on the dashboard → Approve → hot-load | Lower third: "Sped up [[n]]×; the real run took [[s]]" ("ready in 328 s, gate 52/52" if this is that run) |
| 1:25–1:40 | A player asks by voice: "Was that last one on the edge?" | Spoken answer from the geometry check, with BETA when close | Only if `referee serve` runs live (needs the Anthropic key); otherwise cut and lengthen 1:05 |
| 1:40–2:00 | **The problem + how it's built** | Quick cuts: the table, the dashboard | "Pickup games don't have referees, so every close call is an argument. Phones stream to a Mac; BlurBall tracks the ball at 30 fps; a rule engine decides; Cartesia speaks every call; SpacetimeDB keeps every screen in sync." |
| **2:00** | ——— end of the Cartesia cut ——— | | |
| 2:00–2:20 | **Spacetime** | Two phones and the dashboard side by side, updating on the same call | "Spacetime is the referee's memory: every camera's measurements and the game state, synced to every device and agent. Video never goes in; only facts do." |
| 2:20–2:40 | **The Droid writes the rules from the laws** | The `compile-rules` run: empty `rules:` → a pack where every rule cites an ITTF clause and lists what it couldn't encode; gate result | "We didn't hand-write the referee. A Factory Droid wrote it from the ITTF laws, and it repairs it from the judge's corrections." (Measured: 531 s, 34/34) |
| 2:40–2:50 | **Serves** (Mu Du's recorded serve analysis) | Toss height and angle traced on a recorded serve vs ITTF 2.6.2 (16 cm) | Label: **"Recorded analysis: live serve calls are next"** |
| 2:50–3:00 | **Trophy Watch** recap → ★ Play of the game → close | | "Trophy. Settle it, keep playing." Small "coming next" sport row (basketball, pickleball, volleyball…) labelled as not built |

**Numbers that may appear on screen** (all measured on the Mac, Apple M5, single runs, unless noted):
- BlurBall on MPS: **30 fps, 0 frames skipped, lag p50 ~100 ms** on the team's two recorded takes; two simultaneous cameras at 29–30 fps each (#19).
- First audio of a spoken call: **83–321 ms** after the call row (#36).
- Judge correction → score fixed: **< 3 s**, every time (#36).
- Droid house rule (synthetic fixtures): pending → **ready in 27.5–30.6 s**, gate 19/19; approve → hot-load **0.5–0.8 s**.
- iPhone 720p through `trophy.photo`: **29.9 fps received**, capture → Redis p50 145 ms (last 10 s only; demo PC, not the Mac).
- Spacetime reducer → subscriber: **p50 3.4–5.0 ms** (Windows localhost, not the Mac).
- **Never on screen:** "ball found in 97 % of frames" as accuracy (it's detection presence on unlabelled footage), or any synthetic 3D error figure without "synthetic".

---

## 2. Devpost writeup (paste-ready; fill or cut every `[[…]]`)

### Project name
Trophy

### Tagline (≤ 200 chars)
A network of phones that referees your pickup games: it calls every point out loud, says how sure it is, and lets the players decide the rest.

### Inspiration
Our teammate Mu Du is an internationally ranked table-tennis player, and even he can't always tell whether a ball clipped the edge or a serve toss was legal. In a tournament an umpire settles it. In a pickup game at [[the named community: e.g. "the [[club]] at Berkeley's RSF"]], nobody does: close calls become arguments, and arguments end games. [[One real player quote, with permission.]]

We wanted a referee anyone could set up with the phones already in their pocket, one that's honest about what a camera can and can't see.

### What it does
- **Phones become cameras.** Scan a QR code and your phone streams to the referee; the table's corners are found automatically. Several phones can watch one game.
- **Live ping-pong refereeing.** Trophy tracks the ball, scores rallies and applies the edge rule, and **speaks every call and the score** in a referee voice (Cartesia).
- **Honest confidence.** Every call is **AUTO** (p ≥ 0.90), **BETA** (shows p, can be challenged) or **PLAYERS DECIDE** (the cameras can't judge it). Judgment fouls are never forced.
- **Challenge → instant replay** with the ball's track and its uncertainty, plus a background second opinion from Claude that never delays a call.
- **The judge is always in charge.** One tap ("that was one rally, won by A") fixes the score, and that correction becomes a labelled example a Factory Droid uses to repair the rules.
- **The rules are written by a Droid, from the laws.** Starting from an empty rule list, a Factory Droid writes the table-tennis rule pack from the ITTF laws, citing a clause for every rule and declaring what it couldn't encode. Groups can add their own house rules in plain English; the Droid writes, tests and applies them after the judge approves.
- **Ask the ref** by voice: "was that on the edge?" gets an answer from the geometry; rules questions are answered only from the rules Trophy actually enforces. [[Keep only if it ran live.]]
- **Trophy Watch** after the game: recap, ★ Play of the game, highlights, condensed game, moments, stats and search.
- **Serve analysis (recorded):** toss height and angle under ITTF law 2.6.2, measured on recorded serves. Live serve calls are next.
- **Coming next (not built):** basketball, pickleball, tennis, badminton, volleyball, two-hand touch.

### How we built it
- **Capture:** a PWA (Vite + React 19, strict TS) streams 720p JPEG over WSS to a FastAPI gateway on an M5 Mac, through Caddy at `https://trophy.photo`. Frames ride a Redis frame bus to a recorder (2 s fMP4 HLS for replay) and the vision module. **Video never leaves the Mac.**
- **Vision:** BlurBall (blur-aware ball detection) on Apple MPS in fp16 tracks the ball at 30 fps per camera; a sport module turns tracks into bounces, contacts, net and edge events, merged across cameras, each with a position in table metres, σ and confidence.
- **Rules:** perception only measures, and only rule packs decide. A rule engine (YAML + CEL) applies the Droid-written pack and a confidence gate that assigns AUTO, BETA or PLAYERS DECIDE.
- **World state:** SpacetimeDB 2.13 is the shared world state: observations, track samples, game state, calls, votes, house rules, Droid runs, asks and moments. Each backend service writes through its own identity-checked reducers, and every phone, the dashboard and Trophy Watch subscribe.
- **Voice:** Cartesia Sonic speaks every call (≈ 83–321 ms from the call to first audio on the Mac); Ink-2 handles push-to-talk; browsers get short-lived tokens minted by the gateway, never the key.
- **Factory Droid:** triggered by a `house_rule` row or a judge's correction in Spacetime. It runs in a per-run git sandbox with a PreToolUse guard (allowlisted files, one allowed command), a git audit after every turn, and a `replay_test` gate that replays labelled games with no network. The dashboard streams its plan, steps, diff and gate; the engine hot-loads the pack from the gated commit only after the judge approves.
- **Claude:** a second-opinion voter on challenged calls (labelled uncalibrated, 4 s timeout, never in the call path), the phrasing of spoken answers from geometry numbers, and post-game commentary. The Droid itself runs on Claude Sonnet.

### Challenges we ran into
- **The hand-written rules were wrong on real play.** One recorded rally scored 5–6 points under our hand-written pack. Instead of patching filters, we had the Droid write the pack from the laws and repair it from judge-labelled rallies.
- **Single-camera confidence drifts between runs** (the same false bounce scored 0.68, 0.75 and 0.81), so thresholds flip. That pushed us toward multi-camera evidence.
- **Phones send 4:2:0 JPEG**, so a 5–10 px ball loses its colour; the detector is tuned on frames that went through the phone path.
- **Handheld footage breaks calibration**, so the demo uses fixed mounts, side-on at the net, with automatic corner detection.
- **Replay clips cut mid-game hung for 30 s** because ffmpeg waited on the live HLS playlist; cutting from a closed snapshot fixed it (0.7 s).
- **The 30° serve rule** turned out to be ITTF's review criterion, not law text, so we measure the angle on the rise only, and say so.

### Accomplishments that we're proud of
- A full live loop on one laptop: phones → BlurBall at 30 fps → rule engine → Spacetime → a spoken call, about [[x]] s after the point ends [[measure, or cut]].
- A referee whose rules were written by an agent from the official laws, and that gets better when the judge corrects it.
- Honest confidence everywhere: nothing claims more certainty than the cameras have.
- [[Mu Du / the team's pick]]

### What we learned
[[Each teammate: one sentence.]]

### What's next
Live serve calls from the fused 3D track; a labelled evaluation with real accuracy numbers; calibrated AI-vote probabilities; then more sports from the same rule-pack + Droid flow (the Droid has already drafted a pickleball pack from its rulebook, rules only).

### Built with
python, fastapi, redis, spacetimedb, typescript, react, vite, cartesia, claude, factory-droid-sdk, blurball, pytorch, opencv, ffmpeg, caddy, cel

### Prior work and third-party components (keep this; "all work must be done during the hackathon")
- Vendored unchanged from our earlier project Replay (MIT): `tv-core` (the media clock in Trophy Watch).
- BlurBall source (MIT; weights' license unstated, used locally, not redistributed); 4D-Humans, RacketVision, E2E-Spot sources (MIT/BSD) in the serve-analysis prototype.
- Full list: `docs/licenses.md`. Clip credits: `data/clips/credits.json`.

### Links
- GitHub: https://github.com/rustybubble/trophy [[must be public or shared with judges]]
- Video: [[YouTube/Vimeo URL]] · Cartesia 2-minute cut: [[URL]]
- Image: the dashboard mid-game (score, call feed, world view, Droid panel)

### Prize tracks to opt into on the submission form
| Track | Evidence to point at |
|---|---|
| **Spacetime** | README "Spacetime"; video 2:00–2:20; every device on one world state |
| **Anthropic: Claude for Public Benefit** | Named community + quote; README "Anthropic" (where it could go wrong + containment); Claude in the voter, the answers and the Droid |
| **Meta: Bringing People Closer Together** | Strangers and a ranked player can share a table without arguing; QR join; one shared call for everyone; Watch recap |
| **Factory Droid SDK** | README "Factory Droid" (trigger, sandbox, gate, visible plan/diff); video 1:05–1:25 and 2:20–2:40 |
| **Cartesia** | The 2:00 cut; README "Cartesia" (setup, features, limitations) |
| **MLH: GoDaddy Registry domain** | `trophy.photo` |
| **MLH: Commit Fellowship** | Opt in **and submit MLH's supplemental form** |
| **Cal Hacks:** Most Technically Complex, Most Creative, Best People-First, Hacker's Choice | The whole project |
