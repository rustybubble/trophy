# Agent 3 brief: the Factory Droid writes this calibration's geometry checks; the engine runs them live

*Status: adopted 2026-10-24 (D-36). Replaces `agent-3-rules-ai-droid.md` and `agent-3-part-2-rulebook.md` (now in `docs/archive/`). PRs #6 and #8 are closed; their branches `a3/wk-rules-droid` and `claude/distracted-davinci-69e418` are kept for salvage (map in §8). Work on `a3/droid-realtime`.*

## 1. The idea in one paragraph

Perception produces a **3D map**: the ball's position over time plus the field (table, net, lines) in one metric frame, fused from two phones running **BlurBall**. The **Factory Droid** does not look at that stream live. It runs **once per setup, at calibration time**, for about a minute, with this setup's calibration and a warm-up recording in its sandbox, and writes a small library of **check scripts** specialised to this calibration: "was the ball out at *t*", "which side did it bounce on", "serve toss height and angle", "did it clip the edge", "where does a rally start and end". Each script is tested against fixtures before it is accepted. From then on the **engine** runs those scripts in milliseconds on every event and every question, Claude phrases the answer, Cartesia speaks it, and the conversation is stored with the game. The scripts belong to the session and are discarded with it; a handwritten golden library is what persists in the repo.

Why the Droid is not in the hot path: a Droid run is a full agent session. Measured on this project (2026-10-24, `claude-sonnet-5`, effort low): the smallest job took **30.6 s**, a module derivation **69.2 s**, and the runner caps a run at 90 s. A spoken call must land in about 1.5 s. So the Droid writes the code; it never answers a call.

## 2. Input: the 3D map (provisional, be flexible)

Details are not final. Build the checks against a **thin adapter** so the shape below can change without touching the checks. Required fields are marked; everything else is optional and may arrive later.

**`field` (once per calibration):**
```json
{
  "sport": "table_tennis",
  "frame": "field",                         // metric, right-handed; origin = table centre on the surface, x along the table length, y across, z up
  "surface_z_m": 0.0,
  "table": {"length_m": 2.74, "width_m": 1.525, "height_m": 0.76},
  "net": {"x_m": 0.0, "height_m": 0.1525, "overhang_m": 0.1525},
  "corners_m": [[-1.37,-0.7625,0],[1.37,-0.7625,0],[1.37,0.7625,0],[-1.37,0.7625,0]],   // required
  "sides": {"A": "x<0", "B": "x>0"},
  "cameras": [{"cam_id": "c1", "P": [[...3x4...]], "reproj_err_px": 1.8}],              // optional
  "time": {"sync_method": "clap", "skew_sigma_s": 0.008}                                  // optional, used for σ
}
```

**`track3d` (stream, one record per fused ball sample):**
```json
{"t_s": 12.3456,                 // required, field clock (the gateway's clock WS)
 "xyz_m": [0.42, -0.11, 0.21],  // required
 "cov_m2": [[...3x3...]],       // optional; else "sigma_m": 0.03 ; else the adapter assumes a default per calibration
 "conf": 0.91,                  // required (normalised; BlurBall's raw `score` is a blob sum and must be divided by max(hm))
 "n_views": 2,                  // optional: 2 = triangulated, 1 = single-view on the surface plane (homography), 0 = interpolated
 "views": [{"cam_id": "c1", "frame": 3310, "xy_px": [812, 411], "L_px": 9.5, "theta_deg": -31.0, "vis": 1}]   // optional provenance, BlurBall's own columns
}
```
BlurBall's own per-frame output, which fusion consumes, is `Frame, X, Y, Visibility, L, Theta` per camera (pixels in the original resolution, `L` = blur half-length in heatmap pixels ×2.5 at 1280 wide, `Theta` in degrees, unsigned direction; see `docs/research/build-cards-flight-family.md` §1, verified at commit `2f0f549`). Fusion into `track3d` is perception's work, not this brief's; this brief consumes it.

**Rules for consumers:** never use a sample without σ in an AUTO call (treat missing σ as the calibration default, and report `calibrated: false`); carry σ into every `p`; treat `n_views: 0` samples as hints only.

## 3. Round detection: when play starts and stops

There is no external indicator. The signals that exist in the 3D map, in order of reliability:

