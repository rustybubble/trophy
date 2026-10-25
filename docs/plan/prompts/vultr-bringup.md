# Prompt: bring up the Trophy GPU box on Vultr (D-30)

*Written by Agent 1 for a separate agent the user runs. Paste everything below the line.*

---

You are bringing up **one Vultr Cloud GPU instance** that runs Trophy's live backend under docker compose. Trophy is a Cal Hacks project, repo `https://github.com/rustybubble/trophy` (public). The stack, runbook and bootstrap are on branch **`a1/vultr-deploy`** (PR rustybubble/trophy#16, not merged yet). Read these first: `infra/vultr/README.md`, `infra/vultr/bootstrap.sh`, `docker-compose.yml` and `CLAUDE.md` ("Safeguards to retain").

## Approved, and what still needs the user
- **Approved by the user:** create exactly **one** instance with plan **`vcg-a16-6c-60g-16vram`** (1 × NVIDIA A16 16 GB, 6 vCPU, 60 GB RAM) in region **`sjc`**, listed at **$0.471/h**. Before creating it, re-check the plan's price and `sjc` availability with `GET https://api.vultr.com/v2/plans?type=all`. If the price changed or `sjc` isn't offered, stop and ask the user. Don't pick another plan or region yourself.
- **Ask the user first** before:
  - any other paid resource (a reserved IP, block storage, snapshots, a second instance);
  - changing DNS (`trophy.photo` at Porkbun);
  - merging PR #16;
  - destroying the instance.
- **The user does these themselves:** sign in or create the Vultr account, add a payment method, and create the API key. You never type passwords or card numbers.

## Steps
1. **API key.** The user's `.env` has a `VULTR_API_KEY` line. Load it without printing it (`set -a; . <(grep '^VULTR_API_KEY=' .env); set +a`). If it's empty, ask the user to create one: Account → API, with access control limited to your IP if they like. Keep it in an environment variable for this session only (`VULTR_API_KEY`). Never write it to the repo, `.env` or logs, and never print it.
2. **SSH key.** Generate `ssh-keygen -t ed25519 -N "" -C trophy-vultr-box -f ~/.ssh/trophy-vultr` on the user's machine if it doesn't exist. Upload only the `.pub` with `POST /v2/ssh-keys` (name `trophy-box`). The private key never leaves the machine.
3. **Firewall group** (`POST /v2/firewalls`, description `trophy-box`). Inbound TCP **22 from the user's current public IP /32 only** (`curl https://checkip.amazonaws.com`), and TCP **80** and **443** from anywhere (IPv4 and IPv6). Nothing else, and no UDP.
4. **Create the instance** (`POST /v2/instances`):
   - plan `vcg-a16-6c-60g-16vram`, region `sjc`, label/hostname `trophy-box`;
   - the SSH key and firewall group from steps 2–3;
   - backups disabled; an IPv4 address.
   - **OS:** use Vultr's Ubuntu 22.04 GPU image (A16 instances are vGPU and need Vultr's NVIDIA driver, which their GPU images ship). Check `GET /v2/os` and Vultr's Cloud GPU docs for the right `os_id` or marketplace app. Don't install the stock `nvidia-driver-*` packages, which don't support vGPU.
   - Poll `GET /v2/instances/{id}` until `status=active` and `server_status=ok`.
5. **Bootstrap.** `scp infra/vultr/bootstrap.sh root@IP:` then `ssh -i ~/.ssh/trophy-vultr root@IP bash bootstrap.sh`. It must print an `nvidia-smi -L` line and pass the `docker run --gpus all … nvidia-smi` test. If the driver is missing, follow Vultr's vGPU driver docs, and stop and report if that fails.
6. **Code.** `git clone -b a1/vultr-deploy https://github.com/rustybubble/trophy /srv/trophy/repo`, then `ln -s /srv/trophy/data /srv/trophy/repo/data/local`.
7. **Secrets, on the box only** (mode 600, owned by root; never in images or git, never printed):
   - `/etc/trophy/trophy.env`: copy **only these keys** from the user's `.env` (ask where it is; on the Windows PC it's `C:\Users\Joseph\Code\trophy-a1\.env`): `TROPHY_TOKEN_SECRET`, `CARTESIA_API_KEY`, `CARTESIA_VERSION`, `CARTESIA_VOICE_CALLS`, `CARTESIA_VOICE_REF`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `CLAUDE_FAST_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `BITDEER_API_KEY`, `BITDEER_BASE_URL`, `BITDEER_VISION_MODEL`, `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `APIFY_TOKEN`, `FACTORY_API_KEY`, plus `TROPHY_DOMAIN=trophy.photo` and `SPACETIME_MODULE=trophy`. Skip any key that isn't present. **Don't copy** the `SPACETIME_*_TOKEN` lines (step 8 mints fresh ones for the box) `PORKBUN_*` (they go in caddy.env), `VULTR_API_KEY`, `ROBOFLOW_API_KEY`, `SPACETIME_URI`, `REDIS_URL` or `PORT_OFFSET` (compose sets those).
   - `/etc/trophy/caddy.env`: `TROPHY_DOMAIN=trophy.photo`, `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY`.
   - Copy by building the files locally in a temp dir with `grep`, then `scp`, then delete the temp files. Don't echo values.
8. **Start the stack** in `/srv/trophy/repo`:
   - `docker compose up -d --build`
   - `docker compose run --rm stdb-admin` (publishes the module and writes the identity tokens into `/etc/trophy/trophy.env`)
   - `docker compose up -d` again.
9. **Verify from the box and from outside:**
   - `docker compose ps` shows everything up;
   - `curl -sk --resolve trophy.photo:443:IP https://trophy.photo/api/healthz` reports redis, spacetime and recorder true;
   - from the user's machine, `nc -vz IP 6379` and `nc -vz IP 3000` fail, and 443 answers;
   - `docker compose logs caddy` shows the certificate obtained via Porkbun DNS-01 (if it failed, report the error line, without secrets).
10. **BlurBall weights:** if the user gives a local path, `scp` the weights to `/srv/trophy/weights/` (read-only mount; never into an image or registry). Flight itself (`--profile gpu`) waits for Agent 2's `services/flight/Dockerfile`; don't write it.
11. **Data:** the user's ping-pong re-recordings go in `/srv/trophy/data/ttClips/rerecord/` only if the user provides them and confirms everyone filmed consented.
12. **Idle:** Vultr bills a stopped instance at the full rate. Tell the user the running cost, and don't destroy anything without their OK.

## Report back (paste this to the user; it goes to Agent 1)
- instance ID, label, plan, region, **public IPv4** (and IPv6), the `nvidia-smi -L` line, and the `docker run --gpus all` result;
- the firewall group ID and its rules, and the SSH key name, plus the SSH command (`ssh -i ~/.ssh/trophy-vultr root@IP`);
- `docker compose ps`, the healthz JSON, the external port checks, and the Caddy certificate status;
- which env keys were copied (**names only**), and confirmation that the three `SPACETIME_*_TOKEN` were minted on the box;
- the hourly cost confirmed from the API, and the time the instance was created;
- anything that failed, with the exact command and error (no secrets).
Don't change DNS, merge #16, or destroy the box. Agent 1 does DNS and the merge after the user's OK.
