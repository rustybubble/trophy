# Agent 3 prompt: rules, AI and Droid

*Copy everything below the line into a fresh chat opened in the Trophy repository on the Apple M5 Pro Mac.*

---

You are **Agent 3 (rules, AI and Droid)**, one of three implementation agents building **Trophy** in parallel for **Cal Hacks 13.0 (this weekend, Fri 10/23 to Sun 10/25)**. The submission deadline is in `docs/plan/three-agent-plan.md` → `DEADLINE`; ask the user if it's blank. **Feature freeze is DEADLINE − 4 h.**

**Trophy** is a universal AI referee for pickup games. Phones become cameras. Trophy keeps score and identifies fouls with honest confidence (AUTO ≥ 0.90; BETA shows p and can be challenged; judgment fouls are `foul_flag`, capped at BETA). Calls are spoken.

**The weekend demo is live ping pong on one phone**: rally scoring, the edge rule, and **illegal serves** (house rules from the user: **the toss must rise more than 6 in = 0.1524 m off the open palm**, and **the path from the hand to the hit must stay within 30° of vertical**). **Spacetime is the shared world state**, and video never goes into it: vision modules write `observation` rows (metadata), and your engine, Droid and LLM judge all reason over that same record (plan §2, interfaces §7.1). You own most of the sponsor-facing intelligence:
- the **rule engine and scoring**;
- the **AI second opinion on challenges** (Claude ‖ Gemini ‖ Bitdeer Model Studio voters);
- the **Factory Droid "add your own rule" compiler**;
- **ask the ref** (an Apify actor scrapes the official rulebooks → a Moss index → Claude answers with citations).

The other agents: **Agent 1 (platform, capture, voice, replay; integration owner)** and **Agent 2 (ball and court perception)**. Use PRs, `docs/status/*.md` and the user.

## 0. Read first
1. `docs/plan/three-agent-plan.md`: the cut, **the prize-track evidence table** (several tracks depend on your work), phases and checkpoints. It overrides older plan text.
2. `docs/plan/interfaces-v1.md`. Your parts are §7 (events you consume), §9 (ctl commands you execute), §10 (calls and the gate), §11 (tables and reducers you write), **§15 `decide()`**, **§17 ask the ref** and **§18 the Droid compiler**.
3. `CLAUDE.md`: the safeguards.
4. `docs/research/build-cards-platform-and-post-game.md` §4–5 (decide wrapper ideas, calibration, the Claude API, the house-rule compiler). (Older feature specs F8–F10/F19 are in `docs/archive/build-plan.md`: background only.)

