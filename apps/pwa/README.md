# Capture PWA (owner A)

**Stack:** Vite + React + strict TypeScript (+ Three.js/Spark where 3D is needed), SpacetimeDB TypeScript SDK. Built to `dist/` and served by Caddy.

## Responsibilities
- Device-test page **first** (lens labels, `getSettings()` fps/resolution, recorder MIME types, WebRTC codecs, storage, wake lock, beep).
- Join by QR, landscape only, one camera track: WebRTC 720p to ingest **and** MediaRecorder 1080p at about 12 Mbps in 2 s chunks → OPFS (worker) → signed GCS upload.
- AudioWorklet onset detector (AEC/NS/AGC off). Web Audio beep (unlocked on Join; `navigator.audioSession.type='playback'`) + full-screen flash; `navigator.vibrate` on Android only.
- Challenge button + "Trophy, challenge" (Deepgram) + crossed-arms gesture (server-side). Calls arrive through the SpacetimeDB TypeScript SDK subscription.
- Tap-corners calibration UI (suggested corners from courtcam/TT3D, draggable).
