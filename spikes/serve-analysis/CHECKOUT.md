# Using this checkout

This is the standalone analysis app from the Cal Hacks working directory. It
contains serve spotting, two-camera toss evidence review, the actual-footage demo
renderer, and the ball/pose/replay code that the combined workflow uses. It does
not wire these experiments into Trophy's live flight service or rule engine.
Run commands from `spikes/serve-analysis`; this avoids mixing its `trophy` Python
package with `packages/py-trophy`.

## Setup and checks

Use native Python 3.12 on macOS, as in the original measured runs:

```sh
cd spikes/serve-analysis
bash scripts/bootstrap.sh
bash scripts/bootstrap_serves.sh
.venv/bin/python -m pytest -q tests/test_serves.py tests/test_serve_legality.py
node --test tests/test_toss_frame_proof.mjs
```

The serve tests and frame-proof tests above do not require recordings or model
weights. HTTP tests bind an ephemeral localhost port. The broader prototype suite
(`.venv/bin/python -m pytest -q`) additionally uses locally downloaded sample
footage/calibrations and model assets from the original workspace; see
[MULTIVIEW.md](MULTIVIEW.md), [VALIDATION.md](VALIDATION.md) and the asset setup
scripts before running those integration checks.

The setup scripts download verified public assets. They do not supply the locally
trained table-tennis checkpoint. Transfer `weights/serves/table-tennis-final.pt`
and its report from the original working directory into this directory's ignored
`weights/serves/`, or follow the training commands in [SERVES.md](SERVES.md).
The published tennis initialization is deliberately rejected for table-tennis
inference. Model and dataset terms remain separate from source-code licenses.

## Actual-footage demo

The original validated video remains local at
`/Users/mudu/Developer/calhacks/artifacts/serve-legality/actual-demo/toss-legality-demo.mp4`.
Footage, recordings, generated images, model weights, environments and runtime
caches are excluded from this source distribution under Trophy's repository
policy. No participant recordings are embedded in this branch.

To rebuild the first-serve demonstration, place the two authorized original
recordings in the repository's ignored `data/local/ttClips/` directory, with the
filenames in `configs/actual-toss-demo-session.json`, or supply a separate session
JSON with `session_id` and two `views` containing `id` and local `video` paths.
Relative video paths are resolved from the command's working directory.

```sh
.venv-serves/bin/python scripts/build_actual_toss_demo.py
# Optional inputs and destination:
.venv-serves/bin/python scripts/build_actual_toss_demo.py \
  --session /absolute/path/session.json \
  --geometry configs/actual-toss-demo-geometry.json \
  --output artifacts/serve-legality/actual-demo
.venv-serves/bin/python -m http.server 8508 --bind 127.0.0.1 \
  --directory artifacts/serve-legality/actual-demo
```

The checked-in numeric camera fit is an **unvalidated demo estimate** for the
original pair around 8 seconds. It is not transferable to a different recording
or camera setup. The renderer's reviewed release/apex times, orange-ball regions,
source resolution and background registration also target that original pair.
Its nominal original estimates were 8.7 cm and 30.7°, not validated officiating
measurements. Source pixels and assumptions are exported alongside the MP4.
See [SERVE_LEGALITY.md](SERVE_LEGALITY.md) for rules, methods and limitations.

For the manual evidence workflow, see [SERVES.md](SERVES.md) and
[SERVE_LEGALITY.md](SERVE_LEGALITY.md). Example session/calibration files under
`configs/` point at ignored local media and must be matched to the exact source
files. A copied example calibration never becomes validated automatically.

## Vendored code

Only source and notices are included from upstream repositories; their demo
images, example recordings, Git histories and model weights are excluded.
`vendor/UPSTREAM.json` records the BlurBall pin and checksums for the included
files, plus an explicit list of omitted media. The optional 4D Humans code retains
its MIT notice; SMPL assets and pretrained models require separate acquisition
and terms. Three.js and E2E-Spot notices remain beside their source.
