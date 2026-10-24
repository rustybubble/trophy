# py-trophy (`trophy`)

The shared Python library (interfaces-v1 §0). Runtime deps: `pydantic>=2`, `redis>=5`, `python-ulid`. Imports on py3.11 and py3.12. Add it to a service as a uv path dependency:

```toml
[project]
dependencies = ["trophy"]

[tool.uv.sources]
trophy = { path = "../../packages/py-trophy", editable = true }
```

| Module | What |
|---|---|
| `trophy.contracts` | Generated Pydantic models for every schema (`Event`, `BouncePayload`, `ServeTossPayload`, `Call`, `CtlCommand`, `Calibration`, …). Never hand-edit; `make contracts` |
| `trophy.events` | `make_event(...)` (validates the payload for its type), `event_json`, `parse_event`, `payload_of` |
| `trophy.ids` | `new_game_id`, `new_cam_id`, `new_player_id`, `new_join_key`, `new_ulid` |
| `trophy.timebase` | `now_ms`, `t_game_s`, `ClockFit` (min-RTT phone→server fit; `to_srv(t_phone_ms, extra_offset_ms=audio_offset_ms)`) |
| `trophy.framebus` | 16-byte WS header `pack_header`/`parse_message`, `jpeg_size`, `FrameWriter` (XADD `frames:{cam}` MAXLEN ~300), `FrameReader` (`mode="latest"` or `"all"`; never a backlog; dedupes by `seq`) |
| `trophy.streams` | Redis key helpers, `publish_event`, `EventConsumer` (group `engine`), `make_ctl`/`publish_ctl`/`parse_ctl`, `role_allows` (the §9 allowlist) |
| `trophy.tracks` | `BallTrackWriter`, `PlayersTrackWriter`, `read_ball_track(r, cam, t0, t1)`, `Downsampler` |
| `trophy.world` | **`ObservationWriter`** and **`TrackSampleWriter`**: mirror events / the 10 Hz ball track into Spacetime (D-21) |

## Vision modules: the two-line pattern
```python
from trophy.events import make_event
from trophy.streams import publish_event
from trophy.world import ObservationWriter, TrackSampleWriter

obs, trk = ObservationWriter(), TrackSampleWriter()     # one each per process
ev = make_event(game_id=g, t_game_s=t, sport="table_tennis", type="bounce", source="flight",
                cams=[cam], conf=0.97, side="B", pos_m={"x": 1.2, "y": 0.3, "z": 0}, sigma_m=0.018,
                payload={"surface": "table", "side": "B", "d_lines_m": {"end_B": 0.17}, "p_in": 0.99,
                         "edge": None, "timing": "audio"})
publish_event(r, ev)   # hot path: Redis ev:flight (the engine reads this)
obs.post(ev)           # world state: Spacetime observation (batched every 100 ms; ball_dead flushes at once)
trk.post(g, cam, t, pos_m=(x, y, z), px=(u, v), conf=0.9)   # down-sampled to 10 Hz per camera
```
`trophy.world` calls the reducers `post_observations(batch_json)` and `post_track_samples(batch_json)` (one JSON-array string argument; HTTP body `["<json>"]`) at `$SPACETIME_URI/v1/database/$SPACETIME_MODULE/call/<reducer>` with `Authorization: Bearer $SPACETIME_VISION_TOKEN`. It never blocks or raises on the hot path: if Spacetime is down it drops and counts (`writer.dropped`). Until the module lands (P1), pass `RecordingClient()` to test offline.

## Dev
```bash
cd packages/py-trophy
uv sync
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```
