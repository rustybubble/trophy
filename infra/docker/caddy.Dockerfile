# Caddy with the Porkbun DNS-01 module, serving the built PWA (and later the dashboard and Watch), from the repo root:
#   docker build -f infra/docker/caddy.Dockerfile .
FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json tsconfig.base.json ./
COPY packages packages
COPY apps apps
COPY spacetime/package.json spacetime/package.json
RUN npm ci --no-audit --no-fund && npm run build -w @trophy/pwa \
    && mkdir -p apps/dashboard/dist apps/watch/dist

FROM caddy:2.11-builder AS caddy
RUN xcaddy build --with github.com/caddy-dns/porkbun

FROM caddy:2.11
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
COPY --from=web /app/apps/pwa/dist /srv/cam
COPY --from=web /app/apps/dashboard/dist /srv/dashboard
COPY --from=web /app/apps/watch/dist /srv/watch
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