| Signal | What it looks like in `track3d` | Used for |
|---|---|---|
| **Ball dead** | no sample with `conf ≥ c` for `gap_s` (default 1.5 s), or `|v| < 0.3 m/s` for 1 s, or a floor bounce (z crossing below the surface outside the table) | rally end, between-points state |
| **Serve toss** | ball near-stationary above an end of the table, then rising with `v_z > 1 m/s` with no prior contact; the serve check then measures the toss height and the hand-to-hit angle | rally start, server side, serve legality |
| **Contact** | reversal of `v_x` away from the table surface | shots, last hitter |
| **Bounce** | local minimum of z at the surface; side from the sign of x | scoring |
| **Judge voice** | "point", "let", "replay", "start game" through Ink STT | manual override, always wins |

The engine already has the rally state machine (serve → rally → point, at-fault side, score replay from the call log) and `ball_dead`/bounce/contact/net detection in the golden `sports/table_tennis/events.py` on the closed branch. Port both to the 3D input and add a `phases` check that emits `rally_start` / `rally_end` / `between_points` / `timeout` with timestamps and a confidence. It is one of the checks the Droid specialises (gap thresholds, the serve-zone box and the floor plane depend on the calibration). Label the phase detector's accuracy from the warm-up recording and the labelled rallies at C3; until then its calls are BETA.

## 4. The Droid at calibration time

**Trigger:** the judge finishes camera setup (corners tapped, clap sync done, a warm-up recording captured). The gateway writes a `droid_run` row of kind `calibrate_checks`; the compiler picks it up as the house-rule watcher does today.

**Sandbox contents** (fresh git repo per run, nothing else): `field.json`, the warm-up `track3d.jsonl` with its labels, the **golden check library** (`checks/*.py`, handwritten, read-only reference), the synthetic fixtures generated for this calibration, `TASK.md`, and `./check_test` (the gate). No repo, no `.env`, no network. The existing PreToolUse hook, allowlist, git audit, 90 s timeout and approval path carry over unchanged.

**Job:** copy the golden library into `session/checks/` and **edit** it to this calibration: set the table and net geometry, the camera σ model, the surface plane, the serve-zone boxes, the dead-ball gap, the edge band; add nothing the task did not ask for. Editing a reference is what measured 30 to 70 s; writing from scratch timed out (`docs/status/a3.md` on the closed branch). Budget: 60 s target, 90 s cap. If the run fails, the session uses the golden library unedited with `calibrated: false` on every check, and says so on the judge view.

**Gate (`check_test`):** (a) every check loads under the import allowlist and is deterministic; (b) synthetic tracks generated **from this calibration's geometry** (the closed branch's `trophy_engine.synth.generate`, ported to 3D) with known truth: in/out at 1 cm to 20 cm margins, edge hits, net clips, legal and illegal serves; (c) the **warm-up protocol**: the judge drops the ball on each corner and the net line, and serves three times, confirming each by voice; those become labelled fixtures. The gate prints before/after tables and writes them to the `droid_run` row, which the judge view shows next to the plan and the diff. Approve applies the checks to the session.

**Lifecycle:** `data/local/sessions/<session_id>/checks/` lives as long as the session. New calibration, new run. House rules still go through the Droid, but as edits to the session's `rules.yaml`, as before.

**What this gives the Factory track:** a Droid that reads a real calibration, writes and tests geometry code under a scoped sandbox with visible plan, diff, test table and blocked calls, every setup, with a human approval step. Measured numbers go in `docs/progress.md`.

## 5. Play time: the hot path

```
track3d ─▶ engine: phases + events (ms) ─▶ rule pack (CEL) ─▶ call {tier, p, evidence}
                                                               ├─▶ Spacetime ─▶ phones (banner, Cartesia line)
                                                               └─▶ transcript row (what was called, why, which check, inputs)
judge voice question ─▶ Ink STT ─▶ router ─▶ matching check(s) over the stored track ─▶ Claude phrases ─▶ Cartesia
                                        └─▶ no matching check: "give me a moment", Droid writes one (30–60 s), gate, answer, keep it for the session
```
Budget for a cached check (estimates unless marked): fusion + check under 50 ms; Claude phrasing 0.5 to 1.5 s; Cartesia first audio chunk 112 ms (**measured** on an iPhone); engine event → call 2.4 ms p50 (**measured**, memory state). Total about 1 to 2 s.

