# Trophy, cloud-only architecture (Cal Hacks 13, researched 2026-10-23)

**New constraint:** nothing runs on the team's laptops. Laptops act as thin clients only: a browser, plus VS Code/Cursor over Remote-SSH. Compute runs on AWS ($10k YC University credits) or the listed credit services. Phones run the PWA in the browser.

This document moves the build plan's §0 process table and F1-F18 to the cloud. Source labels:
- **[V]** verified today from a primary source (vendor docs or pricing page).
- **[3P]** third-party tracker or review; treat as approximate.
- **[I]** my inference or estimate. Measure it at hour 0.

---

## 0. TL;DR

- **Region: us-west-2 (Oregon).** us-west-1 (N. California) offers only G4dn, Inf1, P5 and P5en accelerated instances: no G5, G6, G6e, G7 or G7e [V]. us-west-2 offers all of them [V]. Oregon adds roughly 20-25 ms of RTT over N. California [3P], which is small next to cellular latency.
- **Live box: one g6e.4xlarge** (1× L40S 48 GB, 16 vCPU, 128 GB, about $3.00/h on demand) [3P]. It runs ingest, flight, possession, resting, audio, engine and gateway as separate Docker Compose services on the NVIDIA container toolkit (DLAMI Base OSS, Ubuntu 24.04).
- **Batch box: a separate one** (g6e.2xlarge, or g7e.2xlarge for 96 GB), so RIFE, GVHMR and ReCamMaster can't starve live calls.
- **Dev boxes:** small, one per teammate.
- **Blocker #1:** the default **"Running On-Demand G and VT instances" quota is 0 vCPUs** on a new account [V]. Request about 96-128 vCPUs today, in us-west-2 plus one backup region, and file the separate Spot quota too.
- **Phones send WebRTC to aiortc on an Elastic IP.** STUN gives a server-reflexive (srflx) candidate. aiortc picks random UDP ports and can't restrict them [V, source]. So open UDP 32768-60999. aiortc has **no ICE-TCP** [V, source], so add **coturn with TURN over TLS on 443** for networks that block UDP. The JPEG-over-WSS fallback stays.
- **Call push path:** our own gateway WSS carries the critical beep path, because the phone already holds that socket for clock sync. **Supabase** holds the database, Realtime for the dashboard and spectators, and Presence. **S3** holds the recordings: Supabase free storage is 1 GB with a 50 MB per-file cap [V].
- **Roboflow:** train RF-DETR on Universe datasets in Roboflow cloud. Then **self-host** in the `roboflow-inference-server-gpu` container on our EC2, which is free: "Running a model on your own hardware doesn't use credits" [V]. Use Serverless only for one-frame-per-throw scoring.
- **Decide chain:** SubQ Snap → **Gemini 3.8 Flash** → Claude votes → geometry. **Drop local vLLM/Qwen3-VL** unless the L40S has spare VRAM.
- **Latency budget:** about 0.5-0.8 s for geometry-only calls and about 1.0-1.6 s for Snap-judged calls (p50) [I]. The 2.0 s Snap timeout falls back to a geometry call marked "challengeable".
- **Cost for the 40 h weekend:** about **$450-650 of AWS** plus about $100-200 of other services, well inside the credits.

---

## 1. AWS

