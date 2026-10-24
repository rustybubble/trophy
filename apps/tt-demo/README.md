# Recorded two-camera rally room

Static local UI served by `python tools/tt_demo.py` at `http://127.0.0.1:8765/` after clip preparation. No build step, hosted fonts, CDN, or network inference is required for playback.

- Both source views share seek, play/pause, speed, frame inspection, point selection, and evidence bookmarks. Actual source presentation timestamps are displayed separately from the shared playback clock.
- Detector coordinates in original-image pixels are mapped to the browser proxy resolution. Gaps break the trail. A detector score is never displayed as ruling confidence.
- Paused close-ups lazily decode `/original/{camera}` at full source resolution; playback crops use the preview and are labeled as proxies. Click a source view to choose the crop center, or allow a detected ball to center it.
- Real footage and synthetic fixtures use separate referee state. The UI advances `/api/advance` at rally ends and only speaks decisions returned by the referee; seeking/replaying does not locally invent or duplicate points.
- Player/official resolution calls the authoritative API, updates the score, and retains the manual decision in history. Corrections use the same backend path. The local browser voice is explicitly a development fallback, not Cartesia.
- Metric calibration and capture-time synchronization remain distinct from playback alignment. Manual camera offset is available in Session setup. Missing 3D ball positions stay hidden; avatar motion is explicitly estimated and is never used as rule evidence.
- Continuous procedural skinned bodies use a grid shader bound to rest-surface coordinates. The surface deforms with the rig. It does not infer a palm, face, paddle orientation or missing trajectory.

`vendor/` contains unmodified Three.js 0.180.0 files and MIT license copied from the prior local prototype. `vendor/ASSETS.json` preserves upstream URLs and hashes. `avatar-high.json` and `avatar.js` derive from the local Trophy prototype's procedural mesh/rig, with a rest-surface grid shader added here. These assets contain no recorded people or third-party character mesh.

Keyboard: Space toggles playback; Left/Right step one primary-source frame when focus is outside a form control. All actions also have labeled buttons. The layout adapts to mobile; failed media or WebGL leave source-review controls available.
