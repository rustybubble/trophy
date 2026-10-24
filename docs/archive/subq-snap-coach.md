# Trophy: SubQ Snap as referee + coach (research, 2026-10-22)

Scope: SubQ Snap API facts, access status, Jev, a concrete Snap-coach design for Trophy, evaluation plan, risks and fallbacks.

Bottom line:
- **The API is real and documented, and it's self-serve.** Sign up at console.subq.ai and get 100M free tokens. Two caveats: the launch post says new users "may be waitlisted when capacity is reached", and Product Hunt says the 100M free tokens are for "the first 10,000 users". **Check current access, create a key and run the smoke test below before relying on this integration.**
- **Facts changed today.** Snap 1.1 launched on 2026-10-22. The documented model ID is now `subq-snap-1.1`, not `subq-snap-preview`, and the price is $0.04/M input tokens, not $0.05. Output is still free.
- **SubQ Snap uses Jev's API design.** Jev is TypeSafe AI's "System One" decision model. Both use `POST /v1/systemone` with `state` + `questions`, and both have `noul`/`choice`/`score` question types, `probabilities` and `confidence`. Code written for one ports to the other with small changes. That makes Jev the cheapest fallback.
- **Design rule taken from both vendors' docs: keep code in charge.** Geometry decides IN/OUT. Snap handles semantic, rule-interpretation and tactical judgments, and its probabilities feed the confidence gate after calibration.

---

## 1. SubQ Snap: exact API facts

Sources: docs.subq.ai (llms-full.txt, fetched 2026-10-22), subq.ai, subq.ai/introducing-subq-snap, subq.ai/subq-snap-1-1, subq.ai/pricing.

### Endpoint, auth, model
| Item | Value |
|---|---|
| Base URL | `https://api.subq.ai/v1` |
| Decisions endpoint | `POST /v1/systemone` (the "Decisions API", status: Public preview) |
| Auth | `Authorization: Bearer $SUBQ_API_KEY` (keys from console.subq.ai, shown once) |
| Model ID | `subq-snap-1.1` (current docs). The launch-week ID `subq-snap-preview` appears only on third-party pages (LLM Reference, OpenClaw). Check `GET /v1/models` and use whatever your key lists. |
| List models | `GET /v1/models` (OpenAI-compatible, so `openai` SDK `client.models.list()` works with `base_url`) |
| Price | $0.04 / 1M input tokens, output free (Snap 1.1, "20% price cut"). Launch price for v1.0 was $0.05. |
| Free credits | "Free 100M tokens for new users" (subq.ai pricing page). Product Hunt says "for the first 10,000 users". Requests without credits return `402`. |
| Context | 384K tokens (393,216). Requests over the limit or close to it fail with `400`, so stay well under, e.g. ≤ 250K. |
| Data retention | Inputs/outputs are deleted within 60 days. ZDR is available on request. Decisions with images store the images too. |

### Request body
```json
{
  "model": "subq-snap-1.1",
  "state": "<string | object | array>",
  "images": [ { "mediaType": "image/jpeg", "base64": "<one-line base64, no data: prefix>" } ],
  "questions": {
    "<question_name>": { "type": "noul",   "instructions": "...", "criteria": { "true": "...", "false": "..." } },
    "<question_name>": { "type": "choice", "instructions": "...", "criteria": { "OPTION_A": "description or null", "OPTION_B": null } },
    "<question_name>": { "type": "score",  "instructions": "...", "criteria": ["level 0", "level 1", "level 2"] }
  }
}
```
- **Questions:** 1–128 named questions per request (current docs; third-party pages say 1–16, which is outdated). Names can be up to 100 characters. Every question sees the whole `state` and every image. Ask related questions in one call, because the state is billed once.
- **Choice:** 2–255 options. Each option is a key, and its description can be `null`. `instructions`/`criteria` may be strings, objects or arrays, so you can give structured descriptions.
- **Score:** 2–10 ordered levels. It returns a probability-weighted `score` (can fall between levels), plus `legend`, `probabilities` and `confidence`.
- **Noul:** a yes/no gate. It returns `noul` = P(yes), 0–1.
- **Images:** up to 4 per request. Formats: PNG/JPEG/WebP. Limits: 4 MiB decoded each, 8 MiB decoded total, 13 MiB body. **Each image costs only ~64–256 tokens**, so the model sees a heavily downsampled image. Video isn't supported; the docs say "sample up to 4 frames and send them as images". URLs and `data:` URLs are rejected with `422`. Images are a top-level array; they aren't referenced inside the state.

