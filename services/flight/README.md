# Flight family (owner B)

**Env:** py3.11 · numpy 1.26.4 · opencv-contrib-python 4.10.0.84 · torch CUDA 12 · GPU

## Responsibilities
- Ball/shuttle tracking:
  - **BlurBall** for table tennis (fix the BGR→RGB bug; turn duplicate-frame filtering on; white balls).
  - **WASB** weights for tennis, pickleball, badminton and volleyball, run through BlurBall's runners.
  - **TrackNetV3** for badminton, post-game only.
- Calibration comes from `courtcam-adapter`. Triangulate across 2+ cameras (OpenCV DLT / aniposelib) and fit gravity parabolas between bounces.
- Bounce time comes from the nearest audio onset. σ = fit + calibration + blur + timing. Emit `bounce`, `net`, `contact_height`, `touch_count`, `wall_bounce` to `ev:flight`.
- Priority calls: pickleball near-line in/out, table-tennis edge vs. side, badminton in/out, roundnet rim (with audio). See build plan F4 and §3.
- Cards: `docs/research/build-cards-flight-family.md`.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
