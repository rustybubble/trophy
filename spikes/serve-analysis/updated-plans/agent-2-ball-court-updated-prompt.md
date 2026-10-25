# Trophy — updated Agent 2 kickoff prompt

You are Agent 2 of 3 building Trophy, an AI referee for recreational play, for Cal Hacks 13.0 this weekend. Your worktree is `../trophy-a2`, on branch `a2/wk-ball`.

Read `AGENTS.md` and `docs/plan/prompts/agent-2-ball-court.md` in full, then read `docs/plan/three-agent-plan.md` and `docs/plan/interfaces-v1.md`. Follow the current plan and interface contracts. They override anything in `docs/archive/`. This kickoff adds the demo requirements below. Surface conflicts in `docs/status/a2.md`; coordinate interface changes with the other agents instead of silently changing shared contracts.

This revision incorporates the user's latest authorization to find and use additional testing footage, the supplied wireframe-player visual reference, and official ITTF rule sources. It supersedes the earlier kickoff's per-clip testing-download approval requirement and its provisional serve thresholds/hand-to-hit angle interpretation.

Also read the complete companion specification at `/Users/mudu/Developer/calhacks/updated-plans/table-tennis-demo-model-spec.md` and incorporate it into the new repo under `docs/plan/`. It defines the recommended three-bundle perception stack, the non-model geometry/rules components, the detailed demo storyboard, and validation gates. Copy the supplied visual reference alongside the plan. Resolve ownership/interface conflicts with the current three-agent plan explicitly.

## Product and required demo

Our table tennis demo must show:

1. **Score calling:** a recorded rally produces evidence for a point award, the rules component decides, and the shared scoreboard and spoken call update through the components that own them.
2. **Illegal serves:** measure the serve toss and provide evidence for the rules component to evaluate it.
3. **Point start/end timestamps:** identify candidate rally boundaries on a shared timeline, with uncertainty and evidence, so each point can be selected and replayed.
4. **Synchronized camera views:** play both original views together with shared seeking, playback speed, and point selection.
5. **A 3D reconstruction and close-up evidence view of the point or call:** target the smooth wireframe human models in the supplied reference. Let the viewer inspect the decisive moment and understand the evidence behind the call. Ship the original-video close-up first if reconstruction is not yet reliable, and report 3D readiness explicitly.

The intended flow is: watch a rally → hear/see the point call and score update → select or challenge that point → inspect synchronized slow-motion views and a close-up or 3D evidence view. Include an inconclusive case with an explicit unresolved state that the rules/UI components can hand to the players.

You own the perception, calibration, synchronization, measurements, and replay inputs assigned to you by the plan. **Emit measurements, never rulings.** Do not independently award points, declare a serve illegal, or make an edge ruling. Ensure your measurements can drive the complete flow through the agreed interfaces.

## Actual recordings and synchronization

The user has recordings of the **same rally captured simultaneously on two separate phones**:

- One camera directly from the side.
- One camera at a diagonal angle behind one player.

Audio availability, frame rates, exposure characteristics, calibration, and actual synchronization accuracy have not yet been established. Inspect the original files when available. Request their location if needed; continue independent work meanwhile.

Do not assume matching recording starts, equal frame rates, or corresponding frame numbers. Preserve source timestamps and frame identity. Estimate a coarse offset from shared audio when available, then verify/refine using visible events and cross-view geometry. Account for sound travel when using audio for precise alignment. Check alignment at multiple times and estimate drift if necessary. Provide manual offset adjustment as a fallback.

Report estimated alignment and its uncertainty. Separate synchronized playback from verified capture-time accuracy. Interpolation does not create an observed frame or prove an impact. Never promise perfect synchronization; reject measurements that are too sensitive to the remaining timing uncertainty.

## Existing work to reuse

Prior work is available locally at `/Users/mudu/Developer/calhacks`. Inspect and selectively port useful implementation and tests, respecting licensing and the new repo's contracts. Useful references include:

- `README.md`, `MULTIVIEW.md`, `REPLAY.md`, `VALIDATION.md`, and `PROVENANCE.md`.
- `trophy/model.py`, `trophy/pipeline.py`, and `trophy/replay/`.
- `scripts/`, `configs/`, and `web/multiview/`.

