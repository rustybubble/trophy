# Trophy: PWA multi-phone capture research

Researched 2026-10-22. Current shipping browsers: **iOS Safari 27.0.x** (Safari 27 was announced at WWDC26 in June 2026; a WebKit bug comment on 2026-10-06 references "Safari 27.0.1"). Many players will still be on **iOS 26.x**, and a few on 18.x. The Android baseline is **Chrome 15x** (caniuse lists 156).

Confidence tags used below:
- **[V]**: verified from a cited source.
- **[C]**: community or bug-tracker report.
- **[E]**: my estimate or prior knowledge. Test it on a device during hour 1.

---

## 0. TL;DR architecture

```
 Travel router (GL.iNet-class, 5 GHz, client isolation OFF, laptop gets a static DHCP lease)
   |
   +-- Laptop (GPU) --------------------------------------------------------------
   |     Caddy/uvicorn HTTPS on 443 with a REAL cert (own domain via DNS-01, or local-ip.sh / traefik.me)
   |     FastAPI app:
   |       /           PWA (static)
   |       /ws         control WebSocket: join, clock sync, calls, challenges, health
   |       /offer      WebRTC signaling -> aiortc  (live path A)   [or LiveKit server + Python SDK]
   |       /frames     WebSocket binary JPEG, latest-frame-wins     (live path B, the fallback; build it FIRST)
   |       /upload     resumable chunked upload (tus or simple PUT ?offset=)
   |     Model workers (PyTorch) read the newest frame per camera; post-game pipeline aligns uploads
   |
   +-- Phone 1..4: Safari or Chrome tab, opened from a QR code (do not "Add to Home Screen" for v1)
         one getUserMedia track (rear, landscape, 1920x1080 @ 30, or 60 where available)
           ├─ MediaRecorder (H.264 MP4 on iOS, MP4 or WebM on Android, ~12 Mbps, timeslice 2 s) -> OPFS -> upload after the game
           ├─ live: RTCPeerConnection sender, scaleResolutionDownBy so ~720p, maxBitrate ~2.5 Mbps   (path A)
           │        or canvas grab at 640x360 @ 10-15 fps -> JPEG -> WS, with a timestamp header   (path B)
           └─ control WS: NTP-style ping every 2 s; receives "CALL" -> beep + full-screen flash + vibrate (Android only)
```

Key decisions:
1. **Phones are dumb cameras.** All inference runs on the laptop GPU. On-device ML is optional at most (Section 6).
2. **Use separate live and archival paths from one camera track.** The live path is low-res and lossy. MediaRecorder captures the full-quality local copy, which is uploaded after the game.
3. **Get HTTPS with a publicly trusted cert, not a self-signed one.** iOS will not accept self-signed certs for wss:// even after you click through the warning.
4. **Use your own timestamps and clock sync.** Do not rely on RTP or RTCP. Run an app-level NTP over WebSocket, add a one-time visual "timecode" calibration per phone, and align recordings in post using audio or visual events.
5. **No haptics on iOS.** iOS has no Vibration API, and the `<input switch>` haptic hack is dead as of iOS 26.5. Use a loud Web Audio beep plus a full-screen color flash, and add `navigator.vibrate` only on Android.

---

## 1. Camera capture

### 1.1 Resolution and frame rate

| | iOS Safari (26/27) | Android Chrome |
|---|---|---|
| Max resolution via getUserMedia | **4K works.** Addpipe recorded 2160p in iOS Safari, and its iOS recorder lists 3840x2160 among accepted resolutions. Older devices (e.g., the XS front camera) can't do 4K [V] | **4K works on flagships.** Addpipe recorded 2160p on a Galaxy S21 FE in Chrome [V]. Many mid-range phones cap at 1080p [E] |
| 60 fps | Generally available at 720p and 1080p on recent iPhones [E/C]. A WebKit thread says iOS/iPadOS capture and WebRTC are effectively capped at 60 fps [C] | Device-dependent. Chrome only offers fps ranges the Camera2 HAL advertises, so many devices top out at 30 [C/E] |
| 120/240 fps (slow-mo) | **Not available.** No evidence getUserMedia exposes the 120/240 slow-mo formats. Apple documents those as native AVCaptureDevice formats, and the highest ones need HEVC [V/C] | Not available in practice [E] |
| frameRate constraints | **Buggy.** `max` frameRate > 16 was ignored. The fix (305858@main, Jan 2026) still reproduced on Safari 26.5 and 27.0.1 per comments on 2026-10-06 [V]. Older bugs: `min`/`exact` erroring, applyConstraints not changing fps [C] | Works as specified. Use `ideal` [V] |
| `resizeMode` | Not reliably supported [E] | Supported. `resizeMode: 'none'` gives native sensor modes rather than downscaled crops [E] |

**What to do:** request `ideal` values only, then read back `track.getSettings()` and `getCapabilities()`, then log both to the server. Don't hard-fail on fps.

```js
const stream = await navigator.mediaDevices.getUserMedia({
  audio: true,                       // needed for audio-based post-sync; see 4.3
  video: {
    facingMode: { ideal: 'environment' },
    width: { ideal: 1920 }, height: { ideal: 1080 },   // LANDSCAPE dims; see the orientation gotcha
    frameRate: { ideal: 60 },
  }
});
const [track] = stream.getVideoTracks();
report({ settings: track.getSettings(), caps: track.getCapabilities?.(), label: track.label });
```