The transcript (question, answer, check name, inputs, p, σ) is a Spacetime table so the judge can keep talking about a call and the post-game view can replay the reasoning. Claude never computes geometry; it only phrases a check's result and may refuse to answer when no check covers the question.

## 6. Table tennis check library v1 (golden, handwritten first)

| Check | Returns | Tier ceiling |
|---|---|---|
| `bounce_side(t)` | side, p, d_to_line_m, σ | AUTO |
| `in_out(t)` | in / out / edge, p, which line, margin_m | AUTO; edge → BETA |
| `edge_hit(t)` | top_edge / side_face / miss, p | BETA (+ AI second opinion on challenge) |
| `net_touch(t0, t1)` | yes / no, p, x at the net plane | BETA |
| `serve_toss(rally)` | toss height_m, angle_deg from vertical, legal, p | AUTO when σ allows; else BETA |
| `double_bounce(rally)` | yes / no, p | AUTO |
| `phases(window)` | rally_start / rally_end / between_points, t, p | BETA until labelled |
| `rally_summary(rally)` | shots, longest, speed_max, bounce map | informational |

Each check is a pure function `check(track, field, params, **q) -> {"verdict", "p", "evidence", "calibrated"}` over the session's `track3d` buffer, stdlib + numpy only, under the loader's import allowlist.

## 7. Staging

1. **Golden library + adapter + gate** on synthetic 3D tracks (no Droid, no keys). Done when all v1 checks pass `check_test` on synthetic truth and the engine scores a synthetic game from them.
2. **Droid calibrate_checks run** end to end on this Mac with `FACTORY_API_KEY`: sandbox → edited checks → gate → approve → engine hot-load. Measure wall time, attempts, gate table. Done when a second calibration (different corners) produces different, passing checks.
3. **Phases + voice transcript**: router, Claude phrasing, Cartesia line, Spacetime transcript table, the "give me a moment" fallback. Done when a judge can ask "was that out?" on a recorded 3D track and hear the answer with its margin.
4. **Real 3D input** from perception's fusion as soon as it exists; label the warm-up protocol and report accuracy per check. Everything before this is on synthetic or recorded data and is labelled as such.

## 8. Salvage from the closed branch (`a3/wk-rules-droid`, worktree `../trophy-a3`)

| Keep | Where | Change |
|---|---|---|
| compiler: sandbox, `hooks/guard.py`, allowlist, runner loop, sinks, Spacetime watcher, approve | `services/compiler` | new job kind `calibrate_checks`; gate command `./check_test` |
| engine: rally state, scoring by call-log replay, CEL rules, gate, calls, ctl | `services/engine` | events come from checks over `track3d`, not from 2D homography |
| `sportmod` loader with the import allowlist | `services/engine/trophy_engine/sportmod` | loads `checks/*.py` too |
| synthetic generator | `trophy_engine/synth` | emit 3D tracks from a `field.json` |
| decide(): Claude second opinion on BETA calls | `trophy_engine/decide` | Claude only (Gemini and Bitdeer dropped unless the user says otherwise) |
| Drop | `services/rules`, `actors/`, Moss, Apify, `/coach`, moments index | D-36 (the simplified-architecture proposal was not adopted and is deleted) |

## 9. Honest limits

- **No 3D data exists yet.** Stages 1 to 3 run on synthetic and recorded tracks; say so everywhere they appear.
- **Two unsynchronised phones at 30 fps** give up to 16 ms skew, about 15 cm at 10 m/s. For bounces on the surface, a single calibrated view through the homography is often more accurate than triangulation; the adapter should prefer `n_views: 1` surface samples at bounce time when fusion marks them. Every `p` must carry the σ that results.
- **BlurBall weights** have an unstated license (repo issue #2) and the detector asserts CUDA; the user decides on the public demo, and perception owns the MPS patch.
- A Droid run can still produce a wrong but passing edit (a threshold that passes synthetic truth and fails on a real table). The judge sees the diff and the warm-up table before approving, and every check reports `calibrated`.

## 10. Open with the user

1. Who owns `track3d` fusion and the clap sync (perception, PR #9's tracker?), and when a first recording can be made.
2. Whether the session's checks should survive to the next game on the **same** calibration (cheap to keep; the brief says discard).
3. Gemini and Bitdeer: keep as voters or drop (this brief assumes drop).
