# The whole dev stack (D-12, D-26). `make dev` or `npm run dev` runs it with scripts/dev.py, which (re)starts every
# line in order, waits for each one's dependencies (scripts/dev.py WAITS) and keeps the others running if one exits.
# `honcho start` also works where honcho is installed. $SPACETIME defaults to `spacetime` (set it in .env otherwise).
redis: docker run --rm --name trophy-redis -p 127.0.0.1:6379:6379 redis:7.4-alpine
spacetime: $SPACETIME start --listen-addr 127.0.0.1:3000 --non-interactive
gateway: uv run --directory services/gateway --frozen python -m gateway
voice: python spikes/cartesia-voice/serve.py --port 8765
pwa: npm run dev -w @trophy/pwa -- --logLevel warn
caddy: python infra/caddy/run.py
flight: uv run --directory services/flight --frozen python -m flight.live --game next --post-calls
review: uv run --project services/flight --frozen python tools/tt_review.py data/local/ttClips/side_IMG_4342.mp4 data/local/tt-track/side_full.jsonl --out data/local/tt-review/side --serve 8770
