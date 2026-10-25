# Prompt: run Trophy's live backend on the M5 Pro Mac (D-30, revised: the Mac, no cloud)

*Written by Agent 1 for an agent running on the user's Mac. Paste everything below the line.*

---

You are bringing up Trophy's live backend **natively on this Mac** (Apple M5 Pro). The phones reach it at `https://trophy.photo`, whose A record points at the Mac's LAN IP. There's no cloud box: the user cut Vultr and AWS. Repo: `https://github.com/rustybubble/trophy` (public), branch `main`. Read these first: `CLAUDE.md` ("Safeguards to retain"), `Procfile`, `scripts/dev.py`, `infra/README.md` and `infra/caddy/Caddyfile.dev`.

## Ground rules
- **Ask the user first** before:
  - changing DNS (step 7);
  - installing anything with `sudo`;
  - copying secrets from another machine;
  - anything that costs money.
- **Never** print, log or commit secret values. `.env` stays gitignored. Keep footage in `data/local/` (gitignored).
- Ask the user to confirm everyone filmed consented before any footage goes into `data/local/ttClips/rerecord/`.

## Steps
1. **Tools.** Check each, then install what's missing (Homebrew where possible; ask before `sudo`):
   - `git`, `python3.11`, `uv`, Node **22** + npm, `ffmpeg`;
   - Docker Desktop (for `redis:7.4-alpine`), or `brew install redis` and change the Procfile's redis line to `redis-server --port 6379 --bind 127.0.0.1 --save "" --appendonly no`;
   - the **SpacetimeDB 2.13** CLI: `curl -sSf https://install.spacetimedb.com | sh`, then check that `spacetime --version` says 2.13.x.
2. **Caddy with the Porkbun DNS module.** Download a darwin/arm64 build with `github.com/caddy-dns/porkbun` from `https://caddyserver.com/download?package=github.com%2Fcaddy-dns%2Fporkbun`, or run `go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest && xcaddy build --with github.com/caddy-dns/porkbun`. Put it at `~/.trophy/bin/caddy`; `infra/caddy/run.py` looks there. Check: `caddy list-modules | grep porkbun`.
3. **Code.** `git clone https://github.com/rustybubble/trophy ~/Code/trophy && cd ~/Code/trophy && npm ci`.
4. **`.env`.** Copy `.env.example` to `.env`. Ask the user to fill the secrets themselves, or to securely copy the Windows PC's `.env` (`C:\Users\Joseph\Code\trophy-a1\.env`).
   - **Delete or replace** the `SPACETIME=` line: on the PC it holds a Windows path. Here use `SPACETIME=spacetime`, or remove it.
   - **Delete** the three `SPACETIME_*_TOKEN` lines. Step 5 mints fresh ones for this Mac's SpacetimeDB.
   - Keep `TROPHY_DOMAIN=trophy.photo`, `SPACETIME_URI=http://127.0.0.1:3000` and `SPACETIME_MODULE=trophy`.
5. **SpacetimeDB.** In one terminal: `spacetime start --listen-addr 127.0.0.1:3000 --non-interactive`. In another:
   - `make stdb-publish` (it runs `spacetime publish -s local -p spacetime --yes=skip-login trophy`);
   - `make stdb-provision` (writes the identity tokens into `.env`);
   - `make stdb-seed` (a labelled-synthetic smoke test of every reducer).

   Then stop that spacetime: `make dev` starts its own.
6. **Run everything:** `make dev`. It (re)starts redis, spacetime, gateway, recorder, voice, PWA, dashboard, Watch and Caddy from the `Procfile`; `python3 scripts/dev.py --stop` stops them all. Then check:
   - `curl -s http://127.0.0.1:8000/api/healthz` reports redis, spacetime and recorder true;
   - `http://127.0.0.1:5174/?demo=table_tennis` shows the synthetic dashboard;
   - `make e2e` (it needs `data/local/clips/table_tennis/7maQFqJ3XQ0.mp4`; if it's missing, run `python3 tools/fetch_clips.py --sport table_tennis`, which checks the CC BY license, after the user says OK to the download). Expect PASS for stack health, frame bus and recorder + replay, and PENDING for calls until flight and the engine exist.
7. **DNS (user OK first).** `python3 infra/dns/porkbun_set_ip.py` points `trophy.photo` at this Mac's LAN IP (rerun if DHCP changes it). Caddy gets the certificate via Porkbun DNS-01. Then from a phone on the **same Wi-Fi**, open `https://trophy.photo/cam/`. Watch for client isolation and DNS-rebind protection on campus or guest Wi-Fi; a travel router avoids both.
8. **macOS firewall.** If it's on, allow incoming connections for `caddy` (the user approves the prompt). Only Caddy listens beyond 127.0.0.1; every other service binds localhost.
9. **Flight (Agent 2's BlurBall on MPS).** Not part of this setup: Agent 2 adds the `flight:` Procfile line when `services/flight` lands. The BlurBall weights stay in a local ignored path, never in git.

## Report back (paste this to the user; it goes to Agent 1)
- the macOS version, plus the `spacetime --version`, `uv --version`, `node --version`, `ffmpeg -version | head -1` and `caddy version` lines;
- the `make dev` result, the healthz JSON, the `seed_demo.py --check` result and the `make e2e` lines;
- the Mac's LAN IP, and whether DNS was changed (only with the user's OK) and the certificate obtained;
- whether a phone on the same Wi-Fi loaded `https://trophy.photo/cam/`;
- anything that failed: the exact command and error (no secrets).
