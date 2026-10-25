# The Trophy GPU box on Vultr (D-30)

One Vultr Cloud GPU instance runs the whole live backend under `docker compose` (`docker-compose.yml` at the repo root): Redis, SpacetimeDB + the Trophy module, gateway, recorder, Caddy, and, as they land, engine, rules, compiler and Agent 2's flight (BlurBall on CUDA). The phones and the dashboard use `https://trophy.photo` from any network. The Mac path is unchanged: `make dev` runs the same services natively, with flight on MPS. The Windows PC is a dev machine and browser only.

**Every resource needs the user's OK first, with plan and hourly price. Destroy the box when idle.** Vultr bills a stopped instance at the full rate, so stopping it doesn't save money; only destroying does. Snapshot first if the state matters.

## Plan

| | Plan | GPU | vCPU / RAM / disk | Price (Vultr API, 2026-10-24) | Regions |
|---|---|---|---|---|---|
| **Pick** | `vcg-a16-6c-60g-16vram` | 1 × NVIDIA A16 (16 GB) | 6 / 60 GB / 350 GB | **$0.471/h** ($344/mo cap) | `sjc` (closest to Berkeley), ewr, ord, atl, lhr, fra, nrt, sgp, blr |
| If A16 misses 30 fps/cam | `vcg-a40-24c-120g-48vram` | 1 × A40 (48 GB) | 24 / 120 GB / 1.4 TB | $1.712/h | `lax`, ewr, lhr, fra, syd, sgp |

Why the A16: it's the cheapest NVIDIA plan on offer (the L40S and A100 single-GPU plans list no available regions today). BlurBall is a ~1.5M-parameter model at 288×512, so one A16 GPU should run it well above 30 fps for one or two cameras. That's an **estimate**, not a measurement: Agent 2 measures BlurBall fps on the box first, and we move to the A40 if it misses 30 fps per camera. The 6 vCPUs also have to decode 2 × 30 fps JPEG and run libx264 for the recorder, so watch CPU too.

## Bring-up (after the user approves)

1. **Create** (Vultr console or `vultr-cli`): plan above, region `sjc`, Ubuntu 22.04 GPU image with the NVIDIA driver, the user's **SSH key**, and a **firewall group** allowing only TCP 22, 80 and 443 inbound. Optional: a reserved IPv4 (a few $/mo), so the A record survives destroy/recreate.
2. **Bootstrap:** `scp infra/vultr/bootstrap.sh root@BOX: && ssh root@BOX bash bootstrap.sh`. This installs Docker + the NVIDIA container toolkit, sets up ufw (22/80/443), turns on key-only SSH, and creates `/etc/trophy` and `/srv/trophy/{data,weights}`.
3. **Code:** `git clone https://github.com/rustybubble/trophy /srv/trophy/repo`. It's a public repo, so no credentials go on the box for this.
4. **Secrets, on the box only** (never in images or git):
   - `/etc/trophy/trophy.env` (600): copy the needed keys from your `.env` (`TROPHY_TOKEN_SECRET`, `CARTESIA_*`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `BITDEER_API_KEY`, `MOSS_*`, `APIFY_TOKEN`, `FACTORY_API_KEY`, `TROPHY_DOMAIN=trophy.photo`, `SPACETIME_MODULE=trophy`) with `scp`. `SPACETIME_*_TOKEN` are written by step 6.
   - `/etc/trophy/caddy.env` (600): only `TROPHY_DOMAIN`, `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY`.
5. **BlurBall weights** (license unstated; used, not redistributed): `scp` them to `/srv/trophy/weights/`, which is mounted read-only into flight. Never `COPY` them into an image or push them to a registry.
6. **Start:** `cd /srv/trophy/repo && docker compose up -d --build && docker compose run --rm stdb-admin`, then `docker compose up -d` again so the services pick up the new identity tokens.
7. **DNS (user OK first):** `python infra/dns/porkbun_set_ip.py <BOX_PUBLIC_IP>` from a machine with the Porkbun keys. Caddy already has the certificate through DNS-01.
8. **Flight:** `docker compose --profile gpu up -d flight`, once Agent 2's `services/flight/Dockerfile` exists.
9. **Data:** `ln -s /srv/trophy/data /srv/trophy/repo/data/local`, so repo tools see the same footage as the containers. The user's re-recordings go in `/srv/trophy/data/ttClips/rerecord/` (everyone filmed has consented). The CC BY clips: `python tools/fetch_clips.py` (needs `yt-dlp` + `ffmpeg`; it checks each video's CC BY license before downloading and writes `data/clips/credits.json`).

**Tear-down:** `docker compose down`, copy anything needed out of `/srv/trophy/data` (footage stays local; blur non-consenting people before sharing), then destroy the instance, and point DNS back at the Mac if needed.

## Checks
**Tested locally (Windows PC, Docker Desktop, no GPU; 2026-10-24):** every image builds. In the stack (Caddy on 8443 with `TROPHY_TLS=internal`), `stdb-admin` published the module and registered the three identities into the env file, `/api/healthz` reported redis, spacetime and recorder OK, and 90 synthetic frames over WSS through Caddy reached the gateway, the still endpoint and the recorder (HLS segments + sprite in the data volume). `/stdb` reducer calls and SQL returned 403. No `.env`, weights or footage in any image. **Not tested:** the GPU, flight, DNS-01 against Porkbun from the box, and real phones over 5G.

- `curl -sI https://trophy.photo/api/health` → 200.
- A `wss://trophy.photo/stdb/v1/database/trophy/subscribe` connection works, and `POST /stdb/v1/database/trophy/call/...` returns 403 from outside.
- From outside the box: `nc -vz BOX 6379` and `nc -vz BOX 3000` both fail (only 22/80/443 are open).
