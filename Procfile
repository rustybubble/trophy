# The whole dev stack, natively (D-12, D-30). `make dev` or `npm run dev` runs it with scripts/dev.py, which (re)starts every
# line in order, waits for each one's dependencies (scripts/dev.py WAITS) and keeps the others running if one exits.
# `honcho start` also works where honcho is installed. $SPACETIME defaults to `spacetime` (set it in .env otherwise).
# The same services run under docker compose on the Vultr GPU box (infra/vultr, D-30).
# flight (BlurBall: MPS on the Mac, CUDA on Vultr) is Agent 2's; its entry goes here when services/flight lands, e.g.
#   flight: uv run --directory services/flight --frozen python -m flight ...
redis: docker run --rm --name trophy-redis -p 127.0.0.1:6379:6379 redis:7.4-alpine
spacetime: $SPACETIME start --listen-addr 127.0.0.1:3000 --non-interactive
gateway: uv run --directory services/gateway --frozen python -m gateway
recorder: uv run --project services/recorder --frozen python -m recorder
voice: python spikes/cartesia-voice/serve.py --port 8765
pwa: npm run dev -w @trophy/pwa -- --logLevel warn
caddy: python infra/caddy/run.py