### 1.1 Region
| | us-west-1 (N. California) | us-west-2 (Oregon) |
|---|---|---|
| Accelerated families | **G4dn, Inf1, P5, P5en only** [V: [EC2 instance types by Region](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-regions.html)] | G4dn, G5, G6, G6e, G6f, Gr6, **G7, G7e**, P4d, P5, P6 and more [V, same page] |
| RTT from SF | ~2-5 ms (the region sits in the Bay Area) [I] | ~20-25 ms (inter-region us-west-1↔us-west-2 ≈ 20.5-24 ms) [3P: [economize](https://www.economize.cloud/resources/aws/latency/us-west-1-vs-us-west-2/)] |
| Verdict | Only T4 GPUs (g4dn). A possible latency-only edge box, not worth splitting regions | **Use this.** The 20 ms is small next to 5G latency (Ookla 5G median latency ~44 ms for T-Mobile) [3P: [RCR/Ookla](https://www.rcrwireless.com/20260203/5g/ookla)] |

Backup region if us-west-2 capacity or quota fails: **us-east-2 (Ohio)**. It has G6, G6e, G7 and G7e [V], adding roughly 50-60 ms RTT from SF [I].

### 1.2 GPU instance choice and price (Linux on demand, us-west-2; spot is volatile)
| Type | GPU | vCPU / RAM | On-demand $/h | Spot $/h | Notes |
|---|---|---|---|---|---|
| g6.xlarge | 1× L4 24 GB | 4 / 16 | 0.805 | ~0.36-0.46 in us-west-2 [3P] | Good dev box |
| g6.2xlarge | L4 | 8 / 32 | 0.978 | — | Dev box for B and C |
| g6.4xlarge | L4 | 16 / 64 | 1.323 | — | Cheap live box, but 24 GB VRAM is tight with every model loaded |
| g5.xlarge / 2xlarge / 4xlarge | 1× A10G 24 GB | 4 / 8 / 16 vCPU | 1.006 / 1.212 / 1.624 | ~0.53-0.77 (xlarge) [3P] | Older; costs more than g6 |
| g6e.xlarge | 1× L40S 48 GB | 4 / 32 | 1.861 | — | |
| g6e.2xlarge | L40S 48 GB | 8 / 64 | 2.242 | — | Batch/post-game box |
| **g6e.4xlarge** | **L40S 48 GB** | **16 / 128** | **3.004** | — | **Recommended live box.** 16 vCPU for software decode of 4×720p plus 48 GB VRAM |
| g6e.8xlarge | L40S 48 GB | 32 / 256 | 4.529 | — | Use if decode or CPU-side pose saturates 16 vCPU |
| g7.2xlarge (new, GA June 2026) | 1× RTX PRO 4500 Blackwell 32 GB | 8 / 32 | 2.52 | 0.74-0.85 [3P] | Only in Ohio and Oregon [3P: [HPCwire/AWS](https://www.hpcwire.com/off-the-wire/aws-announces-amazon-ec2-g7-instances-accelerated-by-nvidia-rtx-pro-4500-blackwell-server-edition-gpus)]. Blackwell needs CUDA 12.8+ torch builds, so the old repo pins risk breaking |
| g7e.2xlarge | 1× RTX PRO 6000 Blackwell 96 GB | 8 / 64 | 3.363 | ~1.81 (>20% interruption) [3P] | Use for ReCamMaster or TrajectoryCrafter (≥ 28 GB). Same Blackwell pin risk |

Prices come from [DevZero g6](https://www.devzero.io/instances/aws/families/g6), [g6e](https://www.devzero.io/instances/aws/families/g6e), [g5](https://www.devzero.io/instances/aws/families/g5), [g7e](https://www.devzero.io/instances/aws/g7e.2xlarge), [g7](https://www.devzero.io/instances/aws/g7.2xlarge) and [cloudprice g6e](https://cloudprice.net/aws/ec2/instances/g6e.xlarge) [3P]. Confirm in the console. The DevZero family pages' spot column shows the cheapest region worldwide, not us-west-2.

**Why the L40S (g6e) and not the L4 or Blackwell:**
- The L40S is Ada generation, so it works with the plan's pinned torch and cu12x stacks (BlurBall/WASB on numpy 1.26, rtmlib with onnxruntime-gpu, RF-DETR with TensorRT).
- 48 GB holds every live model at once, plus Qwen3-VL-8B-FP8 if you keep it.
- Blackwell (G7/G7e) needs CUDA 12.8+ and newer torch, the same issue the plan flags for RTX 50-series laptops.

**Don't use spot for the live demo box.** A 2-minute interruption notice during judging would end the demo. Spot is fine for dev boxes and batch jobs.

### 1.3 Quota (blocker)
- **"Running On-Demand G and VT instances": the default is 0 vCPUs**, and it is adjustable [V: [EC2 instance-type quotas](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)]. Quotas count **vCPUs**, not instances. Spot has a **separate** quota, "All G and VT Spot Instance Requests" [V: [re:Post](https://repost.aws/knowledge-center/ec2-on-demand-instance-vcpu-increase)].
- **Approval speed:** there is no SLA. Anecdotes run from about 20-30 minutes (auto-approved), to denials within 20 minutes, to several days of human review [3P: [re:Post thread](https://repost.aws/questions/QUBBbH23A8TliNJqb8XliSYg/how-long-to-wait-for-a-response-to-a-quota-increase-reply), [yomotherboard](https://yomotherboard.com/question/can-i-spin-up-15-g5-xlarge-ec2-instances-on-a-new-aws-account/)]. New accounts with no usage history get the most scrutiny.
- **What to request, now:**
  - us-west-2, On-Demand G and VT: **128 vCPU**. That covers g6e.4xlarge (16) + g6e.2xlarge (8) + 4× g6.2xlarge (32) + headroom. Request 64 if you want a smaller ask that is likelier to auto-approve.
  - Use case text: "Hackathon (Cal Hacks), real-time computer vision inference, 40 hours, YC credits applied".
  - File the same request in **us-east-2**, and file the **Spot G and VT** quota in both regions.
  - Open a support case (Account and billing support is free) to speed things up, and ask any AWS staff at the venue.
- **Also check:**
  - The credits are applied to this account, and the account isn't still in "verification pending".
  - Lambda concurrency (Remotion): new accounts may get **10** instead of 1000 [V: [AWS Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html), [Remotion](https://remotion.dev/docs/lambda/troubleshooting/rate-limit)].

### 1.4 AMI, Docker and per-service environments
- **AMI:** "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)". The 2026-10-06 release ships driver 595.91.07, default CUDA 13.2 (other CUDA versions selectable) and **NVIDIA Container Toolkit 1.20.1**, with Docker packaged [V: [DLAMI release notes](https://docs.amazonaws.cn/en_us/dlami/latest/devguide/aws-deep-learning-ami-gpubaseoss-ul2404-2026-10-08.md)]. Run each Python service in its own container image with its own pins. CUDA user-space comes from the image (e.g. `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`), and the host driver supports it.
- **Docker Compose GPU stanza** (per GPU service):
  ```yaml
  deploy:
    resources:
      reservations:
        devices: [{driver: nvidia, count: all, capabilities: [gpu]}]
  ```
  Every container can share the single GPU.
- **The shared-memory ring buffers need IPC sharing.** Docker gives each container its own IPC namespace, so `multiprocessing.shared_memory` segments are invisible across containers by default [3P: [DZone](https://dzone.com/articles/docker-in-action-the-shared-memory-namespace)].
  - Simplest fix: **`ipc: host` on ingest, flight, possession and resting**, plus a large `/dev/shm`.
  - Alternative: `ipc: shareable` on `ingest`, and `ipc: "service:ingest"` (or `container:<name>`) on the readers.
  - Also put the Python `resource_tracker` on the creating process only, so readers don't unlink segments on exit.
- **Networking:** run `ingest` with **`network_mode: host`**. aiortc binds random UDP ports, which can't be pre-published (see §1.6). The other services stay on a compose bridge network. Redis binds to the bridge and is never exposed publicly.
- **Bake an AMI** once the box works, Saturday ~9 AM (create an image plus a launch template). A dead instance then comes back in about 10 minutes.

### 1.5 Remote development (laptops as thin clients)
- **VS Code Remote-SSH, or Cursor's Remote-SSH extension**, into the dev boxes and the live box.
  - Give each person their own Linux user (or own dev box) to avoid stepping on each other's venvs.
  - Forward ports for dashboards with `LocalForward` in `~/.ssh/config`.
- **Security for SSH:**
  - Key-only auth.
  - Either open 22/tcp only to the venue's egress IP (it can change, so update the SG), or skip port 22 and use **SSM Session Manager** / **EC2 Instance Connect Endpoint** as the SSH ProxyCommand.
- **Git:** GitHub, with **Greptile** on PRs (§5). Claude Code or the Cursor agent can run *on* the box.
- **Data:** a 200-300 GB gp3 EBS root volume per box. Pre-download the weights onto the live box tonight (BlurBall, WASB, RIFE, PANNs, TT3D, RF-DETR checkpoints, and Qwen if kept). Downloads now run in the datacenter, not over venue Wi-Fi.

### 1.6 WebRTC on EC2: security groups, NAT, STUN and TURN
**How aiortc behaves (read from source today):**
- `RTCIceGatherer` uses **`stun:stun.l.google.com:19302` by default** if `iceServers` is None.
- It keeps at most one STUN and one TURN server. TURN may be `turn:` over UDP/TCP or `turns:` over TCP+TLS [V: [rtcicetransport.py](https://raw.githubusercontent.com/aiortc/aiortc/main/src/aiortc/rtcicetransport.py)].
- aioice binds host candidates to **port 0 (OS-chosen)**, with no port-range option, and creates **UDP candidates only (no ICE-TCP)** [V: [aioice ice.py](https://raw.githubusercontent.com/aiortc/aioice/main/src/aioice/ice.py)].

**What that means on EC2:**
- The instance's NIC only knows its private IP. The public Elastic IP is a 1:1 NAT [3P: [Pion NAT guide](https://www.mintlify.com/pion/ice/guides/nat-traversal)].
- That NAT preserves ports and is endpoint-independent. aiortc's STUN query therefore yields an **srflx candidate `EIP:same-port`**, which is reachable once the SG allows it [I, standard behaviour].
- Keep egress open so STUN to Google works. If the STUN server is unreachable, aiortc fails to connect [3P: [willow PR](https://github.com/toverainc/willow-inference-server/pull/140)]. Or point it at our own coturn.
- **Security group for the live box:**
  - 80/tcp and 443/tcp from 0.0.0.0/0 (Caddy).
  - **UDP 32768-60999 from 0.0.0.0/0**, the Linux default `ip_local_port_range` that aiortc's random ports come from. Optionally narrow it with `sysctl net.ipv4.ip_local_port_range="40000 40999"` on the host and open just that range.
  - 22/tcp restricted as in §1.5.
  - Nothing else.
- **Phones on cellular CGNAT:**
  - The phone is the side behind a (often symmetric) NAT, and the server has a public address. The phone's connectivity checks reach `EIP:port`, and aiortc learns the phone's **peer-reflexive** address from them. So **symmetric NAT on the phone doesn't require TURN** when the server is public [I, standard ICE].
  - TURN is needed only when the phone's network **blocks outbound UDP**: some guest or venue Wi-Fi, corporate networks, occasional carrier quirks.
  - Rough industry split for P2P (not client↔server): ~70% srflx, ~25% TURN, ~5% fail [3P: [expressturn](https://www.expressturn.com/blog/webrtc-calls-fail-on-mobile-networks)]. Client↔public-server sessions do much better.
  - Because aiortc has no ICE-TCP, a UDP-blocked phone has **no path** without TURN-over-TCP/TLS.
- **TURN options:**
  1. **coturn on a small EC2** (t4g.small, ~$0.02/h) with its own Elastic IP. Listen on **443/tcp (TLS)** plus 3478 udp/tcp. Open relay ports UDP 49152-65535. Use static-auth-secret (REST API credentials, minted by the gateway). Give phones `turns:turn.<domain>:443?transport=tcp` as well as UDP TURN. Most robust.
  2. **AWS Kinesis Video Streams WebRTC managed TURN:** `GetIceServerConfig` returns TURN URIs and credentials.
     - Limits: 5 Mbps per allocation, **5-minute credential lifetime**, 50 allocations per channel [V: [KVS WebRTC quotas](https://docs.aws.amazon.com/kinesisvideostreams-webrtc-dg/latest/devguide/kvswebrtc-limits.html)].
     - TURN minutes reportedly about $0.12 per 1,000 [3P].
     - Works with a standard WebRTC client per the docs' description, but this is unconfirmed for aiortc. A plan B.
- **Always keep F2B (JPEG or WebCodecs over WSS on 443)**: it works through any network that allows HTTPS. Option worth considering: **WebCodecs H.264 over WSS** (≈2 Mbps instead of MJPEG's ~5-10 Mbps).
  - Safari has had `VideoEncoder` with avc1 since 16.4 [3P: [WebKit bug 258060](https://bugs.webkit.org/show_bug.cgi?id=258060)]. Full parity came in Safari 26 [3P].
  - **WebTransport is Baseline since Safari 26.4 (Mar 2026)** [3P: [webrtc.ventures](https://webrtc.ventures/2026/04/webtransport-is-now-baseline-what-it-means-for-real-time-media/)].
  - Test on the actual demo iPhones at hour 0.

### 1.7 Caddy with auto-HTTPS on a public domain
- Point an A record `trophy.<domain>` (and `turn.<domain>` to the coturn EIP) at the Elastic IP. Route 53 is fine and comes out of credits.
- The Caddyfile `trophy.<domain> { reverse_proxy /ws* gateway:8000; reverse_proxy gateway:8000 }` gets a Let's Encrypt certificate automatically, as long as 80 and 443 are reachable. WebSocket upgrade proxying works by default.
- This **removes the plan's LAN problems** (router DNS-rebind, `.local` mDNS, WSL mirrored networking). iOS gets a valid HTTPS origin for getUserMedia, wake lock and Web Audio.
- If coturn shares the box, it can't also use 443. Give it a second EIP, or use 5349.

### 1.8 Remotion Lambda (trophy clip render)
- **Setup** [V: [Remotion Lambda setup](https://www.remotion.dev/docs/lambda/setup)]:
  1. `npx remotion add @remotion/lambda`.
  2. Create the IAM policy from `npx remotion lambda policies role`, then the role `remotion-lambda-role`.
  3. Create IAM user `remotion-user` with an access key, saved in `.env` as `REMOTION_AWS_ACCESS_KEY_ID` and `REMOTION_AWS_SECRET_ACCESS_KEY`, with an inline policy from `npx remotion lambda policies user`. Check with `npx remotion lambda policies validate`.
  4. `npx remotion lambda functions deploy`. Redeploy whenever you change the Remotion version.
  5. `npx remotion lambda sites create src/index.ts --site-name=trophy`.
  6. `npx remotion lambda quotas`.
  7. `renderMediaOnLambda()` from the broadcast service.
- **Limits:** up to 10 GB RAM, 10 GB disk, 15 min timeout. Default concurrency is 1000 per region, but **new accounts may have only ~10**. Work around it with a larger `framesPerLambda` (e.g. 100 frames → ~9 renderers), or request an increase (`npx remotion lambda quotas increase` works for root accounts only) [V: [limits](https://www.remotion.dev/docs/lambda/limits), [rate-limit](https://remotion.dev/docs/lambda/troubleshooting/rate-limit)].
- **Cost:** examples run $0.001-$0.11 per render. A 1-minute video from the same S3 bucket costs ≈ $0.017 in ≈ 19 s [V: [cost example](https://www.remotion.dev/docs/lambda/cost-example)]. A 20 s 9:16 trophy clip should cost about $0.01 and take 15-30 s [I].
- **Notes:**
  - Put the RIFE-interpolated hero clip and source chunks in S3 in the **same region** as the Lambda (us-west-2), so the render doesn't pay egress or latency.
  - Licensing: Remotion is free for individuals and companies of ≤ 3 people (the plan's note). A 4-person student hackathon team isn't a company, so this should be fine [I].
  - Fallback: render with the plain Remotion CLI in a container on the batch box.

---

## 2. Phone uplink: venue Wi-Fi vs 5G/LTE

**Bandwidth needed:**
- Live: 720p30 H.264/VP8 at **~1.5-3 Mbps per phone**, so 6-12 Mbps for 4 phones.
- Recording: the plan's 1080p at **12 Mbps** is the heavy part. Each minute of rally uploaded costs 90 MB per phone.
- Challenge crops and onset snippets are negligible.

**Cellular in the US (2026):**
- Ookla 5G median **upload**: T-Mobile 13.57, Verizon 13.06, AT&T 8.98 Mbps. Median 5G **latency** for T-Mobile is 44 ms [3P: [RCR Wireless / Ookla](https://www.rcrwireless.com/20260203/5g/ookla)].
- One phone can sustain 2-3 Mbps live with headroom. It **can't** also upload 12 Mbps 1080p in real time.
- Expected RTT from phone to us-west-2: **~55-80 ms median on 5G, p95 150-250 ms**. On LTE it's ~70-120 ms with heavier tails [I: Ookla latency plus ~20 ms SF→Oregon].
- Each phone on its own radio gives **path diversity**. Use at least two carriers among the 4 phones.

**Venue Wi-Fi** (Palace of Fine Arts, 2,000+ hackers; Cal Hacks 12 had 2,156 on Devpost):
- There are no published measurements [searched; none].
- Assume it's congested at peaks (opening, demos), possibly with client isolation, and possibly blocking UDP. Uncongested RTT to Oregon would be ~25-40 ms [I].
- **Test at hour 0 and again around 8 PM.** Check the ICE candidate types that win (`getStats()` `candidate-pair`), RTT, and achieved bitrate.

**WebRTC over cellular, reliability:**
- Congestion control ramps the bitrate. Roboflow notes it can take up to a minute to reach full quality at 1080p30 [V: [Roboflow streaming docs](https://docs.roboflow.com/deploy/serverless-video-streaming-api)].
- Packet loss on cellular causes freeze-then-recover. aiortc supports NACK and PLI.
- Use `degradationPreference='maintain-framerate'` in the PWA (ball tracking needs frame rate more than resolution), plus a bitrate cap (`maxBitrate` 2.5 Mbps) and a 960×540 floor.

**Recommendations:**
1. **Live stream from each phone over its own 5G.** Use venue Wi-Fi only if the hour-0 test beats cellular. A dedicated 5G hotspot isn't a laptop and is allowed, but four separate radios beat one shared hotspot.
2. **Don't stream recordings.** Keep the 1080p recording on-phone (OPFS). Upload **only the chunks for a challenged or closing rally** (±1.5 s ≈ 4.5 MB per phone at 12 Mbps, under 3 s on 5G). Upload the full game after the game, over Wi-Fi, straight to **S3 multipart via presigned URLs**.
3. **Clock sync over the internet is noisier.** Min-RTT NTP filtering over cellular with asymmetric paths gives roughly ±5-15 ms instead of ±1-3 ms on a LAN [I].
   - **Rely on the per-camera QR-timecode calibration (F2).** It is optical, so network jitter doesn't affect it. Show it on any phone or tablet screen, not a laptop.
   - Timestamp audio onsets against the **same phone's** `requestVideoFrameCallback` clock, so the audio-video offset comes from one device.
   - The network offset then matters only for display, not for fusing bounces.

---

## 3. Roboflow (hosted options and training)

| Option | What | Latency | Price | Fit for Trophy |
|---|---|---|---|---|
| **Serverless Cloud API** (formerly Hosted API v1/v2) | `https://serverless.roboflow.com`, one endpoint for models and Workflows, GPU autoscaling, 20 MB upload cap [V: [docs](https://docs.roboflow.com/deploy/serverless-hosted-api-v2)] | Not published. Roboflow's own recipe says "seconds (per-frame after upload)" for hosted vs "tens of ms" for self-hosted [3P via [Roboflow docs](https://docs.roboflow.com/developer/recipes/process-a-video-stream)] | RF-DETR Medium ≈ 0.000188 credits per image (~5,330 per credit); Nano ≈ 0.000125 [V: [pricing](https://roboflow.com/pricing)] | **Only for 1-frame-per-event calls**: the cornhole or mini-golf "at rest" snapshot. Not live tracking |
| **Serverless Video Streaming (WebRTC)** | The SDK opens a WebRTC session to a serverless Workflow. JS SDK `@roboflow/inference-sdk` for browsers. Regions us/eu/ap; plans `webrtc-gpu-small`/`medium`/`large`; **10 concurrent streams per workspace by default**; quality ramps over up to ~1 min [V: [docs](https://docs.roboflow.com/deploy/serverless-video-streaming-api)] | Not published | Small 10 h per credit, Medium 5 h per credit, Large 2.5 h per credit [V: [credits](https://roboflow.com/credits)] | **Interesting fallback** if GPU quota is denied. Phones (or our server, re-streaming) could run RF-DETR + ByteTrack Workflows without our own GPU. Keep the API key off the phone; it needs a backend proxy |
| **Dedicated Deployment** | A private Roboflow-managed server running Inference. gpu-small = T4, gpu-medium = L4. Dev deployments auto-delete after 3 h; prod is persistent with a subdomain. **Core or Enterprise only** [V: [docs](https://docs.roboflow.com/deploy/dedicated-deployments)] | Predictable; US data centres | **1 credit per GPU-hour**, billed per minute [V] | Quota-denied fallback for possession or resting |
| **Self-hosted Inference container on our EC2** | `roboflow/roboflow-inference-server-gpu`. Pulls our trained model with the API key, caches it, serves HTTP locally | Model time plus ~5-15 ms local HTTP [I] | **Free**: "Running a model on your own hardware doesn't use credits" [V: [credits](https://roboflow.com/credits)] | **Primary path for Roboflow-trained models.** As its own container, it also keeps the `inference` package out of the live venvs, which the plan warns about |

**Training RF-DETR in Roboflow cloud from Universe datasets:**
1. Fork *Cornhole Referee* (394 images, CC BY 4.0), `minigolf-ball-detection/5`, the roundnet dataset (861 images) and flag football into the workspace.
2. Generate a version (augmentations, 640 px), then **Train → RF-DETR**.
3. Cost: **1 credit = 30 min of GPU training** [V: [credits](https://roboflow.com/credits)].
   - Users report RF-DETR time estimates running badly long (a "3 h" job took 10.5 h and 20+ credits) [3P: [Roboflow forum](https://discuss.roboflow.com/t/rf-detr-training-glitch-10-5-hours-20-credits-and-no-progress-past-epoch-12/9320)]. Roboflow says it has since shipped early stopping.
   - **Set an epoch cap, and start the jobs tonight.**
   - Medium and larger sizes are reportedly paid-only [3P]. Nano or Small is enough for bags and balls.
4. Plans: Free has 10 credits a month. **Core is $39/mo** for +10 credits, Dedicated Deployments and premium features. Extra credits cost $4-6 each [V: [pricing](https://roboflow.com/pricing)].
5. **Pulling to our EC2:**
   - (a) Use the inference container with the model ID, which needs no weight download and is free to run.
   - (b) Download the weights. The "download trained weights" feature is for premium plans per the Feb 2025 changelog [3P: [changelog](https://docs.roboflow.com/reference/changelog/changelog/february-2025/download-trained-model-weights-from-roboflow)]. Then load them in `rfdetr` with TensorRT inside the `possession` container.
   - Do (a) first. Do (b) if you want TensorRT FP16 speed and no runtime key dependency.
6. **Alternative that avoids Roboflow credits entirely:** export the dataset (free key) and fine-tune with `rfdetr[train]` on the batch g6e box (5-15 min for ~400 images [I]).

---

## 4. Supabase

**Realtime limits** [V: [Realtime limits](https://supabase.com/docs/guides/realtime/limits)]:

| | Free | Pro ($25/mo) |
|---|---|---|
| Concurrent connections | 200 | 500 |
| Messages/s | 100 | 500 |
| Channel joins/s | 100 | 500 |
| Presence msgs/s | 20 | 50 |
| Broadcast payload | 256 KB | 3,000 KB |
| Messages/month | 2 M | 5 M |

- **Latency (Supabase's own benchmark):** WebSocket broadcast median **6 ms / p95 28 ms** under 32k users. A 1 KB payload is 13 / 36 ms. DB-triggered broadcast is 46 / 132 ms [V: [benchmarks](https://supabase.com/docs/guides/realtime/benchmarks)]. These are measured inside AWS. Add the phone's own last-mile.
- **Server-side send:** POST `https://<ref>.supabase.co/realtime/v1/api/broadcast` with `messages[{topic, event, payload}]` [V: [Broadcast docs](https://supabase.com/docs/guides/realtime/broadcast.md)], or the Python realtime client's `send_broadcast`.

**Storage:**
- Free: **1 GB total, 50 MB max file**. Pro: 100 GB included, up to 500 GB per file [V: [pricing](https://supabase.com/pricing), [file limits](https://supabase.com/docs/guides/storage/uploads/file-limits)].
- **TUS resumable uploads:** `https://<ref>.storage.supabase.co/storage/v1/upload/resumable`. **6 MB chunks** (fixed "for now"); upload URLs are valid for 24 h; clients are `tus-js-client` or Uppy; uploading to an existing path returns 400 unless `x-upsert` is set [V: [resumable](https://supabase.com/docs/guides/storage/uploads/resumable-uploads)].
- **Volume check:** 4 phones × 12 Mbps × 10 h of play ≈ **216 GB**, too much for Supabase.

**Postgres and Edge Functions:**
- Free tier: 500 MB database. **Free projects pause after 1 week of inactivity**, so make sure it isn't paused on Friday.
- Edge Functions: 256 MB, **2 s CPU per request**, 150 s (Free) or 400 s (paid) wall clock [V: [function limits](https://supabase.com/docs/guides/functions/limits)]. Fine for the house-rule compile proxy, token minting (Cartesia, Deepgram) and AgentMail sends. Don't run CV in them.
- **Region:** create the project in **us-west-2 (Oregon)** [V: [regions](https://supabase.com/docs/guides/platform/regions)], next to EC2, so gateway writes take ~1-2 ms.

**Verdict:**
- **Use Supabase for:**
  - Postgres (games, players, events log, calls, labels for calibration, rule packs).
  - Auth (anonymous plus a QR join token).
  - **Realtime for the dashboard, spectator view, scoreboard and Presence** (which phones are live, battery, fps).
  - Storage for **small** assets: thumbnails, rendered trophy clips, highlight MP4s ≤ 50 MB.
- **Don't route the beep path through Supabase.** The phone already holds a WSS to `gateway` for clock sync and challenges. Pushing the call down that socket is one hop (EC2 → phone). Supabase is two (EC2 → Supabase REST → Realtime node → phone). Mirror every call to Supabase asynchronously for the UI and history.
- **Keep Redis Streams on EC2** for internal fan-out between perception, engine and broadcast. Supabase Realtime's 100-500 msgs/s caps would throttle per-frame events, and the extra hops add latency. Supabase replaces Redis only for *client-facing* state.
- **Recordings go to S3** (presigned multipart PUT from the phone, same region) instead of Supabase Storage. Free Supabase can't hold them, and S3 multipart has no 6 MB-chunk constraint.
- **Convex** (event sponsor) could replace Supabase's reactive layer, and it has a **prize** (EP-133 + ESP32 display, ~$1.3k listed) [repo notes: `sponsor prize deep-dive.md`]. Pick **one** reactive backend. If you want the Convex prize, use Convex for the dashboard, scoreboard and Presence plus game data, and drop Supabase. Otherwise Supabase. Don't run both.

---

## 5. Voice and AI services: use or skip

| Service | Use? | Role | Facts |
|---|---|---|---|
| **Deepgram** ($15k credits) | **Yes** | **Nova-3 streaming STT with `keyterm=Trophy&keyterm=challenge…`** for voice commands ("Trophy, challenge!", "Trophy, replay", "Trophy, score"). The phone streams mic audio straight to Deepgram over WSS with a short-lived token minted by our backend. Alternative: **Flux** (turn-detecting conversational STT) for the "ask the ref" voice chat | Keyterm prompting supports Nova-3 and Flux, up to 100 terms [V: [Deepgram keyterm](https://developers.deepgram.com/docs/keyterm)]. Nova-3 streaming is $0.0048-0.0077/min [3P], so 4 phones × 10 h ≈ $12-18, covered by credits. Use a separate mic stream with `echoCancellation:true` for STT; the onset detector needs AEC/AGC off, so open two tracks, or use one raw track and accept slightly worse STT [I]. **Aura-2 TTS:** ~313 ms P50 time-to-first-audio vs Cartesia Sonic-3 ~188 ms in one (competitor-run) benchmark [3P: [Gradium/Coval](https://gradium.ai/content/tts-latency-benchmark-2026)]. Aura-2 is $0.030 per 1k characters [3P] |
| **Cartesia** (event sponsor, prize) | **Yes, primary TTS** | Commentary and call announcements (F12) | Faster than Aura-2 in the benchmark above. **The free tier allows only 2 concurrent TTS requests and ~27 min/month; buy Pro at $5** [repo notes]. Keep **Aura-2 as an automatic TTS fallback** (paid from credits) |
| **Anthropic Claude** | **Yes** | Commentary text, house-rule compiler (F10), rule-pack drafting, highlight re-rank, the 5-vote decide fallback | Unchanged from the plan |
| **Google Gemini** ($2k) | **Yes, as decide fallback #1 and for highlight captions** | Replace local **Qwen3-VL on vLLM** with `gemini-3.8-flash` (stable) [V: [models](https://ai.google.dev/gemini-api/docs/models)]. Send 4 crops, or a **2-3 s clip inline with a custom `fps`** in the `processing` object (default sampling is 1 fps, which "might lose detail" on fast action) [V: [video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)]. Use enum structured output with 5 shuffled votes, the same as Claude | Tokens: ~258 per frame at default resolution, 66 at low, plus ~32/s for audio [V]. Inline requests should stay < 20 MB. No published latency, so assume 1-3 s [I]. Fits challenge replays (6 s budget) and post-point calls, not the 1.5 s live tier. Post-game: captions and "Play of the Game" description over the highlight reel |
| **OpenAI** ($1k) | Light | Fallback #3 (after Claude) for text-only decisions, or a structured-output check. Not needed if Gemini and Claude both work | — |
| **Langfuse** | **Yes** (choose it over Respan) | Trace every `decide()` call (backend, latency, probs, p_cal, image hashes), prompt management for commentary and compiler prompts, **datasets** of labelled calls for calibration runs, LLM-as-judge on commentary hallucination | LLM-as-judge, annotation queues, prompt experiments and the playground became **MIT and free to self-host** on 2025-06-04 (self-host ≥ v3.65) [V: [Langfuse changelog](https://langfuse.com/changelog/2025-06-04-open-sourcing-langfuse)]. **The free cloud tier allows only 2 users** (50k units/mo) [3P], so with 4 people use the credits on Core ($29, unlimited users) or self-host on a CPU box |
| **Respan** (formerly Keywords AI) | Skip | Managed observability, evals and gateway | No self-host found; it duplicates Langfuse [3P: [Respan docs](https://www.respan.ai/docs/documentation/overview)] |
| **Vapi** | Optional P2 | "Ask the ref" by voice: a web call from the judge's phone, with tools that hit `gateway` (`get_rule`, `explain_call`, `game_state`) | $0.05/min platform fee plus providers. Function calling needs a Server URL. Pay-as-you-go may cap at 10 concurrent calls [3P: [Vapi FAQ](https://docs.vapi.ai/faq)]. **Cheaper to build in-house** with Deepgram Flux → Claude → Cartesia, which is also eligible for the Cartesia prize |
| **Tavus CVI** | Optional P2 wow | A "virtual referee" avatar that explains challenge verdicts. Create a conversation with `POST /v2/conversations` and embed the `conversation_url` iframe. **Echo mode** lets us push our own deterministic verdict text for the replica to speak, so it can't hallucinate [V: [Tavus docs](https://docs.tavus.io/sections/conversational-video-interface/quickstart/build-first-app)] | ~600 ms (vendor) to ~800 ms round-trip [3P]. **Billing starts at creation, with a 30 s minimum per conversation.** Pay-as-you-go is ~$0.32-0.37/min; the free tier has 25 min [3P: [Tavus pricing](https://www.tavus.io/pricing)]. Use `test_mode` while developing. Pre-create one conversation per challenge view, or record one pre-rendered explainer clip for the demo |
| **AgentMail** | **Yes** (cheap, 1-2 h) | After the game, email each player their recap: score, calls, coach cards, trophy-clip and highlight links. A Supabase Edge Function or `broadcast` sends it | Python SDK `client.inboxes.messages.send`; **attachments supported** [V: [AgentMail docs index](https://docs.agentmail.to/llms.txt)]. Free tier is ~3 inboxes, 3k emails/mo, about a 100/day cap, an @agentmail.to sender and a footer [3P]. Send links, not MP4 attachments |
| **Firecrawl** | **Yes** (1-2 h) | Scrape official rulebooks (USA Pickleball, BWF, ITTF, USA Football flag, roundnet, ACL cornhole) into Markdown and JSON as grounding for Claude's rule-pack compiler. Cache to Postgres | 1 credit per page, **+1 per PDF page**, **+4 for JSON extraction**, +4 for enhanced mode [V: [Firecrawl billing](https://docs.firecrawl.dev/billing)]. Prefer the Markdown output and let Claude extract (cheaper). Many rulebooks are PDFs, so check the new `/parse` endpoint |
| **Blaxel** | Optional | Sandbox for the **house-rule compiler's** replay tests: run Claude-generated CEL and Python test harnesses against recorded traces in a microVM, not on the live box | Resume from standby in < 25 ms; create from template ~200-600 ms; standby is free [V: [Blaxel docs](https://docs.blaxel.ai/Sandboxes/Overview)]. CEL is already non-Turing-complete and safe, so Blaxel only matters if the compiler emits Python. A nice "safe codegen" talking point |
| **Greptile** | **Yes** (5 min) | AI review on GitHub PRs. It catches integration bugs across 4 people's services | Install the GitHub app on the repo |
| **Roboflow** | **Yes** | §3 | |
| **SubQ Snap** | **Yes, primary decider** | Unchanged. Calls from AWS skip venue-Wi-Fi upload | Vendor ~1 s at 100K tokens; budget 0.3-1.0 s at ~3K tokens [repo notes: `Trophy - SubQ Snap coach.md`] |
| **Convex** (event sponsor) | Either-or with Supabase | §4 | Prize ~$1.3k in hardware |
| **sync.** (lip-sync) | Skip | Only useful if dubbing commentary onto a talking head; Tavus covers that | |
| **Coinbase (Base, x402)** | Skip, unless spare time | The prize is $500 USDC per member for x402. A forced fit (a "pay-per-challenge" or rules-API paywall) | [repo notes] |
| **Sarvam AI** | Skip, unless you want multilingual commentary | Indic STT and TTS. Cartesia and Deepgram cover English | |
| **Bolna** | Skip | India-focused voice-agent platform; duplicates Vapi | |
| **Razorpay** | Skip | Indian payments; no use | |
| **Gumloop** | Skip | No-code automation; AgentMail plus a function does the recap email directly | |
| **Browser Use** | Skip | Firecrawl covers the rulebook ingest | |
| **écentic, Corsair** | Skip | No clear fit found for a CV referee | |

---

## 6. Concrete cloud architecture

### 6.1 Where everything runs
```text
PHONES (PWA, Safari/Chrome)                     LAPTOPS: browser + Remote-SSH only
 ├─ WebRTC 720p30 (UDP) ───────────────┐
 │    (TURN/TLS 443 via coturn if UDP blocked; JPEG/WebCodecs-over-WSS fallback)
 ├─ WSS control: join, clock sync, onsets+150ms PCM, calls↓, beep↓, challenge↑
 ├─ Deepgram WSS (voice cmds, temp token)   ├─ Cartesia WSS (TTS, access token)
 ├─ Supabase Realtime (scoreboard, presence) └─ S3 presigned multipart (rally chunks, full game later)
                                        ▼
AWS us-west-2
 ┌──────────────── LIVE BOX: g6e.4xlarge (L40S 48 GB), Elastic IP, Caddy :443 ───────────────┐
 │ caddy ─► gateway (FastAPI: WSS, REST, PWA+dashboard static, token minting)                 │
 │ ingest (aiortc, network_mode: host, UDP 32768-60999) ─► /dev/shm rings (ipc: host)          │
 │ flight (BlurBall/WASB, torch cu12)   possession (RF-DETR TRT, trackers, rtmlib ORT-GPU)     │
 │ resting (RF-DETR or roboflow-inference-server-gpu container)   audio (PANNs)               │
 │ engine (rule packs/CEL, decide(): Snap → Gemini → Claude → geometry) ─► calls              │
 │ redis (streams, internal only)    broadcast (Claude → Cartesia; highlights; S3 writes)     │
 │ [optional] vlm (vLLM Qwen3-VL-8B-FP8) only if VRAM/time allow                              │
 └────────────────────────────────────────────────────────────────────────────────────────────┘
 ┌─ BATCH BOX: g6e.2xlarge (or g7e.2xlarge) ─ RIFE 4.25, GVHMR, TT3D replays, ReCamMaster, RF-DETR fine-tunes ─┐
 ┌─ coturn: t4g.small + EIP (443/tcp TLS, 3478, relay 49152-65535/udp) ─┐
 ┌─ 4× dev boxes: g6.2xlarge (B, C) / c7i.2xlarge or g6.xlarge (A, D); spot OK ─┐
 ┌─ S3 (recordings, clips, weights)  Lambda (Remotion renders)  Route 53 (domain) ─┐
EXTERNAL
 Supabase (us-west-2): Postgres, Realtime, Auth, Edge Functions (AgentMail send, token mint)
 SubQ Snap · Gemini 3.8 Flash · Claude · Cartesia · Deepgram · Langfuse · Roboflow (training) · Firecrawl · Tavus (opt.)
```

### 6.2 Latency budget for one live call (target ≤ 1.5 s from the event to the beep)
| Stage | Geometry-only call (AUTO) | Snap-judged call (BETA, ambiguous) | Basis |
|---|---|---|---|
| Glass → encoder (exposure, ISP, encode) | 50-100 ms | 50-100 ms | [I] |
| Uplink phone → us-west-2 (one-way) + aiortc jitter buffer | 40-120 ms (5G) | same | Ookla 44 ms 5G latency + 20 ms to Oregon [3P/I] |
| Decode (software, per frame) + write ring | 5-15 ms | same | [I] |
| Perception per frame (BlurBall/WASB ~15 ms, RF-DETR TRT ~5-10 ms, pose on near-ball players ~10-20 ms) | 20-40 ms | same | plan [F]/[P] numbers, scaled [I] |
| **Event confirmation needs future frames** (post-bounce parabola, at-rest N frames, rim crossing + 4) | 100-250 ms | same | [I] |
| Rules engine + gate | < 10 ms | < 10 ms | |
| Crop encode + upload to Snap (datacenter to datacenter) | — | 20-60 ms | [I] |
| SubQ Snap (~3K tokens), second shuffled call in parallel | — | 300-1,000 ms (timeout 2.0 s → geometry + "challengeable") | vendor claim [repo notes] |
| Push gateway WSS → phone (one-way) | 30-80 ms | same | [I] |
| Web Audio beep + full-screen flash (pre-unlocked context) | 10-50 ms | same | [I] |
| **Total (p50)** | **≈ 0.3-0.7 s** | **≈ 0.6-1.6 s** | |
| Optional TTS line (Cartesia TTFA ~190 ms + playback start) | +0.2-0.4 s | +0.2-0.4 s | [3P] |

**p95 risks:**
- Cellular tail RTT (+200 ms).
- Snap tail. The 2.0 s timeout bounds it.
- aiortc decode falling behind with 4 streams. Mitigate with 16+ vCPU, 720p30 cap, and draining to a latest-frame slot.

**Supabase Realtime is not on this path.** Mirroring a call there for the dashboard adds about 20-80 ms of extra hops.

### 6.3 Cost estimate for the 40-hour weekend
| Item | Calc | $ |
|---|---|---|
| Live box g6e.4xlarge on demand | 40 h × $3.00 | ~120 (g6e.8xlarge: ~181) |
| Batch box g6e.2xlarge | ~25 h × $2.24 | ~56 (g7e.2xlarge 10 h for ReCamMaster: +34) |
| Dev boxes | 2× g6.2xlarge × 40 h × $0.98 + 2× g6.xlarge × 40 h × $0.81 | ~143 (spot would be ~40-60% less) |
| coturn t4g.small + EIPs (public IPv4 $0.005/h each) | | ~3 |
| EBS gp3, ~1 TB total for 3 days | | ~8 |
| S3 + data transfer out (clips and replays to phones, ~50-100 GB × $0.09) | | ~5-10 |
| Remotion Lambda (dozens of renders) | | < 5 |
| **AWS subtotal** | | **≈ $340-450** (≈ $650 with the larger options and a 20% buffer) |
| Supabase | Free, or Pro $25 | 0-25 |
| Roboflow | Core $39 + a few extra credits | 39-80 |
| Cartesia Pro | | 5 |
| Deepgram (credits), Claude (credits), Gemini (credits), SubQ (100M free tokens), Langfuse Core | | ~0-60 out of pocket |
| Tavus (optional) | ~20-40 min | ~10-15 |
| **Total** | | **≈ $450-650 in credits; < $150 out of pocket** |

### 6.4 Failure fallbacks
| Failure | Detection | Fallback |
|---|---|---|
| **GPU quota denied or slow** | No approval by Fri ~8 PM | Try in order: (1) the same request in us-east-2, plus the Spot G quota; (2) **GCP Cloud Run with L4 GPUs**, where a project's first L4 deployment in a region gets **3 GPUs automatically** (us-central1/us-east4, no us-west1 listed) [V: [Cloud Run GPU](https://docs.cloud.google.com/run/docs/configuring/services/gpu)], so containerize flight and possession; (3) **Roboflow Dedicated Deployment** (L4, 1 credit/h) or **Serverless Video Streaming** for the possession and resting families; (4) a CPU-only g-less box (c7i.8xlarge) at 360p/15 fps with motion-candidate ball detection, and calls "after the point" |
| **Venue Wi-Fi down or UDP blocked** | ICE fails, or the candidate pair is relay-only | Phones on their own 5G (default). TURN/TLS on 443. JPEG or WebCodecs over WSS. Recording continues in OPFS and uploads later |
| **Cellular congestion** | Bitrate < 1 Mbps, RTT > 300 ms | Drop to 640×360@15 fps for live. Switch the UI to "calls within 2 s after the point". Use 1080p rally chunks for the call |
| **SubQ Snap down or slow** | 429/5xx/timeout > 2.0 s | Gemini 3.8 Flash (enum, votes) → Claude 5-vote → geometry-only call shown as "challengeable". Show the backend on the call card |
| **Supabase down** | Health check | Calls still flow over the gateway WSS. The dashboard falls back to a gateway SSE endpoint |
| **Live box dies** | Health check | Relaunch from the baked AMI and launch template (~10 min). Keep the EIP so DNS and TURN stay valid |
| **Cartesia limit or outage** | Error or concurrency 429 | Deepgram Aura-2 (credits) → on-screen banner only |
| **Deepgram down** | — | The big **Challenge** button (always present) |
| **Lambda concurrency = 10** | `npx remotion lambda quotas` | `framesPerLambda` ≥ 100, or render on the batch box with the CLI |
| **Roboflow training overruns** | Credits burn | Train RF-DETR yourself on the batch box (`rfdetr[train]`) from the exported dataset |

---

## 7. Changes to the build plan (§0, F1-F18)

- **§0 OS note:** delete the WSL2 and mirrored-networking guidance. Everything is Linux containers on EC2.
- **§0 process table:**
  - Each "env" becomes a Docker image.
  - Rings need `ipc: host`, and `ingest` needs `network_mode: host`.
  - `vlm` becomes optional and is replaced by Gemini.
  - `dashboard` and `pwa` are static builds served by Caddy.
- **F1:** recording stays at 1080p but is **not streamed**. Upload on demand (challenge or closing rally) to S3 with presigned URLs, and upload the full game after the game.
- **F2:**
  - Add a TURN config (`turns:` 443).
  - ICE servers: our coturn for STUN and TURN, Google STUN as a spare.
  - Clock sync gets noisier, so rely on QR-timecode calibration. Display the QR on a phone, not a laptop.
- **F7:** "fine-tune locally" becomes "train in Roboflow cloud, or on the batch box; serve via the inference container on the live box".
- **F9:** the fallback chain is Snap → **Gemini 3.8 Flash** → Claude → geometry. Trace everything in Langfuse.
- **F12:** Cartesia Pro. Aura-2 as fallback.
- **F14:** Remotion on Lambda (or the batch box). RIFE on the batch box.
- **F16/F18:** GVHMR and ReCamMaster on the batch box (g6e or g7e).
- **Hour-0 smoke test #1 (replacing `nvidia-smi` in WSL2):**
  - `nvidia-smi` inside each container.
  - Phones connect over 5G **and** venue Wi-Fi.
  - Log the winning ICE candidate pair type, RTT and bitrate.
  - Time a Snap call from EC2.
  - Time a Gemini call and Cartesia TTFA from EC2.

## 8. Blockers to act on today (Fri Oct 23)
1. **AWS G and VT On-Demand quota.** Default is 0. Request 128 vCPU (or 64) in us-west-2, the same in us-east-2, plus the Spot G quota in both. Open a support case, and confirm the YC credits are on this account.
2. **Domain and DNS.** Register or choose a domain. A records for `trophy.` and `turn.` point at the Elastic IPs once the boxes exist.
3. **Roboflow.** Fork the Universe datasets and start RF-DETR Nano/Small training **tonight**, with an epoch cap. Decide on Core ($39) for weight download and dedicated deployments.
4. **Supabase project in us-west-2.** Make sure it isn't paused. Or pick Convex instead, for its prize; don't run both.
5. **Keys and tiers:**
   - SubQ (100M free tokens, possibly waitlisted).
   - Cartesia **Pro** (the free tier allows only 2 concurrent TTS requests).
   - Deepgram key and token minting.
   - Gemini API key on the $2k project.
   - Langfuse (Core for 4 users, or self-host).
   - Firecrawl, AgentMail, Tavus (test_mode).
6. **Remotion Lambda.** Deploy the function and site. Check `npx remotion lambda quotas`, since new accounts can have ~10.
7. **Pre-stage the weights on S3/EBS from the datacenter**, not over venue Wi-Fi: BlurBall, WASB, RIFE 4.25, PANNs CNN14, TT3D encoder, RF-DETR checkpoints, and Qwen3-VL only if kept.
8. **Phone network test at the venue:** 5G vs Wi-Fi RTT and upload to an EC2 echo, and UDP reachability.
