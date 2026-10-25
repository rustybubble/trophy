# Droid rule compiler: audit and spec (2026-10-24, late evening)

**Goal (the user):** the Factory Droid must *programmatically* produce the rules of a sport from the sport's laws,
not patch a hand-written pack. Today it does not. This document records what is hand-written, what the Droid has
actually produced, why the current design cannot answer "did the Droid encode the rules", and the spec to fix it.

## 1. Audit: who wrote what

| Artifact | Lines | Author | Droid-editable today? |
|---|---|---|---|
| `sports/table_tennis/rules.yaml` (8 rules, params, field, scoring) | 164 | human | yes (`house_rule`, `compile`) |
| `sports/table_tennis/events.py` (2D layer 1 → 2 events) | 356 | human | yes (`compile`, `retune`) |
| `sports/table_tennis/checks/*.py` (7 geometry checks over the 3D track) | 711 | human | yes (`calibrate_checks`, parameters only in practice) |
| `trophy_engine/checks/events.py` `TrackEventer` (binds checks → events) | 236 | human | **no**: the check names `phases`, `contacts`, `serve_toss`, `bounces`, `net_touch` are hard-coded |
| `trophy_engine/checks/api.py` (the maths a check may call) | 585 | human | no, by design |
| `services/referee/referee/catalog.py` (check catalog the ask router uses) | — | human | no |

**What the Droid has produced, ever:** three `house_rule` runs (all in `data/local/droid_runs/`), each adding the
same 12-line `serve_net_let` rule to `rules.yaml`. Zero Python. The `compile` (pickleball) rehearsal in the README
left no artifact in this checkout. `calibrate_checks`, `retune` and `new_check` have never run against Factory.

**Findings that block the "Droid encodes the rules" claim:**

1. **The Droid never sees the laws.** No prompt hands it rule text. `house_rule.md` gives it one sentence from the
   judge; `compile.md` tells it, in our words, which fields to change (even the kitchen rule is dictated by the
   prompt). The Droid is a patch applier with the answers in its brief.
2. **The eight scoring rules are hand-written and pre-exist every run.** Six fire on 2D events; the two serve-toss
   rules need the 3D track, which perception does not produce yet. Nothing in the pack came from the Droid.
3. **The gate cannot judge a new rule.** `replay_test` replays two synthetic rallies with no net touch, no serve
   toss, no edge, no let. Any rule about those passes 19/19 whether right or wrong. The `serve_net_let` rule the
   Droid wrote fires on *any* serve net touch, without the "lands in" condition, in all three runs, and the gate
   passed it every time. A rule under an AUTO tier was approved with no evidence.
4. **The event vocabulary is closed.** A rule can only reference `bounce`, `contact`, `net`, `ball_dead`,
   `serve_toss` and their payload fields. The laws D-31 names (`serve_hidden`, `serve_position`, struck-on-descent,
   net touch + good bounce = let) have no event, so a Droid-written rule for them is dead YAML.
5. **New checks cannot reach the engine.** Even if the Droid wrote `checks/serve_position.py`, `TrackEventer` would
   never call it: the check → event wiring is Python, not data. `new_check` exists only as an enum value.
6. **No real labelled footage exists for any of this.** `data/local/recordings/g_*` holds seven games of source
   JPEGs (196–1960 frames per camera) and two 4K/60 iPhone 17 uploads (`take1.MOV`, `take2.MOV`), none labelled.
   The user recorded net hits on purpose; they are the first real gate material we have.

The hand-written 2D `events.py` emits `net` only with `kind: into` (a direction reversal at the net plane). It never
emits `touch`. So on the 2D phone path the let rule has nothing to fire on at all.

## 2. What "programmatic" has to mean

A rule is two layers, and only one is Python:

- **Measurement**: a check over the ball track emits an event with numbers and σ (`net_touch` → `net{kind, clearance_m, p}`).
- **Judgement**: a `rules.yaml` entry with a CEL condition over the event plus rally state, a tier, text, speech.

The Droid must produce **both** from the laws, under a gate that contains the situation each law covers. Where a
law needs a measurement no check provides, the Droid writes the check **and** declares the event it emits; the
engine binds it from data, not from code we edited for it.

## 3. Spec

### 3.1 Inputs the Droid gets (new)

`sports/<sport>/laws.md`: the rule text, one law per `### <law_id>` heading, with the official reference and the
review criteria (for table tennis: 2.6.2 toss ≥ 16 cm, rise within 30° of vertical as the ITTF TTR criterion;
2.6.4 position; 2.6.5 hidden; 2.9.1.1 serve let; 2.10 points; 2.11 game to 11, win by 2; 2.13 service alternation;
2.15 expedite is out of scope). **Source:** pasted by a human from the ITTF Handbook, with a `source:` line and
date. The Droid cannot browse (web fetch stays disabled in the sandbox), so the fetch step is outside it: a one-time
human paste for the demo; a `trophy-droid fetch-laws` CLI step that writes this file from a URL is a follow-up and
must record the URL and retrieval date in the file header.

`sports/<sport>/events.md`: generated, not written: the event types the module can emit and every payload field
with its unit, produced by `trophy-engine describe-events` from `event.schema.json` plus the check library's
`EMITS` blocks (3.3). This is the Droid's vocabulary and the only thing it may reference in CEL.

### 3.2 Job `compile_rules` (new kind; replaces nothing, sits beside `house_rule`)

Sandbox: `laws.md`, `events.md`, `sports/<sport>/rules.yaml` **with the `rules:` list emptied** (params, field,
scoring kept: those are the table, not the rules), `schema/`, `samples/`, `replay_test`. Allowlist:
`sports/<sport>/rules.yaml` only.

