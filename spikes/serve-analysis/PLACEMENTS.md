# Per-player placement analysis

Open **http://127.0.0.1:8503/#placementHeading**. The replay now contains a **Placement patterns** section with a separate heatmap for each player's shots. It analyzes the current scene's actual reconstructed ball trajectory; it does not use reference tracking or generate simulated shots.

## Customize in the browser

- **Time range** or **Up to replay time**: analyze the entire clip, a selected interval, or only events up to the current replay position.
- **Density / zone counts / both**, heat spread, colour palette, opacity, depth zones per table half, and width lanes.
- **Shared density scale** compares the two maps directly; individual scaling highlights each player's own distribution. Colours represent nearby contact counts, not calibrated probabilities.
- **Player perspective / fixed court coordinates**, player names, and end assignment. With player perspective, both players attack from the left toward the right of their map. Zone left/right labels are always from the sending player's perspective.
- **Include own-side contacts**, **Reviewed / manual only**, detector-score threshold, contact-height tolerance, minimum vertical/longitudinal speeds, minimum contact separation, and maximum tolerated tracking gap.
- **Show contact markers on replay** overlays the included positions in blue/orange on the 3D table.

Settings and contact corrections automatically persist in this browser, scoped to the source-video hashes. **Reset settings** restores visual/detection defaults and retains reviews. **Save settings + reviews** downloads a JSON preset. **Load preset** restores it; a preset from another rally applies settings but not that other rally's annotations.

Each card downloads a **900 × 610 PNG**. **Export contacts CSV** includes every candidate and manual contact, with a flag for inclusion in the current heatmaps, coordinates in metres, timestamp, attributed player, detector score, and review status.

## Review and correct

Expand **Review and correct contacts**. Click a timestamp to pause/seek the 3D scene and both source videos at their calibrated time offset. Edit the sending player, X/Y coordinates in centimetres, review status, or inclusion checkbox. Unknown contacts remain unassigned until corrected. You can add a missed contact at an entered timestamp or the current replay time, and remove manual contacts.

The defaults do **not** claim that automated detections are confirmed labels. `estimated`, user-`confirmed` (shown as **Reviewed**), and `manual` are distinct export statuses. A human review is not an independently calibrated measurement.

## Detection and attribution

The shared implementation is `web/multiview/placements-core.js`:

1. Consider valid reconstructed ball positions only. Find local height minima with enough samples before and after, rejecting support windows with gaps longer than the configured threshold.
2. Fit incoming/outgoing vertical lines over approximately 100 ms on each side. Require downward-to-upward motion with configurable minimum speeds.
3. Intersect the vertical fits to estimate contact time, check the fitted centre height against the tabletop plus the 2 cm ball radius, and fit nearby horizontal coordinates. Reject positions outside the tabletop (with a 2 cm candidate edge tolerance).
4. Infer the sending end from incoming motion along the table. Require evidence that the ball visited that player's end since the preceding contact, except the continuation after a same-player own-side serve bounce. This prevents a net rebound or repeated table bounce from becoming an invented new player's shot. If support is insufficient, retain the contact as **unassigned**.
5. Apply user reviews, time/status/score filters, and own-side exclusions before accumulating counts or Gaussian density.

Default candidate thresholds: height tolerance **8 cm**, vertical speed **0.35 m/s**, longitudinal speed **0.6 m/s**, contact separation **0.18 s**, maximum support gap **0.06 s**. The score is the minimum ball detector score in the support window; it is not a bounce probability. Own-side contacts, including the serve's first bounce, are excluded by default. Net-centred and unassigned contacts are also excluded unless corrected appropriately.

The original ball trajectory, model detections, timing alignment, body poses and existing reference accuracy are unchanged. The analysis is derived from the current reconstruction, so missed/incorrect tracking, sparse sampling near impacts, calibration error, and slow/inside-table shots can cause missed or wrong bounce/ownership estimates. The source-end support rule is deliberately conservative and can leave valid shots unassigned when the clip starts mid-flight. The editable review table addresses these cases.

## Executed sample and verification

On TT3D game_00 / rally 010, the default configuration finds **11 candidate contacts**:

- **6 included target placements: 3 Blue and 3 Orange**.
- **2 own-side contacts** excluded from placement maps by default.
- **3 late contacts unassigned**, excluded from per-player counts.

Included times are approximately **1.385, 2.078, 2.817, 3.284, 3.961 and 4.581 seconds**. Visually inspected both original camera views at these times; the projected markers are consistent with table contact. There are **no independent bounce-time/placement labels**, so this is a qualitative check, not a measured bounce-detection accuracy claim. The contact sheet is `artifacts/placements/contact-review.jpg`.

With the default 3 × 3 grid per half, each player's three shots occupy three different cells, so the UI honestly reports a tie instead of inventing a dominant zone. A short clip with three contacts per player cannot establish a long-term tactical tendency. The panel explicitly labels the small sample.

Browser checks executed:

- Changing time range to 3.0–4.5 seconds gives **one included contact per player**.
- Palette and depth-grid changes update the maps and survive reload.
- Reviewing one Blue contact and selecting reviewed-only gives **1 Blue / 0 Orange**.
- Adding a temporary manual Blue contact gives **4 Blue**, removing it restores **3**; excluding/reincluding an inferred contact gives **2 → 3**.
- Timestamp seeking sets the source clocks to approximately **1.384625 / 1.387653 seconds**, preserving the camera offset, and the playhead filter includes just the first placement.
- CSV, preset JSON and PNG downloads executed. CSV contains **11 rows / 6 included**; PNG is a real browser-canvas export. Saved-preset import restores the controls and reviews.

Temporary test contacts were removed and test review statuses restored to **Estimated**.

## Commands

No new runtime dependency is needed by the local UI: serve the existing built scene. The normal `build_multiview.py` copies the new modules with the replay assets.

```bash
.venv/bin/python scripts/serve_replay.py --directory artifacts/multiview/demo --port 8503
```

The optional CLI uses the same analysis functions as the browser, with Node 18+ (executed here with Node 26.0.0):

```bash
node scripts/analyze_placements.mjs \
  --scene artifacts/multiview/demo/scene.json --output artifacts/placements

# Apply an exported browser preset. Reviews apply only to matching source hashes.
node scripts/analyze_placements.mjs \
  --scene artifacts/multiview/demo/scene.json --output artifacts/placements/custom \
  --preset /absolute/path/to/trophy-placement-preset.json

node --test tests/test_placements.mjs
.venv/bin/python -m pytest -q
```

CLI outputs are `analysis.json` and `contacts.csv`; PNGs are exported by the browser. The 12 Node tests cover bounce geometry, floor/missing/rolling rejection, serve handling, the real-rally regression and net-origin gate, attribution/end swaps, time/score/review filters, immutable source observations, player-relative coordinate orientation, heatmap counts/density, and preset/manual-input validation. The 36 existing Python tests also pass.
