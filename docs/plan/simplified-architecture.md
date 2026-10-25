# Trophy: the simplified architecture (proposal, 2026-10-24)

*Status: **proposal, not yet adopted.** Written after a review of what is built on `origin/main`, PR #6 (Droid, engine, rules) and PR #8 (rulebook). Adopting it means a new decision (D-32; D-31 is taken by the Agent 3 restart), a rewrite of `three-agent-plan.md`, `interfaces-v1.md` and `CLAUDE.md`, and closing or trimming PRs #6 and #8.*

## Why

The stack serves eleven prize tracks and ten services. On 2026-10-24 the state is:

| Built and merged | Built, unmerged | Not started |
|---|---|---|
| contracts, py-trophy, state client, Spacetime module (13 reducers), gateway, capture PWA, Cartesia voice (works on an iPhone), `trophy.photo` | engine + table-tennis pack, Droid compiler (rehearsals pass), rules service + Apify actor (two versions: PR #6 and PR #8) | **flight (the ball tracker)**, recorder, dashboard, Trophy Watch, courtcam-adapter, ingest, players, possession |

The sponsor-facing code (Droid, three AI voters, Apify, Moss) is about 14,000 lines. The perception that every call depends on is 0 lines, and no agent branch exists for it. Trophy cannot referee a single point today. Every integration kept from here on is time not spent on the ball.

## The cut

**Keep four sponsors, each of which is also the product:**

| Sponsor | Why it stays | Already built? |
|---|---|---|
| **Spacetime** | The shared state. Phones, the judge view and every service already read and write it; replacing it means rebuilding working code. | Yes (module, state client, verified at 7–14 ms reducer → client) |
| **Cartesia** | "Every call is spoken" is the product. TTS and STT both work on an iPhone. | Yes (spike passed on the phone) |
| **Anthropic** | The AI second opinion on close calls, ask-the-ref answers, and the house-rule fallback. One model, one key. | Partly (voters and `/ask` in PR #6 / #8) |
| **Factory Droid** | The house-rule compiler is built, rehearsed (house rule in 30.6 s) and is the biggest single prize. **Optional cut:** Claude-only compiler, same UX, one fewer runtime (Node + `droid` CLI + sandbox hook). | Yes (PR #6) |

**Drop seven:**

| Dropped | What it carried | Replaced by |
|---|---|---|
| **Gemini, Bitdeer** | Two of the three challenge voters | Claude alone, blended with geometry. The Anthropic rule "Claude never makes a line call alone" still holds, since geometry votes too. Removes two keys, two clients, the parallel fan-out and two README sections. |
| **Apify, Moss** | Scrape official rulebooks → vector index → retrieval for ask-the-ref | **A clause file in the repo.** The ITTF laws and a pickleball rulebook are a few hundred clauses; they fit in Claude's context with prompt caching. `/ask` becomes one Claude call over `rulebooks/*.json` with the existing citation gate (quote must appear verbatim in the file). No index service, no actor, no scraping approval needed. |
| **Vultr** | GPU fallback for BlurBall | Classical tracker on the demo machine. If it misses 25 fps, that is a tracker decision, not a sponsor one. |
| **GoDaddy / .Tech** | MLH domain prize | `trophy.photo` is at Porkbun, so it likely never qualified. Keep the domain, drop the claim. |
| **Meta** | Writeup only | Unchanged; costs nothing. Opt in at submission. |

**Drop the unbuilt scope with them:** Trophy Watch (D-24, vendored Replay `tv-core`, HLS, sprites, watch party, broadcast mode), recorded basketball and the whole people stack (players, possession, courtcam-adapter, RF-DETR, CoreML), pickleball, WebRTC ingest (JPEG over WS already measured 30.0 fps). Other sports stay on the "coming next" wall, labelled not built.

## What remains

```
Phone PWA  /cam  (capture, 720p JPEG over WSS, audio onsets, call banner, Cartesia TTS + Ink STT, replay viewer)
           /judge (score, calls, challenge + Claude's opinion, house-rule panel, ask transcript)   ← replaces apps/dashboard
      │
      ▼
gateway (FastAPI)  frames → Redis ring  frames:{cam}      ·  /api/clips (phone-uploaded replay clip)
                   Cartesia token  ·  /api/ask (Claude over rulebooks/*.json)  ·  ctl → engine
      │
      ▼
flight  (ball tracker → bounce, edge/side p, serve toss height + angle, σ)  ─observations─▶  Spacetime
engine  (table_tennis pack, CEL, scoring, confidence gate; Claude second opinion on BETA calls) ─▶ Spacetime
compiler (Droid, or Claude)  ◀─ house_rule row ─▶  Spacetime
      │
Spacetime ─subscriptions─▶ every phone
```

| | Before | After |
|---|---|---|
| Sponsors integrated | 11 | 4 (3 if the Droid goes) |
| Services | 10 + 3 apps | 4 + 1 app (gateway, flight, engine, compiler; PWA) |
| API keys | Anthropic, Gemini, Bitdeer, Cartesia, Factory, Apify, Moss, Porkbun, Vultr, Roboflow | Anthropic, Cartesia, Factory, Porkbun |
| Event paths | Redis `ev:*` hot path **and** Spacetime observations (D-21) | Spacetime only. Measured 3–5 ms p50, so the duplicate hot path buys nothing. Redis keeps frames only. |
| Replay source | recorder service (ffmpeg, 2 s segments, HLS) | The clip the phone already uploads on challenge (PR #5), plus the Redis frame ring for the ball trail |
| Calibration | separate courtcam-adapter (py3.12) | Four corner taps on the phone → one homography in flight. The table is a known 2.74 × 1.525 m rectangle. |
| Perception stacks | flight + people | flight |
| Agents | 3 (Agent 2 never started) | 2: **perception** (flight, calibration, labels, accuracy) and **everything else** (gateway, PWA, engine, compiler, ask, video) |

## Checkpoints, simplified

- **C1** a phone streams 720p ≥ 25 fps through `trophy.photo`; a Cartesia line plays.
- **C2** the CC BY ping-pong segment → flight → engine → Spacetime → the phone speaks point calls; replay works; `/ask` returns a cited answer.
- **C3** live table: ≥ 20 labelled rallies, ≥ 10 staged edge hits, ≥ 12 staged serves, with accuracy reported; call spoken ≤ 1.5 s; challenge → replay ≤ 4 s with Claude's opinion; a house rule applied end to end.
- **C4** freeze, three rehearsals, 2-minute video, README (Cartesia, Factory, Spacetime, Anthropic limits), writeup.

## Effect on open work

- **PR #6 (Droid, engine, rules):** keep `services/engine`, `services/compiler`, `rulepacks`. Drop `services/rules`, `actors/`, the moment index, `/coach` and the post-game `moment` rows.
- **PR #8 (rulebook):** close. Salvage the citation gate (`services/rules/rules/ask.py`) into the gateway's `/api/ask`, and the synthetic laws fixture for tests.
- **PR #7 (clip_as_phone):** merge unchanged; it is the C2 harness.
- **Docs:** `trophy-watch-postgame.md`, `agent-3-part-2-rulebook.md` and the Watch sections of `interfaces-v1.md` move to `docs/archive/`. D-5, D-8, D-19, D-23, D-24 are superseded by D-32.

## What this does not fix

The ball. A classical tracker on a white ball against a dark table, from one side-on phone at 30 fps, is unproven on this hardware; the team's own 4K footage shows the ball motion-blurred at every resolution (PR #7). That spike is the first task after this cut, before any further integration work.
