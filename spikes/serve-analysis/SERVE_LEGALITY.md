# Toss height and direction: rules, measurements, and proof

## Actual-footage demo video

The ready-to-play 20-second, 1920×1080 H.264 demo is
`artifacts/serve-legality/actual-demo/toss-legality-demo.mp4`. It uses the original
phone footage of the first serve, with native 60 FPS orange-ball observations,
reviewed release timing, static-background camera-motion compensation, and a
visually refined +83 ms camera offset. Both camera views, source timestamps, ball
trails, release/apex markers, the projected 16 cm reference, a 3D angle diagram,
and the rule comparisons are burned into the video.

The nominal demo estimates are **8.7 cm** rise and **30.7°** from vertical. They
are labeled as demo estimates, including the comparisons with the 16 cm minimum
and 30° TTR criterion. The measurements, actual tracked pixels, registration
homographies, calibration identity, and source provenance are retained alongside
the MP4. This explicit demo mode does not promote these estimates to supported
officiating measurements or change the production quality gates.

Rebuild it locally with:

```bash
.venv-serves/bin/python scripts/build_actual_toss_demo.py
```

The existing serve-review page also has a **Play annotated footage demo** link.

The review UI now supports a separate, review-assisted toss measurement stage.
It records ball-center marks on source frames, reconstructs them from two cameras,
draws projected vertical/height references, and exports rule-linked evidence.
The serve-contact model does **not** yet locate hand release or apex automatically.
The phone recordings do **not** yet have a validated calibration or timing error
bound, so this implementation cannot presently substantiate fault calls on them.

## Official rule and interpretation

Research checked 24 October 2026. Pin the rules profile to a source/version rather
than silently changing how an older recording is evaluated.

