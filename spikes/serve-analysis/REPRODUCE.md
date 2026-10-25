# Reproduce the recorded-analysis results on another computer

Use this page as the receiving agent's entry point. The clone supplies the code;
the owner-supplied **private asset kit** supplies the exact inputs and reference
outputs. The kit is not in Git and has no public download URL.

The current branch is `codex/serve-legality-demo`. Its initial source snapshot
already included automatic table outlines, clickable correction, audio/visual sync,
BlurBall, HMR2, serve/toss review, placements, missing-first-root recovery, and video
byte-range playback. These experiments are isolated from Trophy's live services.
See [handoff validation](repro/VALIDATION.md) for the checks actually run in the
isolated receiving-style checkout.

## Clone, transfer, install

Prerequisites: access to `rustybubble/trophy`, Git, Python **3.12**, a working
**Node.js >=20**, and roughly **25 GB free disk** for the tar, extracted assets,
four environments and fresh outputs. No Trophy cloud-service credentials are
needed for this standalone recorded analysis.

```sh
git clone --branch codex/serve-legality-demo https://github.com/rustybubble/trophy.git
cd trophy/spikes/serve-analysis
```

Have the owner transfer `trophy-analysis-assets-20261024.tar` and its `.sha256` companion
through their chosen private channel. It is **7,105,792,000 bytes**, about 7.1 GB.
It contains participant footage and separately acquired model assets: keep it
private, outside Git and public artifact/release hosting. The source notices and
separate code/model/data terms in `PROVENANCE.md`, `SERVES.md` and the repository's
`docs/licenses.md` still apply. Copying the kit is not permission for redistribution.

Verify the archive and then install with **Python 3.12**:

```sh
# Run beside the transferred tar and companion checksum file:
shasum -a 256 -c trophy-analysis-assets-20261024.tar.sha256
# From trophy/spikes/serve-analysis:
python3.12 repro/bootstrap.py --bundle /private/path/trophy-analysis-assets-20261024.tar
.venv/bin/python repro/bundle.py verify
.venv/bin/python repro/reproduce.py doctor
.venv/bin/python repro/reproduce.py test
```

The archive SHA-256 is
`92319e9f21e7ab92c246c977450e909c65e82bf88e1b507412b2e75c37fe602a`.
The importer compares its complete manifest with `repro/asset-manifest.json`,
checks every restored file, restricts writes to ignored asset storage, rejects
links/traversal/unexpected entries and preserves existing mismatched files.

The bootstrap creates four independent environments from exact locks:
`.venv`, `.venv-pose`, `.venv-serves`, `.venv-hmr2`. A small `.venv-tools` contains
pinned uv for installation. No environment is copied from the original machine,
and no `.pth` points to its site-packages. Python package installation needs
internet access or a suitable uv cache; model/video downloads are unnecessary
after importing the kit. Node.js is needed for the JavaScript regressions and
placement export. Doctor checks that `node` works and is new enough. If your PATH
selects a broken or unsuitable installation, use `TROPHY_NODE=/absolute/path/to/node`
with the bootstrap/doctor/test commands; do not copy a Node binary from this Mac.

**Platform:** native Apple Silicon macOS/Python 3.12/MPS is the measured reference.
The neural and browser workflow also has an explicit POSIX CPU path (`--device cpu`),
but CPU runtime and numerical equivalence on a different machine were not measured
here. Bootstrap selects CPU PyTorch wheels on Linux and checks installed dependency
compatibility. Linux native media/audio/graphics libraries may need installation
for the selected platform; a complete Linux setup was not executed here.
The scripts use `bin/python`; native Windows is not a supported setup path.
Legacy offscreen MP4 rendering needs native OpenGL on macOS or an EGL-capable Linux
graphics setup. The latest interactive mesh replay does not need offscreen rendering.
Font rendering in the toss MP4 now falls back when macOS Arial is unavailable.

## Immediately open the exact existing result

```sh
.venv/bin/python repro/reproduce.py serve --port 8508
```

Open `http://127.0.0.1:8508/`. This serves the imported room-video replay, both source
clips, annotated detections and the linked serve reviewer. Static MP4 byte ranges
are supported, including when the reviewer API is embedded. The result uses a
15-second analyzed prefix; the two-player body replay spans **2.7–14.9667 s**. It is
not a full-recording reconstruction of the 44/39-second inputs.

`artifacts/sessions/ccc43c2099f540f2/` is the recovered, completed reference run.
Its original failure report is retained beside the successful report. The archive
preserves historical JSON provenance, including old machine paths. The latest
replay's source-video URLs are relative and portable. To generate new runtime
reports bound to this checkout, use the commands below; do not treat historical
file paths or modification times as valid source identity on another machine.