Brief (`prompts/compile_rules.md`): for every law in `laws.md`, either write a rule using only `events.md`
vocabulary, with `rule_ref: "<law_id>"`, the tier justified in one comment line (AUTO only for a geometric fact at
p ≥ 0.90; anything judged is BETA, D-17), or list it under `## Not encodable` with the missing measurement named
in one line. The result section must contain the table `law | rule_id | tier | or reason not encodable`.

Gate additions to `replay_test` (3.4) decide `ready`. The Droid's gap list becomes `droid_run.gaps[]` (new field,
`{law_id, missing_measurement}`), shown in the dashboard panel next to the diff.

**Acceptance for the demo:** starting from an empty `rules:` list, the run reproduces the six 2D-decidable rules
and the two serve-toss rules (the ids may differ; the gate compares calls, not ids), writes the serve let with the
"followed by a good bounce" condition (3.4 forces it), and lists hidden serve, serve position and spin as not
encodable. The hand-written `rules.yaml` is then **deleted from the repo** and replaced by the approved Droid output
plus its `run.jsonl`, so the claim "the Droid wrote the pack" is checkable from the artifact.

### 3.3 Job `new_check` (build the consumer; the enum exists)

Trigger: a `compile_rules` gap, or the referee's `request_check` (interfaces §20). Sandbox: the check library copy,
`reference/checks/`, `laws.md` (the one law), `samples/` with 3D fixtures, `schema/track3d.schema.json`,
`check_test`. Allowlist: `checks/<new_name>.py` only (one new file per run).

A check file gains a mandatory `EMITS` block next to `PARAMS`:

```python
EMITS = {"event": "serve_position", "payload": {"min_height_m": "m", "behind_end_line_m": "m", "p": "prob"}}
```

The loader (`checks/library.py`) validates `EMITS` against `event.schema.json` (new event types are allowed when
the payload declares units for every field). `TrackEventer` replaces its hard-coded five calls with a loop over
`library.json`'s `pipeline:` list (`phases` first, then every check with an `EMITS`, each over the open rally
window); an approved `new_check` run appends to `pipeline:`. This is the change that makes a Droid-written check
reach the engine without anyone editing Python. `catalog.py` reads the same `EMITS`/`about` metadata so ask-the-ref
routes to new checks too.

Gate: `check_test` runs the new check on every fixture, requires determinism, the allowlist, and that the labels
file has at least one labelled instance of the event (3.4); without one the run is `failed: no evidence`, never
`ready`.

### 3.4 Gate: evidence, not just regression

`replay_test` and `check_test` gain a **coverage row per rule**: a rule is `PASS` only if at least one sample
triggers it and the labelled call agrees, or the labels say the situation does not occur and the rule did not fire.
A rule with zero triggering samples is `FAIL: no evidence`, which blocks `ready`. This alone would have caught the
`serve_net_let` bug.

Fixtures to add, in this order:

1. **Synthetic 3D scenarios** in `trophy_engine/synth/track3d.py`: `serve_net_let` (touch, then good bounce),
   `serve_net_fault` (touch, then off the table), `serve_toss_low`, `serve_toss_angled`, `serve_struck_rising`.
   Cheap, deterministic, labelled by construction, marked `SYNTHETIC`.
2. **The user's net-hit recordings**, labelled: a `labels3d.json` per clip with `nets[]` (`t_s`, `kind`,
   `from_side`), `rallies[].let`, `rallies[].winner`, and a `source: "recording g_xxx/c_yyy"` line. Until a fused
   3D track exists, these clips go through the 2D path: `clip_as_phone.py` → `events.py` → `*.l1.jsonl` +
   `*.labels.json`, and the 2D `events.py` must learn `net{kind: touch}` (a crossing with no reversal whose
   lowest image-space clearance at the net column is within the band). The first real number we can report is
   "net touches found on N labelled clips".
3. Serve-toss clips from a side-on phone once the 3D fuse exists (Agent 2).

### 3.5 Honesty rules for the demo

- A rule's provenance is shown: `rules.yaml` entries carry `by: droid run <id>` or `by: human`, and the dashboard
  panel renders the Droid's law table and gap list, not just the diff.
- Rules with no real-footage evidence stay `calibrated: false` and are spoken as BETA, whatever the Droid asked for;
  the engine caps the tier when the coverage row was satisfied by synthetic data only.
- We say "the Droid compiled N rules from the ITTF text and declined M", with the artifact to prove it, and never
  "the Droid knows every rule of ping pong".

## 4. Order of work and estimates (one agent, this machine)

| Step | What | Est. | Unblocks |
|---|---|---|---|
| A | `laws.md` for table tennis (human paste), `describe-events` → `events.md` | 45 min | B |
| B | `compile_rules` job: allowlist, prompt, sandbox layout, `gaps[]`, CLI, one live run | 1.5 h | the demo claim |
| C | Coverage rows in `replay_test` / `check_test` | 1 h | honest gate |
| D | Synthetic serve-let / fault / toss scenarios | 1 h | C has evidence for serve rules |
| E | Label the net-hit recordings; `touch` in 2D `events.py` | 2 h | first real number |
| F | `EMITS` + data-driven `TrackEventer` pipeline; `new_check` consumer | 2.5 h | Droid-written checks run live |
| G | Delete the hand-written `rules:` list; land the Droid's pack + run log; README section | 30 min | provenance |

B and C can run in parallel. F needs the 3D track to matter live but is testable on the synthetic 3D fixtures now.
Decision to record when B lands: **D-38, the Droid compiles rule packs from `laws.md` under an evidence gate;
hand-written rules are removed.**
