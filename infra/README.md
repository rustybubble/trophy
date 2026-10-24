# Infrastructure (Cal Hacks weekend)

- **Mac (M5 Pro):** every service runs natively (`make dev`); Docker on macOS has no GPU access.
- **Domain + HTTPS: `trophy.photo`** (registered by the user on 2026-10-24 at Porkbun; Porkbun nameservers).
  - The phones load `https://trophy.photo`, which resolves to the **LAN IP of the demo machine** (a public A record pointing at a private address). Caddy on that machine gets the certificate with **DNS-01 through the Porkbun API**, so nothing needs to be reachable from the internet. Config: `caddy/Caddyfile.dev` (`/cam/*` PWA, `/` dashboard, `/api/*` gateway, `/stdb/*` SpacetimeDB, `/spike/voice/*` the P0 voice test).
  - Porkbun setup (the user's account): turn on **API access** for the domain, create an API key + secret, and put them in `.env` as `PORKBUN_API_KEY` / `PORKBUN_SECRET_API_KEY`. Never commit them.
  - Caddy needs the `caddy-dns/porkbun` module (a custom build from caddyserver.com/download, or `xcaddy`).
  - Watch for router **DNS-rebind protection** (it blocks public names that resolve to private IPs) and **client isolation** on campus/guest Wi-Fi (phones can't reach the laptop). A travel router avoids both. On Windows, inbound 443 must also be allowed in the firewall, which only the user can change.
- **Vultr (GPU fallback, MLH track):** only if the ball tracker can't reach 25 fps on the Mac. Flight then runs on a Vultr GPU instance, reading the same Redis frames over a private tunnel. **The user creates the account and approves the instance and its hourly cost.** Stop it when idle.
- `docker-compose.yml` is a Linux deployment sketch for later. It isn't used this weekend.