### 1.2 Choosing the rear, ultra-wide, or wide lens

- **iOS:** after permission is granted, `enumerateDevices()` returns labeled virtual and physical devices. Since iOS 16.4, `facingMode:'environment'` gives a virtual multi-camera ("Back Triple Camera" / "Back Dual Wide Camera") that starts at the **widest** lens (0.5x) and **auto-switches lenses** while cropping to keep the field of view. That is a regression since iOS 17, still open (WebKit 262416, NEW) [V/C]. Scanbot's docs select `"Back Ultra Wide Camera"` by label [V], so physical lenses are addressable by label. Labels are **localized**, though, so match on `/ultra wide/i` with a fallback [C].
  - For a referee camera on a tripod, the ultra-wide FOV is good. Lens switching mid-game, however, causes FOV and focus jumps that ruin calibration. **Pin a physical device** ("Back Camera" = wide, or "Back Ultra Wide Camera") by `deviceId` instead of using the virtual triple camera. Apple Forums thread 776460 (iOS 18.3, iPhone 15 Pro) reports switching even with `deviceId` + `zoom:1` on the virtual device, with no answer [C]. A WebKit engineer suggested `{zoom:false, facingMode:'environment'}` as an experiment [C].
  - **Two cameras at once is impossible on iOS:** a second getUserMedia mutes the first track [C]. Open the camera once and `clone()` the track if needed.
- **Android:** labels look like "camera2 0, facing back". Whether the ultra-wide appears as a separate device depends on the OEM exposing its physical cameras to Camera2. Some Samsungs expose it, and Pixels expose only the logical camera [E]. Fall back to whatever `facingMode: environment` gives.

### 1.3 Focus and exposure lock

| Constraint | iOS Safari | Android Chrome |
|---|---|---|
| `focusMode`, `focusDistance`, `pointsOfInterest` | **No.** Dynamsoft (updated Jul 2026): "iOS Safari does not expose focus constraints" [V-vendor] | Yes: `continuous`/`manual`/`single-shot`, plus `focusDistance` [V-vendor] |
| `exposureMode`, `exposureCompensation`, `exposureTime`, `iso` | No [E] | Yes. Chrome Canary lists focusMode/exposureMode as supported [V] |
| `whiteBalanceMode` | Yes (iOS 16.4 getSupportedConstraints) [V] | Yes |
| `zoom` | Yes [V] | Yes, on many devices |
| `torch` | Works since roughly iOS 17.5. getSettings readback bug fixed Dec 2024 [C] | Yes |

On iOS you cannot lock exposure. Expect auto-exposure pumping when players in white jerseys fill the frame. Mitigations: shoot with the sun behind the camera, use a fixed wide lens, and do exposure normalization server-side.

### 1.4 ImageCapture (high-res stills on a call)

- Safari: `takePhoto`, `getPhotoCapabilities`, and `getPhotoSettings` since **18.4**; `grabFrame` since **26** [V, MDN BCD]. Chrome Android has had all of them since 59-61 [V].
- **Gotcha:** `takePhoto()` reconfigures the capture session. Safari 27 had to add a fix that queues `takePhoto`/`applyConstraints` "avoiding concurrent capture session reconfiguration" [V]. Expect a **stutter in the live stream and MediaRecorder** when you snap a 12 MP still. For "evidence frames", pull the frame from the 1080p recording in post instead.

### 1.5 Wake lock, fullscreen, and orientation

- **Screen Wake Lock:** Safari 16.4+ in the browser. It is **broken in Home Screen web apps until iOS 18.4** (WebKit 254545) [V]. Chrome Android has had it since 84 [V]. Re-request on `visibilitychange` because the lock is released whenever the page is hidden. Also tell users to **turn off Low Power Mode**, which shortens auto-lock and throttles the device [E].
- **Fullscreen:** caniuse marks iOS Safari 12-27.2 as **partial**. On iPhone, Element.requestFullscreen is not available. It works on iPad, and on iPhone only `<video>` native fullscreen is available, which takes over the UI [V partial + E for the iPad-only detail]. For a capture UI this is fine: Safari's minimal UI in landscape is enough. Fully chrome-less requires Add to Home Screen. In iOS 26, every site added to the Home Screen opens as a web app by default [V].
- **`screen.orientation.lock()`:** **not supported** in Safari or iOS Safari, any version [V, MDN BCD]. Chrome Android has supported it since 38 but requires fullscreen first [V/E].
- **Orientation gotcha (iOS 26.6 regression, Apple Forums 844826 / WebKit 323550):** portrait-dimension constraints return an unrotated 1920x1080 buffer, `getSettings()` lies, and the MP4 **`displaymatrix` rotation flag is now missing**, so recordings play sideways [C]. **Fix:** request landscape dimensions, mount phones in landscape, disable iOS Portrait Orientation Lock, show a "rotate to landscape" overlay, and **handle frame width/height per frame server-side**, because a bumped tripod can flip it mid-game. The same poster suggests listing **H.264 High before Baseline** in your MIME candidates, because Baseline looked soft [C].

### 1.6 Background and lifecycle

