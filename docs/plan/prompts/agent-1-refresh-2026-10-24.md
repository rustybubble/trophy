# Agent 1 refresh prompt (2026-10-24 evening)

*Paste the block below into Agent 1's chat. It reflects the repo as of `origin/main` `28064f5` and the open PRs #6, #8–#12.*

```text
New direction from the user. Stop the colour-tracker work: we are NOT building a fallback tracker. BlurBall is the ball tracker, and it runs on a Vultr cloud GPU (so it works anywhere) and on the Mac (MPS). It does not run on the Windows PC. You go back to your original role: Agent 1 = platform, capture, voice, replay, and integration owner (docs/plan/prompts/agent-1-platform-capture-replay.md). Agent 2 owns the ball tracker again.

Repo state you're starting from:
- origin/main is 28064f5 (PR #7 merged).
- Your PR #9 (a1/tt-tracker) is open.
- Your ../trophy-a1 worktree has UNCOMMITTED work: the PWA table crop (apps/pwa/src/lib/crop.ts + LiveView/CalibrateView/streamer/frame), the FrameReader buffering fix, gateway changes, Procfile + scripts/dev.py, tools/tt_sweep.py, tools/tt_label.py, labels.
- Agent 2 (mudu1735) opened PRs in YOUR areas, waiting on you: #10 (Spacetime reducers/tables + ctl types that unblock PR #6), #11 (recorder + authenticated replay APIs), #12 (live evaluation + re-record labelling kit).
- Agent 3 has two overlapping PRs: #6 (changes requested; review at https://github.com/rustybubble/trophy/pull/6) and #8 (rulebook capability from a second session).

Do this, in order:

1) Save and split your work.
   a) Commit everything in ../trophy-a1 now.
   b) Then split: move the PLATFORM pieces into a new branch a1/platform-fixes off origin/main and open a PR. That covers the PWA table crop (keep it: sending a calibrated table crop at 1280x720 gives BlurBall 2–3x more ball pixels), the FrameReader buffering fix + test, the gateway changes, the clip_as_phone libjpeg q70 change, Procfile + scripts/dev.py (`make dev` that restarts everything with one command) and the flight lint/test CI step.
   c) Convert PR #9 to draft and retitle it "Colour tracker (superseded by BlurBall, D-30): reference only", noting in the PR that Agent 2 may reuse its event logic, track gating and review page. Don't delete it.
   d) Stop tt_sweep / threshold work.

2) Integration-owner reviews (you own these directories, so review as the owner; ask me before merging anything that touches secrets or infra).
   - #10 first, since it unblocks PR #6: check the reducers match interfaces-v1 §11/§19 and D-25, the identity checks, and that `make contracts` is clean. Merge when green.
   - Then #11: recorder HLS/sprite and the replay /clip, /overlay, /frames routes. Check the replay token auth and that footage stays in data/local.
   - Then #12.
   - Tell Agent 3 (via PR comment) to consolidate #8 into #6, or to say which one supersedes the other: they both add services/rules and the Apify actor. Don't merge either until #6's blockers are fixed.

3) Contracts for the official serve law (the user chose the official ITTF rulebook). Update the Event/serve contract and interfaces-v1, then regenerate types. Record the change as D-31:
   - Law 2.6.2: the ball is projected near-vertically upwards from the open palm, without spin, and rises at least 16 cm (0.16 m, NOT 6 in) after leaving the palm, then falls without touching anything before it's struck. So:
     - `serve_toss` carries `height_m` (palm release → apex) and `angle_from_vertical_rad` measured on the UPWARD toss (release → apex). The 2026 near-vertical definition is 30°, from an unconfirmed report; Agent 2 says it verified the source, so confirm it.
     - It also carries `struck_on_descent` (bool/p), `release` and `apex` intervals with σ, `evidence_missing[]` and `estimator: {name, version}`.
     - Replace the old max(rise, fall) definition. This is Agent 2's earlier request.
   - Add events for the other serve faults the re-recordings show:
     - `serve_hidden`: Law 2.6.5, the ball hidden from the receiver by the server's body, clothing or free arm, from release until struck. Payload: visible fraction from the receiver's side, occluder, which cameras.
     - `serve_position`: Law 2.6.4, the ball must be above the playing surface and behind the end line from the start of service until struck.
     - A let on serve, Law 2.9.1.1: the served ball touches the net assembly and then otherwise lands correctly. Use the existing `net` event with kind `touch` + a `serve` flag.
   - Rule-pack parameters: `toss_min_height_m: 0.16`, `toss_max_from_vertical_rad: 0.5236`, `toss_angle_segment: rise`. The old house values (6 in / hand-to-hit) become an optional `house` variant.

4) Deployment so it works anywhere (D-30). You own infra/, Agent 2 owns the BlurBall container.
   - Bring up ONE Vultr Cloud GPU instance (NVIDIA, CUDA 12, Ubuntu) running the live backend with docker compose: Redis, SpacetimeDB + our module, gateway, recorder, engine, rules, compiler, and Agent 2's flight (BlurBall on CUDA).
   - Fix docker-compose.yml + the Dockerfiles for that (GPU reservation for flight only). Run Caddy on the box with the existing trophy.photo Porkbun DNS-01 setup, and point the A record at the box's public IP. Open only TCP 80/443 (+ UDP only if we add WebRTC). Use SSH key auth.
   - Secrets: put an env file on the box only, never in images or git. The BlurBall weights go on a volume, not in an image or registry: their license is unstated, and the user accepts using them but we don't redistribute them.
   - BEFORE creating anything: pick the smallest Vultr NVIDIA GPU plan that runs BlurBall at ≥ 30 fps per camera (it's a 1.5M-param model), and post the plan name + hourly price to me for an OK. Stop or destroy it when idle.
   - Keep the Mac path: `make dev` runs the same services natively, with flight on MPS.
   - The Windows PC stays a dev machine/browser only. Remove D-26's "demo machine = Windows PC" and record D-30.

5) Then your original backlog:
   - the iPhone 15-min C1 run against the Vultr origin (fps, sync error, capture→Redis latency over 5G and Wi-Fi);
   - challenge clips on the iPhone;
   - the dashboard (score, call feed, AI-votes panel, Droid panel, ask-the-ref transcript, live world-state view);
   - `make e2e` (C2) using the CC BY ping-pong clip;
   - then Trophy Watch (docs/plan/trophy-watch-postgame.md).

Data:
- The user's new ping-pong re-recordings (several angles; 30°, < 16 cm/6 in, bad serves, hidden serves, lets, etc.) are in a Georgia Tech SharePoint folder that needs a sign-in; the planning session couldn't fetch it. Ask the user to put them in data/local/ttClips/rerecord/ (on the Mac and on the Vultr box) and confirm that everyone in them consented.
- The CC BY clips for the other sports are fetched by tools/fetch_clips.py into data/local/clips/ (credits in data/clips/credits.json). Re-run it on the Mac and the Vultr box.

Update docs/status/a1.md and docs/decisions.md as you go. Ask me before any spend, DNS change or publishing.
```
