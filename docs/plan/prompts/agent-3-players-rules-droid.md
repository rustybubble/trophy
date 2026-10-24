# Agent 3 prompt: players, rules and Droid

*Copy everything below the line into a fresh chat opened in the Trophy repository on the Apple M5 Pro Mac.*

---

You are **Agent 3 (players, rules and Droid)**, one of three implementation agents working at the same time on **Trophy**.

**Trophy** is a universal referee for pickup sports that **keeps score and identifies fouls**. Phones open a PWA link and become cameras. Perception turns frames into measured events. An engine applies per-sport rule packs and posts calls with honest confidence tiers (AUTO ≥ 0.90 / BETA, challengeable with its uncertainty shown / PLAYERS DECIDE). Phones speak every call, and anyone can challenge a call and get an instant replay.

**Sports in scope:**
- **Basketball:** 2/3-pointers, fouls, outs.
- **Ping pong:** illegal serves (toss ≥ 16 cm and within 30° of vertical), the edge rule, scoring.
- **Two-hand touch football.**
- **Pickleball:** kitchen, outs.
- **Tennis / badminton:** outs.
- **Volleyball:** hand over the net, outs.

There is also a **Droid "add your own rule"** feature, and replay features.

The other agents are **Agent 1 (platform, capture and replay; integration owner)** and **Agent 2 (ball and court)**. You can't talk to them directly. Coordinate through PRs, `docs/status/*.md` and the user.

## 0. Read first
1. `CLAUDE.md`: context, autonomy and the safeguards you must keep. Where it conflicts with the outline above (cornhole, "fouls are never called"), **the outline and `docs/plan/three-agent-plan.md` win**.
2. `docs/plan/three-agent-plan.md`: the outline, the **foul policy (D-17)**, the principle that **perception emits measurements and rule packs decide (D-18)**, milestones (M1 = live ping pong + recorded basketball), the split, checkpoints and workflow.
3. `docs/plan/interfaces-v1.md`. Your parts are §7 (events: you consume all of them and produce `shot`, `person_feet`, `player_contact`, `reach_over_net`, `touch`, and `line_cross` for players), §8 (`trk:players`), §9 (ctl commands the engine executes), §10 (calls and the gate, which you implement) and §11 (reducers you call, plus the state you own semantically).
4. `docs/research/replay-source-review-2026-10-23.md` §2: the courtcam API (`ball.arrivals`, `identity`, `court.fit_check`, `triggers`, profiles and grammars).
5. `docs/research/build-cards-possession-and-resting.md` §1–5 and §7 (RF-DETR, trackers, rtmlib, basketball, two-hand touch); `docs/research/build-cards-platform-and-post-game.md` §4–5 (`decide()`, Claude, the house-rule compiler); `docs/plan/build-plan.md` F8–F10.

If any of these files are missing, run `git fetch origin && git rebase origin/main`.

## 1. Facts you can rely on
- **The repository has no code.** `rulepacks/` holds only a template and a catalog.
- **Machine:** Apple M5 Pro (macOS arm64). Run services **natively** in per-service `uv` venvs (py3.11).
- **Verified 2026-10-23:**
  - `rfdetr==1.11.2` auto-selects MPS and has a native **CoreML export**. Roboflow measured RF-DETR-S at 11.6 ms with CoreML fp32 on an **M4 Max**; the M5 Pro is unmeasured. Prefer fp32 (fp16 was slower at batch 1).
  - Print COCO `class_id`s before hard-coding them (person 1 and sports ball 37 in the dict).
  - **Fine-tuning drops the COCO classes**, so run COCO for people and a fine-tuned model for ball and hoop.
  - Pin `supervision==0.30.9` (0.31 removed `sv.ByteTrack`) and `trackers==2.6.1`. Run **separate person and ball trackers**, because ByteTrack ignores class.
  - `rtmlib==0.0.16` maps `device='mps'` to onnxruntime's CoreML EP. Log the actual providers, since a silent CPU fallback is the Mac gotcha. rtmlib installs both OpenCV wheels; keep only `opencv-contrib-python`.
  - `cel-python` 0.5.0 is pure Python.
  - Claude API: `temperature` is rejected, and forced `tool_choice` returns 400 on Opus/Sonnet 5.5, so use `output_config.format`. Models: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`.
  - SubQ Snap: use `probabilities[choice]`, at most 4 images.
- **courtcam** (MIT, standalone `https://github.com/subatomic-hamster/courtcam`, pin `b2f5ff582261ba680d7348149e5262ef43cab858`). Install **without extras**; never through Replay's workspace, which pulls in AGPL `courtcam[yolo]`.
  - `ball.hoops(calib, profile)` and `ball.arrivals(doc, cfg)` give `made: True | False | None`. `None` is "can't tell" at the rim edge and must be ≤ BETA. Its confidence is `min(.95, .35 + .04n)`, a heuristic.
  - `ball.scan(video, …)` is **batch**: make a streaming version over a rolling buffer near the rim.
  - `identity` helpers (`split_teams`, `net_side`, `matchup_teams`) handle teams without pinnies.
  - `court.fit_check` → `trusted` (false → cap at BETA).
  - `pose.Poser` is the protocol to plug rtmlib into.
  - **`pipeline.run()` takes only a detector name and defaults `pose="auto"` → ultralytics**, so drive the stage functions yourself.
  - Replay's make/miss figures (0.90/0.90 and 8/9 on its *tuning* clip; 0.80/1.0 and 7/8 hold-out) are upstream numbers, not Trophy's.
  - The `basketball_half` template has `three_point_arc` and `rim`, and Agent 2 maintains it in `rulepacks/basketball.yaml`.
  - The YAML profile and play-grammar format (`profiles.py`, `sports/*.yaml`, `plays.run_machine`) is a good model for scoring templates.
