# Can a makeshift system exist for every sport in scope? (2026-10-24)

*Written before building the ball-track MVP, to check that the same stack covers every sport in the outline. Detector facts come from `docs/research/` (dated evidence, verified 2026-10-22; speeds are the authors' own). Nothing here was run.*

## The shared stack (identical for every sport)

```
camera pose     four field corners once per camera (taps or a court detector) → cv2.solvePnP against the rule pack's field dims
ball detector   3 frames at 512×288 → heatmap            ← the ONLY sport-specific piece; one architecture, per-sport weights
tracker         gate + constant-velocity filter → one continuous 2D track per camera
3D lift         time-align the two tracks → triangulate; snap to the field plane at bounces; σ per axis
events          bounce (contact with a plane), hit (velocity reversal), out (crossed a boundary), dead (track lost)
people          RF-DETR person + rtmlib pose with feet   ← only for sports whose calls depend on bodies
rules           rule pack (CEL) → AUTO / BETA / PLAYERS DECIDE → Spacetime
```

**The detector is one architecture with per-sport weights.** BlurBall is a fork of WASB-SBDT (MIT) trained on table tennis. WASB ships weights for tennis, badminton, volleyball, soccer and basketball with the same 3-frame 512×288 input and the same heatmap output, so the inference wrapper written for BlurBall runs every one of them. That is the generalizable "ball tracking model": the weights are the per-sport asset, the way a rule pack is the per-sport rules.

## Per sport: the calls in the outline

| Sport | Call | Features needed | Detector (license) | Calibration | Tier | Makeshift demo |
|---|---|---|---|---|---|---|
| **Table tennis** | rally scoring | bounce side, hit side, dead | BlurBall TT weights (code MIT, weights unstated); white ball | 4 table corners | AUTO | **Live.** Two propped phones, side-on at the net + diagonal |
| | edge rule | bounce position vs end/side lines, σ | same | same | BETA near 4 cm band, AUTO beyond | Live, staged edge hits |
| | illegal serve (6 in toss, 30° from vertical) | release, apex, contact in the vertical plane | same | same | AUTO when clear, BETA close | Live, side-on camera |
| **Pickleball** | kitchen volley foot fault | player feet vs kitchen line at the hit | RF-DETR person + rtmlib feet (Apache) | 4 court corners (Good-Pickleball court model, Apache) | AUTO | **Live** in a 3×4 m space: taped kitchen line, mini net |
| | outs | bounce position vs lines | WASB-tennis weights (MIT) or TrackNet-Pickleball (no license, demo only) | same | AUTO clear, BETA ≤ 10 cm | Live |
| **Tennis** | outs | bounce position vs lines | WASB-tennis (MIT) | 4 court corners (TennisCourtDetector, no license; or taps) | AUTO > 15 cm, BETA close (serve moves 1.4 m per frame at 30 fps) | **Recorded only.** No indoor court |
| **Badminton** | outs | landing position (the shuttle falls nearly vertically, so it is the easiest in/out of all) | TrackNetV3 (MIT, F1 98.6) or WASB-badminton (MIT) | 4 court corners (CourtKeyNet, MIT) | AUTO | Live if a hall with ceiling height exists |
| **Volleyball** | outs | landing position vs lines (ropes or cones, tapped) | WASB-volleyball (MIT) or asigatchov stack (MIT) | 4 corners + antenna tops | AUTO | Partial live (pepper drill) or recorded |
| | hand over the net | wrist keypoints vs the net plane, ball contact | RF-DETR + rtmlib | same | BETA (weak; a side camera is needed) | Recorded |
| **Basketball** | 2 vs 3 pointer | shooter's feet at release vs the arc; release = 3 frames of upward ball velocity | RF-DETR person + COCO `sports ball` (Apache); rtmlib feet; courtcam make/miss | 4 court landmarks (courtcam) | AUTO feet clear of the arc, BETA on the line | **Recorded** on the CC BY half-court clip |
| | outs | ball or holder's foot across the boundary | same | same | AUTO clear, BETA ≤ 1 ball diameter | Recorded |
| | fouls | contact between tracked players: min distance, closing speed, first mover | same | same | **PLAYERS DECIDE** (`foul_flag`, capped at BETA by D-17) | Recorded; shown as evidence, never called |
| **Two-hand touch** | touch made | both defender wrists inside the carrier's box within ~200 ms | RF-DETR person + rtmlib wrists; ball class fine-tuned (COCO `sports ball` is weak on footballs) | 4 field corners (cones) | BETA ("2 hands, 74%") | Recorded; no open repo detects a snap or the line of scrimmage |
| | out of bounds, touchdown | carrier's feet vs lines | same | same | AUTO | Recorded |

**Not in scope, and not reachable from phones:** baseball, golf, hockey. A pitch moves about 40 m/s, over a metre per frame at 30 fps, so real systems use radar or 300 fps cameras. BaseballCV exists but targets broadcast footage. Leave these off the sport wall.

## Answer

**Yes, with the same stack for every sport in scope.** Every call above reduces to the shared events plus, for five of the sports, feet or wrist keypoints from one pose model. Two sport families, not seven systems:

1. **Ball-on-a-plane sports** (table tennis, pickleball outs, tennis, badminton, volleyball outs): detector weights swap, everything else is identical. All AUTO-capable.
2. **Ball-plus-people sports** (pickleball kitchen, basketball, two-hand touch, volleyball net): add the person and pose model as a second observation source; the ball side is unchanged. The showcase calls are AUTO (kitchen foot fault, 2 vs 3), and the judgment calls are honestly BETA or PLAYERS DECIDE.

**The weak points, stated plainly:**
- Table tennis is the only sport with a live demo this weekend; tennis, basketball and two-hand touch are recorded clips, and the plan already says so.
- Two-hand touch and the volleyball net touch are pose heuristics. They will work on clean footage and misfire on crowded footage. BETA is the right tier.
- Basketball fouls are never called by the system; they are flagged with evidence. That is D-17 and it is the honest position.
- Licenses: WASB, TrackNetV3, RF-DETR, rtmlib and the Good-* family are clean (MIT or Apache). BlurBall's and TrackNet-Pickleball's weights are unstated, so they are demo-only until the user decides.
- Nothing above has been run on this project's footage. The first measurement is the table-tennis MVP; every other sport inherits the same tracker and lift, so its result transfers.
