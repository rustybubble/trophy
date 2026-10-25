# Agent 3 brief: rules, AI and Droid (continue, 2026-10-24 evening)

*Written by Agent 1 after the repo cleanup. Paste everything below the line into Agent 3's session.*

---

You are **Agent 3 of 3** on Trophy (Cal Hacks 13.0): rules, AI and the Factory Droid. Read `CLAUDE.md` first ("Where things stand", "Safeguards to retain"), then `docs/plan/prompts/agent-3-droid-realtime.md` (your D-36 design brief: it stays the design reference) and the owner reviews on rustybubble/trophy#19. Work in `../trophy-a3` (or your existing worktree) on `demo/integration` until #19 lands, then on short `a3/*` branches.

## What you've built (on #19, not yet on `main`)
- `services/engine`: CEL rule engine, scoring by call-log replay, the gate, calls, ctl commands incl. house-rule hot-load, moments + ★ best play, commentary, `decide()` (Claude ‖ Gemini ‖ Bitdeer, recorded shapes only), 3D checks API, `check-test`, `TrackEventer`/`TrackFeeder`, ask over checks. Engine tests pass (78).
- `services/compiler`: the Factory Droid with a PreToolUse guard hook; live house rule READY in 27.5–30.6 s, gate 19/19, approve → hot-load 0.8 s; `calibrate_checks` job (tested with a scripted agent only).
- `sports/table_tennis/`: golden module (`config.yaml`, `events.py`, `rules.yaml`) and the 7-check library; synthetic 2D and 3D fixtures.
- `services/referee` (D-37): router, Claude phrasing with a numbers guard, rules Q&A grounded in `rules.yaml`, Cartesia server-side voice (measured first audio 174–723 ms).
- The localhost clip-upload demo (`/api/demo/*`, `flight.clip2l1`, `trophy-play --samples`) and `make e2e-synthetic`.

## What's left, in order
1. **Land #19. It is the critical path: until it merges, `main` cannot referee a single point.**
   - Merge `origin/main` into `demo/integration` (main now includes the 2026-10-24 cleanup). Conflicts and how to resolve them:
     - `Makefile`: keep main's OS-detected `PYTHON` block, and add your `e2e-synthetic` target.
     - `Procfile`, `scripts/dev.py`: take the union. Keep main's `watch` (5175) and caddy waits. Add your `engine`, `referee` (8100) and `compiler` lines and waits. Keep main's quoted `PY`, and keep the PORTS line ≤ 120 chars.
     - `package.json` + lockfile: workspaces `apps/dashboard`, `apps/watch` and `services/compiler`. Keep main's `dev` script, then run `npm install` to regenerate the lock.
     - `CLAUDE.md`, `README.md`, `docs/plan/three-agent-plan.md`: **take main's**. They already describe your services (D-36/D-37).
     - `docs/plan/prompts/KICKOFF.md` and `agent-3-rules-ai-droid.md` were deleted on main: keep them deleted, and **don't re-add `docs/archive/`** (git history has it). Keep `agent-3-droid-realtime.md`.
     - `docs/plan/simplified-architecture.md` is an unadopted proposal that contradicts what shipped (Watch, Gemini/Bitdeer stay). Delete it, or keep only what you adopt as a decision.
   - **Fix the blockers from the owner review** (each one is verified in source; add a test for each):
     1. Droid command allowlist bypass: `TEST_CMD` in `services/compiler/src/allowlist.ts` lets `\s` match a newline and doesn't deny `>`/`<`; the gate script forwards `"$@"`.
     2. `events.py` sandbox: drop `typing`/`collections`/`dataclasses`/`enum` escape hatches or prove they're safe; run Droid-written code in a subprocess with a clean env and no network. Move `DROID_RUNS_DIR` out of the repo tree.
     3. Wrap the `upsert_moment` / `set_best_play` calls so a Spacetime error can't leave a rally open.
     4. Trailing bounces score phantom points: `RALLY_OPENERS` includes `bounce`. Serve, B bounce and three floor bounces must give 1–0, not 2–1.
     5. One malformed event kills the engine: parse per entry inside the try in `EventConsumer.read()` / `loop.py`; ack and log bad entries.
     6. House-rule approval bypass: ignore `pack_path` from args, load the **gated commit** (don't strip `@commit`), and require status `ready`.
     - Add a test that replays a rally with trailing events through `loop.run` against fake Redis.
   - Renumber the stale decision references: `services/referee/pyproject.toml:4` → D-36/D-37; `services/compiler/README.md:30` → D-35; `docs/status/a3.md` → D-33.
   - Get CI green on all three jobs, then ping Agent 1 on the PR. Agent 1 reviews and merges.
2. **Engine handlers for the referee** (interfaces-v1 §20): `run_check` (resolve `t_game_s` or `ref: last | last_rally | call:<id>`, run the session check, XADD `CheckResult` to `reply_to`, `error: no_such_check`), `request_check` (open a `new_check` `droid_run`, reply on gate pass or failure), and pass `speech, kind, check, p, calibrated, by_cam_id` through `_ctl_ask_logged`.
3. **Feed the engine from live flight.** Agree with Agent 2 on the seam in `docs/status/a{2,3}.md` before either of you builds it. The one-phone path is layer-1 samples → `sports/table_tennis/events.py` → `ev:flight`; the two-phone path is `trk:ball3d` → `TrackFeeder`. The MUST is the one-phone path.
4. **Live keys (ask the user for them; never commit them):**
   - `ANTHROPIC_API_KEY`: referee routing/phrasing, commentary, the Claude voter. Measure the phrase latency (budget 0.5–1.5 s).
   - `GEMINI_API_KEY` + `GEMINI_MODEL`, `BITDEER_API_KEY`: **Gemini and Bitdeer are still prize tracks**, so they stay as voters. Run `--votes` on a real BETA call, and confirm all three votes land within 4 s and never delay the spoken call.
   - `FACTORY_API_KEY`: time a live `calibrate_checks` run against the 60 s target / 90 s cap.
5. **Portability:** compiler `ENGINE_PYTHON` defaults to `.venv/bin/python` and the guard hook runs `python3`. Make both work on Windows too, or skip with a printed reason rather than silently.
6. **C3 (with Agents 1 and 2):** the Droid rule end to end < 90 s on the live game; 3 votes shown; voice ask → spoken answer starts ≤ 3 s after the question ends. Record the measured numbers in `docs/progress.md`.
7. **README sections** (in the root `README.md`, honest and short): Factory Droid (trigger, sandbox, guard hook, gate, approval, measured times), Anthropic (community, how Claude is used, "where it could go wrong": Claude never makes a line call alone, uncalibrated votes, grounded answers only), Bitdeer and Gemini (each one's role as a voter, with an on-screen vote).

## Rules
- No keyless or stub fallbacks that pretend to be a model (D-33/D-34). A template line is labelled `template`.
- Everything synthetic is labelled SYNTHETIC. Accuracy comes only from labelled real footage.
- Decision numbers: D-33..D-37 are yours on #19; the next free number is D-38. Check `docs/decisions.md` before adding one.
- Keep `docs/status/a3.md` current: what's built, measured numbers, requests to Agents 1/2, and what you didn't run.
