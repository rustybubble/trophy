# Agent 1 brief: platform, capture, voice, replay and integration (continue, 2026-10-24 evening)

*Written after the repo cleanup. Paste everything below the line into Agent 1's session.*

---

You are **Agent 1 of 3** on Trophy (Cal Hacks 13.0), and the **integration owner**: you review and merge, run the checkpoints and assemble the submission. Read `CLAUDE.md` first ("Where things stand", "Safeguards to retain"), then `docs/status/a1.md`. Work in `../trophy-a1` on short `a1/*` branches.

**You're on the Windows PC; Agent 2 has the M5 Pro Mac**, which is the demo machine. Agent 2 brings the stack up there (`docs/plan/prompts/mac-bringup.md`) and runs every live check on it. Anything you need verified on the Mac (a test that fails only there, a timing, a phone run against the demo stack), ask for in `docs/status/a2.md`. Give Agent 2 exact commands and what to report back.

## What you've built (all on `main`)
- **Foundations:** C0 contracts, codegen, py-trophy, state client (tag `wk-c0`); the Spacetime module with identity-checked writers.
- **Gateway:** games, cam tokens, frames + clock WS, ctl, calibrate stub, Cartesia token, ask proxy, replay/Watch APIs.
- **Apps:**
  - the capture PWA, measured on an iPhone at 29.9 fps received, plus phone-recorded challenge clips and the table crop;
  - the judges' dashboard;
  - Trophy Watch.
- **Run and test:** `make dev` on macOS and Windows; `make e2e` (transport: 30.0 fps, replay OK, calls PENDING).
- **Hosting:** `trophy.photo` over HTTPS through Caddy + Porkbun DNS-01 (on the Windows PC so far).
- **Contract and docs:** the ITTF serve contract (D-31); the Mac bring-up prompt.

## What's left, in order
1. **Land the cleanup PR** (`a1/cleanup`) if it isn't merged yet. Then tell Agents 2 and 3 to read their new briefs.
2. **Review and merge rustybubble/trophy#19** once Agent 3 has merged main into it, fixed the six review blockers and turned CI green.
   - Re-check the blockers yourself: the allowlist regex, the sandbox, trailing bounces, malformed events and the approval path.
   - Check that the dashboard reads the rows #19 writes.
   - Check that `Procfile`/`scripts/dev.py` start `engine`, `referee` and `compiler`. Check it on the PC yourself, and ask Agent 2 to confirm it on the Mac.
   - **Then add the calls hop to `make e2e`**: the CC BY clip should produce calls once flight is live (Agent 2), and Agent 3's synthetic checks stay as `make e2e-synthetic`.
3. **Support Agent 2's Mac bring-up** (`mac-bringup.md`; Agent 2 runs it):
   - Answer its questions on Caddy, Porkbun, `.env` and the Spacetime tokens.
   - The user copies the PC's `.env` to the Mac securely, or fills it in there. Never paste secrets into status files or chat.
   - Once DNS points `trophy.photo` at the Mac (the user's OK first), the PC's Caddy no longer serves phones. Develop against `http://127.0.0.1` on the PC.
4. **Finish C1** on the demo stack, with Agent 2 running the Mac side:
   - a 15-minute iPhone stream at ≥ 25 fps;
   - real Safari as well as WebKit-in-Firefox;
   - onsets arriving and a spoken line.

   You own the method and the write-up in `docs/progress.md`.
5. **Platform requests from #19:**
   - Add `ask` table columns `speech, kind, check, p, calibrated` (today they ride in `json`); regenerate the bindings.
   - Make the PWA's late-answer matching use an ask id instead of question text + time.
   - Fix `services/gateway/tests/test_gateway.py::test_frames_ws_writes_bus_and_still`, which fails only on the Mac (3 rows instead of 4). Ask Agent 2 to run it there with `-vv` and send you the output, then confirm your fix on the Mac the same way.
6. **C3 (live on the Mac, run by Agent 2, with Agent 3)**. You define the measurements and collect them in `docs/progress.md`:
   - the call spoken ≤ 1.5 s after the rally ends (p50);
   - challenge → replay ≤ 4 s;
   - three votes shown and never delaying a call;
   - the Droid rule end to end < 90 s;
   - voice ask → answer starts ≤ 3 s.

   Agent 2 owns the rally, edge and serve accuracy runs.
7. **C3b:** Trophy Watch on the live ping-pong game: recap, moments, highlights ending on ★ Play of the game, condensed, replay with overlays, stats, and moment search with 5 prepared queries.
8. **C4, the submission:**
   - feature freeze;
   - three full rehearsals;
   - the **2-minute demo-first video** (Cartesia's format: one complete flow first, then the problem and how it's built);
   - the root `README.md`: setup, plus the Cartesia (features used + known limits), Spacetime and Meta sections, and Agent 3's Factory/Anthropic/Bitdeer/Gemini sections;
   - the Devpost writeup listing each track with its evidence, and real player quotes (OPEN-8; never invented).
   - Ask the user whether `trophy.photo` (Porkbun) qualifies for the MLH GoDaddy Registry/.Tech prize. Registering another domain is the user's purchase.
9. **Repo hygiene:** keep `CLAUDE.md` → "Where things stand" current as PRs land. If the stale remote branches still exist, give the user the cleanup command from the cleanup PR. Delete merged branches after each merge.

## Rules
- You merge `packages/*`, `spacetime/`, root build/CI and `.env.example` changes; agents merge their own green PRs in their own directories.
- Ask the user before DNS changes, cloud resources, downloads of third-party media, filming people, or anything that costs money.
- Write only measured numbers, with device and method. Label synthetic data.
- Keep `docs/status/a1.md` current: done, measured, blockers, and what you didn't run.