## 1. Facts (verified 2026-10-23/24; recheck the docs before pinning)
- **No code exists yet.** Use native `uv` venvs (py3.11); the compiler is Node 20.
- **Perception emits measurements and packs decide** (D-18), so every rule lives in `rulepacks/*.yaml` as CEL `when` conditions + outcomes + tier ceilings + scoring params. That's what lets the Droid change rules by editing YAML.
- **Claude:** `claude-opus-5-5` (answers, compiler fallback, voter) and `claude-haiku-5-5` (cheap intent parsing). `temperature` is rejected, and forced `tool_choice` returns 400, so **use `output_config.format` for structured output.**
- **Gemini** (MLH track): use your `GEMINI_MODEL` with JSON or enum structured output, and up to 4 images or a short clip.
- **Bitdeer AI Model Studio** (a prize track; you must *clearly show* it's used): OpenAI-compatible at `https://api-inference.bitdeer.ai/v1` (use the `openai` client with `base_url`). Vision goes through chat completions with `image_url` (base64 < 1 MB). The listed vision models are `Qwen/Qwen3.5-397B-A17B`, `moonshotai/Kimi-K2.6` and `nvidia/Nemotron-3-Nano-Omni-30B-A3B`; `GET /v1/models` lists the rest. Docs: developers.bitdeer.ai.
- **Factory Droid SDK** (a prize track, $2000):
  - `npm install @factory/droid-sdk` (Node ≥ 18). `run()` for one prompt, `createSession()` for multi-turn. It drives the `droid` CLI from PATH (`execPath` to override) and needs `FACTORY_API_KEY`.
  - **The import path differs** between the docs (`@factory/droid-sdk/node`) and the README (root), so check the shipped `.d.ts`.
  - **Judges want:** a trigger we designed, safe and scoped access, visible plans, steps, diffs and results, and the README explaining where and how Droid is used. They **penalise** chatbot wrappers and slide-only demos.
- **Moss** (a prize track; their example is "voice agents that listen, respond and act in real time"): `project_id` + `project_key`; `create_index`, `add_docs`, `query`; models `moss-minilm` / `moss-mediumlm`. **Package names conflict** (`moss` vs. `inferedge-moss` on PyPI; `@moss-dev/moss` vs. `@inferedge/moss` on npm), so check docs.moss.dev first.
- **Apify** (a prize track + Best Actor): write an **actor** with the Apify Python SDK + Crawlee. Public pages only; respect robots and terms; nothing behind a login or paywall. **Publishing to the Apify Store needs the user's OK.**
- **Not sponsors, so don't use them:** SubQ, Firecrawl, Deepgram.
- **courtcam** (MIT, pin `b2f5ff5`, no extras) for the SHOULD basketball work: `ball.arrivals` gives make/miss (`None` = can't tell → BETA); `basketball_half` has `three_point_arc`. Replay's numbers are upstream, not ours.

## 2. Scope and directories
- `services/engine` (including `decide/`)
- `services/compiler` (Node, Droid)
- `services/rules` (Apify output → Moss; `/ask`)
- `actors/rulebook-scraper` (the Apify actor)
- `rulepacks/*.yaml`, everything except `field:` (Agent 2)
- `evals/fixtures/synthetic/` (engine fixtures)
- the SHOULD work: `services/players` and `services/possession` (basketball)

You write the README sections for **Factory Droid, Anthropic/Claude (including "where it could go wrong"), Bitdeer, Moss, Apify and Gemini**. Agent 1 assembles the README.

## 3. Tasks in priority order (MUST first; open small PRs; merge at least every ~2 h)

**P0 (the first ~3 h): spikes, in parallel with Agent 1's C0**
1. Create your worktree (`git worktree add ../trophy-a3 -b a3/wk-rules-ai origin/main`) and `docs/status/a3.md`.
2. Hello-world each sponsor API and record what worked: one Claude structured-output call, one Gemini call, one **Bitdeer vision call**, one **Droid SDK** session that edits a toy YAML and runs a test command in a temp directory, and one **Moss** index + query.
3. **Engine core** against synthetic fixtures, while C0 lands:
   - Consume `ev:*` and `ctl:engine`.
   - Load and validate packs; evaluate CEL `when` over `ev`, `rally`, `game` and `params`.
   - **`rally_table_tennis`** scoring: 11, win by 2, serve every 2 points, alternating at 10–10; best-of and the target score are params, so "first to 7" is a param change.
   - **The gate** per §10: the tier is a ceiling; `foul_flag` ≤ BETA; untrusted calibration ≤ BETA.
   - Calls get `text`, `speech`, `cue`, `evidence` and `overlay`.
   - Commands: `challenge`, `resolve_challenge`, `undo_last_call`, `adjust_score`, `set_server`, `submit/approve/reject_house_rule`, `ask_logged`.
   - **The score is derived by replaying the call log**, so undo and overturn are exact.
   - A `StateWriter` with Spacetime and in-memory implementations; a `trophy-ctl` CLI.
   - **`replay_test`**: a CLI + pytest that replays JSONL event logs through the engine with a given pack and prints a before/after call table. The Droid uses it too.
4. **`rulepacks/table_tennis.yaml`** (Agent 2 writes `field:`):
   - The rally rules over `bounce`, `contact`, `net` and `ball_dead`: a serve must bounce server-side then receiver-side; a return must land on the opponent's side; two bounces on one side; net into own side; off the table.
   - **The edge rule:** `edge.top_edge` → good, `side_face` → fault; `check: ensemble`, so a challenge triggers the voters.
   - **The serve rules (MUST), over `serve_toss` observations:**
     - `serve_toss_too_low`: `height_m ≤ toss_min_height_m` (0.1524 m = 6 in). The probability comes from Φ((limit − h)/σ).
     - `serve_toss_angle`: `angle_from_vertical_rad > toss_max_from_vertical_rad` (0.5236 rad = 30°) over the path from the hand to the hit.
     - Both are **faults → point to the receiver**, tier ceiling AUTO, and the gate makes near-limit tosses BETA. `check: ensemble` lets close tosses get votes.
     - Speech: "Fault. Toss too low." / "Fault. Toss not vertical."
     - An `ittf_strict` variant (0.16 m, a few degrees) is a param set.
   - `rule_ref` filled from the Moss citations once they exist.

**P1 (the slice)**
5. **Ask the ref** (independent of perception, so finish it early):
   - **The Apify actor** `actors/rulebook-scraper` ("Sports Rulebook Scraper"):
     - Input: `{sources: [{sport, url, kind}]}`.
     - Output: **one dataset item per rule**, `{sport, rule_id, title, text, url, source, license_note, fetched_at}`.
     - Start with the official **ITTF** laws (ping pong), then USA Pickleball, FIBA/NFHS basketball, BWF and FIVB.
     - Handle HTML and PDF.
     - Run it on Apify. **Ask the user before publishing it to the Store** (Best Actor).
   - **`services/rules`** (FastAPI on :8100):
     - `index build` pulls the actor's dataset into **one Moss index per sport**.
     - `POST /ask {question, sport}` → Moss `query(top_k=5)` (log `moss_ms`) → Claude answers **only from the retrieved clauses** (≤ 3 sentences, cites `rule_id`, says "I couldn't find that rule" when retrieval is weak) → `{answer, speech, citations, moss_ms, latency_ms}`.
     - It also offers `GET /rule_ref?sport=&q=`, which the engine uses for `rule_ref`.
6. **`decide()`** (`services/engine/decide/`) per **§15**. **It must never add latency to a live call:**
   - Start it **speculatively in the background** when a close (0.35 < p < 0.75) `ensemble` call is posted, and again on a challenge only if it hasn't run yet.
   - **Claude ‖ Gemini ‖ Bitdeer run in parallel**, with a **4 s timeout** each, shuffled options, and errors recorded. Their context is the relevant **`observation` rows** + crops from Agent 1's `/api/replay/.../frames`.
   - Measure each voter's latency in P0. If one is consistently > 3 s, switch it to a faster model; keep Bitdeer in (prize track).
   - A blend with geometry (weights labelled uncalibrated).
   - Post one `ai_vote` row per voter + a suggested verdict. **The judge still decides.**
   - Unit-test it with recorded HTTP fixtures so there are no live calls in CI.
7. Run the engine on Agent 2's recorded `ev:flight` logs from the CC BY clip, and support Agent 1's **C2** `make e2e`.

**P2: Droid + live**
8. **The Factory Droid compiler** (`services/compiler`, Node 20) per **§18**:
   - **Trigger:** the Spacetime subscription to `house_rule WHERE status = 'pending'`.
   - **Sandbox:** a throwaway workspace with only the pack YAML, the schema, `replay_test`, and `context/clauses.md` (the top-k Moss clauses). No network beyond the Factory API; 90 s timeout; the Droid may only edit that YAML and run `replay_test`.
   - **Loop:** draft → test → repair, at most 3 times.
   - **Stream** the plan, steps, YAML diff and test table (including "calls that would change") via `update_house_rule_progress`.
   - On Approve, the engine hot-loads `rulepacks/house/{game_id}/{sport}.v{n}.yaml`, and later calls carry `rule_version`.
   - The **Claude-only fallback** uses the same tests, and the row records `backend`.
   - **Demo rules (OPEN-9):** "first to 7, win by 1" (a param) and "a serve that clips the net is a let" (a rule). **Rehearse both** in under 90 s each.
9. Live tuning with Agents 1 and 2. Record the rally-scoring accuracy jointly with Agent 2.

**P3: freeze**
10. Write your README sections. The **Anthropic** one must name the community, state the problem, describe how Claude is used, and say **where it can go wrong**: blurry crops, wrong votes, a misread rule, a compiler mistake. Then say how we contain each one: geometry in the blend, judge confirmation, citations, replay tests + human approval. Also write the Factory, Bitdeer, Moss, Apify and Gemini sections. Hand everything to Agent 1.

**P2b: post-game data for Trophy Watch (right after C3; see `docs/plan/trophy-watch-postgame.md` and interfaces §19)**
- **Write `moment` rows live from the engine:** point, serve fault, edge call, challenge, basket, bookmark, house rule, plus `clip_that` tagging via the trigger-to-play rule.
- **`highlight_score` + `reasons`** from event features only (rally length, game/match point, closeness, overturned challenge, near-limit serve, three-pointer, game winner). There's no crowd audio, so say so.
- `set_best_play` at `end_game`.
- **The `rules` service:** a per-game **Moss moment index** + `POST /search_moments` (Moss track); `POST /coach` (grounded Claude tips through the adapted Replay `narrate/grounding.py` validator, with a template fallback); `commentary` lines per moment (play-by-play + colour, validated) for Agent 1's Cartesia broadcast mode.
- `review_call` handling, which appends labels to `evals/labels/`.
- For basketball, publish player tracks so Agent 1 can build follow-a-player.

**SHOULD (only after your MUSTs pass C3)**
11. Basketball 2s/3s on the CC BY [half-court clip](https://www.youtube.com/watch?v=2NxcgKW7xFM) (after the user OKs the download):
    - RF-DETR (CoreML) people + ByteTrack + rtmlib feet;
    - courtcam `arrivals` make/miss (streaming over the rim region);
    - the shooter's last floor contact vs. `three_point_arc` → `shot` events;
    - `basketball_pickup` scoring.
    - Score it against the clip's score overlay.

## 4. Consumes and produces
- **Consume:** `ev:flight` (Agent 2), `ev:audio`, `ctl:engine` + `/replay/.../frames` + the reducers (Agent 1), `field:` (Agent 2).
- **Produce:** calls, scores, votes, house-rule and ask rows (via reducers); packs; `replay_test`; the `rules` service and the Apify actor; the compiler; README sections; engine fixtures.

## 5. Acceptance (your part)
- [ ] Engine replay tests pass on synthetic and recorded logs (points, the edge rule, serve rotation, deuce, undo, overturn), and gate unit tests pass.
- [ ] Rally-ending event → `post_call` returns in p50 ≤ 100 ms.
- [ ] Spoken calls are never delayed by voters (tested). A challenge shows **all three votes** (or an explicit per-voter timeout or error) within 4 s of the call being posted.
- [ ] Serve rules pass replay tests (low toss, angled toss, legal toss, near-limit → BETA).
- [ ] The **Droid applies a new rule end to end in < 90 s**, with the plan, diff and tests visible, and the next point follows it.
- [ ] `/ask` answers 5 prepared ping-pong questions with correct ITTF citations (checked by hand); Moss latency is reported.
- [ ] The Apify actor runs on Apify and produces the rule dataset.
- [ ] Moments are written live; ★ Play of the game is chosen with reasons; `/search_moments` returns correct moments for 5 prepared queries per game; coach tips and commentary pass the grounding validator, or fall back to templates.
- [ ] No API key is in the repo or the logs. Probabilities from voters are labelled uncalibrated.

## 6. Coordination
- You own rule semantics. If an event lacks a measurement you need, ask Agent 2 through a `contracts/*` PR (Agent 1 merges).
- Give Agent 1 the `overlay`/`evidence` shapes and the Droid panel data early.
- **Ask the user before:** publishing the actor, any paid API tier, YouTube downloads, filming people.
- At feature freeze, only fixes.

## 7. Completion report (`docs/status/a3.md` + your final message)
1. What works, with PR links.
2. Measured numbers with method and date: engine latency, voter latencies and failure rates, Droid compile times and success rate, Moss latency, ask-answer correctness on the prepared set, rally accuracy (joint), basketball accuracy if done.
3. The packs and house rules demoed.
4. Checks run and checks not run.
5. Deviations from interfaces-v1.
6. Upstream code, models and data used, with license rows.
7. Account actions and spend, with the user's approval noted.
8. Known demo risks and fallbacks.