- If the tab is backgrounded, the screen locks, or a call comes in, the **track mutes or ends**. Listen for `track.onmute`/`onended` and `visibilitychange`, and re-acquire the stream [C]. Never call getUserMedia twice concurrently: the second call mutes the first [C]. `history.pushState` muted the track on iOS 17.4.1 [C], so **keep v1 as a single-page app with no router**.
- Home Screen (standalone) apps have a history of **re-prompting for camera permission** on route changes [C]. That is another reason to run in a plain Safari tab.

---

## 2. Recording

### 2.1 MediaRecorder codecs

| | iOS Safari | Android Chrome |
|---|---|---|
| Containers/codecs | MP4 with H.264/AAC (since 14.3). **18.4 added** WebM (VP8/VP9 + Opus), HEVC, AV1 (on hardware with AV1 support), ALAC/PCM audio [V-secondary]. 26 added ALAC/PCM in MP4 [V] | WebM (VP8/VP9/H.264/AV1). **MP4 (H.264) since Chrome 126** (June 2024) [V-secondary]. HEVC in MP4 behind a flag [V] |
| Default bitrate | 10 Mbps. `videoBitsPerSecond` is respected within about 10-15% (1.5/7/14 → 1.57/6.75/12.24 Mbps) [V, Addpipe 2026-04] | Default 2.5 Mbps. **Often ignores the requested bitrate:** 1080p used about 4x expected; 4K default 2.9 Mbps [V, Addpipe] |
| Known bugs | 18.4 beta: WebM recordings rotated 90°, MP4 playback failures [C]. 26.6: missing rotation metadata [C]. Long recordings crashing or reloading the page (older reports) [C] | |

**Recommendation:**
- iOS: `video/mp4;codecs=avc1.640028` (H.264 High) at **12 Mbps for 1080p30, or 20 Mbps for 1080p60**.
- Android: `video/mp4;codecs=avc1` if `isTypeSupported`, else `video/webm;codecs=vp9`.
- Pick the type by probing an ordered list.
- Avoid HEVC/AV1. Encoder availability varies by device, and they gain nothing for a hackathon.
- **Record 1080p, not 4K.** 4K plus WebRTC encode plus a lit screen leads to thermal throttling in about 10-15 min, especially in sun [E], and the upload files are 4x larger.

```js
const types = ['video/mp4;codecs=avc1.640028,mp4a.40.2','video/mp4;codecs=avc1','video/mp4','video/webm;codecs=vp9,opus','video/webm'];
const mimeType = types.find(t => MediaRecorder.isTypeSupported(t));
const rec = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 12_000_000, audioBitsPerSecond: 128_000 });
rec.ondataavailable = e => opfsWorker.postMessage({ seq: n++, blob: e.data, t: syncedNow() });
rec.onstart = () => send({ type: 'rec_start', serverTime: syncedNow() });  // coarse; refine in post (4.3)
rec.start(2000); // 2 s chunks. Concatenation in order = valid (fragmented) file; single chunks after #0 are NOT standalone
```

Post-process every upload with `ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4`. This remuxes the fragmented output into a seekable file, and you can apply `-metadata:s:v rotate=` or a transpose filter if needed.

### 2.2 WebCodecs (for frame-exact control)

- `VideoEncoder`/`VideoDecoder` have been in Safari since **16.4** [V]. AudioEncoder/AudioDecoder arrived in **Safari 26** [V]. `latencyMode:'realtime'` works on Safari but **may drop frames** (WebKit 263606) [C]. Use `avc: {format:'annexb'}` for streaming so that every keyframe carries its SPS/PPS [V, W3C registration].
- **MediaStreamTrackProcessor** has been in Safari **18+, worker-only**. You must `postMessage` the track to a DedicatedWorker. Chrome exposes it on Window (partial) [V, MDN BCD]. `VideoTrackGenerator` is also in Safari 18 [V].
- `VideoFrame.timestamp` from MSTP is **not guaranteed to be wall-clock or capture time** across browsers. The spec only requires ordering, and Chrome camera timestamps started at 0 in one report [C]. Calibrate it empirically (Section 4.2).
- A WebCodecs pipeline is an option for the live path: worker MSTP → VideoEncoder H.264 → WebSocket → PyAV decode. You get exact per-frame metadata and about 2 Mbps for 720p30. It is more code and more Safari edge cases than either of the paths in Section 3, so **save it as a stretch goal**.

### 2.3 Per-frame timestamps

- `requestVideoFrameCallback` has been in Safari since **15.4** and Chrome since 83 [V]. The metadata has `presentationTime`, `expectedDisplayTime`, and `mediaTime`. `captureTime`/`receiveTime`/`rtpTimestamp` are specced for local and remote WebRTC sources, but **WebKit removed captureTime from its own tests as "too unreliable"** (WebKit 266356) [V]. Use `metadata.captureTime ?? (metadata.presentationTime - pipelineOffset)`. Treat it as ±1 frame, and calibrate `pipelineOffset` per phone with the timecode trick (4.2).

### 2.4 Storage and upload

