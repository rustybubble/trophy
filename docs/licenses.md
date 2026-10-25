# Licenses: code, models, data and services

This lists **candidates and adopted components**. When you adopt one, add its revision and where it's used, and keep the required notices. Code, weights and media have separate terms. See [reuse and media guidance](rules-compliance.md).

| Component | License / terms | Use this weekend | Status |
|---|---|---|---|
| subatomic-hamster/replay @ `2db92c0` | MIT ("Copyright (c) 2026 Replay") | Player and auth code to adapt; **never** `docs/media/` or `samples/real/` (private game footage) | candidate |
| courtcam @ `b2f5ff5` | MIT (core). The `[yolo]` extra pulls in AGPL ultralytics, so **don't install it** | Calibration (`calibrate`, `camera_calibration`), basketball make/miss; **don't redistribute its `docs/demo.gif`** | candidate |
| BlurBall (cogsys-tuebingen) @ `2f0f549` | MIT code (© 2023 NTT Communications; `LICENSE.md` kept); **weights license unstated** (issue #2) | Live ping-pong ball detector (`services/flight/flight/blurball.py`). The network source is vendored unmodified at `services/flight/vendor/blurball`. The weights stay in the ignored `weights/blurball_best` (or `$TROPHY_BLURBALL_WEIGHTS`), pinned by SHA-256 `3545206c…`, never committed, never redistributed; the user accepted using them for the demo (D-30) | adopted (code); weights local only |
| PyTorch 2.5.1 | BSD-3 | BlurBall inference on MPS (`services/flight` extra `blurball`) | adopted |
| RF-DETR (Nano–Large) | Apache-2.0 (XL/2XL/Atto–Pico are PML) | People and ball detection (SHOULD) | candidate |
| roboflow/trackers, supervision 0.30.9 | Apache-2.0 / MIT | Tracking | candidate |
| rtmlib 0.0.16 | Apache-2.0 | Pose with feet (SHOULD) | candidate |
| aiortc 1.15.0, PyAV 17.1.0 | BSD-3 / BSD-3 (FFmpeg components LGPL/GPL by build) | WebRTC ingest, only if needed | candidate |
| SpacetimeDB 2.13 | BSL 1.1 for the server (check current terms) / client SDK license per npm | Shared world state | candidate |
| Factory Droid SDK | Factory terms | House-rule compiler | candidate |
| Cartesia, Anthropic, Google Gemini, Bitdeer AI Model Studio, Moss, Apify | Each provider's API terms | Voice, voters and answers, rulebook index and actor | candidate |
| Rulebook text (ITTF, USA Pickleball, FIBA/NFHS, BWF, FIVB) | Each publisher's terms | Scraped only from public pages, quoted briefly with links and attribution | candidate |
| CC BY clips (`docs/plan/clip-library.md`) | CC BY (credits in `data/clips/credits.json`) | Development, the backup demo and labels | candidate |
| OpenTTGames | CC BY-NC | Evaluation only | optional |
| Pillow 13.0.0 | HPND/PIL license (see installed Pillow distribution notices) | Local source-frame crops and storyboard sprites | adopted in py-trophy; no third-party source copied |
| FFmpeg (locally installed executable; tested 7.1 via existing imageio-ffmpeg package) | Build-dependent LGPL/GPL; tested libx264 build is GPL | Recorder HLS and private replay clip encoding | executable is not vendored or redistributed; install an appropriately licensed build on each demo machine |
