# Trophy: build-platform integration cards

Compiled 2026-10-22. These cards are integration facts, not project code. Snippets are short reference shapes to copy.

Tags:
- **[V]**: verified today from the linked source (repo source, docs, PyPI/npm/HF API).
- **[N]**: carried over from the research notes (`docs/research/*.md`), which were verified on 2026-10-22.
- **[E]**: estimate or prior knowledge. Measure it in hour 1.

Each card follows the same order: Install/pins, Entry points, I/O formats, Performance, Gotchas, Plug-in.

---

## 0. Pipeline map (what plugs into what)

```
Phone PWA (Safari/Chrome tab, HTTPS via Caddy wildcard cert)
  getUserMedia(rear deviceId, 1080p landscape, audio raw)
   ├─ MediaRecorder(2 s timeslice) ─► Worker ─► OPFS file ─► post-game resumable upload ─► /upload
   ├─ live A: RTCPeerConnection ─► aiortc /offer (one PC per phone)    ─► latest_frame[cam] (av.VideoFrame, pts @ 1/90000)
   ├─ live B: rVFC ─► canvas JPEG + 16-byte header ─► WS /frames        ─► latest_frame[cam] (ndarray, t_phone→t_server)
   ├─ AudioWorklet onset detector ─► WS /ws {type:'onset', t}
   └─ control WS /ws: NTP ping/pong, calls, challenge, health
Laptop (GPU, game clock = time.perf_counter_ns)
  trackers/geometry ─► events.jsonl ─► decide() [SubQ Snap → Qwen3-VL logprobs → Claude vote → geometry]
  ─► commentary (Claude Haiku 5.5 stream) ─► Cartesia sonic-3.6 WS ─► PCM ─► dashboard/speaker/phones
Post-game (laptop + AWS GPU)
  uploads ─► ffmpeg remux ─► audio/QR sync ─► PANNs + events highlights ─► auto-director Viterbi
  ─► Practical-RIFE slow-mo ─► deface ─► Remotion 9:16 render (Cartesia word timestamps → captions)
  ─► GVHMR (static cam) ─► Three.js + Spark splat court + ball trail + skeletons
  ─► ReCamMaster arc-around (AWS, one clip)
```

**Platform blocker:** the GPU laptop is probably Windows. vLLM ships **Linux wheels only** (no `win_amd64` in vllm 0.32.0 [V]), and GVHMR and ReCamMaster are Linux/CUDA 12.1 projects [V]. Run them in **WSL2 Ubuntu or Docker with GPU passthrough**, or on AWS. aiortc, FastAPI, Caddy, PANNs, deface, RIFE, and Remotion all run natively on Windows (with the caveats noted in their cards).

---

## 1. Ingest

### 1A. aiortc (`aiortc/aiortc` `examples/server`)  [primary live path once B works]

**Install/pins** [V]
- `aiortc==1.15.0` (latest; Python >=3.10). Dependencies: `av>=14,<18`, `aioice>=0.10.2,<1`, `pyee>=13`, `pylibsrtp>=0.10`, `pyopenssl>=25`, `cryptography>=44`, `google-crc32c>=1.1`.
- **Pin `av>=17`.** The 1.15.0 changelog says relaxing to PyAV 17 "fixes a per-frame memory leak", which matters across a 20-minute game.
- Since 1.12, Opus and VP8 go through PyAV, so aiortc is pure Python. The wheels include libvpx and libavcodec, so Windows needs no compiler.
- Example server code: https://github.com/aiortc/aiortc/tree/main/examples/server (`server.py`, `client.js`, `index.html`) [V].

**Entry points** [V, from `server.py` / `rtcrtpreceiver.py` / `codecs/`]
- HTTP `POST /offer` with body `{sdp, type, video_transform}`. The handler:
  1. builds `RTCSessionDescription(sdp, type)`;
  2. creates `pc = RTCPeerConnection()` and stores it in the global `pcs` set;
  3. registers `@pc.on("track")`;
  4. calls `setRemoteDescription` → `createAnswer` → `setLocalDescription`;
  5. returns `{sdp, type}`.
- On `connectionstatechange == "failed"` it calls `pc.close()` and discards the connection.
- CLI flags: `--cert-file --key-file --host 0.0.0.0 --port 8080 --record-to --verbose`. Behind Caddy, run it without certs on 127.0.0.1.
- The example wraps each track as `VideoTransformTrack(relay.subscribe(track))`. Its `recv()` does `frame = await self.track.recv()` → `img = frame.to_ndarray(format="bgr24")` → `VideoFrame.from_ndarray(img, format="bgr24")`, then copies `new_frame.pts = frame.pts` and `new_frame.time_base = frame.time_base`.
- **ICE is non-trickle.** `client.js` waits for `iceGatheringState === 'complete'` before it POSTs the offer. Keep that pattern, because LAN gathering takes about 0.1-1 s [E].

**I/O formats for Trophy (multiple phones)**
- **One `RTCPeerConnection` per phone.** Each phone POSTs `/offer?cam=<id>&token=<join>`. The server records `pc → cam_id`. Multiple PCs in one asyncio process is the normal aiortc pattern.
- The server doesn't send media back. Don't `addTrack` a return path; the answer becomes recvonly for that m-line.
- In `on("track")` for `track.kind == "video"`, spawn a **consumer task** that loops forever:
  ```python
  async def pump(cam, track):
      while True:
          f = await track.recv()                    # av.VideoFrame
          latest[cam] = (f, time.perf_counter_ns()) # overwrite: latest-frame-wins
  ```
  Convert lazily, only in the model worker: `f.to_ndarray(format="rgb24")` gives an HxWx3 uint8 array. Read `f.width`/`f.height` on every frame, because iOS orientation can flip mid-game.