### Response
```json
{
  "model": "subq-snap-1.1",
  "answers": {
    "escalate": { "type": "noul", "noul": 0.92 },
    "queue": { "type": "choice", "choice": "nurse_line",
               "probabilities": { "nurse_line": 1, "primary_care": 0, "pharmacy": 0, "front_desk": 0 },
               "confidence": 1 },
    "acuity": { "type": "score", "score": 1.86, "legend": {"0":"...","1":"...","2":"..."},
                "probabilities": {"0":0,"1":0.13,"2":0.87}, "confidence": 0.79 }
  },
  "usage": { "input_tokens": 477, "output_tokens": 0 }
}
```
- **Calibrated probabilities:** you get a full distribution over every option, not token logprobs. Treat that distribution as the model's belief.
- **`confidence` is not P(correct).** In the TypeSafe/Jev spec that SubQ's output matches, `confidence` for a choice = (p_max − 1/n)/(1 − 1/n), a normalized peakedness. SubQ's docs example fits that formula. **For the Trophy gate, use `probabilities[choice]` (calibrated), not `confidence`.** With 5 options, confidence 0.90 corresponds to p_max 0.92.
- **Probabilities can saturate.** The doc example returns exactly 1/0, and Jev publishes 0.01 increments. Clip to [1e-3, 1−1e-3] before taking logs for calibration.
- **Not deterministic.** The docs say "Outputs can vary between requests". Average 2–3 calls for high-stakes decisions.

### Errors / limits
`400` over the token limit or rejected input · `401` · `402` no credits · `403` key can't use the model · `422` validation (bad image, not a decision model) · `429` rate limit · `5xx`/`503` temporarily unavailable. **No numeric rate limits are published.** The docs only say "retry 429 and 5xx with backoff". Python examples use a 60 s timeout.

### Latency
- Vendor claim from the v1.0 launch: ~1 s per decision on 100K tokens ("sub-second decision layer" for 1.1). There are no independent measurements.
- For comparison, Jev measured ~73 ms floor + ~6 ms per 1K tokens (independent probe), median ~0.14 s.
- **Budget for Trophy:** assume 0.5–1.5 s at ≤ 100K tokens, plus image upload time on venue Wi-Fi. Measure p50/p95 on day 1.

### SDKs and examples
- **No official SubQ SDK for the Decisions API.** The docs show raw `fetch` (TS), `urllib` (Python) and cURL. The OpenAI SDK works only for `/v1/models`, Chat Completions and Responses, not `/v1/systemone`. Write a 40-line `requests`/`httpx` wrapper.
- The OpenClaw `@openclaw/subq` plugin is unpublished and has no image support. Skip it.
- **TypeSafe's Python SDK (`typesafe-sdk`) and JS SDK (`@typesafe-ai/sdk`) might work with a custom `base_url` pointed at SubQ, but that's unverified, and image formats differ** (TypeSafe uses `assets` + references, SubQ uses a top-level `images` array). Don't depend on it.
- Cookbooks: SubQ has only the quickstart examples (triage, keyboard photo). TypeSafe's docs have about 20 cookbooks that apply to Snap's contract. The useful ones are confidence routing, self-consistency for choices/nouls, hierarchical classification with beam search, and composite scoring.

### Smoke test (run tonight)
```bash
curl -sS https://api.subq.ai/v1/models -H "Authorization: Bearer $SUBQ_API_KEY"
curl -sS -X POST https://api.subq.ai/v1/systemone -H "Authorization: Bearer $SUBQ_API_KEY" \
  -H "Content-Type: application/json" -d '{"model":"subq-snap-1.1","state":"Ball bounced on the far edge of the table, then the receiver touched the net with his hand.","questions":{"call":{"type":"choice","instructions":"Under ITTF rules, what is the correct call for this rally?","criteria":{"POINT_SERVER":null,"POINT_RECEIVER":null,"LET":null,"NO_CALL":null}}}}'
```

