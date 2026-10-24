# Table-tennis calibration adapter

`POST /calibrate` accepts `trophy.calibration_request.v1` and returns `trophy.calibration.v1`. `calibration.py` also exposes `calibrate(request) -> dict` for the recorded demo. The local server binds to `127.0.0.1:8050`.

```sh
/Users/mudu/Developer/calhacks/.venv/bin/python services/courtcam-adapter/server.py
curl -s http://127.0.0.1:8050/healthz
```

For a new environment, install the pinned dependencies from this directory's `pyproject.toml` with `uv sync`; then use `uv run python server.py`. This implementation uses OpenCV directly, reports `solver: "opencv-planar-v1"`, and does **not** claim to run the previously planned courtcam dependency. It has no web-framework or model dependency.

The table's coordinate frame comes from `rulepacks/table_tennis.yaml`: centre of tabletop is `(0,0,0)`, `+x` points toward end B, `+y` is left facing A to B, and `+z` points up. Dimensions are 2.74 × 1.525 m; net height is 0.1525 m; floor is z = −0.76 m. Tap end A first in named order `A_left, A_right, B_right, B_left`.

A valid four-corner request (pixels must be replaced with the actual frame's taps):

```json
{"schema":"trophy.calibration_request.v1","game_id":"g_ttdemo01","cam_id":"c_side01","sport":"table_tennis","seq":0,"image_size":{"w":1280,"h":720},"points":[{"name":"A_left","px":[200,420]},{"name":"A_right","px":[350,560]},{"name":"B_right","px":[1000,420]},{"name":"B_left","px":[780,330]}]}
```

The solver rejects missing/duplicate names, nonfinite or out-of-image taps, self-intersection/nonconvexity, nearly collinear/tiny quadrilaterals, very close corners and badly conditioned geometry. Reprojection residuals and projected field lines are returned. Invalid requests produce HTTP 422 with `trusted:false` and an explanation.

Four coplanar points can fit a homography exactly; that zero residual does not establish airborne-ball height accuracy. The default result is **untrusted**, with an approximate pinhole pose only where the assumed camera produces a plausible solution. Its explicit assumptions are square pixels, centred principal point, focal length `max(w,h)`, zero lens distortion, and an above-table camera. A homography applies only to the tabletop plane. It must never turn an airborne ball pixel into a claimed measured toss height. Recalibrate after camera movement or zoom; do not apply one static calibration to the handheld demo recordings.

The optional extensions `intrinsics:{K:[...9]}` and `validation_points:[{pos_m:[x,y,z],px:[u,v]}, ...]` can establish trust using known intrinsics plus at least four independently measured elevated points, with z-span ≥0.16 m and max reprojection error within `max(5px, 1% click span)`. These are additional request properties, preserving v1. Nonzero distortion is rejected: rectify the source image first. Passing this residual gate is still not an independently measured ball-localization or timing error bound.

## Clip ingestion and probe

```sh
# Timing audit: no Redis required, original source PTS and seq retained.
/Users/mudu/Developer/calhacks/.venv/bin/python tools/play_clip.py \
  'data/ttClips/Adobe Express - IMG_4342.mp4' --start 5 --end 7 \
  --index data/local/tt-demo/ingest-index.jsonl --index-only --fast

# Frame bus: requires py-trophy dependencies and a running Redis.
PYTHONPATH=packages/py-trophy python tools/play_clip.py your.mp4 \
  --game g_ttdemo01 --cam c_side01 --offset 0 --sync-err-ms 20 --width 1280
PYTHONPATH=packages/py-trophy python tools/framebus_probe.py c_side01 --duration 10
```

`play_clip.py` preserves decoder PTS, original frame indices, and `t_game_s = source_time_s + clip_offset_s`; it refuses absent/nonincreasing timestamps rather than fabricating an FPS clock. `--start/--end` select source times without resetting source identity. Encoding to JPEG and optional width reduction happen only on the bus; native files remain untouched. It publishes `source=file`, never measurements/rulings, and never sends frames to Spacetime. `--calibration` installs an already matching calibration in Redis. `--game-epoch-ms` must be the shared gateway `t0_ms` when ingesting multiple cameras into an existing game; omitted, a local playback epoch is assumed and reported. A supplied calibration must match the resized bus dimensions. Audio-onset extraction is not implemented by this ingest tool. `--fast` can overrun the latest-frame bus and is for diagnostics; paced mode is the normal integration path.

Run the isolated acceptance checks:

```sh
/Users/mudu/Developer/calhacks/.venv/bin/python -m pytest -q tests/test_calibration.py
```

These tests cover synthetic geometry, degenerate calibration rejection, elevated validation/trust, wire-contract serialization and variable-cadence source timestamp preservation. They do not establish accuracy on the phone recordings. Redis publication needs a running local Redis and the shared `py-trophy` dependencies.