- **Quota:** Safari 17+ gives an origin up to **60% of disk** in the browser app (80% across all origins). Home Screen apps get the same quota. Eviction is LRU under storage pressure or after inactivity. `persist()` is granted heuristically, e.g., if the site is a Home Screen app [V, WebKit storage policy]. A 1080p @ 12 Mbps recording is about **90 MB/min**, so a 20-min game is about 1.8 GB per phone. That fits on most phones, but check `navigator.storage.estimate()` before starting.
- **OPFS** has been on iOS since 15.2. `createSyncAccessHandle` is worker-only [V]. Append each chunk from a worker and flush every N chunks. **Do not keep Blobs in a JS array**, because long recordings have crashed Safari tabs [C].
- **Upload:** the page must stay in the foreground, because iOS has no Background Fetch or Background Sync. Use resumable chunked PUTs (`/upload?cam=2&offset=…`, or tus-js-client) at 4-8 MB per request. On a 5 GHz travel router, expect about 100-300 Mbps LAN, so 1.8 GB takes about 1-3 min per phone; upload phones **one at a time** [E]. Optionally trickle-upload during play at low priority, but **throttle it**, because it competes with the live stream on the same radio.

---

## 3. Streaming phones to the laptop

### 3.1 Options compared

| Option | Latency on LAN | Python frames | Effort | Notes |
|---|---|---|---|---|
| **B. WebSocket JPEG, latest-frame-wins** | about 80-200 ms [E] | trivial: `cv2.imdecode` | **2-3 h** | 640x360 @ 15 fps ≈ 35 KB/frame ≈ 4 Mbps per phone; 4 phones ≈ 17 Mbps, fine on 5 GHz. TCP head-of-line blocking is bounded by sending the next frame only after an ack, or when `ws.bufferedAmount===0`. Per-frame timestamps go in your own header. **Build this first as the safety net.** |
| **A1. aiortc (Python WebRTC) direct** | about 100-250 ms [E] | `await track.recv()` → `frame.to_ndarray(format="bgr24")` | 4-6 h | Fork `aiortc/examples/server`, which is literally browser webcam → Python OpenCV transform. VP8 + H.264 only. No simulcast receive. CPU decode (PyAV) handles 4× 720p30 fine; 1080p×4 gets tight with the GIL [E]. Low resolution confirmed stable even on a Pi [C]. |
| **A2. FastRTC (Gradio, MIT, 4.6k★)** | same as aiortc | handler receives numpy frames | 2-4 h | `Stream(handler, modality="video", mode="send-receive")`, `.mount(app)` on FastAPI gives WebRTC and WS endpoints for **your own frontend** [V]. Multi-client is undocumented [V], so test 4 phones early. |
| **A3. LiveKit self-hosted + Python SDK** | about 100-200 ms [E] | `rtc.VideoStream` async iterator; RGBA/I420/NV12 frames with conversion [V] | 4-6 h | `livekit-server --dev` (keys `devkey`/`secret`; **add `--bind 0.0.0.0`** for LAN access) [V]. You need a token endpoint, but you get a robust JS SDK, simulcast, reconnection, and adaptive stream. Best for the "polished" path. |
| **A4. MediaMTX / go2rtc** | WebRTC ingest is low; **RTSP reading in OpenCV adds 200-1000 ms** of buffering unless tuned [E] | via RTSP → `cv2.VideoCapture` (FFmpeg) | 2-4 h | MediaMTX: WebRTC/WHIP browser publish (WHIP = RFC 9725), records fMP4/MPEG-TS server-side, converts protocols [V]. go2rtc: WebRTC ingest into a pre-created empty stream; RTSP/MJPEG/WebRTC out [V]. Good for a server-side backup recording, poor for frames into PyTorch. |
| **A5. VDO.Ninja + Raspberry Ninja** | 30-200 ms claimed [V-maintainer] | `--framebuffer STREAMID` puts raw BGR frames in shared memory for numpy/OpenCV; `--record-room` records every participant without transcoding [V] | 1-2 h to demo | Fastest path to a working 4-phone rig. Check the license (LICENCE.md) and expect a heavy UI to strip. Good for a **Friday-night spike**. |
| mediasoup / Pion / simple-peer / PeerJS | | | | mediasoup and Pion are SFU building blocks. They solve fan-out, which you don't need, and still leave the Python bridge to build. simple-peer and PeerJS are P2P browser↔browser and don't help get frames into Python. **Skip.** |

**Recommendation:** ship **B on Saturday morning**, then upgrade to **A1 (aiortc) or A3 (LiveKit)** if time permits. Choose aiortc if you want one Python process. Choose LiveKit if you want robustness and simulcast. Both paths share the same control WS and the same recording code, so this is low-risk.

### 3.2 WebRTC details that bite

- **Codecs:** iOS sends H.264 (hardware) or VP8. Android Chrome only offers H.264 when the device has a whitelisted hardware encoder, and `setCodecPreferences` filters codecs but cannot add them [C]. **Check `RTCRtpSender.getCapabilities('video')`. Prefer H.264 on iOS and VP8 on Android**, since aiortc supports both.
- **Downscale the live sender, not the track:** `sender.setParameters({encodings:[{scaleResolutionDownBy:1.5, maxBitrate:2_500_000, maxFramerate:30}]})`. The recorder still sees the 1080p track.
- **ICE on LAN:** Chrome and Safari hide host IPs behind `.local` mDNS names. A stack that doesn't resolve `.local` drops every candidate silently, as webrtc-rs did until July 2026 [C]. Once camera permission is granted, browsers expose real host IPs [E], so you should be fine, but **verify the candidates in the offer**. No TURN is needed on a single LAN.
- **Safari RTP timestamp bug (18.4.1):** H.264 RTP used a 900 kHz clock instead of 90 kHz, a duplicate of 292273 "LibWebRTCCodecs is not preserving encoder timestamps", since fixed [V]. That is one more reason **not** to build sync on RTP timestamps.
- **Old Safari H.264 issues:** a 500 kbps cap with the low-latency encoder (2022), and freezes after about 20 s on some servers [C]. Watch `getStats()` for `framesPerSecond` and `qualityLimitationReason`.
- **Safari 27 additions:** `RTCRtpReceiver.jitterBufferTarget`, `targetLatency` on receivers, and video source width/height in stats [V]. These help only browser receivers, not aiortc.

