# Infrastructure (Cal Hacks weekend)

- **Mac (M5 Pro):** every service runs natively (`make dev`); Docker on macOS has no GPU access.
- **Domain + HTTPS:**
  - Register the domain through the MLH partner (GoDaddy Registry or .Tech), which needs the user's account.
  - Run Caddy on the Mac with a DNS-01 certificate and an A record pointing at the Mac's LAN IP. Use `caddy/Caddyfile` (`/cam/*` PWA, `/` dashboard, `/api/*` gateway, `/stdb/*` SpacetimeDB).
  - Watch for router DNS-rebind protection and guest-Wi-Fi client isolation; a travel router avoids both.
  - Never commit DNS API tokens.
- **Vultr (GPU fallback, MLH track):** only if the ball tracker can't reach 25 fps on the Mac. Flight then runs on a Vultr GPU instance, reading the same Redis frames over a private tunnel. **The user creates the account and approves the instance and its hourly cost.** Stop it when idle.
- `docker-compose.yml` is a Linux deployment sketch for later. It isn't used this weekend.
