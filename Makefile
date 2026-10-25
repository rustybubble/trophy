.PHONY: dev e2e contracts fixtures check stdb-publish stdb-provision stdb-bindings stdb-seed
# macOS and most Linux ship only `python3`; Windows has `python` (and a Store stub named python3).
ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif
dev:        ## (re)start the whole stack natively from the Procfile (also: npm run dev; stop: $(PYTHON) scripts/dev.py --stop)
	$(PYTHON) scripts/dev.py
e2e:        ## CC BY clip as a phone -> frames -> recorder/replay -> Spacetime observations + calls (C2; stack running)
	uv run --project services/gateway --frozen python scripts/e2e.py
contracts:  ## regenerate TS (@trophy/contracts) + Pydantic (py-trophy) from packages/contracts/*.schema.json
	node scripts/gen-contracts.mjs
fixtures:   ## rebuild the labelled-synthetic MockState scripts
	node --experimental-strip-types packages/state-client/scripts/build-fixtures.ts
check:      ## what CI runs: lint, types, tests, fixture validation, codegen staleness
	cd packages/py-trophy && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen pytest -q
	uv run --project packages/py-trophy --frozen ruff check scripts && uv run --project packages/py-trophy --frozen python scripts/validate_fixtures.py
	npm run typecheck && npm run lint && npm test
	$(MAKE) contracts fixtures && git diff --exit-code -- packages/contracts/gen packages/py-trophy/trophy/contracts packages/state-client/fixtures
SPACETIME ?= spacetime
stdb-publish:   ## publish the module to the local server as `trophy` (spacetime start must be running; additive migrations only, see spacetime/README.md)
	$(SPACETIME) publish -s local -p spacetime --yes=skip-login --break-clients trophy
stdb-provision: ## engine/vision/compiler identities -> .env, registered with the module
	$(PYTHON) spacetime/scripts/provision.py
stdb-bindings:  ## regenerate the TS client bindings after module changes
	$(SPACETIME) generate --lang typescript -p spacetime -o packages/state-client/src/bindings --no-config -y
stdb-seed:      ## replay the labelled-synthetic demo into a new game and check it
	$(PYTHON) spacetime/scripts/seed_demo.py --check

.PHONY: recorder recorder-check gateway-check
recorder:      ## local frame-bus HLS archive (install FFmpeg separately)
	uv run --frozen --project services/recorder python -m recorder
recorder-check:
	uv run --frozen --project services/recorder ruff check services/recorder
	uv run --frozen --project services/recorder pytest -q services/recorder/tests
gateway-check:
	uv run --frozen --project services/gateway ruff check services/gateway
	uv run --frozen --project services/gateway pytest -q services/gateway/tests

.PHONY: eval-live-check
eval-live-check:
	uv run --frozen --project packages/py-trophy ruff check tools/eval_live.py tests/test_eval_live.py
	uv run --frozen --project packages/py-trophy python -m pytest -q tests/test_eval_live.py