### 3.3 Latency budget (target under 500 ms from event to beep)

Capture and exposure take about 33 ms. Encode takes 10-20 ms. Wi-Fi takes 5-20 ms, with spikes. Jitter buffer and decode take 10-40 ms. Inference on 4 streams, batched, takes 20-60 ms. Decision logic takes about 10 ms. The WS message to the phone takes about 10 ms. Audio output takes 20-50 ms. **Total: about 150-250 ms typical [E].** The main risks are Wi-Fi congestion from the venue (use 5 GHz on a channel away from the venue APs) and TCP buffering in path B (mitigated by latest-frame-wins).

### 3.4 HTTPS on a LAN (getUserMedia needs a secure context)

| Approach | Verdict |
|---|---|
| **Own domain + Let's Encrypt wildcard (DNS-01) issued before device testing**, public or router-local A record `trophy.example.com → 192.168.8.10` | **Best.** Zero per-phone setup, and it works offline if the router serves the record. Get the cert tonight (Caddy with a DNS plugin, or certbot-dns-cloudflare). |
| **local-ip.sh / traefik.me** (`192-168-8-10.local-ip.sh` with a public wildcard cert you download) [V] | Good backup and zero setup. However, it needs internet for DNS, and **local-ip.sh failed to resolve when I fetched it today**, so don't depend on it alone. |
| mkcert + install the root CA on each iPhone (download profile → install → Settings → General → About → Certificate Trust Settings → full trust) | Works, but takes 2-3 min per phone and is unacceptable for "any player's phone". Fine for your own 4 test phones as a fallback. The cert needs the IP/hostname in **SAN** [C]. |
| Self-signed + click through the warning | **Breaks on iOS:** Safari rejects `wss://` to that host even after the HTTPS warning is accepted (WebKit 41419, open since 2010) [C]. |
| Cloudflare Tunnel / ngrok | Useful for serving the page and signaling only. WebRTC media still flows LAN-direct via ICE. Path B (frames over WS) would detour through the cloud and venue internet, adding 20-150+ ms and a dependency. **Avoid for media.** |

**Router gotcha:** OpenWrt and GL.iNet dnsmasq **DNS-rebind protection drops public DNS answers that point at private IPs**. That breaks nip.io, sslip.io, local-ip.sh, and your own `trophy.example.com → 192.168.x.x`. Whitelist the domain (`rebind_domain`) or disable rebind protection, or add a local DNS entry on the router [V]. Also: venue Wi-Fi usually has **client isolation**, so bring the travel router. An iPhone Personal Hotspot works as a fallback LAN (172.20.10.x), but it caps at a few clients and gets hot.

---

## 4. Clock sync

### 4.1 App-level NTP over WebSocket (do this)

- `enmasseio/timesync` (median filtering, pluggable transport) was **archived 2025-07-16** [V]. Write your own instead; it is about 40 lines:

```js
// phone: every 2 s (and 10x rapidly at join); server replies {t0, t1: serverRecv, t2: serverSend}
const t0 = performance.now(); ws.send(JSON.stringify({type:'ping', t0}));
// on pong:
const t3 = performance.now();
const rtt = (t3 - t0) - (msg.t2 - msg.t1);
const offset = ((msg.t1 - t0) + (msg.t2 - t3)) / 2;      // server_clock - phone_clock
samples.push({rtt, offset, t: t3}); keep the last ~30;
// estimate: take the 25% lowest-RTT samples; fit offset(t) = a + b*t (linear) to absorb drift
```

- Expected accuracy: **±1-3 ms** on a quiet 5 GHz LAN with min-RTT filtering, and **±5-10 ms** under load [E].
- **Phone Wi-Fi power save** causes RTT spikes of 50-300 ms when idle. Constant streaming keeps the radio awake, so it is less of an issue during a game [E].
- Use `performance.now()` (monotonic), not `Date.now()`. Safari coarsens timers to about 1 ms [E], which is fine.
- **Drift:** phone oscillators drift 10-50 ppm, which is 12-60 ms over a 20-min game. Resync continuously and use the linear fit [E].
- Server clock: `time.perf_counter_ns()` in one process, and expose it as the "game clock".

### 4.2 Per-phone capture-latency calibration ("timecode board")

The NTP offset tells you *phone clock to server clock*. It does **not** tell you when the sensor captured a frame. Camera pipeline delay is about 30-100 ms and varies by model [E]. To measure it:

1. On join, show "point camera at laptop for 3 s". The laptop shows a full-screen **QR or large digits of the server clock**, updated every vsync at 60 Hz.
2. The server decodes the QR in each received frame. `server_time_in_image` vs. the frame's phone timestamp (synced) gives `pipelineOffset` per phone, at ±8 ms (display refresh) plus rolling shutter.
3. This also measures **end-to-end live latency** per phone: compare the receive time with `server_time_in_image`.