## Rerun inference, not just the saved viewer

```sh
# Both latest uploaded videos: real ball/pose/serve/HMR2 inference and body fit.
.venv/bin/python repro/reproduce.py run room-demo-15s --device auto
# A small real public two-camera sample, through the same complete pipeline.
.venv/bin/python repro/reproduce.py run public-smoke --device auto
# The original longer recordings: trained serve spotting and merged events.
.venv/bin/python repro/reproduce.py run serves-original --device auto
# Reviewed actual-footage toss demonstration on those original recordings.
.venv/bin/python repro/reproduce.py run toss-original
# Historical 2.9-second HMR2 experiment: rerun neural body inference, fit and MP4s.
.venv/bin/python repro/reproduce.py run legacy-hmr2 --device auto
# Ball-only refinement/completion and MP4s from the restored cached detections.
.venv/bin/python repro/reproduce.py run ball-only
```

Each command prints its new output directory under `artifacts/reproductions/`.
It never overwrites the archived reference. Use `--output /new/absolute/directory`
to choose a destination. Profiles in `repro/profiles` contain exact segment,
calibration, regions and timing settings with checkout-relative video paths.
The room profile preserves the original automatic detector's initialization; the
upload UI reruns automatic segmentation from the actual image pixels.
The separate ball-only profile preserves the later visually inspected table
corners and robust geometry refinement. Its gap filling is explicitly labelled
as estimated; it does not replace the combined replay's original observations.

The two combined profiles automatically verify finite mesh buffers, mesh indices,
frame counts, unchanged measured/missing ball records, shared replay/review clocks,
and body-fit improvement. Reference comparisons use explicitly recorded tolerances:
they are reproducibility checks, not independently measured 3D accuracy or a
promise of bitwise-identical GPU floating-point results. Check an existing new run:

```sh
.venv/bin/python repro/reproduce.py check-result \
  artifacts/reproductions/<new-run>/analysis --profile room-demo-15s
.venv/bin/python repro/reproduce.py serve \
  --directory artifacts/reproductions/<new-run>/analysis/replay --port 8509
# For a fresh serves-original run, open its active source-video reviewer:
.venv/bin/python scripts/serve_serve_review.py \
  --directory artifacts/reproductions/<serves-run>/serves --port 8504
.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

For fresh public triangulation accuracy and placement reproduction, the existing
`bash scripts/build_multiview_demo.sh` builds/evaluates both TT3D rallies and exports
placements. It operates in its historical `artifacts/multiview` paths; copy/retain
the reference kit if you want byte-identical archived files before rerunning it.
See `MULTIVIEW.md`, `PLACEMENTS.md` and `VALIDATION.md` for original commands and
evaluation splits. `REPLAY.md` covers the original single-camera replay.

## What the kit includes

| Group | Files | Bytes | Purpose |
|---|---:|---:|---|
| recordings | 4 | 1,792,759,881 | The two latest uploads and the original pair used for serve/toss/legacy demos |
| runtime | 15 | 2,798,244,308 | Exact HMR2 checkpoint/config/body buffers, pose and BlurBall weights, trained serve checkpoints and reports |
| samples | 14 | 12,876,817 | Official clips, calibrations and reference labels needed by existing tests/evaluations |
| reference | 1,569 | 2,498,646,385 | Completed replays, source excerpts, detections, poses, mesh buffers, reports, evaluation/training assets and demo outputs |

`repro/asset-manifest.json` identifies every file by destination, size, SHA-256 and
group. If disk is limited, import selected groups with `repro/bundle.py import
<tar> --groups runtime recordings samples`; the complete regression/reference
workflow uses all groups. Venvs, `.pth` files, secrets, duplicate UI uploads,
temporary downloads and regenerable decoded-frame caches are omitted.

Exact reference outputs can be restored byte for byte. Retraining the serve model
is a separate stochastic experiment; the trained checkpoints are supplied so
reproducing inference does not depend on retraining them. Model/data version pins,
calibration assumptions and model-produced versus manual observations remain
documented in the original evidence reports. This kit does not turn demo estimates
into calibrated officiating measurements.

## Receiving-agent task

> Read `AGENTS.md`, `CLAUDE.md`, then `spikes/serve-analysis/REPRODUCE.md`. Work on
> `codex/serve-legality-demo`. Obtain the owner's private asset kit, verify/import
> it, bootstrap independent runtimes, run doctor/tests, then rerun `public-smoke`
> and `room-demo-15s` into new directories. Verify the new results and inspect the
> synchronized source/3D playback. Use the remaining profiles for historical
> serve/toss/legacy outputs. Preserve private media and model assets in ignored
> storage; never replace missing observations with invented tracks. Report the
> actual device, processed interval, coverage and any numerical differences.
