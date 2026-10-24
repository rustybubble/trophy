# Resting-object family (owner A)

**Env:** same env as possession · GPU

## Responsibilities
- Fixed phone + homography to board coordinates. "At rest" = tracker speed below a threshold for N frames. RF-DETR fine-tuned on **Cornhole Referee** (Roboflow cloud training, run locally).
- Zone scoring (hole 3 / board 1 / off 0, cancellation to 21), confirmed by the bag-in-hole sound. Then mini golf, bowling, darts.
- Events: `at_rest`, `score_zone` → `ev:resting`. See build plan F7.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