Bonus demo: show this calibration live. "All four cameras synced to 4 ms" is a great judge moment.

### 4.3 Frame-level alignment in post

- **Audio chirp:** at game start and end, the laptop plays a 200 ms linear chirp (2-6 kHz). Cross-correlate each recording's audio track to get sample-accurate offsets, and use start plus end to estimate drift. **Gotcha:** sound travels at 343 m/s, about **3 ms per meter**. On a 28 m basketball court that is up to ±80 ms of error unless you correct for camera distance. Options:
  - Play the chirp from the court center.
  - Use the BeepBeep-style two-way method, where each phone chirps and all others record. The round trip cancels propagation and gives distances as a bonus.
  - Use **visual** sync instead (next bullet).
- **Visual sync:** use a bright flash visible to all cameras (laptop screen, phone torch via the `torch` constraint, or a clap) and detect the brightness step per frame, accurate to ±½ frame. Or use **Pose2Sim's automatic camera synchronization** (since v0.8, Apr 2024, which accepts phone video) [V]. The NeurIPS 2025 "VisualSync" method aligns unsynchronized videos with <130 ms error, which is too coarse for frame-level work on its own [V].
- **RTCP Sender Reports via aiortc:** in theory, an SR's (NTP, RTP) pair maps RTP timestamps to the sender's wall clock. In practice aiortc doesn't surface the SR's RTP timestamp in its stats, so you'd have to patch it. The sender's NTP is the phone's **system wall clock**, which is only NTP-synced by the OS to about 10-50 ms [E]. And Safari has had RTP clock-rate bugs [V]. **Don't use it.** Your own timestamps (4.1 + 4.2) beat it.

---

## 5. Feedback when a call is made

| Mechanism | iOS | Android | Notes |
|---|---|---|---|
| `navigator.vibrate` | **Never supported** (caniuse: iOS 3.2-27.2 all ✗) [V] | Yes. Needs prior sticky user activation, which the "Join" tap provides [E] | |
| `<input type=checkbox switch>` haptic hack (`ios-haptics`, `web-haptics`) | iOS 18 added switch haptics [V]. WebKit then **required user activation** for them (bug 285120, fixed Jan 2025) [V]. **iOS 26.5 patched the programmatic path entirely**; multiple projects report it dead (Flarum, Open Stage Control) [C] | n/a | **Useless for server-pushed calls.** It might still fire on a direct tap of a real switch, e.g., a haptic on the "Challenge" button styled as a switch, on iOS ≤ 26.4 only. |
| Web Audio beep | Works. Create and `resume()` the `AudioContext` **inside the Join tap**. Set `navigator.audioSession.type = 'playback'` so the **silent switch doesn't mute it**; the default since iOS 17 behaves as `ambient`, which is muted by the switch [C]. The transient types gave no sound on iOS 18 [C] | Works after the gesture | **Gotcha:** an active mic capture (`audio:true`) puts iOS into play-and-record, and output may get quieter or route oddly [E]. Test the beep volume with the mic on. If it's too quiet, drop mic capture and use visual sync only. Re-`resume()` on `visibilitychange`. |
| Full-screen color flash + big text | Works everywhere | Works | Primary signal. Use a red/green border and the call label. |
| Torch flash (`applyConstraints({advanced:[{torch:true}]})`) | Works since about 17.5 [C] | Yes | Visible to players across the court, but **toggling torch may reconfigure capture and blip the recording** [E]. Test before using. |
| Web Push | iOS 16.4+, **Home Screen apps only**; Declarative Web Push in 18.4 | Yes | Not needed: the page is foreground during capture. Use the WS. |

**"Challenge" button:** the tap is a user gesture, so you can play a sound and run the switch haptic (iOS ≤26.4) right there. Send `{type:'challenge', t: syncedNow(), lastCallId}` over the WS. The server replays the last N seconds from all cameras on the laptop screen (from its live frame ring buffer), then re-scores using the high-res uploads after the game.

---

## 6. On-device inference (optional)

- **WebGPU:** iOS 26+ ships it by default. iOS 18 has it disabled by default. It requires iOS 26+ [V, caniuse/WebKit]. Gotchas: a **WebGPU rendering regression in 26.4** (fixed May 2026), and a **TF.js issue where video frames imported via external textures come out rotated about 90° on iOS 26** [C]. The onnxruntime-web npm table still lists iOS as wasm/webgl only [C]. Expect rough edges.
- Options: MediaPipe Tasks Vision (Pose Landmarker / Object Detector, WebGL/WASM), ONNX Runtime Web (WebGPU EP), TF.js (WebGPU backend), and transformers.js (uses ORT WebGPU).
- **Phone FPS estimates [E, no published iPhone Safari benchmark found]:**
  - MediaPipe Pose Lite: about 20-30 fps on an iPhone 13-15.
  - YOLO11n at 320 px on ORT-WebGPU: about 10-25 fps on recent iPhones and flagship Androids.
  - At 640 px: about 5-12 fps.
  - Running ML on top of camera, encode, and recording means heat and dropped frames.
  - For reference, YOLO11n is 6.5 GFLOPs vs. 8.7 for YOLOv8n, with ONNX CPU at 56 ms vs. 80 ms at 640 px on desktop [V].