| Check | Official basis | Implemented comparison |
| --- | --- | --- |
| Toss height | [ITTF Statutes 2026, Law 2.6.2, page 41](https://db.ittf.com/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf#page=41) | Vertical rise after leaving the hand must be **at least 0.16 m**. Equality satisfies this height requirement. |
| Toss direction | Same law: project near vertically upwards | The published January 2026 law gives no numeric angle. The strict-law profile leaves the angle determination to a referee. |
| Numeric technology-review criterion | [ITTF TTR announcement, 8 December 2024](https://www.ittf.com/2024/12/08/table-tennis-review-system-returns-with-a-successful-trial-at-ittf-mixed-team-world-cup-2024/) and [WTT Series & Feeder Handbook 2025, Chapter 7, page 60, footnote 3](https://wttwebcmsprod.blob.core.windows.net/technicaldocuments/WTT_Series%20%26%20Feeder_Handbook_2025_20250227.pdf#page=60) | TTR uses a **maximum 30°** angle from vertical. The optional TTR profile compares the measured chord against that criterion. It is not an official TTR adjudication. |

The WTT PDF is archived at `artifacts/serve-legality/sources/wtt-handbook-2025.pdf`.
Its height footnote says higher than 16 cm; our inclusive height comparison follows
the primary Law's explicit minimum. The [2026 AGM working document, proposition
A-03, page 78](https://documents.ittf.sport/sites/default/files/public/2026-04/ITTF_AGM-WD2026.pdf#page=79)
proposes adding the numeric TTR tolerance to the law. A proposal is not proof that
an amendment took effect; this implementation does not treat it as enacted text.

These checks cover height and direction only. They do not establish compliance
with the other service requirements. No point, warning, or match penalty is issued.
Both passing is labeled **Two checks satisfied**, never **Legal serve**.

## What is actually measured

Let `R` be the 3D ball center at release, `A` its center at the toss apex, and `u`
the calibrated unit gravity-up vector, in a common metric world coordinate system.

```text
d = A - R
h = dot(d, u)
rho = norm(d - h*u)
theta = atan2(rho, h) * 180/pi
```

`h` is vertical rise, not distance along the curved path, height above the table,
height above the starting stationary palm, or the total upward motion of the hand.
Using the same ball-center convention at both endpoints avoids switching between
the ball's top and bottom. `rho` includes both horizontal directions, including
motion that goes toward or away from a camera.

The release-to-apex chord method follows [Yang et al., *Foul Detection for Table
Tennis Serves Using Deep Learning*, Electronics 2025, Eq. 2 and Fig. 7](https://doi.org/10.3390/electronics14010027).
The authors reconstruct the toss with two cameras and show key points against a
vertical reference. Their controlled setup uses an additional verification camera;
reported ball/critical-point detection scores do not establish our fault accuracy.
[The authors' full paper](https://openrepository.aut.ac.nz/server/api/core/bitstreams/9d17ced2-ba07-49d4-aabb-29507355a26e/content)
is accessible independently of the publisher website.

This is an explicit operational definition. A release-to-apex chord and the
initial velocity have different angles because gravity curves the trajectory.
The cited official threshold documents do not disclose the complete TTR
measurement algorithm. Equivalence to that proprietary algorithm is unverified;
the evidence export says so. The strict-law profile reports the angle without
inventing a numerical definition of near vertical.

## Evidence workflow

Open a detected serve, expand **Mark release and apex frames**, and inspect the
whole toss. Pause on each phase and mark the ball center in both camera images:

1. Last frame where the ball is still on the hand.
2. First frame where it has visibly separated from the hand.
3. Adjacent observation before the highest point.
4. The observed apex.
5. Adjacent observation after the highest point.

The first two observations bracket release; the latter three bracket the apex.
Player crops preserve source-coordinate mapping. Every click stores the presented
video-frame timestamp, source resolution, normalized pixel coordinates, view ID,
and human observation provenance. Marking requires a paused, decoded frame and
the browser's `requestVideoFrameCallback` timestamp. A generic playhead timestamp
is not silently substituted. Leave an occluded ball missing.

Click **Compute toss checks**. The API undistorts the points, triangulates them,
and rejects weak parallax, behind-camera solutions, bad correspondences, source
identity/aspect mismatches, and inconsistent temporal order. It checks individual
camera times against the calibration interval and timing envelope. A 40 ms limit
on paired frame mismatch is an outer rejection bound, **not** accepted sync
accuracy for rulings. Validated tolerances may need to be much tighter.

The UI shows release/apex markers, a projected vertical reference, a 16 cm tick,
and a separate diagram of the actual 3D toss plane. The numeric 3D angle is never
drawn as though it were the apparent angle on the oblique video. Ghost markers
explicitly represent different source frames. Unvalidated projections say
**Estimate**. A changed calibration or rule version invalidates displayed results
until they are recomputed.

**Export evidence JSON** saves the annotations, reconstructed points, per-camera
reprojection residuals/ray angles, source times, complete calibration record and
hash, rules profile/links, uncertainty, blockers, and the comparison for each
criterion. The existing reviewed-session export includes this evidence too.
Changing a serve's contact time or its toss marks clears the prior measurement.
Manually added serves can also be measured. **Export proof image** decodes all
ten marked source frames (five phases in two views), verifies their presented
timestamps, and saves a PNG with the markers, projected references, measurements,
bounds, rules, and review status. Unvalidated estimates are labeled as such.

The combined 3D replay serves the same evidence API under `review/`. Its own
camera matrices and source identities are packaged automatically for provisional
overlays; packaging does not mark the reconstruction as validated.

## What qualifies as proof

Small reprojection error means that rays agree; it does not prove correct scale,
gravity alignment, camera timing, or release identification. An estimated table
homography alone cannot measure an airborne ball in metres. See [OpenCV's camera
calibration and reconstruction documentation](https://docs.opencv.org/4.12.0/d9/d0c/group__calib3d.html).

A supported check requires a source-linked calibration validation record covering:

- Intrinsics, lens distortion, both camera poses, metric scale, and gravity-up.
- Camera stability or valid per-interval geometry, covering **all** marked frames.
- Visual synchronization and an accepted frame-pair timing envelope.
- A measured 3D endpoint error bound, validated under those pixel/timing conditions.
- A conservative maximum toss speed, used to bound unobserved release/apex motion.
- Reviewer verification of visible release/apex brackets belonging to this serve.

The implementation uses a server-owned calibration; POST requests cannot replace
its geometry or validation claims. The configured bound must cover the whole
measurement setup, including gravity and correspondence/time effects. A report
hash and method are retained with it. Validation metadata is a documented
measurement claim, not a certificate created by this software.

Let `e3D` be that per-point bound and `V` the validated maximum toss speed.
The nominal release anchor is the first-free observation. Its error envelope is
`eR = e3D + V * release_bracket_duration`. The apex envelope is
`eA = e3D + V * max(apex_time - before_time, after_time - apex_time)`.
These conservative terms avoid crediting unseen hand movement as ball rise.
With `e = eR + eA`:

```text
height interval = [h-e, h+e]
if h-e > 0:
    angle interval = [atan2(max(0,rho-e), h+e), atan2(rho+e, h-e)]
otherwise:
    angle interval = [0°, 180°]
```

For a validated vertical-axis angular uncertainty `alpha`, expand the angle
interval by `alpha` and the height interval by
`2 * norm(A-R) * sin(alpha/2)`. The report must supply this angular bound too;
a camera's screen-up direction is not assumed to be gravity.

These are conditional spatial envelopes, not learned probabilities or a claim
of statistical confidence. At 60 FPS, bracket uncertainty can materially widen
them. We prefer an unresolved close call over false centimetre precision.

| Evidence interval | Result |
| --- | --- |
| Entire height interval below 16 cm | Height violation supported, Law 2.6.2 |
| Entire height interval at/above 16 cm | Height criterion satisfied |
| Height interval crosses 16 cm | Borderline; review |
| Entire angle interval above 30°, TTR profile | Exceeds the TTR angle criterion under the documented chord method |
| Entire angle interval at/below 30°, TTR profile | TTR angle criterion satisfied under that method |
| Angle interval crosses 30° | Borderline; review |
| Missing observation or any validation prerequisite | Insufficient evidence; no supported fault call |

## Current recordings and next physical measurement

`configs/serve-user-two-camera-toss-calibration.json` explicitly marks the existing
phone calibration **unvalidated**. It was estimated for the 8–11 second replay
segment with assumed intrinsics/zero distortion. The oblique phone moves, and the
40 ms offset is an audio estimate. The first serve's toss also precedes that
segment. Those facts prevent treating the current configuration as metric proof
for the entire recording. The new system intentionally retains that limitation.

The practical next step is a calibration recording with the cameras fixed in
their match positions: a checkerboard/ChArUco target across the relevant volume,
a measured vertical reference near the server, and a common visual timing event.
Validate reconstructed ball/target positions against independent known 3D points
and known low/angled toss examples. Measure release/apex timing disagreement and
false-fault rates on footage excluded from fitting. Repeat or track calibration
when a phone moves, zooms, changes crop, or changes stabilization.

Automatic endpoint proposals can then come from a ball detector trained on held,
releasing, ascending and apex frames, with a temporal key-point model. Proposals
must retain actual ball observations and ambiguity. The contact spotter, a
monocular pose skeleton, or a smooth ballistic fit alone is not release evidence.
The existing BlurBall toss probe misses the release region; switching its output
on as an automatic legality judge would not solve this.

## Run and reproduce

```bash
.venv-serves/bin/python scripts/serve_serve_review.py \
  --directory artifacts/serves/final-demo \
  --calibration configs/serve-user-two-camera-toss-calibration.json --port 8504

.venv-serves/bin/python scripts/measure_serve_toss.py \
  --session artifacts/serves/final-demo/serves.json \
  --annotations saved-toss-annotations.json \
  --calibration configs/serve-user-two-camera-toss-calibration.json \
  --output toss-evidence.json
```

The command accepts an exported evidence JSON directly; its source-session and
calibration records make the geometry result reproducible without extracting
nested objects. For example:

```bash
.venv-serves/bin/python scripts/measure_serve_toss.py \
  --annotations toss-evidence.json --output reproduced-evidence.json
```

The Streamlit serve panel also accepts an optional calibration file.
Without calibration, the review page still works and explicitly abstains.

The known-geometry verification renders two synthetic 240 FPS videos and uses
their exact 3D inputs. It verifies the complete measurement/UI path without
misrepresenting phone-footage accuracy:

```bash
.venv-serves/bin/python scripts/verify_toss_geometry.py
.venv-serves/bin/python scripts/serve_serve_review.py \
  --directory artifacts/serve-legality/geometry-check \
  --calibration artifacts/serve-legality/geometry-check/calibration.json --port 8515
```

Expected synthetic result: **45.0 cm**, **18.4349°**, both criteria satisfied;
conservative test envelopes are approximately 39.6–50.4 cm and 10.8–27.3°.
These are generated geometry checks, not measured serves from the user's videos.
Tests cover independent known geometry, threshold equality, noisy endpoint
envelopes, out-of-plane motion, missing evidence, invalid calibration, source
mismatch, drift/timing gates, and API isolation. See
`artifacts/serve-legality/validation-summary.json` for executed verification.
