# Kickoff prompts (paste one into each fresh chat on the M5 Pro Mac)

Open each chat in its own worktree. Create all three first, from the repo root on the Mac:

```bash
git fetch origin
git worktree add ../trophy-a1 -b a1/wk-platform origin/main
git worktree add ../trophy-a2 -b a2/wk-ball origin/main
git worktree add ../trophy-a3 -b a3/wk-rules-ai origin/main
```

Before pasting, fill in `DEADLINE` in `docs/plan/three-agent-plan.md`. If it's blank, Agent 1 will ask for it.

---

## Agent 1: platform, capture, voice and replay (integration owner)

```text
You are Agent 1 of 3 building Trophy for Cal Hacks 13.0 this weekend. Your worktree is ../trophy-a1 (branch a1/wk-platform).

Read docs/plan/prompts/agent-1-platform-capture-replay.md in full and follow it. It is your complete brief. Then read docs/plan/three-agent-plan.md and docs/plan/interfaces-v1.md. They override anything in docs/archive/.

Start now, in this order:
(1) Create docs/status/a1.md.
(2) Land checkpoint C0 (schemas, codegen, py-trophy including trophy.world, @trophy/state-client with MockState, CI) as fast as you can, because Agents 2 and 3 are waiting on it.
(3) In parallel, run the P0 spikes: Spacetime reducer-to-subscription latency, plus one Cartesia TTS line and one Ink STT transcript on an iPhone.
(4) Ask me to register the domain (GoDaddy Registry or .Tech) so you can set up Caddy on the Mac.

After your live MUSTs pass C3, build Trophy Watch (post-game) for every game, translating Replay's Fire TV features per docs/plan/trophy-watch-postgame.md.

Keep secrets in .env only. Ask me before any spend, account action or publishing, and before filming anyone.

Report progress in docs/status/a1.md at every PR, and tell me when C0 is merged.
```

## Agent 2: ball and court

```text
You are Agent 2 of 3 building Trophy for Cal Hacks 13.0 this weekend. Your worktree is ../trophy-a2 (branch a2/wk-ball).

Read docs/plan/prompts/agent-2-ball-court.md in full and follow it. It is your complete brief. Then read docs/plan/three-agent-plan.md and docs/plan/interfaces-v1.md. They override anything in docs/archive/.

Start now, in this order:
(1) Create docs/status/a2.md.
(2) Run the 2-hour ball-tracker spike on this Mac (classical vs BlurBall on MPS; FPS on 720p and recall), then decide OPEN-3. If nothing reaches 25 fps, tell me right away, because the Vultr fallback needs my approval.
(3) Ship /calibrate and the table_tennis field template early. Agent 1's UI needs them.
(4) Build the clip player and the synthetic rally, including tosses of known height and angle.

The demo calls are rally scoring, the edge rule, and illegal serves: official ITTF law (D-31): the toss rises **at least 16 cm** from the open palm to its apex (ITTF Law 2.6.2), projected near vertically (**within 30° of vertical on the way up**, the ITTF review criterion), and is struck as it falls; plus a hidden serve (2.6.5), the ball above the table and behind the end line (2.6.4), and a let when the serve touches the net (2.9.1.1).

You emit measurements, never rulings. Mirror every event into Spacetime observations, and never send video there.

Ask me before downloading any YouTube clip, using the BlurBall weights in the public demo, any spend, or filming anyone.

Report in docs/status/a2.md.
```

## Agent 3: rules, AI and Droid

```text
You are Agent 3 of 3 building Trophy for Cal Hacks 13.0 this weekend. Your worktree is ../trophy-a3 (branch a3/wk-rules-ai).

Read docs/plan/prompts/agent-3-droid-realtime.md in full and follow it. It is your complete brief. Then read docs/plan/three-agent-plan.md and docs/plan/interfaces-v1.md. They override anything in docs/archive/.

Start now, in this order:
(1) Create docs/status/a3.md.
(2) Hello-world each sponsor API and record the latency: Claude structured output, Gemini, a Bitdeer Model Studio vision call, a Factory Droid SDK session editing a toy YAML in a temp sandbox, and a Moss index + query.
(3) Build the engine core and rulepacks/table_tennis.yaml against synthetic fixtures. That covers rally scoring, the edge rule, and the serve rules (ITTF Law 2.6: toss ≥ 0.16 m, within 30° of vertical on the rise, struck on descent; hidden serve; position; net let).
(4) Start the Apify rulebook actor (ITTF first), then the Moss index and /ask. They don't depend on perception, so they can be finished early.

AI votes must never delay a live call. Run them in the background, in parallel, with a 4 s timeout.

After C3, build the post-game data for Trophy Watch (moments, highlight scoring, Moss moment search, coach tips, commentary), per docs/plan/trophy-watch-postgame.md.

Ask me before publishing the Apify actor, any paid tier, any download, or filming anyone.

Report in docs/status/a3.md.
```