- **Verdict:** don't do it for the referee logic, because the laptop GPU does 4 streams better. If anything, run MediaPipe pose at 5 fps on-device for a **"framing coach"** overlay ("move left, the hoop is out of frame") during setup, then turn it off when the game starts.

---

## 7. Open-source to fork or borrow

| Project | Use |
|---|---|
| `aiortc/examples/server` | Browser camera → Python (OpenCV transforms) → back. The closest starting point for path A1. |
| `gradio-app/fastrtc` (MIT) | numpy-frame handler, FastAPI mount, custom JS frontend [V] |
| `livekit/livekit` + `livekit/python-sdks` (+ `livekit/client-sdk-js`) | Robust self-hosted SFU and Python frames [V] |
| `steveseguin/vdo.ninja` + `steveseguin/raspberry_ninja` | Instant phone-as-camera rig. `--framebuffer` gives shared-memory BGR frames, and `--record-room` records all phones [V]. Check the license. |
| `bluenviron/mediamtx`, `AlexxIT/go2rtc` | WebRTC/WHIP ingest and server-side recording backup [V] |
| `perfanalytics/pose2sim` | Multi-phone sync, calibration, and triangulation in post [V] |
| FreeMoCap / OpenCap (Stanford) | FreeMoCap is multi-camera mocap on desktop USB cams; OpenCap is a native iOS app plus a cloud pipeline. Reuse their calibration and triangulation ideas, not their capture clients [E] |
| `tus/tus-js-client` + `tusd` or `tuspy` | Resumable uploads |
| `ios-haptics` / `web-haptics` | Only for Android vibrate plus legacy iOS ≤26.4 tap haptics [V] |

---

## 8. Gotchas checklist (print this)

1. **Cert first.** Get a real wildcard cert tonight. Test from an iPhone on the travel router. Turn off router DNS-rebind protection or add a local DNS record.
2. **One getUserMedia per page**, no client-side routing, and re-acquire on `visibilitychange`, `mute`, or `ended`.
3. **Landscape constraints, landscape mount.** Handle per-frame width/height on the server. Use `ffmpeg -c copy` remux plus rotation fixups.
4. **Pin a physical lens on iOS** ("Back Camera" or "Back Ultra Wide Camera" by deviceId, matching localized labels loosely). The virtual triple camera switches lenses mid-game.
5. **No focus or exposure lock on iOS.** Plan lighting.
6. **frameRate on Safari:** use `ideal` only and read back the settings.
7. **Android Chrome may ignore videoBitsPerSecond,** and **may not offer H.264 for WebRTC**. Check capabilities and use VP8.
8. **iOS: no vibration and no haptic hack (26.5+).** Use audio plus a screen flash. Unlock the AudioContext on the Join tap, set `audioSession.type='playback'`, and test volume with the mic active.
9. **Wake Lock:** re-request on visibility. Low Power Mode off. Phones plugged into power banks: 1080p record plus stream drains about 15-25%/hour [E].
10. **Thermal:** use 1080p, not 4K. Keep phones out of direct sun.
11. **Storage:** check `navigator.storage.estimate()` first. Write chunks to OPFS from a worker; never hold Blobs in memory.
12. **Upload in the foreground**, one phone at a time, resumable.
13. **Clock sync:** min-RTT NTP plus a drift fit, timecode-board calibration per phone, and an audio or visual sync event at start and end. Mind the 3 ms/m acoustic delay.
14. **Latest-frame-wins** on any TCP path. Never queue frames.
15. **Venue Wi-Fi isolation:** bring the travel router, use 5 GHz, and pick a clean channel.
16. **iOS 26 Home Screen = web app by default.** If a teammate adds it to the Home Screen, permission and wake-lock behavior differ. Test the Safari tab path as canonical.
17. **`takePhoto()` and torch toggles can reconfigure the camera session** and glitch recording.
18. **iOS 27** shipped about 5 weeks ago. Nothing in its notes touches capture constraints, but run the hour-1 device test matrix on whatever OS your four phones have.

## 9. Hour-1 device test page (build first, 30 min)

A single HTML page that:
- Logs getSupportedConstraints, getCapabilities, getSettings, and enumerateDevices labels.
- Tries 1080p60 and 4K30.
- Lists `MediaRecorder.isTypeSupported` for the list above.
- Lists `RTCRtpSender.getCapabilities('video').codecs`.
- Checks `'gpu' in navigator`, `navigator.storage.estimate()`, wake lock, `navigator.vibrate`, and an AudioContext beep with the mic on and off.
- POSTs the results to the laptop.

Run it on every phone you'll demo with and on judges' phones if they volunteer. It decides 60 fps vs. 30, H.264 vs. VP8, and which lens to use.

---

## Sources