That prototype already runs the actual pretrained BlurBall model on Apple Silicon MPS, estimates cross-camera timing offsets, triangulates a ball from calibrated views, and provides paired source playback plus an orbitable replay. Its documented ball errors of roughly 2.5–2.6 cm median were measured on two calibrated TT3D sample rallies, **not the user's phone recordings**. Its reported model timings are not end-to-end throughput guarantees.

The existing player bodies and wrist-attached rackets are illustrative estimates. They do not establish measured paddle-face orientation, ball contact, spin, or an open palm. Original footage and measurement provenance must remain available beside any reconstruction. Do not copy large caches or publish model weights by default.

## Additional testing footage

The user will provide their two original phone videos. They also authorize finding and using other videos for development, regression tests, and checking that the intended behavior works. You may obtain permitted public testing footage, including YouTube footage where downloading is permitted, without asking again for each clip. Prefer official research datasets and downloadable originals with timestamps, calibration, or labels. Existing TT3D/BlurBall samples are useful starting points.

Record each source URL, creator/dataset, usage terms, acquisition date, checksum, frame rate, camera arrangement, and available labels. Testing permission does not by itself authorize redistribution in the public demo. Keep downloaded media out of git unless its terms permit inclusion. Do not incur charges or bypass access restrictions.

Use varied cases: ordinary rally endings, serves with measurable tosses, occlusion, difficult lighting, white/orange balls, and edge/side contacts where independently reviewable. Single-view clips can test detection and event evidence; only calibrated synchronized multi-view clips can establish multi-view reconstruction accuracy. Keep development clips separate from held-out evaluation clips. Performance on research footage does not establish performance on the user's phone footage.

## Official rules as the decision reference

**Understand the official rulebook well enough to build Trophy's referee behavior, rather than merely collecting citations.** Read Chapter 2, The Laws of Table Tennis, in full, including every subsection and exception. Read the applicable competition regulations, official match-official guidance, and TTR guidance needed to interpret and administer those laws. Do not limit the review to serve height, toss angle, and edge balls. The required outcome is a system that can follow a game, determine supported point/let/fault outcomes, maintain scoring and service state, explain its decisions, and recognize when the available evidence is insufficient.

Pull the official sources into the new repo's local rule-source workflow and hand their versioned references to the rules-owning agent. Use **Chapter 2, The Laws of Table Tennis, in the ITTF Statutes** as the primary rules source. Consult the official Handbook for Match Officials and applicable Table Tennis Review (TTR) guidance for interpretation. Start from:

