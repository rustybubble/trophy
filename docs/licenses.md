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
| Cartesia, Anthropic, Google Gemini, Bitdeer AI Model Studio, Moss, Apify | Each provider's API terms | Voice, voters and answers, rulebook index and actor | candidate |
| Rulebook text (ITTF, USA Pickleball, FIBA/NFHS, BWF, FIVB) | Each publisher's terms | Scraped only from public pages, quoted briefly with links and attribution | candidate |
| CC BY clips (`docs/plan/clip-library.md`) | CC BY (credits in `data/clips/credits.json`) | Development, the backup demo and labels | candidate |
| OpenTTGames | CC BY-NC | Evaluation only | optional |

## Adopted for the local two-phone demo (2026-10-24)

- **Prior local Trophy prototype** (`/Users/mudu/Developer/calhacks`): selectively adapted the model adapter, camera math, pose retargeting/smoothing, procedural connected mesh and skinned avatar code. The phone footage, samples, caches and other vendor/model directories were not vendored. File roles and changes are recorded in `docs/tt-demo.md`.
- **BlurBall code @ `2f0f5496f7ba4b5b1a36790749935121b2ce972d`**: only the unmodified architecture and YAML configuration are under `services/flight/vendor/blurball`, with its MIT notice. Architecture SHA-256 `6d147b2f372cf24a080bdcb00aadcc26beec37d2279cf5d3ace42d6702eb8c8a`; config `6c6501405d5d0165be43d9b215b2b5b12dc8eb5c79fba7740d4633b800152e0f`. Official checkpoint remains ignored; hash `3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`. **Checkpoint terms remain unstated; only local private evaluation occurred. Public use needs user approval; no redistribution.** Official source: https://github.com/cogsys-tuebingen/blurball.
- **Three.js 0.180.0**, MIT: locally bundled in `apps/tt-demo/vendor`, preserving `THREE-LICENSE.txt` and upstream asset checksums. No CDN needed during playback.
- **MediaPipe 1.1.1** (Apache-2.0 code): local CPU Pose Landmarker Full float16 v1 and Hand Landmarker Full float16 v1; official Google task assets, hashes/URLs in `tools/extract_tt_poses.py` and local reports. No downloaded model asset is versioned or rehosted. Model outputs are inferred landmarks, not calibrated metric truth. Documentation: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker and https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker.
- **User-supplied original footage**: `data/ttClips`, local processing authorization from this request. SHA-256/source metadata live in `data/local/tt-demo/footage-manifest.json`. Preview transcodes, crops, avatars, audio and derived tracking remain in ignored `data/local`. No publishing or participant filming occurred.
- **ITTF Statutes 2026**: copyrighted source cached locally for rule reference, with version/hash manifest in `docs/rules/source-manifest.json`. No PDF/full extracted rulebook is versioned. HMO retrieval returned 403; it was not read. The spec uses rule IDs and paraphrases, with brief source references.