- WebKit, *WebKit Features in Safari 18.0*: https://webkit.org/blog/15865/webkit-features-in-safari-18-0/
- WebKit, *News from WWDC25: Safari 26 beta*: https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/
- WebKit, *News from WWDC26: Safari 27 beta*: https://webkit.org/blog/17967/news-from-wwdc26-webkit-in-safari-27-beta/
- mjtsai, *Safari 27 announced*: https://mjtsai.com/blog/2026/06/12/safari-27-announced/
- Safari 18.4 release notes: https://developer.apple.com/documentation/safari-release-notes/safari-18_4-release-notes ; MediaRecorder summary: https://ppc.land/safari-18-4-release-brings-major-web-platform-enhancements/
- MDN browser-compat-data: MediaStreamTrackProcessor, WakeLock, ScreenOrientation, ImageCapture, VideoEncoder, HTMLVideoElement (https://github.com/mdn/browser-compat-data/tree/main/api)
- caniuse: vibration https://caniuse.com/vibration ; fullscreen https://caniuse.com/fullscreen ; WebGPU https://caniuse.com/webgpu ; WebTransport https://caniuse.com/webtransport (iOS 26.4+)
- WebKit bugs:
  - 261461 (frameRate max): https://bugs.webkit.org/show_bug.cgi?id=261461
  - 262416 (lens auto-switch): https://bugs.webkit.org/show_bug.cgi?id=262416
  - 270779 (supported constraints): https://bugs.webkit.org/show_bug.cgi?id=270779
  - 280970, 243075 (torch)
  - 272393 (fps caps): https://bugs.webkit.org/show_bug.cgi?id=272393
  - 285120 (switch haptics user activation): https://bugs.webkit.org/show_bug.cgi?id=285120
  - 292858 (H.264 RTP clock): https://bugs.webkit.org/show_bug.cgi?id=292858
  - 266356 (rVFC captureTime unreliable): https://bugs.webkit.org/show_bug.cgi?id=266356
  - 263606 (realtime encoder): https://bugs.webkit.org/show_bug.cgi?id=263606
  - 41419 (wss self-signed): https://bugs.webkit.org/show_bug.cgi?id=41419
  - 204681, 272704, 179363, 215884 (track lifecycle/permissions)
  - 290223 (WebM rotation 18.4 beta)
  - 234784, 274222 (bitrate)
- Apple Developer Forums: 776460 (lens switching) https://developer.apple.com/forums/thread/776460 ; 844826 (iOS 26.6 sideways recording) https://developer.apple.com/forums/thread/844826
- Scanbot FAQ (ultra-wide label): https://docs.scanbot.io/faq/common_web_integration_issues/
- Addpipe: MediaRecorder bitrates (2026-04) https://blog.addpipe.com/mediarecorder-video-bitrates/ ; iOS inline recorder https://blog.addpipe.com/inline-recorder-on-ios-beta ; constraints https://blog.addpipe.com/getusermedia-video-constraints/
- Dynamsoft focus control (Jul 2026): https://www.dynamsoft.com/codepool/camera-focus-control-on-web.html
- web.dev rVFC: https://web.dev/articles/requestvideoframecallback-rvfc
- WebKit storage policy: https://webkit.org/blog/14403/updates-to-storage-policy/
- ios-haptics: https://npmjs.com/package/ios-haptics ; iOS Haptics Tester (26.5 patch): https://rapidtoolset.com/en/tool/ios-haptics-tester ; Flarum thread: https://discuss.flarum.org/d/39406/17
- AudioSession: https://developer.mozilla.org/docs/Web/API/AudioSession/type ; https://bugs.webkit.org/show_bug.cgi?id=237322
- timesync (archived): https://github.com/enmasseio/timesync
- LiveKit local: https://docs.livekit.io/home/self-hosting/local/ ; Python SDK reference: https://tessl.io/registry/tessl/pypi-livekit
- FastRTC: https://github.com/gradio-app/fastrtc
- MediaMTX: https://github.com/bluenviron/mediamtx ; WHIP walkthrough: https://dev.to/masonwritescode/ship-a-go-live-button-browser-whip-publishing-with-mediamtx-no-sdks-4kfp
- go2rtc: https://github.com/AlexxIT/go2rtc
- VDO.Ninja: https://docs.vdo.ninja/readme/why-use-vdo-ninja-over-other-solutions ; Raspberry Ninja: https://github.com/steveseguin/raspberry_ninja
- local-ip.sh: https://local-ip.sh/ ; traefik.me: https://github.com/pyrou/traefik.me ; OpenWrt rebind: https://forum.openwrt.org/t/nip-io-doesnt-work-for-local-network-behind-lede-solved-dns-rebind-protection/7766 ; GL.iNet: https://forum.gl-inet.com/t/what-is-dns-rebinding/38845/4
- Kurento self-signed certs on iOS: https://doc-kurento.readthedocs.io/en/latest/knowledge/selfsigned_certs.html
- Chrome codec preferences: https://lists.w3.org/Archives/Public/public-webrtc-logs/2024Feb/0047.html
- TF.js iOS 26 WebGPU rotation: https://github.com/tensorflow/tfjs/issues/8733 ; WebKit 26.4 WebGPU regression: https://bugs.webkit.org/show_bug.cgi?id=315186
- Ultralytics YOLOv8 vs YOLO11: https://docs.ultralytics.com/compare/yolov8-vs-yolo11
- Pose2Sim: https://pypi.org/project/pose2sim/ ; VisualSync (NeurIPS 2025): https://proceedings.neurips.cc/paper_files/paper/2025/hash/20ceffa1fcec0f882868e5b891e3e7fa-Abstract-Conference.html
- Chrome 126 MP4 MediaRecorder: https://blog.addpipe.com/tag/mediastream-recording-api/ ; HEVC intent: https://groups.google.com/a/chromium.org/g/blink-dev/c/YJ1QijNiHeM/m/3EhMjMVwAgAJ