- [ITTF official documents index](https://www.ittf.com/committees/umpires-referees/documents/).
- [ITTF Statutes 2026, effective 1 January 2026](https://documents.ittf.sport/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf), Chapter 2, printed pages 39–45.
- [Handbook for Match Officials, 18th edition, February 2026](https://www.ittf.com/wp-content/uploads/2026/02/HMO-18th-edition-February-2026.pdf), linked from the official index. If retrieval is blocked, record that accurately and continue with the verified Statutes; do not claim the handbook was downloaded or read.
- [Official ITTF explanation of TTR review criteria](https://www.ittf.com/2025/04/13/enhanced-table-tennis-review-system-to-feature-at-ittf-mens-and-womens-world-cup-macao-2025/), which documents a 16 cm minimum toss height and 30° maximum toss angle for that review system.

Check official amendments and effective dates before labeling a ruleset current. An AGM proposition is not proof of adoption or effective law. Pin the exact retrieved edition for the demo instead of changing rules at runtime. Save source files, extracted rule text, retrieval date, source URL, version/effective date, and SHA-256 in a source manifest. Include a reproducible fetch/extract command and local cached operation so the demo does not require live web access.

Demonstrate that understanding in `docs/rules/table-tennis-referee-spec.md`, coordinated with the rules-owning agent. Cover every Chapter 2 section and identify the applicable interpretations, prerequisites, exceptions, and resulting state changes. For each rule, record the evidence needed, how it interacts with other rules, its implementation owner, and whether the system can enforce it automatically, needs player/official input, or does not yet support it. Knowing a rule and being able to observe its trigger are separate requirements; unsupported detection must remain explicit.

Turn that specification into referee scenarios and executable acceptance tests through the owning components. Include normal and exceptional scoring sequences, service/receiving order and corrections, game/match progression, legal and faulty serves, returns, lets versus points, edge/side distinctions, interrupted or incomplete rallies, applicable doubles and accessibility provisions, and conflicting or insufficient observations. Derive expected outcomes and precedence from the pinned official sources. Test whole sequences as well as individual events, including replayed/duplicate observations and corrections, so a single rally cannot accidentally score twice. Do not claim full referee coverage solely because the rulebook has been indexed or an LLM can answer rule questions.

Prioritize implementation of the five demo features while preserving this complete rules inventory. In the status report, distinguish rules understood, rules implemented, rules validated, and rules awaiting observable evidence. Coordinate the referee engine and scoring-state work with the agent that owns rulings; Agent 2's event stream remains measurement-only under the agreed contract.

Create a concise rule-to-measurement map and coordinate its integration with the rules owner:

- Table surface/edge versus vertical side: **2.1.1–2.1.2**.
- Rally/in-play boundaries: **2.5.1–2.5.4**. Keep UI clip padding separate from candidate in-play timestamps.
- Service: **2.6.1–2.6.6**.
- Returns, lets, and point awards: **2.7, 2.9, 2.10**.
- Game scoring and service order: **2.11, 2.13**.

Correct the provisional serve settings: the verified 2026 Laws require a rise of **at least 0.16 m after release**, rather than greater than 0.1524 m. They describe the upward toss as near vertical. The official TTR explanation supplies a **30° maximum toss-angle review criterion**; identify that provenance explicitly in any numerical profile. The earlier statement that the entire hand-to-hit path must remain within 30° is not established by these sources and must not be encoded as official law. Verify the angular measurement convention against applicable official technical guidance. If unavailable, expose the chosen estimator as an implementation convention, not an official definition.

The rules owner should implement a deterministic, tested rule profile from these references and attach rule identifiers, source edition, measurement evidence, and a plain-language explanation to each decision. An LLM may explain a supported decision using retrieved rule passages; it must not invent thresholds or visually adjudicate from illustrative avatars. Keep any recreational house rules in a separately named profile. Missing evidence remains unresolved and must not automatically become an illegal-serve call. Do not claim complete serve legality from height and angle alone.

Agent 2 still emits measurements only. Supply the source map and evidence required by the rules agent, and document the integration handoff in `docs/status/a2.md`.

## 3D visual target

Use [the supplied screenshot](references/table-tennis-wireframe-target.png) as a visual reference: a continuous, anatomically recognizable human surface, dark shaded body, cyan/blue mesh lines, articulated torso/limbs/head/hands/feet, a visible paddle, and a dark scene with a subtle floor grid.

Build on the existing skinned-avatar renderer. Use a suitable rigged mesh with clean surface-grid topology or a UV/shader grid that deforms with skinning. A raw triangle wireframe may not reproduce the reference's orderly grid appearance. Retarget observed poses to the rig; separate display smoothing from raw measurement data. Check arm/shoulder deformation, crouches, feet, and fast swings. Do not require a new body-fitting model or personalized anatomy to achieve the visual style.

Support orbit/zoom, both recording-camera views, slow motion, event freeze frames, and close-ups of the palm/toss or table edge. Overlay measured ball trajectories and, when available, toss-height markers, a vertical reference/angle visualization, and uncertainty. Hide or mark unsupported trajectory segments. Label estimated body/paddle pose, measured ball positions, and synthetic fixtures appropriately. A posed avatar's palm or racket must not supply missing measurement evidence.

Acceptance: both players appear as continuous skinned bodies with stable surface lines and understandable motion, the decisive event can be inspected beside synchronized source footage, and the visual styling does not alter measured ball positions or rule inputs. Document any remaining hand/face detail differences from the reference.

## Execution order

### 1. Create the status file immediately

Create `docs/status/a2.md` first. Record your scope, dependencies, interface handoffs, OPEN-3 status, benchmark results, decisions, commands, blockers, and next steps. Keep it current, with timestamps and clear distinctions between implemented, tested, and planned work.

After creating the status file, start the official-source retrieval, full playing-rule review, referee specification, and rule-map handoff early without delaying the tracker spike or Agent 1's calibration dependency. Record verified sources, blocked downloads, and unverified interpretations separately.

### 2. Run the two-hour ball-tracker spike and decide OPEN-3

Compare a classical tracker against BlurBall on MPS on this Mac, using representative 720p input. Benchmark each camera separately and report the throughput implications of processing both views.

Measure sustained end-to-end processing FPS, model-only timing separately, latency, and recall against a small manually labeled set. State how recall is defined, the localization tolerance, sample size, and false positives. Detection coverage alone is not recall. Include difficult serve, occlusion, and bounce intervals where available.

Use existing approved local assets and additional testing footage under the authorization above. If the user's files are unavailable, label sample-footage results clearly and rerun on their footage when available.

Choose OPEN-3 using the plan's criteria. **If nothing reaches 25 FPS, tell the user immediately and record it in the status file. Vultr use or any spend requires approval.** Continue work that does not depend on that approval.

### 3. Ship `/calibrate` and the `table_tennis` field template early

Agent 1's UI needs them. Implement the agreed contract early and provide a minimal working example. Include the table geometry, coordinate conventions, camera calibration inputs, units, and validation needed for metric ball and serve measurements. Calibration failure must be explicit; do not turn uncalibrated pixels into claimed metric accuracy.

Hand off the usable calibration interface and template before finishing the full tracker. Document required inputs and a working invocation in the status file.

### 4. Build the clip player and synthetic rally

Build the synchronized two-view clip player and an integration fixture with a synthetic rally. Support play/pause, shared seeking, slow motion, point selection, and seeking directly to measurement evidence. Add a close-up of the decisive event and a 3D reconstruction when calibration and tracking support it.

The synthetic fixture must include tosses with known heights and angles, cases on both sides of the configured thresholds, and uncertain/missing observations. Include exact 0.16 m height and configured angle boundary cases, with and without uncertainty spanning a threshold. Test the chosen toss-angle estimator separately from the subsequent falling/hit segment. Keep synthetic truth separate from detector output. Label synthetic content visibly and never present it as measured real footage or evidence of real-world accuracy.

## Measurements needed for the demo

- **Rally scoring:** timestamped ball tracks, candidate table bounces, side/surface identity, candidate contacts where supportable, and terminal-event evidence. Export candidate point start/end times with reasons, uncertainty, source references, and unresolved status when necessary. Ball disappearance alone is insufficient evidence of a particular point outcome.
- **Edge rule:** provide the ball position and uncertainty relative to the tabletop boundary and side surface, plus source frames and close-up evidence. Distinguish supported measurements from ambiguous edge-versus-side cases. The rules component decides the outcome.
- **Serve legality:** emit raw toss rise above release, upward-toss angle/path measurements, release/apex/candidate-hit times, hand/ball observations, calibration/timing uncertainty, and source references for the versioned rule profile described above. Preserve the falling/hit segment separately. Do not assume a wrist landmark proves an open palm or establishes exact release height. Return unavailable or uncertain measurements when the footage cannot support them; unmeasured requirements remain unverified.

Use deterministic, meaningful tests for geometry, timestamp mapping, known synthetic tosses, missing observations, and interface serialization. Validate the real demonstration clips separately against manually reviewed events.

## Observations, permissions, and completion

Mirror every emitted measurement event into **Spacetime observations** through the agreed schema. Preserve IDs, session/camera identity, timestamps, units, uncertainty, provenance, and references using the existing contract. Never send video, frames, or encoded video payloads there. Follow the plan's ownership boundaries for shared state, rulings, score updates, and speech.

The user has authorized finding and using additional permitted testing videos, so do not ask again for each such clip. Ask the user **before using BlurBall weights in the public demo, any spend, or filming anyone**. Prior local/private experiments do not imply permission for public-demo use. Do all independent authorized work while an approval is pending.

Your deliverable is a working, documented measurement and replay path supporting all five required demo features through integration with the other agents, a complete official playing-rule review and referee specification with scenario-based acceptance tests, a versioned official rule-source handoff, a reproducible testing-footage manifest, and the reference-inspired 3D player style. Report implementation, validation, handoffs, limitations, and remaining dependencies in `docs/status/a2.md`.