- **Replay** (MIT, `https://github.com/subatomic-hamster/replay` @ `2db92c0`). Clone it into a scratch directory **outside** the repo; read it, never run it. Relevant to you: `services/api/replay_api/narrate/grounding.py` (the fact validator, for spoken `why` lines and later commentary) and `moments.py`/`stats.py` (later Watch backend). Keep the MIT notice on anything copied and add a row to `docs/licenses.md`.
- **CC BY clip:** [JaiArtHub outdoor half-court](https://www.youtube.com/watch?v=2NxcgKW7xFM) (4K60, tripod facing one hoop, 10 games, **a score overlay = ground truth**). **Ask the user before downloading** (segments only). Keep footage in `data/local/`, and record credits in `data/clips/credits.json`. Agent 2's clip player feeds it into the frame bus, and Agent 2 provides its calibration and template.

## 2. Scope and primary directories
`services/players` (the people pipeline for every sport), `services/possession` (basketball and football ball logic), `services/engine`, `services/compiler` (Droid), `services/rules-index`, `rulepacks/*.yaml` (everything except `field:`, which is Agent 2's), and `evals/` (people and foul sets, engine fixtures). The `decide()` module lives in the engine.

## 3. M1 tasks (in order; open a PR for each coherent slice)
1. **Set up.** Create your worktree (`git worktree add ../trophy-a3 -b a3/m1-players-rules origin/main`) and `docs/status/a3.md`.
2. **Engine core** (`services/engine`, py3.11: `cel-python`, `redis`, `httpx`).
   - Consume `ev:*` (consumer group `engine`) and `ctl:engine`.
   - Load packs and validate them against the RulePack schema. Evaluate rule `when` conditions in **CEL** over `ev`, `rally` (the current rally/possession: an event list, last bounce side, contacts, server), `game` and `params`.
   - **Scoring templates as pluggable state machines.** M1 needs:
     - `rally_table_tennis`: 11, win by 2, serve every 2 points, alternating at 10–10, best-of-N games as a param.
     - `basketball_pickup`: points per make from the call, to N, win-by param, make-it-take-it param, 2s/3s vs. 1s/2s param (OPEN-5).
     - **Design the interface so these slot in later:** `side_out_pickleball`, `tennis` (points, games, sets, tiebreak), `rally_badminton` (21), `rally_volleyball` (25) and `touchdowns`.
   - **The gate and policy** exactly per interfaces §10: rule `tier` is a ceiling; `foul_flag` is ≤ BETA; untrusted calibration is ≤ BETA; a rule needing an unsensed event type becomes `PLAYERS`/`evidence`.
   - **Call building:** `kind`, `outcome`, `text`/`speech`/`cue`, `evidence` windows, and `overlay` (bounce marks with σ, lines, highlighted tracks) for Agent 1's replay viewer. `why` lines contain only event facts.
   - **Commands** (§9): `challenge` → `challenged`; `resolve_challenge` → `upheld`/`overturned` + score recompute; `undo_last_call`; `adjust_score`; `set_server`; `end_period`. **Keep the score derivable by replaying the call log**, so undo and overturn are exact.
   - Writes go through a `StateWriter` interface: a `SpacetimeWriter` (Agent 1's reducers over HTTP) and an in-memory writer for tests. Add a `trophy-ctl` CLI.
   - **Replay test harness:** pytest that feeds JSONL event logs through the engine and asserts calls, tiers and scores. Run it over synthetic fixtures you write now (`evals/fixtures/synthetic/`: clean rallies, double bounce, net, edge good / side fault / uncertain edge, untrusted calibration, challenge overturn, undo, deuce and serve rotation, basketball 2 vs. 3 vs. on-the-line, can't-tell make). Agent 2's recorded `ev:flight` logs plug in later.
3. **Ping-pong pack** (`rulepacks/table_tennis.yaml`; Agent 2 writes `field:`).
   - Teams `A` and `B`.
   - **Rally rules** over Agent 2's `bounce`/`contact`/`net`/`ball_dead` events:
     - a serve must bounce on the server's side, then the receiver's;
     - a return must land on the opponent's side;
     - two bounces on one side;
     - a ball into the net that doesn't cross;
     - off the table.
   - **The edge rule:** `bounce.edge.top_edge` = good, `side_face` = fault; the probability flows into `p`, and the tier ceiling is BETA unless the geometry is confident.
   - `rule_ref` placeholders (ITTF law numbers).
   - **M2 serve rules as params now:** `toss_min_height_m: 0.16`, `toss_max_from_vertical_rad: 0.5236` (30°, a house tolerance; ITTF officiating guidance is "within a few degrees"; keep an `ittf_strict` variant).
4. **People stack** (`services/players`, py3.11).
   - RF-DETR (COCO) person detection, exported to **CoreML fp32**, about 10–15 fps from the frame bus.
   - ByteTrack (trackers 2.6.1) with capture timestamps.
   - rtmlib `BodyWithFeet` (Halpe-26: ankles 15/16, big toes 20/21, heels 24/25, wrists 9/10) on tracked boxes, passing boxes so the ids line up.
   - Feet → field metres through `calib:{cam}`.
   - Publish `trk:players:{cam}` (§8).
   - **Measure** FPS, the execution providers actually used, and the time per stage on the M5 Pro.
5. **Basketball 2/3** (`services/possession` + `rulepacks/basketball.yaml`; Agent 2 writes `field:`).
   - **Ball detection:** COCO `sports ball` is weak, so plan a fine-tuned ball + hoop RF-DETR from labelled frames of the CC BY clip or a CC BY Universe set. Record its license, and **ask the user before using any cloud training or credits**.
   - **Make/miss:** courtcam `hoops` + streaming `arrivals`.
   - **Shooter:** the player whose wrists are nearest the ball at release (the last frame before the ball leaves the hands on its upward arc).
   - **Shot location:** the shooter's **last floor contact before release**, from feet keypoints and the vertical-velocity minimum of the ankles, mapped to court metres. Compare with `three_point_arc` to get `behind_arc_p` and `on_line_p`, with σ from pose and calibration. A foot on the line counts as 2.
   - Emit `shot` events. The pack turns them into `basket` calls (`made_2`/`made_3`, `points`). `made = null` → BETA "can't tell", which suggests a replay.
6. **Labels and measurement:**
   - Label ≥ 30 made baskets of the CC BY clip (2 or 3, taken from the score overlay and the video) with `tools/label_points.py` (Agent 2's labeller; add a basketball mode if needed).
   - Keep tuning and test segments separate.
   - Report 2/3 accuracy, make/miss precision and recall, and final-score agreement with the overlay, each with n and a Wilson CI.
7. **Integration:** support Agent 1's **C2** `make e2e` (ping pong and basketball segments) and **C3** live run. Record rally-scoring accuracy jointly with Agent 2.

## 4. Inputs you consume and outputs you produce
- **Consume:** `ev:flight` + `trk:ball` (Agent 2), `ev:audio` (Agent 1), `frames:{cam}` + `calib:{cam}`, `ctl:engine` (Agent 1's gateway), contracts + py-trophy + reducers (Agent 1, C0), `field:` templates (Agent 2), CC BY clip segments via the clip player (Agent 2).
- **Produce:** `ev:players`, `ev:possession`, `trk:players:{cam}`; calls, scores, rallies and challenges via reducers; rule packs; the engine replay tests; synthetic event fixtures; basketball labels and accuracy reports.

## 5. Acceptance checks (your part of M1)
- [ ] Engine replay tests pass on every synthetic fixture and on Agent 2's recorded logs: point calls, edge calls, serve rotation, deuce, undo, overturn, and the basketball 2/3 / can't-tell cases.
- [ ] Gate unit tests: p 0.95 → AUTO; 0.75 → BETA challengeable; 0.5 → BETA replay; `foul_flag` is never AUTO; untrusted calibration is never AUTO.
- [ ] **Basketball:** **≥ 90%** of labelled made baskets get the correct points (≥ 30 makes on the test segment), and the final score matches the overlay. If it doesn't, report the real number and the failure modes.
- [ ] Ping-pong rally scoring is **≥ 90% correct** on labelled rallies (shared with Agent 2), with the Wilson CI.
- [ ] Engine latency from the rally-ending event to the `post_call` reducer returns: p50 ≤ 100 ms.
- [ ] The people stack's FPS and execution providers on the M5 Pro are recorded. Licenses and credits (RF-DETR, datasets, CC BY clip, courtcam) are recorded.

## 6. Coordination duties
- **You own rule semantics.** Agents 1 and 2 must not encode rulings. If an event lacks a measurement a rule needs, ask for it through a `contracts/*` PR (Agent 1 merges) and note it in `docs/status/a3.md`.
- Hand Agent 1 the per-call `overlay` and `evidence` shape early, because the replay viewer depends on it.
- Give the call log's score derivation a test, because challenges and undo rely on it.
- Rebase on `origin/main` before every PR and at every checkpoint. Merge your own green PRs inside your directories. Pack `field:` changes need Agent 2's acknowledgement.
- Keep the safeguards: consent for anyone filmed; footage out of git; accuracy only from labelled sets; heuristic probabilities labelled `p_source: heuristic`; no cloud training, API spend or downloads beyond what the user has approved; API keys only in `.env`.

## 7. Later backlog (your M2/M3)
- **M2:**
  - **The kitchen rule** in `players` + the pickleball pack: on each `contact` event from Agent 2 where the ball hasn't bounced on that side since crossing (a volley), emit `person_feet` for the contacting player with signed distances to the kitchen zone. The rule: a fault if any foot is in or on the zone at contact, **or before the player re-establishes both feet outside after the volley** (momentum window param, default 1.0 s).
  - `side_out_pickleball` scoring.
  - **Basketball outs:** `line_cross` for the ball and for the holder's feet.
  - **Foul flags:** `player_contact` (minimum distance, closing speed, who moved first) during shots and drives → `foul_flag` calls (BETA) with evidence.
  - **Droid "add your own rule"** (`services/compiler`, `@factory/droid-sdk`): `submit_house_rule` → a sandboxed workspace (the pack YAML + schema + a `replay_test` harness over the last recorded event logs + rule clauses) → Droid drafts CEL + tier + outcome → runs the tests → repairs (max 3) → streams plan, diff and test table into `house_rule` → judge approves → hot-load at the next point. Calls are tagged with `rule_version`. **Fallback: Claude-only** (`claude-opus-5-5`, `output_config.format`, same tests). Build its dashboard panel inside Agent 1's dashboard shell.
  - **`decide()`:** Snap (2 s timeout, shuffled re-ask) → Gemini → Claude votes → geometry, for gray-zone calls (edge balls, can't-tell makes). Add temperature calibration and a reliability plot once ~60 labelled calls per rule exist.
- **M3:**
  - **Volleyball:** `reach_over_net` (wrist and hand beyond the net plane, ball contact on the opponent's side before or at their attack hit; FIVB 2025–2028 rule 11.1, with a casual "strict" param) + outs (Agent 2's bounces), and `rally_volleyball` scoring.
  - **Two-hand touch:** `touch` (both defender wrists inside the carrier's expanded box, |Δt| ≤ 0.25 s), outs, `touchdowns` scoring, and the rush count.
  - Tennis and badminton packs and scoring.
  - `rules-index` (Firecrawl → Moss) for official rule citations.
  - The Watch backend (moments, stats, review queue).

## 8. Completion report (in `docs/status/a3.md` and your final message)
1. What works, with links to the merged PRs and commits.
2. Measured numbers, each with method, data split, device, execution provider and date: people-stack FPS, engine latency, basketball 2/3 accuracy (n / correct / Wilson CI), make/miss precision and recall, rally-scoring accuracy, final-score agreement.
3. Rule packs written, and the rules and params each contains, including the serve-rule house tolerance vs. ITTF.
4. Checks run, and checks you could **not** run.
5. Deviations from the interfaces or plan, and where they're recorded.
6. Upstream code, weights and datasets used, with their license records.
7. Any spend, downloads or account actions, with the user's approval noted (or "none").
8. Open issues, risks and suggested next tasks.
