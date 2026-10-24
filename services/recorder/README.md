# Recorder

Reads every retained `frames:{cam}` entry in order and records video locally under
`data/local/recordings/{game}/{cam}/`. Video never enters Spacetime. Start before the cameras.

```bash
uv sync --frozen --project services/recorder
uv run --frozen --project services/recorder python -m recorder --redis-url redis://127.0.0.1:6379/0
```

Install FFmpeg separately and put it on PATH, or set `TROPHY_FFMPEG` to its executable.
`--encoder auto` tries actual one-frame encoding, starting with portable `libx264`; it then tries NVENC,
Quick Sync, AMF and VideoToolbox. Use `--encoder h264_qsv` on the Windows demo PC after checking that it
works there. No Windows performance result is claimed by the Mac validation. The startup log names the
encoder actually used. `--fps 30` is the default; supported range is 1–60.

The archive contains:

- `index.m3u8`, `init.mp4`, `seg_000000.m4s`, etc.: H.264 fMP4 HLS with 2-second segments. The event
  playlist retains the full game and is atomically replaced. `end_game` on `ctl:engine` drains pending
  frames before finalization; Ctrl-C/SIGTERM also writes the ENDLIST. `--idle-exit 3` is useful for smoke tests.
- `meta.json`: camera size, actual encoder, FPS, game time at media PTS zero, duration, closed/error status,
  source-frame count, sequence gaps and held-video-frame count.
- `index.jsonl`: one row per original frame: `seq`, `t_game_s`, segment, media `pts`, source JPEG file,
  sync error, source and `held_frames_before`. It is not a fabricated list of tracking observations.
- `frames/*.jpg`: exact original bus JPEGs for voter crops and precise human labelling. These are extra
  disk storage by design; keep the archive local and remove it manually when it is no longer needed.
- `sprite_{n}.jpg` and `sprite.json`: 10×10 sheets of 160×90 thumbnails every two seconds, updated during play.
  Capture gaps leave empty storyboard cells. Sprites use recording-relative time, anchored by `t0_game_s`.
- `tracks_ball.jsonl`, `tracks_players.jsonl`: original `trk:*` samples plus Redis stream ids. Missing-ball
  samples remain missing. Camera calibration is copied into `calibration.json` when available.

CFR video holds the last picture over capture gaps; the index records the holds. Evidence crops always use
actual source frames. Backward timestamps, camera-size changes and gaps over 30 seconds fail explicitly.
Existing archives are never overwritten. Restarting a recorder for the same game requires a new game id;
resume after a crash is not implemented. No audio is captured by this recorder.

```bash
uv run --frozen --project services/recorder pytest -q
```

Codec integration tests require an installed FFmpeg (otherwise those tests are explicitly skipped).
Tests cover HLS decoding/cutting, source indexing, capture gaps, duplicate frames, sprites, track persistence,
calibration, end-game backlog draining and archive path isolation.
