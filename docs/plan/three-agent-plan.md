# Trophy: three-agent plan for the Cal Hacks 13.0 demo weekend

*Planning lead, revised 2026-10-24 (cleanup pass the same evening: Moss, Apify and Vultr dropped; current status lives in `CLAUDE.md` → "Where things stand") for the **Cal Hacks 13.0 prize tracks** and a **demo-weekend cut**. Cal Hacks runs Fri 10/23 to Sun 10/25. **The exact submission and judging times are not confirmed** (the schedule page wouldn't load them). There is no fixed deadline (see below). Wire formats: [interfaces-v1.md](interfaces-v1.md). Prompts: [`docs/plan/prompts/`](prompts/). Replay and courtcam reuse: [replay-source-review-2026-10-23.md](../research/replay-source-review-2026-10-23.md).*

> **DEADLINE:** none fixed. The user decided on 2026-10-24 that **we stop when the features are done**. Read "DEADLINE − n h" elsewhere as "once the MUSTs pass C3": then feature freeze, rehearsals, the video and the writeup.

---

## 0. What we're building

**Trophy** is a universal AI referee for pickup games. Players open a link on their phones, and the phones become cameras. Trophy **keeps score and identifies fouls with honest confidence**:
- clear calls are automatic (AUTO, p ≥ 0.90);
- close calls show their probability and can be challenged (BETA);
- judgment fouls are flagged, never forced.

Every call is **spoken**. Players can **challenge** a call and get an **instant replay** with the ball trail and the bounce's uncertainty ellipse. They can **ask the ref** a rules question by voice, and **add their own house rule** in plain English, which a Factory Droid compiles, tests and applies from the next point.

**The community we're building for** (needed for the Anthropic track, **confirm with the user**): students who play pickup ping pong and basketball at Berkeley (RSF courts, dorm lounges). With no referee, every close edge ball, every "was that a three?" and every house rule turns into an argument. **Get two or three real quotes** from players this weekend and put them in the Devpost writeup. Don't invent them.

### The demo-weekend cut

| Tier | What | Prize tracks it serves |
|---|---|---|
| **MUST (the demo)** | **Live ping pong on one phone:** rally scoring, the **edge rule** (top edge good / side fault, with probability), **spoken calls** (Cartesia), live score on every phone and the dashboard (Spacetime) | Overall, Most Technically Complex, Cartesia, Spacetime, Meta |
| **MUST** | **Illegal-serve rules (ping pong):** official ITTF law (D-31): the toss must rise **at least 16 cm (0.16 m)** from the open palm to its apex, **within 30° of vertical on the way up**, and be struck as it falls; plus hidden serves (2.6.5), position (2.6.4) and net lets (2.9.1.1). Measured in metres and degrees with σ, called AUTO when the geometry is clear and BETA when it's close, PLAYERS DECIDE when evidence is missing, and shown on the replay as a toss trace with the 16 cm line and a 30° cone | Overall, Most Technically Complex, Cartesia (spoken "Fault: toss too low") |
| **MUST** | **Challenge → instant replay** (0.25× slow-mo, ball trail, bounce mark + ellipse) → **AI second opinion**: Claude votes on the crops next to the geometry, and the vote is shown → the judge upholds or overturns. **The vote never delays a live call:** it starts in the background as soon as a close (BETA) call is spoken, so it's usually ready by the time someone taps Challenge (§2.1) | Anthropic, People-First |
| **MUST** | **"Add your own rule" with a Factory Droid:** the judge types or says "first to 7, win by 1" or "no lets: a serve that clips the net is played on". A Droid in a sandbox edits the pack YAML, runs replay tests, and streams its plan, diff and tests to the dashboard. The judge approves, and it is enforced on the next point | **Factory ($2000)**, Anthropic (Claude-only fallback) |
| **MUST** | **"Trophy, what's the rule on…?"** Cartesia Ink speech-to-text → the referee service (D-37): judge phrases run a geometry check over the ball track; rules questions are answered by Claude grounded only in the sport's `rules.yaml` + approved house rules → spoken by Cartesia | Cartesia, Anthropic |
| **MUST** | A real domain from the MLH partner (GoDaddy Registry or .Tech) on the HTTPS origin for the phones | MLH domain prizes |
| **SHOULD** | Recorded **basketball 2s/3s + score** on the CC BY [half-court clip](https://www.youtube.com/watch?v=2NxcgKW7xFM) | Overall ("universal") |
| **SHOULD (post-game core, first SHOULD after C3)** | **Trophy Watch for every game we run** (live ping pong + recorded basketball), translated from Replay's Fire TV app ([trophy-watch-postgame.md](trophy-watch-postgame.md)): recap page, seek bar with moment notches + sprite preview, moments list with filters, **highlights reel + ★ Play of the game (with reasons)**, condensed game, replay of any moment with overlays + votes, **stats** (ping-pong bounce heatmap, serve faults, edge balls; basketball shot chart, 2PT/3PT), **search moments** (keyword; the Moss version is dropped). Then, if time allows: broadcast mode with Cartesia play-by-play, grounded coach tips (Claude), review queue, follow a player (basketball), clip + share, **watch party** (Spacetime), reconstructed top-down views | Spacetime, Cartesia, Anthropic, Meta, Overall |
| **SHOULD** | Ping pong on the CC BY [club match](https://www.youtube.com/watch?v=7maQFqJ3XQ0) with its disputed edge ball at 8:36, as a backup demo if the live table fails | Demo safety |
| **STRETCH** | pickleball kitchen or outs on the CC BY [clip](https://www.youtube.com/watch?v=QhLECLlXU3c) | Overall |
| **CUT for the weekend** | Tennis, badminton, volleyball and two-hand touch (shown on a "coming next" sport wall, labelled as **not built**), basketball fouls, SAM 2.5D free view/player's view, face profiles, phone-side recording upload | — |

**Foul policy (D-17):** measurable violations go through the confidence gate. Judgment fouls are `foul_flag` calls capped at BETA, and players decide.

**Principle (D-18):** perception emits measurements and only rule packs decide. That's what makes the Droid's YAML edits enough to change a rule.

### Tracks and what each needs at submission

| Track | Requirement | Owner of the evidence |
|---|---|---|
| **Factory Droid SDK** | Droid does real work in the running product; **a trigger we designed** (a new `house_rule` row in Spacetime); **scoped access with safety built in** (a throwaway workspace containing only the pack YAML, schema and `replay_test`; no network; 90 s timeout; human approval); **visible plan, steps, diff and results**; **the README explains where and how Droid is used** | A3 (compiler), A1 (dashboard panel) |
| **Cartesia** | Voice is core; a working demo; **a 2-minute demo-first video** (one complete flow, then the problem + how we built it); **a README listing the Cartesia features used and known limitations**; no keys in the repo | A1 (voice client), all (video) |
| **Spacetime** | Spacetime is **the** shared world state: vision observations from every camera, live game state, the challenge flow and AI votes, the Droid trigger, ask-the-ref transcripts; devices *and* agents coordinate through it (their "AI agent coordination" example) | A1 (module), A2/A3 (writers) |
| **Anthropic** | A named community, a real problem, it works, **thoughtful Claude use, and where it could go wrong** (README "Limits and failure modes": Claude never makes a line call alone; it can be wrong on blurry crops; answers come only from cited rules) | A3 |
| **Meta: Bringing People Closer Together** | Strengthens human connection; AI essential; original; a strong working demo | Writeup (all) |
| **MLH GoDaddy Registry / .Tech domain** | Register the domain we serve the phones from | A1 (with the user) |
| **Cal Hacks overall / Most Technically Complex / People-First / Hacker's Choice; MLH Commit Fellowship** | Opt in at submission | User |

**Dropped by the user (2026-10-24):** Moss and Apify (ask the ref is grounded in the rule pack instead, D-36/D-37), Vultr (the backend runs on the Mac, D-30), and Gemini and Bitdeer (Claude is the only model voter, D-41). **Not sponsors, so dropped:** SubQ Snap (→ the Claude voter), Firecrawl (→ Apify), Deepgram (→ Cartesia Ink STT). Langfuse, AgentMail, Greptile and Remotion are out for the weekend. **Convex** is not used: Spacetime is our backend, and running both would weaken each.

---

## 1. Where the repository is
See `CLAUDE.md` → "Where things stand" (kept current) and `docs/status/a{1,2,3}.md`. Verified integration facts are in `CLAUDE.md` → "Gotchas" and `docs/research/`.

## 2. Architecture (weekend): Spacetime is the shared world state; video never goes into it
```
Phone(s) ─video─▶ gateway ─▶ Redis frames:{cam} (video stays out of Spacetime) ─▶ vision module per sport family
                                                                                   (ping pong: flight = ball tracker + bounce/edge/serve-toss)
vision module ──observations (metadata only: what happened, where, when, how sure, which camera)──▶ Spacetime  observation / track_sample
                                     └─ same events on Redis ev:* (the engine's low-latency hot path)
Spacetime world state ──subscriptions──▶ every phone, the dashboard, and every agent:
   engine (rule packs → calls, scores) · compiler (Factory Droid writes rules over the observation vocabulary) ·
   LLM judge (Claude reads observation rows + crops on close calls) · referee (checks + Claude phrasing + Cartesia: ask the ref)
```
This follows the team's Spacetime direction (D-21):
- **No video frames in Spacetime.** Frames stay on the Redis frame bus and in the local recorder (for replay and crops).
- **The vision module turns video into sport-agnostic metadata**, and *that* is what Spacetime syncs: `observation` rows (bounce, contact, net, serve toss, …, each with time, position in court metres, σ, confidence, camera) and down-sampled `track_sample` rows (the ball's position at 10 Hz). All devices and agents then see the same facts.
- **It scales by adding rows, not schemas.** A second phone just adds observations tagged with its `cam_id`, and the engine fuses them. A new sport needs a vision module that emits the same vocabulary, plus a rule pack.
- **"An LLM judge that adapts to any sport" works at two speeds** (see §2.1):
  - **Live calls stay deterministic and fast.** The engine applies the rule pack to observations in milliseconds.
  - **The LLM side** (Claude) does what needs judgment, reading observation rows as its context: it writes rules for a new sport or house rule (the Droid, grounded in the sport's rule pack), gives a second opinion on close calls, and explains verdicts.
  - So the LLM adapts Trophy to a sport *once*, not on every bounce.
- **Still open: the vision module and the exact metadata** (the "tricky part").
  - For the weekend, the module is Agent 2's ping-pong flight service, and the metadata is the interfaces-v1 §7 vocabulary.
  - Choosing the module per sport family (ball tracker vs. people + pose) and growing the vocabulary is the post-weekend design question, recorded as OPEN-10.

Other runtime notes:
- Everything runs **natively on the M5 Pro** (D-12). The Mac's Wi-Fi LAN carries the phones, behind Caddy with the domain's certificate. A tunnel is only for day-1 UI work.
- **Spacetime writers** are backend services only: the **vision module** (observations and track samples only), the **engine** (game state, calls, votes, ask log) and the **compiler** (house-rule progress). Clients read through subscriptions and write through the gateway.

### 2.1 Latency: the AI votes never sit on the live path
Asking a hosted model does cost time: roughly 1–4 s with images (estimated; measure it in P0). So:
1. **Live calls are geometry plus rules only.** The bounce → spoken call target is ≤ 1.5 s, and no model is called on this path.
2. **The votes are speculative and run in the background.** When the engine posts a close (BETA) call, it starts the Claude voter without waiting, capped by a 4 s timeout. Results land in `ai_vote` rows, usually before anyone taps Challenge.
3. **A challenge never waits on the votes.** The replay starts immediately (≤ 4 s). Votes that are already in are shown; any that are still pending appear as they arrive. A voter that times out shows "no answer", and the judge decides anyway.
4. **The AI votes only when it's worth it:** close calls (0.35 < p < 0.75) or challenged calls. Clear calls never trigger it. This also keeps API spend down.
5. **If the voter is consistently slow** (measure it), drop it to a faster model (for example Claude Haiku).

## 3. Phases (relative to DEADLINE; times are budgets, not promises)

| Phase | Window | Exit check |
|---|---|---|
| **P0: contracts + spikes** | First ~3 h | **C0** contracts merged. Spikes report: tracker FPS on the Mac (classical vs. BlurBall MPS); Spacetime reducer → subscription latency; a Droid SDK hello-world in the sandbox; one Claude vision call; a Cartesia TTS line + an Ink STT transcript from the phone; the domain registered |
| **P1: clip vertical slice** | Next ~6 h | **C2** `make e2e`: the CC BY ping-pong segment → flight → engine → Spacetime → PWA shows and speaks point calls. Replay of a call works. `/ask` returns a grounded answer |
| **P2: live + features** | Next ~6 h | **C3**: live phone ping pong with scoring + edge calls + **illegal-serve calls** + Cartesia voice; challenge → replay → Claude's vote → uphold/overturn; the Droid adds a rule end to end; ask-the-ref by voice |
| **P2b: post-game core** | After C3, before freeze | **C3b:** recap + moments + highlights/★ Play of the game + condensed + replay + stats + moment search work on the live ping-pong game **and** the basketball clip (if basketball shipped) |
| **P3: freeze + submit** | Last ~4 h | **C4**: feature freeze; three full rehearsals; the **2-minute demo-first video** (Cartesia format: flow first); READMEs (root + Factory + Cartesia sections, plus limits); the Devpost writeup listing each track + evidence; measured numbers in `docs/progress.md` |

SHOULD items (basketball, the clip backup) happen only once their owner's MUST items pass C3. STRETCH items happen only after C3, and stop at feature freeze.

## 4. Three agents

| | **Agent 1: platform, capture, voice and replay** (integration owner) | **Agent 2: ball and court** | **Agent 3: rules, AI and Droid** |
|---|---|---|---|
| Dirs | `apps/*`, `services/gateway`, `services/recorder`, `spacetime/`, `packages/*`, `infra/`, root build/CI | `services/flight`, `services/courtcam-adapter`, `tools/`, `evals/` (ball) | `services/engine` (incl. `decide`), `services/compiler`, `services/referee` (ask the ref), `sports/` (sport modules, rules, checks), basketball people stack (SHOULD) |
| MUST | C0 contracts + codegen + py-trophy (incl. the `trophy.world` observation writer) + state client; Spacetime module (incl. `observation`/`track_sample`); gateway (frames, clock, ctl, calibrate proxy, **Cartesia token**, `/ask` proxy, replay); PWA (join, 720p capture, onsets, calibration taps, call banner + **Cartesia TTS**, **Ink STT push-to-talk** for "challenge"/"ask"/"add rule", replay viewer, challenge UI); dashboard (score, calls, **Droid panel**, **AI votes panel**, **ask-the-ref transcript with citations**); the domain + Caddy; `make dev`/`e2e`; **integration, checkpoints, the video and README assembly** | Calibration (`/calibrate`, table template); tracker spike (classical vs. BlurBall MPS → OPEN-3); flight service: bounces fused with phone onsets, **edge vs. side probabilities**, **`serve_toss` (release → apex → hit: height in m, angle from vertical, σ)**, net/dead ball, `trk:ball`; **observations + track samples written to Spacetime**; CC BY clip prep (after the user's OK) + labels; staged edge hits | Engine + table-tennis pack (**incl. the 6 in / 30° serve rules**) + scoring + gate + challenge flow; **`decide()`: the Claude voter on crops** + geometry; **Droid compiler** + Claude-only fallback; **the referee service** (`/ask`: checks + Claude grounded in `rules.yaml`); README sections for the Factory and Anthropic tracks |
| SHOULD / STRETCH | **Trophy Watch** (`apps/watch`): recap, seek bar + sprite, moments, highlights, condensed, replay, stats, search UI; then broadcast mode, watch party, clip + share, follow a player, reconstructed views; recorder HLS + sprite + watch API. Also the clip-backup demo mode and the sport wall | Pickleball outs on the CC BY clip | **Post-game data:** live `moment` rows + highlight scoring + ★ best play, moment search, grounded coach tips + commentary lines, `review_call`; player tracks for follow-cam. Basketball 2/3 on the CC BY clip (people stack + courtcam make/miss); pickleball kitchen |

**Dependencies:**
- C0 (A1, about 1–2 h) unblocks typed events everywhere. Until then, everyone uses interfaces-v1.md.
- A2's events + A1's frames feed A3's engine. A3 develops on synthetic and recorded event logs until C2.
- The challenge voters need frames/crops from A1's replay API (`/api/replay/.../frames`).
- The Droid needs the engine's `replay_test` harness, which A3 owns, so there's no cross-agent wait.
- **Ask-the-ref is independent of perception**, so it can be finished early.

## 5. Checkpoints (A1 runs them, tags `wk-cN`, writes `docs/progress.md`)

| CP | Pass condition |
|---|---|
| **C0** | Schemas + codegen + py-trophy + `MockState` (labelled synthetic) + CI merged; A2 and A3 acknowledge |
| **C1** | A phone streams 720p at ≥ 25 fps via the domain origin; onsets arrive; a Cartesia line plays on the phone |
| **C2** | `make e2e` passes on the CC BY ping-pong segment; the replay API works; `/ask` returns a cited answer |
| **C3** | Live: ≥ 20 labelled rallies scored with the accuracy reported; ≥ 10 staged edge hits with the accuracy reported; **≥ 12 staged serves** (4 legal, 4 tossed < 6 in, 4 tossed > 30° off vertical) with the accuracy reported; call spoken ≤ 1.5 s after the rally ends (p50); challenge → replay ≤ 4 s; Claude's vote shown; the Droid rule applied end to end in < 90 s; voice ask → spoken cited answer starts ≤ 3 s after the question ends |
| **C3b** | Trophy Watch core on the live ping-pong game (and the basketball clip if shipped): recap, moments, highlights ending on ★ Play of the game with reasons, condensed, replay with overlays, stats, moment search (5 prepared queries per game) |
| **C4** | Frozen, rehearsed 3×, video + READMEs + writeup done; numbers measured or marked "not measured" |

Accuracy numbers come **only from labelled clips or staged hits**, with n and a Wilson CI, and are labelled as weekend measurements. Never present an estimate as a measurement.

## 6. Workflow
- **Worktrees:**
  ```bash
  git worktree add ../trophy-a1 -b a1/wk-platform origin/main
  git worktree add ../trophy-a2 -b a2/wk-ball origin/main
  git worktree add ../trophy-a3 -b a3/wk-rules-ai origin/main
  ```
  Use small PRs to `main` and squash-merge. Rebase on `origin/main` before every PR. **Merge often (at least every ~2 h)**; this is a weekend.
- **Merge rights:** A1 approves `packages/*`, `spacetime/`, root build/CI and `.env.example`. A3 approves rule packs (A2 approves `field:`). Each agent merges its own green PRs inside its own directories.
- **Coordination:** `docs/status/a{1,2,3}.md` (status, blockers, interface requests, numbers). The user relays any urgent cross-agent asks.
- **Secrets:** `.env` only. Phones get short-lived Cartesia tokens. No keys in the repo; this is also a Cartesia rule.
- **Spend and downloads:** ask the user before downloading YouTube clips, creating any cloud resource, changing DNS, or registering the domain. Each is the user's account action.

## 7. Open decisions
| Id | Item | Default | Decider |
|---|---|---|---|
| OPEN-2 | Domain | **Decided: `trophy.photo`** (the user registered it on 2026-10-24, at Porkbun, with Porkbun DNS). Caddy + DNS-01 through the Porkbun API → the demo machine's LAN IP. Check whether `.photo` qualifies for the MLH GoDaddy Registry prize | User + A1 |
| OPEN-3 | Ball tracker | **Decided (D-30): BlurBall on MPS on the Mac.** The classical detector on #19 is the floor until BlurBall is measured | User |
| OPEN-4 | BlurBall weights license (unstated) | **Decided (D-30): the user accepts using them for the demo; never redistributed** | User |
| OPEN-6 | Serve-toss rule values | **Decided (D-31): the official ITTF law.** `toss_min_height_m: 0.16`, `toss_max_from_vertical_rad: 0.5236` on the rise. The old house values (6 in, hand to hit) are an optional `house` variant | User |
| OPEN-8 | The community named in the writeup | "Berkeley pickup ping pong and basketball players" | User (with real quotes) |
| OPEN-10 | Vision module per sport family and the metadata vocabulary beyond ping pong | §7 vocabulary for the weekend | Team, after the weekend |
| OPEN-9 | Which demo house rule | "First to 7, win by 1" (a scoring change) + "no lets: a serve that clips the net is played on" (a rule change: it turns off the ITTF net let, 2.9.1.1) | A3 + user |
| A-1 | The live stack runs on the M5 Pro, which Agent 2 has; Agent 1 develops on the Windows PC; one live game at a time; recordings stay local | | |
