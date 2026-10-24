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
| `moss` 1.21.0 (PyPI, Moss SDK) | Moss SDK license / Moss API terms (docs.moss.dev) | `services/rules`: the one rules index `trophy-rules-v1` (A3 Part 2) | adopted 2026-10-24 |
| `anthropic` 2.3.0 | MIT | `services/rules` `/ask` answers (A3 Part 2) | adopted 2026-10-24 |
| `apify` 4.1.0, `crawlee` 1.11.0, `apify-client` 3.3 | Apache-2.0 | `actors/rulebook-scraper`; dataset pulls in `services/rules` | adopted 2026-10-24 |
| `pypdf` 6.21.2, `beautifulsoup4` 4.15, `pyyaml` 6 | BSD-3 / MIT / MIT | PDF and HTML text in the actor; `check-pack` reads packs | adopted 2026-10-24 |
| Rulebook text: ITTF Laws (via Table Tennis England's 2026-27 PDF), 2026 USA Pickleball Official Rulebook (via Pickleball Canada's PDF), FIBA Official Basketball Rules 2024 | Each publisher's copyright; ITTF states reproduction is encouraged with the source mentioned; USA Pickleball and FIBA: quoted for rule lookup with attribution | Scraped from public PDFs only (robots respected, no 403 evasion); full text in `data/local/` (gitignored); ≤ 25-word quotes with a link; `source` + `license_note` on every item | proposed 2026-10-24, awaiting the user's approval of `sources.json` |
| Rulebook text (BWF, FIVB, NFHS) | Each publisher's terms | Not scraped this weekend | not used |
| CC BY clips (`docs/plan/clip-library.md`) | CC BY (credits in `data/clips/credits.json`) | Development, the backup demo and labels | candidate |
| OpenTTGames | CC BY-NC | Evaluation only | optional |