- **Timestamps** [V + E]:
  - The receiver's `TimestampMapper` subtracts the first RTP timestamp and handles 32-bit wrap, so `pts` = RTP ticks since that track's first frame.
  - The codec sets `packet.time_base = VIDEO_TIME_BASE`, which is 1/90000 (aiortc's `mediastreams.VIDEO_TIME_BASE`) [V for the packet; 1/90000 from prior knowledge].
  - `frame.time = float(pts * time_base)` = seconds since the first frame, in the **sender's capture clock**, because libwebrtc derives RTP timestamps from capture time [E].
  - To map onto the game clock, fit `t_server = a + b·frame.time` per track using the QR-clock calibration (section 3B). Re-anchor at game end so `b` captures drift.
  - RTCP SR NTP time is available only as `getStats()` → `remote-outbound-rtp.remoteTimestamp`, which is the phone's OS wall clock. **Don't use it for sync** [V/N].
- **Codecs** [V]:
  - Default offer order: VP8 (PT 97, rtx 98), H.264 `42001f` (PT 99), H.264 `42e01f` (PT 101), all with `packetization-mode=1` and `level-asymmetry-allowed=1`. **Only Constrained Baseline H.264 is advertised.**
  - Safari's hardware H.264 encoder negotiates fine at baseline [E].
  - Decode is software (libavcodec `h264`, libvpx through PyAV). The encoder is `libx264` Baseline (unused here). There is no NVDEC path.
  - To steer the codec, filter the offer SDP in the browser (the example's `sdpFilterCodec` keeps `a=rtpmap` matches + their RTX), or call `transceiver.setCodecPreferences()`. Chrome supports it; feature-detect on Safari [E].
  - Rule from the notes: H.264 on iOS, VP8 on Android Chrome (Android only offers H.264 with a whitelisted HW encoder) [N].

**Performance**
- No published aiortc throughput numbers.
- Estimate: 4× 720p30 CPU decode is OK on a modern 8-core. 1080p×4 is tight because of the GIL; keep the live sender at about 720p (`scaleResolutionDownBy: 1.5`) [N/E].
- `to_ndarray` at 720p costs about 2-4 ms of swscale [E]. Convert only the frames you infer on.

**Gotchas** [V]
- **The receive queues are unbounded.** Both `RTCRtpReceiver.__decoder_queue` (`queue.Queue()`) and the track `_queue` (`asyncio.Queue()`) have no bound. The video jitter buffer has `capacity=512`. If you `await track.recv()` slower than frames arrive, memory and latency grow without limit. **Always run the pump task above, and run inference off the latest slot.**
- The example's "cartoon" transform uses `COLOR_RGB2GRAY` on BGR. That's a harmless upstream bug, but don't copy it.
- `MediaRelay` (`relay.subscribe`) is only needed if two consumers read one track (e.g., a server-side `MediaRecorder` backup plus inference).
- mDNS `.local` candidates: aioice resolves them [E]. Verify the answer SDP contains host candidates on 192.168.8.x.

**Plug-in**
- `latest[cam]` feeds the model workers.
- `MediaRecorder("cam2.mp4")` on `relay.subscribe(track)` gives a free server-side backup recording (aiortc 1.14+ also writes WebM) [V].
- Data channel: one per PC, for per-frame side-info such as phone `rVFC` timestamps keyed by seq. This is optional, because the QR fit gives the mapping.

### 1B. FastRTC (`gradio-app/fastrtc`)  [alternative; not recommended for Trophy]

**Install/pins** [V]
- `fastrtc==0.0.34` (PyPI, released 2025-11-24; Python >=3.10). It depends on `gradio>=4.0,<6.0`, unpinned `aiortc`, `aioice>=0.10.1`, `librosa`, `numba>=0.60`, and `numpy`.
- Repo: MIT, 4,632★, pushed 2026-10-21, 84 open issues.
- **Docs site `fastrtc.org` has an expired TLS certificate today.** Read the docs from `github.com/gradio-app/fastrtc/tree/main/docs` instead.

**Entry points** [V, `stream.py`]
- Constructor:
  ```python
  Stream(handler, *, mode="send-receive"|"receive"|"send", modality="video"|"audio"|"audio-video",
         concurrency_limit="default", time_limit=None, allow_extra_tracks=False, rtp_params=None,
         rtc_configuration=None, server_rtc_configuration=None, track_constraints=None,
         additional_inputs=None, additional_outputs=None, additional_outputs_handler=None, ui_args=None, verbose=True)
  ```
- `stream.mount(app, path="")` adds:
  - `POST /webrtc/offer`
  - `WS /websocket/offer`
  - `POST /telephone/incoming`
  - `WS /telephone/handler`
- **Custom frontend:**
  1. Create a data channel `"text"` before the offer (required).
  2. POST `{sdp, type, webrtc_id}` to `/webrtc/offer`. `webrtc_id` is generated by the client.
  3. Trickle ICE goes to the same endpoint with `{type:"ice-candidate", candidate, webrtc_id}`.
  4. Inputs: your own `/input_hook` route → `stream.set_input(webrtc_id, ...)`.
  5. Outputs: your own SSE route over `stream.output_stream(webrtc_id)` [V, docs/userguide/api.md].

**Frame delivery** [V, `tracks.py` `VideoCallback`]
- The handler gets `handler(frame_ndarray, *additional_inputs)`.
- The code does `frame.to_ndarray(format="bgr24")`, but the docs say "(height, width, RGB)". **Check channel order on day 1** by pointing a phone at something red.
- **The handler never receives `pts`/`time_base`**, so there are no capture timestamps.
- `VideoStreamHandler(fn, skip_frames=True)` jumps to the newest frame, but the queue still grows (`put_nowait` with no draining).
- Per-connection identity: `from fastrtc.utils import get_current_context; get_current_context().webrtc_id` (`Context(webrtc_id, websocket=None)`). Encode the camera ID in your client-chosen `webrtc_id` ("cam2-…").

**Can it take 3-4 phones?**
- Yes, but **`concurrency_limit` defaults to 1, and `None` is also coerced to 1** (`1 if concurrency_limit in ["default", None] else concurrency_limit`) [V].
- **Set `concurrency_limit=8` explicitly**, or the second phone is refused.
- Each connection gets its own handler callback. Multi-client behavior is otherwise undocumented [N].

**Verdict:** FastRTC wraps aiortc and loses timestamps and backpressure control. Use raw aiortc (1A) unless you want the Gradio UI.

### 1C. WebSocket JPEG fallback ("path B")  [build FIRST, Saturday morning]

**Install/pins**
- `fastapi`, `uvicorn[standard]` (websockets), `opencv-python-headless`.
- Optional: `PyTurboJPEG` (about 2-3x faster decode [E]), or GPU batch decode with `torchvision.io.decode_jpeg(list_of_tensors, device="cuda")`.

**Wire format** (binary message, little-endian; our own design)
- Header (16 bytes):
  ```
  u8  version=1 | u8 cam_id | u16 flags(bit0=keyframe-ish, bit1=calib) | u32 seq | f64 t_capture_phone_ms
  ```
  Then the JPEG bytes.
- Server: `ver, cam, flags, seq, t_ph = struct.unpack_from('<BBHId', buf)`, then `img = cv2.imdecode(np.frombuffer(buf, np.uint8, offset=16), cv2.IMREAD_COLOR)`.
- `t_server = t_ph + offset_cam(t_ph)` (section 3A) `+ pipelineOffset_cam` (section 3B).

**Phone loop** (latest-frame-wins)
1. In `video.requestVideoFrameCallback((now, md) => …)`, take `t = md.captureTime ?? md.presentationTime`.
2. Draw the video to a 640×360 canvas, then `canvas.toBlob(cb, 'image/jpeg', 0.7)`. `OffscreenCanvas.convertToBlob` works in a worker.
3. **Send only if `ws.bufferedAmount === 0`** (or after the server ACKs `seq`). Otherwise drop the frame.

**Performance:** 640×360 at q=0.7 is about 35 KB per frame. At 15 fps that's about 4 Mbps per phone, about 17 Mbps for 4 phones; 80-200 ms glass-to-numpy [N/E].

**Gotchas**
- TCP head-of-line blocking: never queue frames.
- Safari `toBlob` JPEG encode takes about 5-15 ms at 360p [E].
- Use `binaryType = 'arraybuffer'`.

**Plug-in:** writes the same `latest[cam]` slot as 1A, so the model workers are transport-agnostic.

---

## 2. Browser-side recipes (PWA)

All of these need a secure context (2G). Keep v1 a single page with no router: `pushState` muted tracks on iOS 17.4 [N].

### 2A. getUserMedia, rear camera pinned by deviceId
1. **Permission first.** Call `s0 = await getUserMedia({video:{facingMode:{ideal:'environment'}}, audio:true})`, then `devs = await navigator.mediaDevices.enumerateDevices()`. Labels are empty before permission.
2. **Pick a physical lens.** On iOS, match `/back ultra wide/i` (or `/^back camera$/i` for the wide lens). Avoid "Back Triple/Dual Wide Camera": that is the virtual device that auto-switches lenses. Labels are localized, so match loosely and fall back [N]. On Android, use whatever `facingMode: environment` returns.
3. **Stop all `s0` tracks, then reacquire once.** A second concurrent getUserMedia mutes the first on iOS [N].
   ```js
   const stream = await navigator.mediaDevices.getUserMedia({
     video: { deviceId: { exact: id }, width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 60 } },
     audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } // keep transients for onsets/sync
   });
   const v = stream.getVideoTracks()[0]; report(v.getSettings(), v.getCapabilities?.());
   ```
   - Use `ideal` only; Safari's frameRate handling is buggy [N].
   - Request landscape dimensions; there's an iOS 26.6 rotation regression [N].
   - Re-acquire on `track.onended`, `onmute`, and `visibilitychange`.
   - Turning AEC/NS/AGC off is [E]: Safari honors `echoCancellation`; support for the other two varies. Log `getSettings()`.

### 2B. MediaRecorder with timeslice → OPFS in a worker
- **Main thread:**
  ```js
  const types = ['video/mp4;codecs=avc1.640028,mp4a.40.2','video/mp4;codecs=avc1','video/mp4','video/webm;codecs=vp9,opus','video/webm'];
  const rec = new MediaRecorder(stream, { mimeType: types.find(t => MediaRecorder.isTypeSupported(t)), videoBitsPerSecond: 12e6 });
  rec.ondataavailable = e => w.postMessage({ seq: n++, blob: e.data, t: syncedNow() });  // Blob is structured-cloneable
  rec.start(2000);
  ```
- **Worker:**
  ```js
  const root = await navigator.storage.getDirectory();
  const fh = await root.getFileHandle(`cam${id}.mp4`, { create: true });
  const ah = await fh.createSyncAccessHandle();                       // worker-only API
  let off = 0;
  onmessage = async ({ data }) => { const b = new Uint8Array(await data.blob.arrayBuffer());
    off += ah.write(b, { at: off }); if (data.seq % 5 === 0) ah.flush(); postMessage({ seq: data.seq, bytes: off }); };
  ```
- Concatenated chunks form a valid fragmented file; chunks after #0 are not standalone.
- Call `ah.close()` on stop.
- Check `navigator.storage.estimate()` before starting: about 90 MB/min at 12 Mbps [N].
- Upload with ranged `PUT /upload?cam=&offset=` (4-8 MB slices read through `fh.getFile().slice()`), in the foreground, one phone at a time [N].
- Server step: `ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4`.

### 2C. requestVideoFrameCallback metadata [V, MDN]
- Callback `(now, metadata)`. Fields:
  - `presentationTime`, `expectedDisplayTime`, `width`, `height`, `mediaTime`, `presentedFrames`, `processingDuration`.
  - WebRTC/local camera: `captureTime`, `receiveTime` (remote only), `rtpTimestamp`.
  - Baseline 2024. Feature-detect with `'requestVideoFrameCallback' in HTMLVideoElement.prototype`.
- Recipe: put the stream on a `<video muted playsinline autoplay>`, then loop `v.requestVideoFrameCallback(cb)`.
- Use `t = md.captureTime ?? md.presentationTime`. WebKit removed `captureTime` from its tests as "too unreliable" [N], so the per-phone `pipelineOffset` comes from 3B.
- Use gaps in `presentedFrames` to count dropped frames, and report them in health messages.

### 2D. AudioWorklet onset detection (on phone)
- **Graph:** `ctx.createMediaStreamSource(stream)` → `BiquadFilterNode{type:'highpass', frequency:1500}` → `AudioWorkletNode('onset')`. The high-pass isolates ball/racket/hand claps from voice.
- **Processor** (`registerProcessor('onset', class extends AudioWorkletProcessor{ process(inputs){…; return true;} })`), per 128-sample block:
  - Compute energy `e = Σx²/128` and the envelope `env = max(e, env·0.97)`.
  - Keep a ring of the last ~375 blocks (1 s at 48 kHz) and set an adaptive threshold `thr = median + k·MAD` with k≈6.
  - Fire when `e > thr` and more than 60 ms have passed since the last onset. Refine to the sample by taking the argmax of |x| inside the block.
  - Timestamp in context time: `tc = (currentFrame + i)/sampleRate`. `currentFrame` and `sampleRate` are AudioWorkletGlobalScope globals.
  - Post `{tc, peak, e}` through `this.port`.
- **Map to performance.now() on the main thread:**
  - `const {contextTime, performanceTime} = ctx.getOutputTimestamp(); t_perf = performanceTime + (tc - contextTime)*1000`.
  - Then convert to server time through 3A.
  - Input latency isn't exposed; it is about 5-20 ms and device-dependent [E]. Absorb it into a per-phone audio offset measured with the start chirp.
- **Use:** bounce and contact candidates in real time (table tennis especially), and the clap/chirp sync event. Send over WS `{type:'onset', cam, t_server, peak}`.
- Create and `resume()` the AudioContext **inside the Join tap**.

### 2E. Screen Wake Lock [N]
```js
let lock; const want = async () => { try { lock = await navigator.wakeLock.request('screen'); } catch {} };
want(); document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && want());
```
- Safari 16.4+ in the browser tab; broken in Home Screen apps before iOS 18.4. Chrome 84+.
- Tell users to turn Low Power Mode off.

### 2F. audioSession API [V, MDN]
- Values: `auto` (default), `playback`, `transient`, `transient-solo`, `ambient`, `play-and-record`.
- Set `navigator.audioSession.type = 'playback'` before playing call beeps, so the silent switch doesn't mute them. It is Safari-only and experimental; guard with `if ('audioSession' in navigator)`.
- With the mic active, iOS may force play-and-record and route quietly. Test the beep volume with the mic on [N].
- Fallback: full-screen color flash, plus `navigator.vibrate` on Android only.

### 2G. HTTPS on a LAN IP: Caddy + Let's Encrypt DNS-01 wildcard [V]
- Let's Encrypt **requires DNS-01 for wildcards**. Caddy refuses public certs for bare IPs, `.local`, `.internal`, and `.home.arpa`, so you need a real domain.
- **Build:** `xcaddy build --with github.com/caddy-dns/cloudflare` [E for the command; the module name `dns.providers.cloudflare` is V]. Or download a build with the plugin from caddyserver.com/download.
- **Cloudflare token:** `Zone.Zone:Read` + `Zone.DNS:Edit`, scoped to the zone [V].
- **Caddyfile:**
  ```
  *.trophy.example.com, trophy.example.com {
      tls { dns cloudflare {env.CF_API_TOKEN}
            resolvers 1.1.1.1 }            # needed if the laptop's DNS is the travel router / hosts file
      reverse_proxy /offer* 127.0.0.1:8080  # aiortc
      reverse_proxy 127.0.0.1:8000          # FastAPI (WS proxied automatically)
  }
  ```
- **DNS:** a public A record `trophy.example.com → 192.168.8.10` (the laptop's static DHCP lease), and/or a router-local DNS entry.
- **Disable router DNS-rebind protection or whitelist the domain** (GL.iNet/OpenWrt `rebind_domain`). Otherwise the private-IP answer is dropped [N].
- Issue the cert **tonight**, while there is internet. It is valid for 90 days and works offline after that.
- Caddy stores certs in `%AppData%\Caddy` on Windows [E].

---

## 3. Clock sync

### 3A. App-level NTP over WebSocket
**Algorithm** (per phone, `performance.now()` on the phone, `perf_counter_ns` on the server)
- Phone sends `{type:'ping', t0}`. The server stamps `t1` on receive and `t2` just before send, and replies `{t0,t1,t2}`. The phone stamps `t3`.
  - `θ = ((t1 − t0) + (t2 − t3))/2`. This is the offset, server minus phone.
  - `δ = (t3 − t0) − (t2 − t1)`. This is the round-trip network delay.
  - **Error bound: |θ − θ_true| ≤ δ/2** (if path asymmetry is unknown). Small δ means a trustworthy sample.
- **Cadence:** a burst of 20 pings at 50 ms on join, then 1 every 2 s. Keep a sliding window of the last 60 samples.
- **Min-RTT filter:**
  - Keep samples with `δ ≤ δ_min(window) + 2 ms`, or the lowest 25% by δ, whichever gives more samples.
  - Drop samples with δ > 50 ms entirely. Wi-Fi power-save spikes reach 50-300 ms [N].
- **Drift fit:**
  - Fit `θ(t) = a + b·(t − t_ref)` over the filtered samples. Use weighted least squares with `w = 1/(δ − δ_min + 0.5 ms)²`, or Theil–Sen for robustness.
  - `b` is the relative drift (expect 10-50 ppm, which is 12-60 ms over 20 minutes [N]).
  - Convert with `t_server = t_phone + a + b·(t_phone − t_ref)`.
  - Do the fit **server-side**, so post-game processing can refit over the whole game with both endpoints (better than causal).
- **Accuracy:** ±1-3 ms on a quiet 5 GHz LAN, ±5-10 ms under load [N/E].
- `enmasseio/timesync` is archived; write your own (about 40 lines) [N].
- Stamp `t1` as early as possible in the WS handler. Event-loop delay adds asymmetric error, so run the control WS in a process without blocking inference.
- A page reload resets `performance.timeOrigin`, so resync after a reload.

### 3B. QR-clock camera-latency calibration ("timecode board")
**What it measures:** the NTP offset maps the phone clock to the server clock. `pipelineOffset` maps "frame timestamp the phone reports" to "when photons hit the sensor" (about 30-100 ms, model-dependent [N]).

**Method**
1. **Display.** The laptop (or an iPad) runs a full-screen page from the same origin, synced to the server with 3A over localhost.
   - On every `requestAnimationFrame(ts)`, it draws a QR code (version 2-3, error-correction level L, at least 300 px) that encodes `{k: frameCounter, t: serverTimeAtNextVsync}`.
   - Next to it, it draws a large 16-bit binary stripe of `k` as a motion-blur-robust backup.
   - Log `(k, t_display)` server-side.
2. **Capture.** Show "Point at the screen for 3 s" during join. The phone streams frames (path A or B) or records them.
3. **Decode.** On the server, run `cv2.QRCodeDetector().detectAndDecode` (or `pyzbar`, or `zxing-cpp`) on each frame. Frames whose exposure spans two display refreshes usually fail to decode (rolling shutter); discard them. Keep about 60-150 good frames.
4. **Solve.**
   - **Path B:** `pipelineOffset = median(t_capture_phone→server − t_display)`.
   - **Path A (aiortc):** fit `t_display ≈ α + β·frame.time` by least squares over the decoded frames. That gives each track's mapping straight from pts to the game clock (no phone timestamps needed). Repeat the board at game end and refit β for drift.
   - Residual std is typically ±8 ms (half of a 16.7 ms refresh) plus rolling shutter [N/E].
   - This also gives **end-to-end live latency** = `t_server_receive − t_display`.
5. **Bias.** Display latency (panel processing plus scanout, about 5-30 ms [E]) is a **common-mode** bias: identical for every phone filming the same screen. It cancels in camera-to-camera alignment, which is what multi-view needs. Absolute event-to-beep latency keeps it.
6. **Demo moment:** "4 cameras synced to ±4 ms" on the dashboard [N].

**Post-game refinement:** cross-correlate audio (start/end chirp or clap; 2-6 kHz chirp; correct 3 ms/m acoustic delay) or a visual flash step. Use start + end to estimate drift [N].

---

## 4. SubQ Snap + `decide()` wrapper + fallbacks + calibration

### 4A. SubQ Snap Decisions API [V, docs.subq.ai/markdown/endpoints/decisions-api.md]
- **Endpoint:** `POST https://api.subq.ai/v1/systemone`. Status: Public preview.
- **Headers:** `Authorization: Bearer $SUBQ_API_KEY`, `Content-Type: application/json`.
- **Model:** `subq-snap-1.1` (launched today; `subq-snap-preview` is the old ID). List models with `GET /v1/models` (OpenAI-compatible) [N].
- **No official SDK** for `/systemone`; write a raw `httpx` client [N].
- **Request:**
  ```json
  {"model":"subq-snap-1.1",
   "state": "<string|object|array>",
   "images":[{"mediaType":"image/jpeg","base64":"<one-line base64, no data: prefix>"}],
   "questions":{
     "call":{"type":"choice","instructions":"What is the correct umpire call…?",
             "criteria":{"LET":"Serve touched net then landed legally","FAULT":"…","IN":"…","OUT":"…","NO_CALL":null}},
     "net_touch":{"type":"noul","instructions":"Did the ball touch the net assembly?","criteria":{"true":"…","false":"…"}},
     "severity":{"type":"score","instructions":"…","criteria":["none","minor","major"]}}}
  ```
- **Response:**
  ```json
  {"model":"subq-snap-1.1",
   "answers":{"call":{"type":"choice","choice":"LET","probabilities":{"LET":0.81,"FAULT":0.12,"IN":0.05,"OUT":0.01,"NO_CALL":0.01},"confidence":0.81},
              "net_touch":{"type":"noul","noul":0.92},
              "severity":{"type":"score","score":1.86,"legend":{"0":"none","1":"minor","2":"major"},"probabilities":{"0":0,"1":0.13,"2":0.87},"confidence":0.79}},
   "usage":{"input_tokens":612,"output_tokens":0}}
  ```
- **Limits:**
  - Questions: 1-128 per request; names up to 100 characters.
  - Choice: 2-255 options (a description may be `null`). Score: 2-10 levels.
  - Images: at most 4 per request; PNG/JPEG/WebP; 4 MiB decoded each, 8 MiB total; 13 MiB body.
  - **Each image costs only about 64-256 tokens**, so send crops.
  - URLs and `data:` URIs return 422. Video isn't supported.
  - Context: 384K tokens (393,216). Near the limit returns 400; stay ≤250K.
  - Billing: input tokens only, $0.04/M [N].
- **Errors:** the body is `{"detail":{"error_type","message"}}`.
  - `400`: over the token limit or rejected. Fix it; don't retry.
  - `401`: bad credentials.
  - `402`: out of credits.
  - `403`: the key can't use the model.
  - `422`: validation, including image errors (`validation_error`). Fix it; don't retry.
  - `429` and `5xx` (`503` = temporarily unavailable): **retry with backoff**.
  - **No numeric rate limits are published.** Docs examples use a 60 s client timeout.
- **Semantics** [N]:
  - Outputs are **not deterministic**.
  - `confidence` = (p_max − 1/n)/(1 − 1/n). It is peakedness, not P(correct). **Gate on calibrated `probabilities[choice]`.**
  - Probabilities can saturate at 0/1; clip to [1e-3, 1−1e-3].
  - There is likely an option-order bias (as in Jev), so shuffle the options.
- **Retry policy (ours):**
  - Live: timeout 2.0 s, 1 retry on 429/5xx/timeout after `0.25 s·2^i + jitter`.
  - Batch: timeout 10 s, 3 retries.
  - Max concurrency 4.
  - Circuit breaker: 2 consecutive failures → route live calls to the fallback for 5 minutes.

### 4B. `decide()` wrapper spec (interface only)
```
decide(question: str, options: dict[str, str|None] | "noul", state: dict|str,
       images: list[bytes(jpeg)] = [], *, kind: "choice"|"noul"|"score",
       sport: str, qid: str, mode: "live"|"batch", deadline_s: float, n_votes: int|None = None)
  -> Decision{
       qid, kind, options:[...], choice, probs:{opt: p_cal}, raw_probs:{opt: p_raw},
       p_top, margin(p1-p2), entropy, source:"subq"|"qwen"|"claude"|"geometry",
       model_version, n_calls, agreement (fraction of calls with same argmax),
       latency_ms, tokens_in, cost_usd, calibrator_id, degraded: bool, error: str|None }
```
**Behavior**
1. **Normalize.**
   - Map options to stable keys. Pre-bucket numbers into words ("about 1 cm inside", "LOW") [N]. Downscale and crop images to ≤512 px JPEG q85, ≤4 images.
   - `noul` returns `probs={"true":p,"false":1-p}` so every consumer handles one shape.
2. **Primary (SubQ).**
   - Make one call. If `0.60 ≤ p_top < 0.90`, fire a **second call in parallel with shuffled option order** and average the distributions; this also gives `agreement` [N].
   - Batch/coach mode: always 2-3 shuffled calls.
3. **Fallback chain** (same return type):
   1. **Qwen3-VL-8B via vLLM, per-option logprobs** (4C). Use it for live, offline, and no-rate-limit cases.
   2. **Claude constrained choice with voting** (4D). Coach, batch, and explanations only (2-5 s).
   3. **Geometry-only** (`P_geom = Φ(d/σ)`) for IN/OUT. Semantic calls get "challengeable" [N].
   - (Optional: Jev on the Vercel AI Gateway, text-only, same contract [N].)
4. **Calibrate.** `probs = calibrator[(source, sport, qid_family)](raw_probs)` (4E). If no calibrator is fitted yet, use identity and set `degraded=true`.
5. **Gate** (caller): `p_top ≥ 0.90` → auto-call; `0.60-0.90` → challengeable; `< 0.60` or an atomic-question contradiction → replay [N].
6. **Log** every request/response (with image hashes) to `decisions.jsonl` for later calibration and the eval table.

### 4C. Fallback 1: Qwen3-VL-8B-Instruct on vLLM with per-option logprobs
**Install/pins** [V]
- `vllm>=0.11.0` (Qwen3-VL support; latest is 0.32.0, Python 3.11-3.14) and `transformers>=4.57.0`.
- **Linux only: use WSL2/Docker on the Windows laptop.**
- Models: HF `Qwen/Qwen3-VL-8B-Instruct`, and `Qwen/Qwen3-VL-8B-Instruct-FP8` (exists, about 8.8B params, so about 10 GB of weights).

**Serve** [E for the flags at 8B]
```
vllm serve Qwen/Qwen3-VL-8B-Instruct-FP8 --max-model-len 32768 --gpu-memory-utilization 0.45 \
  --limit-mm-per-prompt '{"image":4}' --max-logprobs 20 --port 8001
```

**Request** (OpenAI chat completions)
- Images go in as `{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,…"}}`.
- The prompt lists options as letters `A) LET  B) FAULT …` and ends with "Answer with one letter."
- Params: `max_tokens=1`, `logprobs=true`, `top_logprobs=20`, `extra_body={"structured_outputs":{"choice":["A","B","C","D","E"]}}`.
  - **`guided_choice` was removed in vLLM v0.12.0**; use `structured_outputs.choice` [V].
- Read `choices[0].logprobs.content[0].top_logprobs`, sum the "A" and " A" variants per letter, renormalize over the allowed letters, and floor any missing letter at 1e-4.
- vLLM's default `--logprobs-mode` reports raw (pre-constraint) logprobs, which is what you want [E].
- Up to 26 options with single-token letters; use two-pass hierarchical choice for more.

**Performance:** about 150-400 ms for 4 images plus 2K text tokens on a 4090, prefill-dominated [E].

**Gotchas:**
- Calibrate it separately; its T will differ from Snap's.
- Shuffle the letters, as with Snap.
- VRAM budget: the trackers need headroom, so set `--gpu-memory-utilization` accordingly.

### 4D. Fallback 2: Claude constrained choice + self-consistency voting
- **Model:** `claude-sonnet-5-5` for coach/batch, or `claude-haiku-5-5` if speed matters.
- **Constrain output** with `output_config={"format":{"type":"json_schema","schema":{…}}}`. Schema: `{"choice":{"enum":[…]}, "p_verbal":{"type":"number"}, "rationale":{"type":"string"}}`, with `required` set and `additionalProperties:false`.
  - Python: `client.messages.parse(..., output_format=PydanticModel)` [V, claude-api skill].
- **Gotchas (current API)** [V, skill]:
  - **Forced `tool_choice` `any`/`tool` returns 400 on Opus 5.5 and Sonnet 5.5**, so use structured outputs instead.
  - **On API version `2026-10-21`, `temperature`/`top_p`/`top_k` return 400 on every model.** Vote diversity comes from default sampling, **option shuffling, and relabeling per sample**, not from temperature.
  - Numeric constraints (`minimum`/`maximum`) are not supported in schemas. The SDK strips them and validates client-side.
  - A new schema has a one-time compile cost, then a 24 h cache.
- **Voting:** run k=5 parallel requests with shuffled options. `p(o) = (votes_o + 0.5)/(k + 0.5·m)`. Optionally average with the normalized `p_verbal` [N].

### 4E. Temperature-scaling calibration + reliability diagram
1. **Data:**
   - 60-100 labelled calls (30 minimum), double-labelled from slow-mo, with disagreements dropped [N].
   - Store `P` (n×k raw probs, clipped to [1e-3, 1]) and `y`.
2. **Choice (temperature):** `p_cal = softmax(log P / T)`. Fit a scalar T by minimizing NLL with `scipy.optimize.minimize_scalar(bounds=(0.25,5), method='bounded')`. T > 1 softens an overconfident model. (Code shape is in the SubQ notes §3a.)
3. **Noul (Platt):** `p_cal = σ(a·logit(p) + b)`. With n < 50, fix b = 0 [N].
4. **Saturation:** if more than 30% of samples sit at the clip boundary, temperature scaling can't spread them. Use the mean of 3 shuffled calls before fitting [N].
5. **Evaluate with leave-one-out:**
   - **ECE:** M = 5 equal-width bins on p_top. `ECE = Σ_m (|B_m|/n)·|acc(B_m) − conf(B_m)|`.
   - **Brier score:** `mean Σ_k (p_k − 1[y=k])²`.
   - NLL.
   - **Selective accuracy** at τ = 0.90, plus coverage (% automated).
   - Wilson 95% CI on accuracy. n = 30 at 90% gives about 74-97% [N].
6. **Reliability diagram** (matplotlib):
   - x = mean confidence per bin, y = accuracy per bin.
   - Draw the diagonal y = x. Put a histogram of bin counts underneath, because small bins mislead.
   - Plot before vs. after on one figure, and print ECE in the legend.
   - Store `T` and `fitted_on` in the rule pack's `calibration:` block [N].

---

## 5. Anthropic Claude API (commentary, coach, house-rule compiler)

**Install/pins** [V]
- Python `anthropic` (PyPI latest 2.1.0, Python >=3.10). Pin the exact version you install tonight.
- Models: `claude-opus-5-5` ($4/$20 per MTok), `claude-sonnet-5-5` ($2/$10), `claude-haiku-5-5` ($0.10/$0.50 for prompts ≤100K tokens), all with 1M context [V, skill].
- **Thinking:**
  - Opus 5.5 can't disable thinking (400). Effort defaults to `medium`; set `output_config.effort`.
  - Sonnet 5.5: `thinking:{type:"disabled"}` is a 400; use `{type:"between_tools"}` (at effort high or below) to turn it off.
  - Haiku 5.5: disabled thinking is allowed at effort high or below [V, skill].
- **No assistant prefill** on these models; use structured outputs or the system prompt [V].
- **Refusal fallbacks** (recommended by the skill for Opus 5.5 / Sonnet 5.5): `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`. Check `stop_reason == "refusal"` before reading content [V].
- **Prompt caching:** put the rules, roster, and persona first; add `cache_control:{type:"ephemeral"}` and verify with `usage.cache_read_input_tokens`. The minimum cacheable prefix is 512-4096 tokens depending on the model [V].

### 5A. Event-grounded live commentary (streaming)
- **Model:** `claude-haiku-5-5`, thinking disabled (or effort low), `max_tokens≈120`.
- **Prompt:**
  - System: persona and rules ("1-2 sentences, ≤ 15 words, only facts in EVENT JSON, never invent names or scores"), cached.
  - User: `EVENT: {t, event, player, points, score, streak, cam, speed_kmh}` plus the last 5 commentary lines (to avoid repeats).
- **Stream:**
  ```python
  with client.messages.stream(model="claude-haiku-5-5", max_tokens=120, system=[...], messages=[...]) as s:
      for delta in s.text_stream:
          cartesia.send(transcript=delta, context_id=cid, continue_=True)
  ```
  Then send a final empty transcript with `continue:false` (6B).
- **Priority/interrupt:** when a higher-priority event arrives, `stream.close()` and send a Cartesia `cancel` for the old `context_id`.
- **Budget:** about 200-500 ms to first token [E], plus about 170-190 ms Cartesia TTFA [N], so roughly 0.5-0.8 s from event to voice.
- **Post-game script:** `claude-sonnet-5-5` writes a 20-40 s Play-of-the-Game script with `<emotion value="excited"/>` and `[laughter]` tags. Its structured output has fields `{lines:[{speaker:"pbp"|"color", text, emotion}]}`.

### 5B. Coach explanations
- **Model:** `claude-sonnet-5-5`, effort medium.
- **Input:** the Snap distribution over options, the bucketed features, the actual option, the outcome, and empirical session win rates [N].
- **Output:** structured `{headline:≤12 words, explanation:1-2 sentences, better_option:<enum of option keys>, ghost_target_zone:<enum>}`.
- Constraining `better_option` to the enum keeps it consistent with the 3D ghost trajectory.
- Run it asynchronously after each rally; latency doesn't matter.

### 5C. House-rule compiler (rule text → rule-pack YAML/DSL, verified by replay)
**Method source:** DeepMind, "Code World Models for General Game Playing", arXiv 2510.04542 (Lehrach et al., Oct 6 2025) [V]. Key details:
- The LLM (Gemini 2.5 Pro) turns **rules text + offline trajectories** into an executable world model.
- **Unit tests are generated automatically from the trajectories.** Each one is binary and checks per transition the next state, observations, rewards, action legality, and that no exception is raised.
- **Refinement feeds stack traces of failed tests back** to the LLM, either as a sequential conversation or as a tree search with Thompson sampling over candidates. Each tree-search call sees one failed test.
- It stops at transition accuracy 1.0 or when the budget is spent. The paper's settings: `num_retries=500`, `num_tests_on_init=5`, `num_tests_on_error=1`.
- Simple games needed about 2 LLM calls; Gin Rummy hit the 500 cap at 0.78 train accuracy.
- The **metric is transition accuracy**: the fraction of tests passed, measured on train, a held-out set, and online play.

**Trophy adaptation**
1. **Input:** the house rule in plain English (e.g., "first to 11, win by 2, cap 15; serve rotates every 2; any ball hitting the ceiling is a let; winner's court").
   - Context: `base_pack.yaml` for the sport, the **event field registry** (enumerated event types and fields), and 5-20 recorded rallies from `events.jsonl` with human-labelled outcomes.
2. **Output:** `claude-opus-5-5`, effort high, streaming, `output_config.format=json_schema(RulePackPatch)`.
   - **Structured outputs don't support recursive schemas or numeric/length constraints** [V]. So the schema is **flat**:
     ```
     RulePackPatch = {
       sport: enum, extends: enum[base pack ids],
       scoring: {points_to_win:int, win_by:int, cap:int|null, rally_scoring:bool, serve_rotation_every:int},
       overrides: [{ id:str, description:str,
                     trigger: enum[event types],                    # e.g. "ball_contact_ceiling"
                     when: str,                                     # expression in OUR mini-DSL (below)
                     effect: enum["award_point","fault","let","replay","side_out","ignore","ask_snap"],
                     effect_args: {to: enum["server","receiver","last_hitter","opponent_of_last_hitter"]|null,
                                   snap_question_id: str|null},
                     cites: str }],                                 # quote of the rule sentence it implements
       tests: [{ name, events:[{t:number, type:enum, side:enum|null, zone:enum|null, player:str|null}],
                 expect:{ call: enum, point_to: enum|null, score_after: str|null } }] }
     ```
   - `when` is a **string in a tiny expression language** that our code parses. It allows comparisons and boolean ops over registry fields, plus `count(type, since="serve")` and `prev(type)`. The expression tree lives in a string because the schema can't be recursive.
   - Validate `when` with a real parser, e.g. `lark` grammar or a whitelisted Python `ast` walk. Field names are checked against the registry.
   - Serialize to YAML for humans and keep JSON as the canonical form.
3. **Verify, in this order:**
   1. JSON Schema / pydantic. Structured outputs guarantee the shape; pydantic checks numeric ranges, which the API can't.
   2. DSL parse and type check.
   3. **Replay all recorded rallies** through the rule engine (base pack + patch). Compare to the labelled outcome (call, point winner, score progression).
   4. Run the **model-written `tests`**: synthetic minimal pairs, e.g., the same rally with and without a ceiling touch.
   5. Run the **unchanged-behavior tests**: rallies the new rule shouldn't affect must still match the base pack. This catches over-broad rules.
4. **Refine** (CWM "conversation" mode):
   - On failure, append `{test name, event trace, expected, actual, exception/stack trace}` to the conversation and ask for a revised patch.
   - Stop after at most 4 iterations or when 100% pass. Report "transition accuracy" = passed/total.
   - Any rule it can't express → `effect:"ask_snap"` with a `snap_question` (semantic judgment at runtime).
5. **Demo line:** "House rule compiled in about 15 s; 47/47 recorded rallies replay identically, and 6/6 generated edge cases pass" [E for timings].

---

## 6. Cartesia sonic-3.6 WebSocket TTS [V, docs.cartesia.ai]

- **URL:** `wss://api.cartesia.ai/tts/websocket?cartesia_version=2026-08-14` [V for the example version string].
  - The query parameter takes precedence over the `Cartesia-Version` header. Versions ≥ 2026-03-01 return structured JSON errors.
- **Auth (server):**
  - The WebSocket reference says header `X-API-Key: <key>`.
  - The API-conventions page says `Authorization: Bearer <key>` for HTTP. **Test both tonight.**
- **Auth (browser):**
  - The server calls `POST https://api.cartesia.ai/access-token` with body `{"grants":{"tts":true},"expires_in":3600}` (max 3600 s) and gets back `{"token": "..."}`.
  - The browser connects with `?access_token=<token>`. **Never ship the API key to phones.**
- **Model:** `sonic-3.6` (alias for snapshot `sonic-3.6-2026-08-27`; stable; 44 languages; backward-compatible with 3.5). `sonic-preview` is beta [V].
- **Generation request:**
  ```json
  {"model_id":"sonic-3.6","transcript":"What a rally!","voice":{"mode":"id","id":"47c38ca4-5f35-497b-b1a3-415245fb35e1"},
   "output_format":{"container":"raw","encoding":"pcm_s16le","sample_rate":24000},
   "context_id":"evt-41-pbp","continue":true,"max_buffer_delay_ms":300,
   "add_timestamps":true,"language":"en",
   "generation_config":{"speed":1.15,"volume":1.3,"emotion":"neutral"}}
  ```
  - Encodings: `pcm_f32le`, `pcm_s16le`, `pcm_mulaw`, `pcm_alaw`. Sample rates: 8000, 16000, 22050, 24000, 44100, 48000.
  - `max_buffer_delay_ms`: 0-5000, default **3000**. **Lower it (about 200-500) for live commentary**, or it waits up to 3 s for more text.
  - Also: `add_phoneme_timestamps`, `use_normalized_timestamps`. Set `language` or `locale`, not both.
- **Ending, flushing, cancelling:**
  - Send the same `context_id` with `continue:false` (or an empty transcript) to finish.
  - Cancel: `{"context_id":"evt-41-pbp","cancel":true}`. It cancels generation that hasn't started yet.
  - Contexts expire about 1 s after the last audio [N].
  - Multiple concurrent contexts per socket work, so use **two voices = two `context_id`s** [N].
- **Responses:**
  - `{"type":"chunk","data":"<base64 PCM>","done":false,"status_code":206,"step_time":…,"context_id":…}`
  - `{"type":"timestamps","word_timestamps":{"words":[…],"start":[…],"end":[…]},"context_id":…}`
  - `{"type":"done","done":true,…}`
  - `{"type":"error","title","message","status_code","error_code","doc_url","request_id","context_id"}`
  - Also `phoneme_timestamps` and `flush_done` (`flush_id`).
- **Emotion gotcha:**
  - The WebSocket schema's `generation_config.emotion` enum lists only `neutral, calm, angry, content, sad` [V].
  - The emotion guide lists about 60 values (`excited, enthusiastic, elated, euphoric, triumphant, amazed, surprised, proud, confident, determined…`), with the 6 primary ones best-supported [V].
  - **Put the sports emotions inline in the transcript as `<emotion value="excited"/>`**, and keep `generation_config.emotion` to the 5 schema values.
  - Other inline tags: `<speed ratio="1.3"/>`, `<volume ratio="1.5"/>`, `[laughter]`. Speed range is 0.6-1.5 and volume 0.5-2.0. The emotion must match the text [V].
- **Latency:** Cartesia gives no number on the model page. Independent measurements put P50 TTFA around **170-190 ms** [N].
- **SDKs:** `cartesia` Python 4.2.0 [V] and `@cartesia/cartesia-js`. Both are Apache-2.0 and were updated 2026-10-16 [N].
- **Distribution:**
  - The **laptop server holds the one Cartesia socket** and relays chunks over our `/ws` as `{type:'tts', ctx, seq, pcm_b64}`.
  - 24 kHz s16 mono is 48 KB/s per listener, which is fine for 4 phones plus a dashboard.
  - Browser playback: decode base64 → `Int16Array` → `Float32Array`. Then use either a ring-buffer AudioWorklet, or schedule `AudioBufferSourceNode`s at `nextStartTime = max(ctx.currentTime, prevEnd)`.
  - **Primary output:** laptop to a Bluetooth speaker. Phones are secondary, because iOS mic capture plus playback has routing issues (2F).
  - Keep the word timestamps in `commentary.jsonl` for Remotion captions (7B).

---

## 7. Post-game

### 7A. Practical-RIFE v4.25 (slow-mo) [V]
- **Install:**
  - `git clone https://github.com/hzwer/Practical-RIFE && pip install -r requirements.txt`. Requires **Python ≤ 3.11**.
  - Download v4.25 (2024-09-19, "recommended default") from Google Drive (`1ZKjcbmt1hypiFprJPIKW0Tt0lr_2i7bg`). Put `*.py` + `flownet.pkl` in `train_log/`.
  - There's also v4.25.lite (2024-10-20) and v4.26.
- **CLI:**
  ```
  python inference_video.py --multi=4 --video=clip.mp4 --output=clip_x4.mp4 [--fps=30] [--scale=0.5|--UHD] [--ext=mp4] [--montage] [--model=train_log]
  python inference_video.py --multi=4 --img=frames/        # numbered PNGs 0.png…N.png
  ```
  - `--exp` = log2 of `--multi`. `--scale=0.5` is for 4K input. `--skip` is obsolete.
  - **`--fps` sets the output fps.** For 8x slow-mo, interpolate 4x and write at the source fps (or set `--fps 30` on 60 fps input).
  - There is no Python API; import `train_log/RIFE_HDv3.Model` (`model.inference(img0, img1, timestep)`) if you need in-process use [E].
- **Speed:**
  - The README gives none. The RIFE paper reports 30+ fps for 2x 720p on a 2080Ti.
  - A 4090 does 1080p 4x at roughly real time [N/E]. A 6 s 1080p60 clip → 4x takes about 10-20 s [E].
- **Gotchas:**
  - Ghosting on fast arm swings; use FILM for the 1 s hero moment if needed [N].
  - Run it on the remuxed (faststart) MP4.
  - On Windows, ffmpeg must be on PATH (it is used for audio passthrough) [E].
- **Plug-in:** auto-director picks the clip → crop → RIFE → Remotion `<OffthreadVideo playbackRate>`.

### 7B. Remotion (9:16 composition from props) [V]
- **Install:**
  - `npx create-video@latest`, or add `remotion @remotion/cli @remotion/renderer @remotion/bundler` to the existing Node project.
  - Pin `remotion@4.0.538` (npm latest today) and keep every `@remotion/*` at the identical version.
- **Composition:** `<Composition id="PlayOfTheGame" component={POTG} width={1080} height={1920} fps={30} durationInFrames={…} defaultProps={…}/>`. Use `calculateMetadata` to set the duration from props.
- **CLI:**
  ```
  npx remotion render src/index.ts PlayOfTheGame out/potg.mp4 --props=props.json --codec=h264 --concurrency=8
  ```
  - **On Windows shells, inline JSON in `--props` doesn't work; pass a file path.**
  - Other flags: `--crf` (not combinable with `--video-bitrate` or HW acceleration), `--frames=0-99`, `--scale`, `--width/--height`, `--gl`, `--hardware-acceleration`, `--chrome-mode`.
  - Default codec is H.264.
- **Node API:**
  ```js
  const serveUrl = await bundle({ entryPoint: 'src/index.ts' });          // @remotion/bundler
  const composition = await selectComposition({ serveUrl, id: 'PlayOfTheGame', inputProps });   // @remotion/renderer
  await renderMedia({ composition, serveUrl, codec: 'h264', outputLocation: 'out/potg.mp4', inputProps,
                      concurrency: '50%', onProgress: ({ progress }) => push(progress) });
  ```
  - Pass the same `inputProps` to both functions.
  - `hardwareAcceleration` exists from v4.0.228.
  - `concurrency` defaults to half the CPU threads.
- **Props contract (ours):**
  ```
  { clipSrc, segments:[{from,to,rate}], scoreBug:{home,away,score}, captions:[{word,start,end}],
    commentaryAudio, gameAudioDuck:0.3, cropTrack:[{t,cx}] }
  ```
  - Serve video and audio via `staticFile()` from `public/`, or an http URL on the laptop.
  - Word captions come from Cartesia timestamps. The TikTok template (`remotion-dev/template-tiktok`) shows the pattern [N].
- **Render time:** no official number. A 20 s 1080×1920 composition with one `OffthreadVideo` takes about 30-90 s on an 8-16 thread laptop [E]. Remotion Lambda is optional.
- **License** [V, LICENSE.md]: free for individuals, for-profits with **up to 3 employees**, non-profits, and evaluation. Otherwise a Company License is required. Check the current license against the actual user or organization.

### 7C. Three.js + Spark (splat court + ball trail + skeletons) [V]
- **Install:** `npm i three@0.180.0 @sparkjsdev/spark@2.4.0`. Spark 2.4.0 was published 2026-10-20 (two days ago); peer dependency `three >=0.180.0`.
- **Upgrade-risk note:** 2.4.0 is very fresh. If anything breaks, pin the previous 2.x minor.
- **Minimal setup:**
  ```js
  import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';
  const spark = new SparkRenderer({ renderer }); scene.add(spark);
  const court = new SplatMesh({ url: '/assets/court.spz' }); scene.add(court);
  ```
  - Formats: `.ply` (incl. compressed), `.spz`, `.splat`, `.ksplat`, `.sog`.
  - Spark "fuses splat and mesh-based objects" in the normal Three.js pipeline, so ordinary meshes render in the same scene.
  - Docs and examples: https://sparkjs.dev/
- **Align the splat:** click the same 4 court corners in the splat and in the court frame, then solve a similarity transform (Umeyama). Apply it to `court.position/quaternion/scale` [N].
- **Ball trail:** keep a ring buffer of the last N 3D ball positions (court frame, metres).
  - Render with `Line2`/`LineMaterial` (examples/jsm/lines) for width, or a `TubeGeometry` over a `CatmullRomCurve3` rebuilt each frame, with alpha fading by age. Add a sphere at the head.
  - Bounce markers: flat `RingGeometry` decals at z = 0.001 (avoid z-fighting with the splat floor) [E].
- **Skeletons:** per player per frame, 24 SMPL joints in JSON.
  - Option 1: `InstancedMesh` spheres plus capsules (cylinders oriented between parent and child joints). This takes about 2 h and is zero-risk [N].
  - Option 2: a rigged SMPL `.glb` driven by bone quaternions or an `AnimationMixer` clip [N].
- **Camera presets:** courtside, top-down orthographic, broadcast-high, and POV from the head joint with slerp smoothing [N].
- **Gotchas:**
  - Splats need sorting. Spark handles multiple splats, but large splats (>2M gaussians) hurt phone GPUs; decimate in SuperSplat [N/E].
  - Phones viewing the replay get a lighter splat.

### 7D. deface CLI (privacy blur) [V]
- **Install:**
  - `python -m pip install deface`.
  - For GPU: `pip install onnx onnxruntime-gpu` (CUDA). For non-NVIDIA on Windows: `onnxruntime-directml`.
- **Command:**
  ```
  deface in.mp4 -o out.mp4 --thresh 0.2 --scale 960x540 --mask-scale 1.3 --replacewith blur --keep-audio --ffmpeg-config '{"codec":"libx264"}' --backend onnxrt
  ```
  - `--replacewith`: `blur`, `solid`, `none`, `img`, `mosaic` (`--mosaicsize 20`).
  - `--boxes` uses boxes instead of ellipses. `--draw-scores` and `--preview` help debugging. `--ep` overrides the execution provider.
- **Speed:** no benchmark; inputs above 720p are slow. Use `--scale` for detection at 540p [V].
- **Gotcha:** it blurs **all** faces, players included. For "players visible, bystanders blurred", run per-track identity first (YOLO + ByteTrack + ArcFace/OSNet) and blur bystander boxes via supervision `BlurAnnotator`. Use deface only as the blanket mode [N].

### 7E. PANNs inference (crowd/cheer audio tagging) [V]
- **Install:** `pip install panns-inference` (needs PyTorch).
- **Windows gotcha:** both checkpoints and the labels CSV are fetched with **`os.system('wget …')`**, which doesn't exist on Windows. Pre-download these into `%USERPROFILE%\panns_data\`:
  - `https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1`, saved as `Cnn14_mAP=0.431.pth`.
  - `https://zenodo.org/record/3987831/files/Cnn14_DecisionLevelMax_mAP%3D0.385.pth?download=1`, saved as `Cnn14_DecisionLevelMax.pth`.
  - `http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv`.
  - The loader re-downloads if a checkpoint file is under 3e8 bytes.
- **API:**
  ```python
  from panns_inference import AudioTagging, SoundEventDetection, labels
  audio, _ = librosa.load(path, sr=32000, mono=True); audio = audio[None, :]
  clipwise, emb = AudioTagging(checkpoint_path=None, device='cuda').inference(audio)       # (1,527), (1,2048)
  framewise = SoundEventDetection(checkpoint_path=None, device='cuda').inference(audio)     # (1,T,527)
  ```
  - Input must be 32 kHz. The SED model is `Cnn14_DecisionLevelMax` with hop 320, so T ≈ 100 frames/s [V for hop/sr; shapes E].
- **Label indices** [V, `class_labels_indices.csv`, 527 classes]:

  | Class | Index |
  |---|---|
  | Speech | 0 |
  | Shout | 8 |
  | Whoop | 10 |
  | Yell | 11 |
  | Children shouting | 13 |
  | Laughter | 16 |
  | Chant | 30 |
  | Whistling | 40 |
  | Clapping | 63 |
  | **Cheering** | **66** |
  | **Applause** | **67** |
  | **Crowd** | **69** |
  | Hubbub/speech babble | 70 |
  | Cowbell | 92 |
  | Air horn | 318 |
  | Buzzer | 398 |
  | Whistle | 402 |
  | Thump/thud | 460 |
  | **Basketball bounce** | **465** |
  | Slap/smack | 467 |
  | Bouncing | 471 |
  | Ping | 482 |

  "Boo" and "ping-pong" are not in the label set.
- **Excitement signal:**
  - `excite(t) = max(framewise[t, [66, 67, 69, 8, 10, 11, 13]])`, smoothed over 1 s and z-scored per game.
  - Fuse with RMS z-score plus referee events (notes §4: `0.35·audio + 0.25·ref_event + 0.2·motion + 0.2·VLM`) [N].
- **Performance:** about 80M params; tens of minutes of audio take seconds on GPU [E].

### 7F. GVHMR quick demo, static camera [V]
- **Environment:** conda Python 3.10, CUDA 12.1 (torch 2.3 cu121). Run `pip install -r requirements.txt && pip install -e .` on Linux (WSL2/AWS).
- **Checkpoints** in `inputs/checkpoints/`:
  - `body_models/smplx/SMPLX_{GENDER}.npz`
  - `body_models/smpl/SMPL_{GENDER}.pkl`
  - `gvhmr/gvhmr_siga24_release.ckpt`
  - `hmr2/epoch=10-step=25000.ckpt`
  - `vitpose/vitpose-h-multi-coco.pth`
  - `yolo/yolov8x.pt`
  - `dpvo/dpvo.pth` (optional)
  - Body models require **SMPL/SMPL-X registration**; everything else is on a Google Drive folder linked from INSTALL.md.
- **Command:**
  ```
  python tools/demo/demo.py --video=clip.mp4 -s [--output_root outputs/demo] [--f_mm 26] [--verbose]
  python tools/demo/demo_folder.py -f in_dir -d out_dir -s
  ```
  - `-s` / `--static_cam` skips VO (camera rotation = identity). The default VO is SimpleVO (SIFT); `--use_dpvo` is optional and slower.
  - `--f_mm` is the full-frame-equivalent focal length. For iPhone wide that's about 26 mm, ultra-wide about 13 mm [E].
- **Outputs:**
  - A torch-saved results dict with `smpl_params_global`, `smpl_params_incam`, and `K_fullimg`.
  - Cached preprocess files (bbox, vitpose, vit_features).
  - Rendered `incam`, `global`, and side-by-side videos. Paths come from the Hydra config; expect `hmr4d_results.pt` [E].
- **Gotchas:**
  - **Single person:** `tracker.get_one_track(video)` gives one bbox track. For multiple players, crop or mask per track and run once per player [V].
  - It **resamples input to 30 fps** [V].
  - Root position: anchor with ground-plane foot projection from your PnP extrinsics [N].
- **Speed:** about 1-2x real time per person-track on a 4090, preprocessing-dominated [N/E].

### 7G. ReCamMaster (generative arc-around re-shoot) [V]
- **Repo:** `KlingAIResearch/ReCamMaster`. Weights: `step20000.ckpt` from HF `KwaiVGI/ReCamMaster-Wan2.1`, which now resolves to **`KlingTeam/ReCamMaster-Wan2.1`**. Place it in `models/ReCamMaster/checkpoints/`.
- **Base model:** `python download_wan2.1.py` puts Wan2.1-T2V-1.3B into `models/Wan-AI/Wan2.1-T2V-1.3B/`.
- **Command:**
  ```
  python inference_recammaster.py --cam_type 9 --dataset_path data/potg [--ckpt_path ...]
  ```
  - `cam_type`: 1 pan R, 2 pan L, 3 tilt up, 4 tilt down, 5 zoom in, 6 zoom out, 7 translate up, 8 translate down, **9 arc left, 10 arc right** (7-10 include rotation).
  - Input: mp4s with **at least 81 frames** plus `metadata.csv` (path, caption), following `example_test_data`. Training uses 832×480; resize the input to 832×480 [E].
- **VRAM/time:** not stated in the README. Estimate about 10-20 GB VRAM, about 6-12 min per clip on a 4090, about 3-5 min on A100/H100 [N/E].
- **Gotchas:**
  - The open Wan2.1 port is weaker than the paper's model, and small fast players hallucinate [N].
  - Pre-render **one** trophy clip on AWS; never on the critical path.

---

## 8. Auto-director: per-camera visibility score + Viterbi with switching cost

**References** (verified links)
- Arev, Park, Sheikh, Hodgins, Shamir, "Automatic Editing of Footage from Multiple Social Cameras", ACM TOG 33(4), SIGGRAPH 2014. PDF: https://studios.disneyresearch.com/wp-content/uploads/2019/03/Automatic-Editing-of-Footage-from-Multiple-Social-Cameras.pdf
  - Many uncalibrated handheld cameras, including sports games. A **trellis graph** is optimized by dynamic programming: maximize coverage of the joint attention point, with cinematographic constraints (180° rule, jump-cut avoidance, shot-length/cut-pacing).
  - **This is the closest published blueprint for Trophy** [V for summary; DP-on-trellis details are from memory].
- Leake, Davis, Truong, Agrawala, "Computational Video Editing for Dialogue-Driven Scenes", ACM TOG 36(4) 2017: https://graphics.stanford.edu/papers/roughcut. Editing idioms are encoded as **HMMs** over clip choices; the HMM is solved by Viterbi-style DP [V for HMM; decoding detail E].
- Chen, Lu, Tian, Little, "Learning Sports Camera Selection from Internet Videos", WACV 2019: https://arxiv.org/abs/1809.02854. A learned per-frame selector; good for citing "learned" vs. our heuristic [V].
- LangView, "Which Viewpoint Shows it Best?" (CVPR 2025): https://github.com/SAGNIKMJR/lang-view (MIT, 8★, pushed 2026-06). Best-view selection on Ego-Exo4D, which includes basketball [V].

**Per-camera score**, per window Δ = 0.25-0.5 s [N]:
```
s_c(t) = 0.30·vis_actor + 0.25·vis_ball + 0.20·facing + 0.15·quality + 0.10·geometry      (each in [0,1])
  vis_actor  = clamp(area(bbox_actor)/A_ref) · (1 − maxIoU with other people)       # actor from events.jsonl
  vis_ball   = 1[ball detected] · edge_margin_factor
  facing     = max(0, n_torso · (−view_dir_c))                                       # SMPL global orient
  quality    = sharpness(Laplacian var, normalized) − blur − shake(global flow)
  geometry   = 1 − dist(play_centroid, camera_c)/D_max
s_c(t) = −∞ if camera c dropped frames / offline in that window
```

**Viterbi with switching cost and min/max shot length** (state = (camera c, dwell d), K ≤ 4 cameras, D = max_shot/Δ)
```
cost(t,(c,d)) = −s_c(t)
transition (c,d) → (c,d+1):   0                         if d < D            (stay)
           (c,d) → (c',1):    λ_t + J(c,c') + R(c,c')   if c'≠c and d ≥ Dmin (cut; forbidden while d < Dmin)
           (c,D) → (c,D):     μ (> 0, discourages over-long shots), or force a cut at D
λ_t  = λ·(0.3 if |t − nearest action boundary (pass/shot release, point end)| < 0.3 s else 1)    # cut on action
J    = jump-cut penalty if angle(view_c, view_c') < 30°
R    = 180°-rule penalty if c and c' are on opposite sides of the line of action
V[0,(c,1)] = cost(0,(c,1));  V[t,s'] = cost(t,s') + min_s (V[t−1,s] + trans(s,s'));  keep backpointers;
path = argmin_s V[T−1,s], then backtrack.   Complexity O(T·K²·D) (T=2400 windows, K=4, D=32: trivial).
```
- Defaults [N]: Dmin = 2 s, D = 8 s, λ ≈ 0.15-0.3 in score units. Tune so you get about 6-12 cuts per minute.
- **Live variant:** a **fixed-lag Viterbi** (decide the cut L = 1-2 s behind live), or a greedy rule with hysteresis: switch only when `s_c' − s_cur > λ` for at least 0.5 s and dwell ≥ Dmin.
- **Replay rule:** for the slow-mo replay, add a constraint `c ≠ live_cut(t)` ("replay from a different angle") [N].
- **Tie-breaker:** send the top-2 thumbnails to a VLM or SubQ `choice` ("which shows the [event] best?") only when `|s1 − s2| < 0.05` [N].
- **Plug-in:** reads `events.jsonl`, the track/ball tables, and per-camera quality. Writes `edl.json` (`[{cam, t_in, t_out}]`) for ffmpeg/Remotion.

---

## 9. Blockers and must-do-tonight checklist
1. **Windows vs Linux:** vLLM (no Windows wheels), GVHMR, and ReCamMaster need WSL2 with CUDA or AWS. Set up WSL2 + the NVIDIA driver tonight, or plan everything ML-heavy on AWS.
2. **Cert:** build Caddy with `caddy-dns/cloudflare`, issue the wildcard, set the A record to the laptop's static LAN IP, and **turn off rebind protection** on the travel router. Test from an iPhone.
3. **SubQ:** create the key; confirm `GET /v1/models` lists `subq-snap-1.1`; run the smoke test; get a spare key from a teammate. No SDK and no published rate limits.
4. **FastRTC:** if used, set `concurrency_limit=8`, because the default and `None` both mean 1. It passes no timestamps. Docs site cert is expired. **Prefer raw aiortc 1.15.0 + av ≥ 17.**
5. **aiortc:** receive queues are unbounded, so always run a draining pump. Only H.264 Constrained Baseline is offered. Non-trickle ICE.
6. **Claude:** `temperature`/`top_p`/`top_k` are rejected (API 2026-10-21). Forced `tool_choice` is rejected on Opus/Sonnet 5.5. Structured-output schemas can't be recursive or carry numeric constraints, so DSL expressions travel as strings and are parsed by our code.
7. **Cartesia:** confirm the auth header (`X-API-Key` vs Bearer) and the version param. The WS `generation_config.emotion` enum is narrow, so use inline `<emotion value="excited"/>`. Lower `max_buffer_delay_ms` from 3000. Browsers use access tokens (≤ 1 h).
8. **Downloads (large/gated):**
   - SMPL/SMPL-X (registration)
   - GVHMR Google Drive checkpoints
   - RIFE v4.25 (Google Drive)
   - PANNs checkpoints + CSV (manual on Windows)
   - `Qwen/Qwen3-VL-8B-Instruct-FP8` (about 10 GB)
   - Wan2.1-T2V-1.3B + ReCamMaster `step20000.ckpt` (on AWS)
9. **Python versions:** RIFE needs ≤ 3.11, GVHMR 3.10, vLLM ≥ 3.11, aiortc/anthropic ≥ 3.10. Use separate venvs or conda envs: `ingest` (3.11), `gvhmr` (3.10), `vllm` (3.11 in WSL).
10. **Remotion on Windows:** `--props` must be a file path. Keep all `@remotion/*` packages at the same version (4.0.538).
11. **Spark 2.4.0** is two days old; be ready to pin back.

## Sources (fetched 2026-10-22)
- aiortc:
  - https://github.com/aiortc/aiortc/tree/main/examples/server (server.py, client.js)
  - src/aiortc/rtcrtpreceiver.py
  - src/aiortc/codecs/__init__.py and h264.py
  - docs/changelog.rst
  - https://pypi.org/project/aiortc/
- FastRTC:
  - https://github.com/gradio-app/fastrtc (backend/fastrtc/stream.py, tracks.py, utils.py; docs/userguide/video.md, api.md)
  - https://pypi.org/project/fastrtc/
- SubQ: https://docs.subq.ai/markdown/endpoints/decisions-api.md
- vLLM:
  - https://docs.vllm.ai/en/latest/features/structured_outputs.html
  - https://pypi.org/project/vllm/
- Qwen:
  - https://github.com/QwenLM/Qwen3-VL
  - https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-FP8
- Claude API: claude-api skill (models, structured outputs, streaming, API version 2026-10-21); https://pypi.org/project/anthropic/
- Code World Models:
  - https://arxiv.org/abs/2510.04542
  - https://arxiv.org/html/2510.04542
- Cartesia:
  - https://docs.cartesia.ai/api-reference/tts/websocket
  - https://docs.cartesia.ai/use-the-api/api-conventions
  - https://docs.cartesia.ai/api-reference/auth/access-token
  - https://docs.cartesia.ai/build-with-cartesia/sonic-3/volume-speed-emotion
  - https://docs.cartesia.ai/build-with-cartesia/tts-models/latest
  - https://pypi.org/project/cartesia/
- MDN:
  - https://developer.mozilla.org/en-US/docs/Web/API/AudioSession/type
  - https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback
- Caddy:
  - https://github.com/caddy-dns/cloudflare
  - https://caddyserver.com/docs/automatic-https
- Practical-RIFE: https://github.com/hzwer/Practical-RIFE
- Remotion:
  - https://www.remotion.dev/docs/cli/render
  - https://www.remotion.dev/docs/renderer/render-media
  - https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
  - npm `remotion` 4.0.538
- Spark:
  - https://github.com/sparkjsdev/spark
  - npm `@sparkjsdev/spark` 2.4.0
- deface: https://github.com/ORB-HD/deface
- PANNs:
  - https://github.com/qiuqiangkong/panns_inference (inference.py, config.py)
  - https://github.com/qiuqiangkong/audioset_tagging_cnn/blob/master/metadata/class_labels_indices.csv
- GVHMR: https://github.com/zju3dv/GVHMR (README, docs/INSTALL.md, tools/demo/demo.py)
- ReCamMaster:
  - https://github.com/KlingAIResearch/ReCamMaster
  - https://huggingface.co/KlingTeam/ReCamMaster-Wan2.1
- Auto-director:
  - Arev et al. 2014 (Disney Research PDF above; CMU RI page https://ri.cmu.edu/publications/automatic-editing-of-footage-from-multiple-social-cameras)
  - Leake et al. 2017 (https://graphics.stanford.edu/papers/roughcut)
  - https://arxiv.org/abs/1809.02854
  - https://github.com/SAGNIKMJR/lang-view
