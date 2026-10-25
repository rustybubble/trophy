# Agent 2 brief: ball and court (continue, 2026-10-24 evening)

*Written by Agent 1 after the repo cleanup. Paste everything below the line into Agent 2's session.*

---

You are **Agent 2 of 3** on Trophy (Cal Hacks 13.0): ball and court. Read `CLAUDE.md` first ("Where things stand", "Safeguards to retain", "Gotchas"), then `docs/demo-setup.md`, interfaces-v1 §5–§8 (frame bus, calibration, events, observations) and §11. **The live ball tracker is the biggest gap in the product:** nothing on any branch turns a live phone stream into calls yet. Work in `../trophy-a2` on short `a2/*` branches. The demo machine is the M5 Pro Mac (D-30).

## What exists
- **Yours, merged:** Spacetime post-game/Droid reducers (#10), recorder + authenticated replay/Watch APIs (#11), the live evaluation + re-record kit `tools/eval_live.py` and `docs/demo-setup.md` (#12).
- **Flight on rustybubble/trophy#19** (`demo/integration`, written by Agent 3, not yet on main): `services/flight`, CPU only.
  - Pipeline: classical MOG2 + colour detector, gated tracker, four-corner calibration → PnP, two-camera DLT lift with covariance, bounce/contact/dead/serve-toss events, and `clip2l1` (one phone, 2D, homography).
  - Measured on **synthetic** renders only: 3D median 2.6 cm; bounces 7/7.
  - Gap: it can't see a ball at rest, so `serve_toss.release_observed` is false.
- **Closed rustybubble/trophy#9** (the colour tracker, D-28): `flight.live`, a measured live loop that reads `frames:{cam}` and writes `ev:flight`, Spacetime `observation`/`track_sample` and `trk:ball:{cam}`. It ran at 29.8 fps on the side clip streamed as a phone. It also has the rally logic, track gating, a review page and hand labels (`evals/labels/ttclips-*.json`). Fetch it with `git fetch origin pull/9/head:pr-9`, and reuse what helps.
- **The archived two-camera demo:** tag `archive/tt-demo-failure-status` if the user ran the cleanup command, otherwise branch `codex/tt-demo-failure-status`. Its failure report lists the traps to avoid.
- **Real footage:** two handheld 4K60 clips in `data/local/ttClips/` on the Windows PC (orange ball). Handheld footage breaks a one-time calibration, so it's useful for detector tuning, not for calibration.

## What's left, in order
1. **Start from #19's flight.** Branch from `origin/demo/integration` now, and rebase onto `main` once #19 lands (Agent 3 is landing it). Don't fork a second flight package.
2. **BlurBall on MPS (D-30, OPEN-3 decided).**
   - Patch the `cuda` assert, fix BGR→RGB, dedupe by `seq`, and pin numpy < 2, OpenCV 4.10 and torch < 2.6 (`CLAUDE.md` Gotchas).
   - **Measure fps at 1280×720 on the Mac** and log the device actually used. Record the number in `docs/progress.md` (Spikes line).
   - Weights stay in an ignored local path and are never committed or redistributed. Add the license note to `docs/licenses.md`.
   - Plug it in as a candidate source next to the classical detector. Keep classical as the floor until BlurBall is measured better on phone-path frames.
3. **The live flight loop (the MUST, one phone).** `python -m flight.live --game <id|next>`:
   - Read `frames:{cam}` with `trophy.framebus.FrameReader`, honouring the `crop` field (D-29), and calibrate from the PWA's four taps (`calib:{cam}`; the gateway stub is untrusted, so calls cap at BETA until a trusted calibration exists).
   - Track, then emit events (bounce with edge/side probabilities, contact, net, dead ball, `serve_toss` per D-31: height from palm release to apex, angle on the rise, `struck_on_descent`, σ, `evidence_missing`).
   - Publish them on `ev:flight` and to Spacetime via `trophy.world.ObservationWriter` / `TrackSampleWriter` (vision token).
   - **Agree the seam with Agent 3 first**, in `docs/status/a{2,3}.md`: either flight runs `sports/table_tennis/events.py` on its layer-1 samples, or it writes samples the engine consumes.
   - Add the `flight:` line to the `Procfile` and `scripts/dev.py` (waits on 6379, 3000, 8000).
   - Target: ≥ 25 fps per camera, and bounce → event on Redis well inside the 1.5 s call budget.
4. **Two phones / 3D (D-36), only once the one-phone path works live:** a second phone, clock-aligned through the gateway fit, writing `trk:ball3d` for the engine's `TrackFeeder` and the Droid's `calibrate_checks`.
5. **Real labelled footage (C3).** With the user, and with consent from everyone filmed:
   - Follow `docs/demo-setup.md`: fixed side mount at the net line, **white ball**, a 16 cm marker.
   - Record ≥ 20 rallies, ≥ 10 staged edge hits and ≥ 12 staged serves (4 legal, 4 tossed < 16 cm, 4 tossed > 30° off vertical).
   - Label them, then score with `tools/eval_live.py`: n, correct and a Wilson CI per call type, written to `docs/progress.md` → "Measured accuracy".
   - Footage stays in `data/local/`.
6. **Backup demo:** the CC BY club match segment (`make e2e`, `data/local/clips/table_tennis/7maQFqJ3XQ0.mp4`) should produce real calls through flight → engine. That flips C2's "calls PENDING" to a measured result.

## Rules
- Perception emits measurements with σ; only rule packs decide (D-18). Never fake a 3D position from one handheld camera.
- Report accuracy only from labelled real footage; synthetic results are labelled SYNTHETIC.
- Ask the user before downloading media or weights, filming people, or spending money.
- Keep `docs/status/a2.md` current: built, measured (device, fps, n), requests to Agents 1/3, and what you didn't run.
