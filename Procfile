# The whole dev stack, natively (D-12, D-30). `make dev` or `npm run dev` runs it with scripts/dev.py, which (re)starts every
# line in order, waits for each one's dependencies (scripts/dev.py WAITS) and keeps the others running if one exits.
# `honcho start` also works where honcho is installed. $SPACETIME defaults to `spacetime`, $PYTHON to the interpreter running dev.py (set them in .env otherwise).
# The same services run under docker compose on the Vultr GPU box (infra/vultr, D-30).
# redis: brew's redis-server on the Mac (no persistence); on the Windows PC use Docker: docker run --rm --name trophy-redis -p 127.0.0.1:6379:6379 redis:7.4-alpine
# flight: live ball tracking (BlurBall on MPS, D-30) on every phone of the newest game, switching to each new game; writes ev:flight,
# trk:ball:{cam} and Spacetime observation/track_sample (vision token). The weights stay in weights/ (ignored), see services/flight/README.md.
# engine: rule packs + scoring + the gate; add --votes once ANTHROPIC/GEMINI/BITDEER keys exist. referee: ask-the-ref voice (:8100), needs ANTHROPIC_API_KEY + CARTESIA_API_KEY.
redis: redis-server --port 6379 --bind 127.0.0.1 --save '' --appendonly no
spacetime: $SPACETIME start --listen-addr 127.0.0.1:3000 --non-interactive
gateway: uv run --directory services/gateway --frozen python -m gateway
recorder: uv run --project services/recorder --frozen python -m recorder
flight: uv run --directory services/flight --frozen --extra blurball python -m flight.live --game follow
engine: uv run --directory services/engine --frozen trophy-engine
referee: uv run --directory services/referee --frozen referee serve
compiler: npm run cli -w @trophy/compiler -- watch
voice: $PYTHON spikes/cartesia-voice/serve.py --port 8765
pwa: npm run dev -w @trophy/pwa -- --logLevel warn
dashboard: npm run dev -w @trophy/dashboard -- --logLevel warn
caddy: $PYTHON infra/caddy/run.py
