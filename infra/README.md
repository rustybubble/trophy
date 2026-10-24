# Infrastructure options

Use local hardware or authorized cloud resources as appropriate. This is the current cloud baseline, not a restriction on providers or local execution; verify balances and pricing before spending.

## GCP live VM (Google credits)
- `g2-standard-8` (1× L4 24 GB, 8 vCPU), on-demand, **us-west1**, Deep Learning VM image (CUDA 12 + NVIDIA container toolkit). Use `g2-standard-16` if decoding saturates the CPU.
- **Quota:** raise `GPUS_ALL_REGIONS` ≥ 2 and NVIDIA L4 in us-west1 ≥ 2 (also us-central1 as backup).
- Static external IP + DNS A record for `$TROPHY_DOMAIN`. Firewall: TCP 80/443, **UDP 32768–60999** (aiortc), TCP 443 for TURN over TLS.
- `docker compose up -d` (repo root). Keep a validated machine image for fast recovery.
- Dev: a shared `g2-standard-4` spot VM; develop through VS Code/Cursor Remote-SSH. Stop VMs when idle.

## Vultr (post-game GPU option)
- L40S 48 GB on demand for RIFE / SAM 2.1 / GVHMR / ReCamMaster. It's also the live-box fallback if the GCP quota is denied.

## AWS (Remotion Lambda baseline; historical credit estimate $100)
- `npx remotion lambda` setup in the region of your choice; check `npx remotion lambda quotas` (new accounts may get 10 concurrent).

## Caddy
- `infra/caddy/Caddyfile`: automatic HTTPS for `$TROPHY_DOMAIN`; routes `/cam` → PWA, `/watch` → Trophy Watch, `/` → dashboard, `/api` → gateway, `/stdb` → SpacetimeDB.
