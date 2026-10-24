# Possession family (owner C)

**Env:** py3.11 · rfdetr[train]==1.11.2 · trackers==2.6.1 · supervision==0.30.9 · rtmlib==0.0.16 + onnxruntime-gpu · GPU

## Responsibilities
- RF-DETR (TensorRT) for person and ball. **Separate** ByteTrack trackers for people and ball. rtmlib `BodyWithFeet` (wrists 9/10, ankles 15/16, toes 20/21, heels 24/25) runs only near the ball.
- From courtcam (via the adapter): on-court filtering, **teams without pinnies**, and basketball **make/miss at the rim** (classical CV, with "can't tell" → BETA).
- Events: `possession`, `contact`, `line_cross`, `step`, `snap`, `player_touch`, `catch`, `in_zone`, `timer` → `ev:possession`.
- Priority calls: two-hand touch (both wrists in the carrier's box, |Δt| ≤ 0.25 s), "off you" last touch, travel step counter, double dribble, rush count (snap detector: frame MSE + median, CVPRW 2013), kitchen foot fault (with B).
- Cards: `docs/research/build-cards-possession-and-resting.md`.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