### Other SubQ products
| Product | What | Access |
|---|---|---|
| **SubQ (LLM)**, `subq-preview` / "SubQ 1.1 Small" | Long-context LLM on Subquadratic Sparse Attention. A research model handles 12M tokens; the launch (May 5 2026) claims RULER-128K 95.6%, SWE-Bench Verified 81.8. Press and critics note it reuses Qwen weights. | **Early access** ("selected design partners"). Chat Completions + Responses endpoints are OpenAI-compatible. **Not openly available.** |
| **SubQ Code** | CLI coding agent that loads a whole repo into context | Private beta / early access since May 2026 |
| **SubQ Search** | Long-context "Deep Research at chatbot speed" | Private beta / early access |
| **SubQ Snap 1.1** | Decision model | **Public preview, self-serve with free tokens, capacity-limited (possible waitlist)** |

### Vendor benchmark claims (all self-reported)
- **Snap v1.0 (Oct 12):** HF Decision Index 0.2.1 61.7 vs Jev 57.9; 16 enterprise benchmarks 67.6 vs 61.6 (13/16 wins); Bespoke Nimble 82.9% vs 76.0%; Decision LCR (72K–115K tokens) 74.0 vs Jev-chunked 48.0.
- **Snap 1.1 (Oct 22):** Artificial Analysis Decision Index 65 (tied #1) vs Jev 1.14 57; HF Decision Index 65.7 vs Jev 60.6. It trails Jev on Knowledge & Reasoning (50.9 vs 55.1). When2Call 96.2 vs 82.6.
- **Calibration claim for 1.1:** ECE on "unseen probability games" 0.108 → 0.014. This is vendor-measured and not on sports. Plan on calibrating it yourself.

---

## 2. Jev (the team's earlier choice)

- **Maker:** TypeSafe AI. It came out of stealth on 2026-09-15 with a $40M seed (DCVC). Co-founder Diogo Almeida is ex-OpenAI. Jev is its first "System One" decision model.
- **What it is:** a closed, API-only decision model (no weights, no self-hosting). It has the same `noul`/`choice`/`score` contract at `POST https://api.typesafe.ai/v1/systemone`, and 1.14 adds a `box` (image bounding-box) question type. TypeSafe trains it with "RLCD" (proper scoring rules), and probabilities come out "pre-calibrated".
- **Models:** `jev-1.13.0` (= `jev-latest`) and `jev-1.14.0` (= `jev-preview`, from Oct 14). Price: $0.042/M input, output free.
- **Context:** 64K per request / 32K per question. With the header `TypeSafe-Danger-Zone-Long-Context: true` it goes to 262K, but slower and less accurate.
- **Images:** "dreamer-ready" (not production quality), enabled with the `TypeSafe-Danger-Zone-Images: true` header. Images go in an `assets` map and are referenced by string inside the state, instructions or criteria. Formats: png/jpg.
- **Speed:** "most queries complete in about 100 ms". Independent measurement: median 0.14 s.
- **Official SDKs:** Python `typesafe-sdk`, JS `@typesafe-ai/sdk`, both with built-in retry. Rate limits are per organization, in tokens/s and requests/s.
- **Access:** the waitlist opened Sep 20, then **new signups were paused on Sep 22** (status after that is unclear). It is also listed on the **Vercel AI Gateway** (`typesafe-ai/jev`, `jev-1.13.0`, `jev-1.14.0`, text input, 32K context). That listing was confirmed live via the gateway's /v1/models today and is the practical way to get Jev without a TypeSafe account.
- **Independent evidence:**
  - Accurate on bounded decisions. Amplitude measured ~12 points of overconfidence on BANKING77 (87.4% mean confidence vs 75.3% accuracy).
  - It can be confidently wrong.
  - Known failure modes: literal reading, **weak at numbers/counting/dates**, distraction from large irrelevant state, **bias toward the first Choice option**, no generation.
- **Snap vs Jev for Trophy:**
  - Snap wins on context (384K vs 64K): it can see a whole match log and both players' tendencies in one call.
  - Snap wins on images (4 first-class images vs an experimental flag).
  - Snap has a slightly lower price.
  - Jev wins on latency (~0.1 s vs ~1 s) and has official SDKs and more cookbooks.
  - **Pick Snap as primary and keep Jev as a text-only backup** (same code shape).

---

## 3. How to use Snap well in Trophy

### Rule zero: what goes to code and what goes to Snap
Both vendors say the same thing: "Rules you can write down belong in code", and the model is "not a calculator". Jev's jaggedness doc lists numeric precision, counting and date math as failure modes. And each image is only ~64–256 tokens, so Snap can't see a 2 mm edge-ball from a frame.

| Decision | Who decides |
|---|---|
| Ball IN/OUT from 3D bounce position | **Code** (geometry + tracker uncertainty gives P(IN) analytically) |
| Double bounce, bounce counts, score, serve order | **Code** (event log state machine) |
| Ambiguous or semantic rule calls: let (serve clipped net, distraction), hand on table, net touch, obstruction, edge vs side ball, illegal serve (toss < 16 cm, hidden serve), basketball travel / carry / charge vs block / goaltending | **Snap** (rule text + event window + 4 key frames) |
| Merging geometry with Snap when both have evidence | **Code** fuses them (below) |
| "Best option" among candidates at a decision point | **Snap** (with long context), checked against empirical stats |
| Human explanation and commentary | **Claude** |

### 3a. Referee adjudication
**Request pattern (one call per disputed or uncertain event, several questions at once):**
```json
{
  "model": "subq-snap-1.1",
  "state": {
    "sport": "table_tennis",
    "rules": "<rule-pack excerpt: only the 3-8 rules relevant to this event type, verbatim ITTF text>",
    "event": {"type": "serve", "rally_id": 41, "server": "A",
              "summary": "Toss height LOW (est. 9-13 cm, below the 16 cm minimum). Ball touched net on the way over. First bounce on receiver half, near right sideline."},
    "event_log_window": "<last ~20 tracker events as compact lines: t, type, side, zone, height bucket>",
    "geometry": {"bounce_distance_to_edge": "about 1 cm inside (uncertainty ±1.5 cm)", "p_in_from_geometry": "HIGH"},
    "frames": "image 1 = toss apex, image 2 = net contact, image 3 = bounce crop (tight 200x200 px around contact), image 4 = wide view"
  },
  "images": [ {"mediaType":"image/jpeg","base64":"..."}, "...x4" ],
  "questions": {
    "call": {"type": "choice", "instructions": "What is the correct umpire call for this serve under the rules in `rules`?",
             "criteria": {"LET": "Serve touched the net assembly and then landed legally on the receiver's court",
                          "FAULT": "Serve is illegal (toss height, hidden ball, wrong bounce) - point to receiver",
                          "IN": "Legal serve, play continues",
                          "OUT": "Serve did not land on the receiver's court",
                          "NO_CALL": "Evidence is insufficient to decide"}},
    "toss_legal": {"type": "noul", "instructions": "Was the toss at least 16 cm high and near vertical, based on `event.summary` and image 1?"},
    "net_touch": {"type": "noul", "instructions": "Did the ball touch the net assembly on the serve (image 2)?"}
  }
}
```
Notes:
- **Pre-bucket numbers into words** ("about 1 cm inside", "LOW") because decision models are weak at numbers. Keep the raw numbers in your logs.
- **Crop images around the event** (the bounce crop is the most useful one). A full 1080p frame is shrunk to ≤ 256 tokens.
- **Decompose.** Ask the atomic nouls (`toss_legal`, `net_touch`) together with the overall `call`. Code can then check consistency (e.g., if `net_touch` > 0.8 and `call` = IN, flag a contradiction and fall into the replay band).
- **Option order bias.** Jev "leans toward the option that comes first". For calls in the 60–90% band, send a second request in parallel with shuffled option order and average the two distributions. This costs one extra call (~$0.0001 at 2K tokens) and no extra latency.

**Fusing with geometry:**
- For line calls, P_geom(IN) = Φ(d/σ). Here d = signed distance from the bounce to the edge and σ = combined tracker + calibration error, measured on day 1 by rolling balls onto known positions.
- When both sources speak: p = softmax(w1·log p_snap_cal + w2·log p_geom), with w fitted on the labelled set. Simpler for a hackathon: use geometry when |d| > 2σ, otherwise use calibrated Snap with frames.

**Confidence gate (the team's design):** p = calibrated probability of the top call (not `confidence`).
- p ≥ 0.90: auto-call (TTS + overlay).
- 0.60 ≤ p < 0.90: show the call as "challengeable" with a challenge button on the PWA.
- p < 0.60, or a contradiction between atomic questions: replay the point.

**Calibration (temperature scaling):**
1. Collect labelled calls. Aim for 60–100; 30 is the bare minimum. Label from 240 fps phone slow-mo by two team members, discard disagreements.
2. For each, store the Snap probability vector p (clipped to [1e-3, 1]).
3. Fit one scalar T to minimize NLL of `softmax(log(p)/T)` against labels (scipy `minimize_scalar` over T ∈ [0.25, 5]). T > 1 softens overconfident outputs.
4. For nouls, fit Platt scaling: σ(a·logit(p) + b). With < 50 points, fix b = 0 and fit only a.
5. Report ECE (3–5 bins), Brier score and a reliability diagram before vs after, with leave-one-out cross-validation so you don't fit and score on the same 30.
6. **Be honest about the CI.** With n = 30, a 90% accuracy has a Wilson 95% CI of about 74–97%. Show it.
7. If p saturates at 0/1 often, temperature scaling can't fix it (log of clipped values). Then use **self-consistency**: run 3 calls with shuffled option order, and set p_final = mean distribution. Disagreement across calls is itself an uncertainty signal.

```python
import numpy as np
from scipy.optimize import minimize_scalar
def fit_T(P, y):            # P: (n,k) Snap probs, y: (n,) label idx
    L = np.log(np.clip(P, 1e-3, 1))
    def nll(T):
        Z = L / T; Z -= Z.max(1, keepdims=True)
        lp = Z - np.log(np.exp(Z).sum(1, keepdims=True))
        return -lp[np.arange(len(y)), y].mean()
    return minimize_scalar(nll, bounds=(0.25, 5), method="bounded").x
```

### 3b. Coach: "wrong move vs optimal move"
**Pipeline per decision point:**
- Table tennis: each shot by player X when the incoming ball is tracked.
- Basketball: each possession end, or the moment of a pass/shot/drive decision.

1. **Detect the decision point** from the event stream (opponent's hit → our player's contact = decision).
2. **Generate candidates from geometry and rules** (code, sport rule pack). Each candidate gets a name, a plain-English description and a few bucketed features:
   - **Table tennis:** placement zone (3×3 grid of the opponent half: deep/mid/short × forehand/middle/backhand), plus spin/pace class (push, loop, flick, block, smash). Prune to the physically reachable set given the incoming ball (height above net, speed, spin bucket). Typically 6–12 options.
   - **Basketball half-court:** shoot now / drive left / drive right / pass to P2…P4 / reset. Add features from geometry: closest defender distance bucket, shot zone and that player's make rate from this session, passing-lane open or closed (angle test), shot clock bucket.
   - **Always include the option the player actually took**, plus `"OTHER"`. Shuffle the order.
3. **Ask Snap** one `choice` question, "Which option maximizes the chance that player X wins this point/possession?", plus an optional `score` question ("How good was the actual choice?" 0–4). The `state` carries the full context:
   - `rules`: short.
   - `match_so_far`: compact log of all prior rallies, ~150–400 tokens each.
   - `tendencies`: computed in code, written as words with counts, e.g. "Opponent B: backhand side under pressure, lost 7 of 9 rallies when pushed deep to backhand; strong forehand loop (won 8 of 10)".
   - `current_situation`.
   - `images`: up to 4 frames (contact moment, player positions).
4. **Compute the regret signal:**
   - p_best = max(probs), p_actual = probs[actual].
   - **Flag a "wrong move"** when (p_best − p_actual ≥ 0.30) and (p_actual ≤ 0.15) and the calibrated p_best ≥ 0.5.
   - Cap the flag to the top 3–5 per game so the coach isn't nagging. Rank by (p_best − p_actual) × leverage (game point, close score).
5. **Sanity check with data before showing it.** Compute the empirical win rate of each option class in this session (and a prior from public match stats if available). Use p_combined = α·p_snap + (1−α)·p_empirical. Only show the flag if both agree on direction. This protects the demo from a confidently wrong Snap pick.
6. **Write it up.** Claude gets the Snap distribution, the features and the outcome, and writes a 1–2 sentence explanation ("You pushed short to his forehand; he's won 8/10 of those. A deep push to the backhand corner was the higher-percentage play.").
7. **Ghost trajectory.** The 3D replay renders the optimal option as a ghost path: target zone center → physics-sampled arc (parabola with drag + Magnus for table tennis, a simple arc or drive path for basketball) from the actual contact point.

**Questions per call:** batch all decision points of one rally into one request (up to 128 questions). `state` = match log + tendencies, and each question names its shot (`rally_41.shot_3`). One call at the end of each rally then covers every shot in it, so it's ~1 s per rally, not per shot.

### 3c. Universal: per-sport rule pack
One YAML/JSON file per sport. The Snap client, gate, calibration and UI stay the same.
```yaml
sport: table_tennis
event_types: [serve, rally_shot, bounce, net_touch, point_end]
code_rules: [double_bounce, score_fsm, serve_rotation, in_out_geometry]   # pure code
snap_questions:
  serve_call: {type: choice, options: {LET: ..., FAULT: ..., IN: ..., NO_CALL: ...}, rule_refs: [2.6, 2.9]}
  toss_legal: {type: noul, rule_refs: [2.6.2]}
coach:
  decision_point: rally_shot
  candidate_generator: tt_zones_3x3_x_stroke
  objective: "maximize chance player wins the point"
gate: {auto: 0.90, challenge: 0.60}
calibration: {T: 1.4, fitted_on: 64 calls}
```

**Third demo, ranked by effort vs payoff:**
1. **Chess from a PGN or public video, the easiest and best for proving accuracy.**
   - Legal moves come from `python-chess`, so the referee part is trivial and handled by code. Typical positions have 20–40 legal moves, well under the 255-option limit.
   - Snap's Choice picks among Stockfish's top-8 candidate moves plus the played move.
   - **Stockfish gives free ground truth**: measure Snap's top-1 agreement with the engine's best move and its "blunder detection" recall (played move loses ≥ 150 centipawns). This produces a real accuracy number in an hour and shows the "same API, different rule pack" story.
   - Caveat: an engine is the real optimal-move oracle. Pitch chess as the **evaluation harness** that validates the coaching method, not as the product.
   - Board-state recognition from a camera is hard; use PGN or digital-board video.
2. **Pickleball or tennis from public broadcast footage.** Kitchen/foot faults and line calls are a good fit for rule packs, but tracking takes more work.
3. **Card games (Uno, Blackjack).** The rules are code; Snap adds little. Skip.

### 3d. Context packing and latency budget
- **Token sizing:**
  - Table tennis: compact event line ~15 tokens, a rally ~10–30 events, so ~300–450 tokens per rally. A 30-minute session (~150 rallies) is ~60K tokens.
  - Basketball: possession ~500 tokens, a 40-minute half-court run ~60–80 possessions, so ~40K tokens.
  - Plus tendencies (~2K), rules (~1–3K) and 4 images (~1K).
  - **The whole game fits in ≤ 100K tokens, about $0.004 per call.** 100M free tokens is about 1,000 full-context calls, or ~5,000 if you cap state at 20K.
- **Packing order** (stable prefix first, volatile last): `rules` → `tendencies` (recomputed per rally) → `match_so_far` (append-only) → `current_situation` → images.
  - No prompt caching is documented, so every call bills the full state.
  - Long irrelevant state lowers accuracy (Jev's jaggedness list). Use **full context for the coach** and **short context for referee calls**: rules for that event type, the last ~20 events, 4 frames, about 2–4K tokens, the fastest path.
- **Live latency budget for the referee:**

  | Stage | Time |
  |---|---|
  | Point ends | t = 0 |
  | Geometry/FSM call | < 50 ms (local) |
  | Upload of 4 JPEG crops (~60 KB each) | ~100–300 ms on venue Wi-Fi |
  | Snap decision at ~3K tokens | ~0.3–1.0 s (vendor claims; measure it) |
  | Second shuffled-order call | 0 s (sent in parallel) |
  | Gate + TTS | ~200 ms |

  - Target: call announced ≤ 1.5 s after the point ends. If Snap hasn't answered by 2.0 s, use the geometry call with a "challengeable" badge.
- **Coach timing:** run it asynchronously after each rally, or as a "post-game analysis" batch. The latency doesn't matter there; the judge sees it in the replay.

---

## 4. Prior art and evaluation ideas

**Decision models and "choose among options" setups in sports and games:**
- **TypeSafe's Jev DOOM bot:** a 10 Hz loop over a text game state with a fixed action set, ~0.11 s per decision, ~$7/h. TypeSafe concedes a scripted bot plays better. This is the closest public example of a decision model in a real-time game loop.
- **TypeSafe Twitch chat filter cookbook:** many questions per message, 8 messages concurrently.
- **RefereeBench (arXiv 2604.15736):** video multimodal LLMs as referees across 11 sports (925 videos, 6,475 QA). The best models reach ~60%; Qwen3-VL ~47%. Models over-call fouls on clean clips and struggle with rule application and timing. **Takeaway: don't let an LLM or VLM make raw visual foul calls unaided. Give it tracker events + rule text + targeted crops, and gate on calibrated confidence.**
- **X-VARS (arXiv 2404.06332):** football foul detection + explanation with a multimodal LLM (SoccerNet-MVFoul). It's precedent for the "decision + explanation" split.
- **DeepMind TacticAI (Nature Comms 2024):** suggests corner-kick positioning adjustments. Liverpool FC experts preferred its suggestions ~90% of the time. It's precedent for "suggest the better option + ghost players" and good pitch framing.
- **Table tennis:** deep-learning serve-foul detection (Electronics 2025, F1 0.93 on serve-point recognition). ChatPPG is an LLM + multi-camera table tennis coaching prototype.

**Accuracy evidence to show judges:**
1. **Referee set:** 60 (minimum 30) labelled events: edge balls, lets, net touches, illegal tosses, clean points.
   - Show the confusion matrix, accuracy with Wilson CI, and the reliability diagram before vs after temperature scaling.
   - **Show selective accuracy:** accuracy in the auto-call bucket (≥ 0.90) and what % of calls were automated. Example: "78% of calls automated, 97% correct; the rest went to challenge/replay."
2. **Snap vs baselines on the same set:** geometry only, Snap only, Snap+geometry fused, Claude self-consistency. It's a small table, and it is the evidence that makes judges believe the numbers.
3. **Coach set:**
   - Chess with Stockfish ground truth: top-1/top-3 agreement and blunder-flag precision/recall over ~200 positions from 5 public games.
   - For table tennis, a human-expert check: a club player marks 20 flagged shots as agree / disagree.
4. **Latency:** p50/p95 per call, logged live on a dashboard tile.
5. **Cost:** tokens per game and $ per game (it will round to cents).

---

## 5. Risks and fallback design

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Access:** waitlist when capacity is reached, or free tokens limited to the first 10K users | Medium | **Sign up tonight.** Verify `/v1/models` lists `subq-snap-1.1` and run the smoke test. Have a second teammate sign up as a spare key. |
| **Preview capacity / 429 / 503 at the event** | Medium | Exponential backoff with jitter. Cap concurrency at 4. Use the circuit breaker in the router below. |
| **Model changed today** (1.1 launched Oct 22, ID and price changed) | Real | Pin `subq-snap-1.1`. Log `response.model`. Calibrate against the exact version you demo. |
| **Vendor claims unverified** (latency, calibration, benchmarks are self-reported; few independent tests) | High | Your own 30–60-call eval *is* the claim you show. Avoid quoting SubQ's benchmark numbers as fact. |
| **Images too low-resolution** (64–256 tokens each) | High for line calls | Code does line calls. Snap gets tight crops. |
| **Option-order bias, nondeterminism** | Medium | Shuffle + average 2 calls on borderline cases. |
| **Confidently wrong** | Medium | Atomic-question consistency checks. Empirical-stats agreement for coach flags. Challenge button. |
| **Venue Wi-Fi** | Medium | Phone hotspot backup. Small JPEG crops. Geometry-only mode. |
| **Proprietary, closed license; data retained 60 days** | Depends on consent and retention requirements | Verify and disclose actual provider retention before sending player video; request ZDR if needed and confirm it is enabled. |

**Fallback stack (same `decide(state, questions, images) -> {probs}` interface, swappable by a config flag):**
1. **Jev via Vercel AI Gateway** (`typesafe-ai/jev-1.14.0`). It's a text-only decision model on the same contract, so you get probabilities without Snap. Send the event summary + tendencies (fits in 32K) and drop the images. Requires a Vercel account and gateway key; get the key ahead of time. Direct TypeSafe signups were paused as of late September.
2. **Local open model with real logprobs on the GPU laptop.** A vision-language model such as Qwen2.5-VL-7B / Qwen3-VL-8B (or a text model like Qwen3-8B) served by vLLM or llama.cpp.
   - Prompt ends with "Answer with one letter:" plus a lettered option list. Read `top_logprobs` for the option-letter tokens, renormalize over the allowed letters, then temperature-scale exactly as above.
   - Works offline and has no rate limits. It will be less accurate, so calibrate it separately.
   - With ~20 GB VRAM, an 8B model in 4-bit fits next to the trackers.
3. **Claude with constrained choice + self-consistency (no logprobs).**
   - Use structured output or tool use with an `enum` of allowed answers and a short rationale field.
   - Sample k = 5 in parallel at default temperature with shuffled option order; p(option) = votes/k, smoothed (votes + 0.5)/(k + 0.5·m).
   - Optionally ask for a verbalized probability too and average it with the vote share.
   - It's slower (~2–5 s with k parallel) and coarser (5 votes = 0.2 steps), so use it for the coach and post-game analysis, not live calls. Claude already writes the explanations, so it is always in the stack.
4. **Geometry-only referee mode.** The gate still works using P_geom; semantic calls (lets, toss) are marked "challengeable".

**Router logic:**
```
try Snap (timeout 2.0 s live / 10 s batch)
  -> on 429/5xx/timeout: retry once with backoff
  -> second failure: switch to the local logprob model for 5 minutes
     (live calls; Jev-via-Vercel if text-only is OK)
  -> Claude self-consistency for coach and batch work
Geometry is always computed, and is always the fallback for IN/OUT.
```

---

## Sources
- SubQ docs: https://docs.subq.ai/ (llms index https://docs.subq.ai/llms.txt; full text https://docs.subq.ai/llms-full.txt), Decisions API https://docs.subq.ai/markdown/endpoints/decisions-api.md, Models https://docs.subq.ai/markdown/using-the-api/models.md
- SubQ site and posts: https://subq.ai/ , https://subq.ai/pricing , https://subq.ai/introducing-subq-snap , https://subq.ai/subq-snap-1-1 , https://subq.ai/introducing-subq
- Third-party: https://www.llmreference.com/model/subq-snap/subq-ai , https://docs.openclaw.ai/plugins/subq , https://alternativeto.net/news/2026/10/subquadratic-launches-subq-snap-a-long-context-decision-model-it-says-outperforms-jev/ , https://www.producthunt.com/posts/1278038 , https://thenewstack.io/?p=22840286 , https://www.technologyreview.com/2026/06/19/1139313/a-startup-claims-it-broke-through-a-bottleneck-thats-holding-back-LLMs/
- Jev / TypeSafe: https://docs.typesafe.ai/llms.txt , https://docs.typesafe.ai/models.md , https://docs.typesafe.ai/confidence , https://docs.typesafe.ai/images.md , https://docs.typesafe.ai/model-jaggedness/jev-1.13.md , https://lilting.ch/en/articles/typesafe-ai-jev-system-one-model , https://www.remio.ai/post/jev-benchmark-finds-a-useful-decision-model-not-a-frontier-reasoner , https://amplitude.com/blog/jev-analysis , https://flaviocopes.com/jev-api-key/ , Vercel AI Gateway model list https://ai-gateway.vercel.sh/v1/models
- Sports AI: https://arxiv.org/abs/2604.15736 (RefereeBench), https://arxiv.org/abs/2404.06332 (X-VARS), https://openrepository.aut.ac.nz/items/5b4770cd-d1b8-4efd-b367-2f9d386b38f5 (TT serve fouls); TacticAI (Nature Communications 2024, cited from memory)
