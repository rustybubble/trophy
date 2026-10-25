# Licenses: code, models, data and services

This lists **candidates and adopted components**. When you adopt one, add its revision and where it's used, and keep the required notices. Code, weights and media have separate terms. See [reuse and media guidance](rules-compliance.md).

| Component | License / terms | Use this weekend | Status |
|---|---|---|---|
| subatomic-hamster/replay @ `2db92c0` | MIT ("Copyright (c) 2026 Replay") | Player and auth code to adapt; **never** `docs/media/` or `samples/real/` (private game footage) | candidate |
| courtcam @ `b2f5ff5` | MIT (core). The `[yolo]` extra pulls in AGPL ultralytics, so **don't install it** | Calibration (`calibrate`, `camera_calibration`), basketball make/miss; **don't redistribute its `docs/demo.gif`** | candidate |
| BlurBall (cogsys-tuebingen) @ `2f0f549` | MIT code; **weights license unstated** (issue #2) | Ping-pong ball tracker; the user decides about public-demo use; no redistribution | candidate |
| RF-DETR (Nano–Large) | Apache-2.0 (XL/2XL/Atto–Pico are PML) | People and ball detection (SHOULD) | candidate |
| roboflow/trackers, supervision 0.30.9 | Apache-2.0 / MIT | Tracking | candidate |
| rtmlib 0.0.16 | Apache-2.0 | Pose with feet (SHOULD) | candidate |
| aiortc 1.15.0, PyAV 17.1.0 | BSD-3 / BSD-3 (FFmpeg components LGPL/GPL by build) | WebRTC ingest, only if needed | candidate |
| SpacetimeDB 2.13 | BSL 1.1 for the server (check current terms) / client SDK license per npm | Shared world state | candidate |
| Factory Droid SDK | Factory terms | House-rule compiler | candidate |
| Cartesia, Anthropic | Each provider's API terms | Voice; the Claude voter and answers | candidate |
| Rulebook text (ITTF, USA Pickleball, FIBA/NFHS, BWF, FIVB) | Each publisher's terms | Scraped only from public pages, quoted briefly with links and attribution | candidate |
| CC BY clips (`docs/plan/clip-library.md`) | CC BY (credits in `data/clips/credits.json`) | Development, the backup demo and labels | candidate |
| TT3D raw dataset (Gossard & Ziegler, Uni Tübingen; Nextcloud share `SCKq85JZEmKoC6J`) | Code MIT; **dataset license unstated** | Preloaded two-view game (`data/local/clips/library/tt3d_game_00`, gitignored) for local evaluation and the demo on this Mac; 200 Hz 3D ground truth for accuracy checks. Never redistributed; ask the authors before any publication | adopted locally |
| 2015 Edmonton Open final, YouTube `D-FHYCRTdEc` + `YSzOgrITjJI` (Edmonton Table Tennis Club uploader) | **Standard YouTube license** | Preloaded two-angle game (`data/local/clips/library/edmonton2015`, gitignored), local demo only. Not for the public video or any publication without the uploader's permission | adopted locally |
| OpenTTGames | CC BY-NC | Evaluation only | optional |
| Pillow 13.0.0 | HPND/PIL license (see installed Pillow distribution notices) | Local source-frame crops and storyboard sprites | adopted in py-trophy; no third-party source copied |
| FFmpeg (locally installed executable; tested 7.1 via existing imageio-ffmpeg package) | Build-dependent LGPL/GPL; tested libx264 build is GPL | Recorder HLS and private replay clip encoding | executable is not vendored or redistributed; install an appropriately licensed build on each demo machine |
| Replay `packages/tv-core` (`types`, `follow`, `clock`, `retry`, `display`, `replays`) @ `2db92c0` | MIT, "Copyright (c) 2026 Replay" (notice in `apps/watch/src/vendor/tv-core/LICENSE`) | Trophy Watch: the media clock (others vendored for later features) | adopted (vendored unchanged) |
| hls.js 1.6.19 | Apache-2.0 | Trophy Watch: HLS playback of recorder archives | adopted (npm) |
| qrcode 1.5.4 | MIT | Dashboard join QR | adopted (npm) |

## Recorded-video analysis prototype

`spikes/serve-analysis` preserves source notices and provenance from the local
prototype. Weights, SMPL assets, footage and generated participant images are not
redistributed in this branch.

| Component | Source / revision | License and local use |
| --- | --- | --- |
| BlurBall source | `cogsys-tuebingen/blurball` @ `2f0f5496f7ba4b5b1a36790749935121b2ce972d` | MIT; source-only snapshot in `vendor/blurball`, checksums in `vendor/UPSTREAM.json`; checkpoint terms remain unstated |
| 4D Humans source | `shubham-goel/4D-Humans` @ `efe18deff163b29dff87ddbd575fa29b716a356c` | MIT; optional HMR2 network code in `vendor/4D-Humans`; separate SMPL/model terms still apply |
| RacketVision source | `OrcustD/RacketVision` @ `c44af2a08524d3cb54d818f19686f4cdea4d2793` | MIT; reference/research source in `vendor/racketvision`; no example imagery included |
| E2E-Spot GSM source | `jhong93/spot`, attribution retained in `vendor/e2e_spot/gsm.py` | BSD-2-Clause embedded GSM notice plus upstream BSD-3-Clause license; temporal serve model |
| E2E-Spot published initialization | `jhong93/e2e-spot-models` @ `10d07a4fb01f2eb76785e15552e5648bf0793509` | Downloaded separately with SHA-256 verification; provenance and separate weight terms in `SERVES.md` |
| Extended OpenTTGames annotations | `moamal01/table_tennis_data` @ `36471a76b969a0340df59258a813bf8214e68e7c` | CC BY-NC-SA 4.0, acquired separately for serve research/training; no media/annotations or derived checkpoint redistributed here |
| Three.js | 0.180.0; asset URLs/checksums in `web/replay/ASSETS.json` | MIT; `web/replay/THREE-LICENSE.txt` accompanies the vendored renderer |
