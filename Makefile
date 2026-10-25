.PHONY: dev e2e contracts fixtures check smoke stdb-publish stdb-provision stdb-bindings stdb-seed
dev:        ## start every service natively on the Mac (Agent 1 implements the Procfile)
	@test -f Procfile || (echo "Procfile not created yet (Agent 1, plan §4)"; exit 1)
	honcho start
e2e:        ## headless clip -> calls -> Spacetime check (Agent 1, checkpoint C2)
	@echo "not implemented yet (Agent 1, checkpoint C2)"; exit 1
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
stdb-publish:   ## publish the module to the local server as `trophy` (spacetime start must be running)
	$(SPACETIME) publish -s local -p spacetime --yes=skip-login trophy
stdb-provision: ## engine/vision/compiler identities -> .env, registered with the module
	python spacetime/scripts/provision.py
stdb-bindings:  ## regenerate the TS client bindings after module changes
	$(SPACETIME) generate --lang typescript -p spacetime -o packages/state-client/src/bindings --no-config -y
stdb-seed:      ## replay the labelled-synthetic demo into a new game and check it
	python spacetime/scripts/seed_demo.py --check
smoke:      ## P0 spikes
	bash scripts/smoke.sh

.PHONY: recorder recorder-check gateway-check
recorder:      ## local frame-bus HLS archive (install FFmpeg separately)
	uv run --frozen --project services/recorder python -m recorder
recorder-check:
	uv run --frozen --project services/recorder ruff check services/recorder
	uv run --frozen --project services/recorder pytest -q services/recorder/tests
gateway-check:
	uv run --frozen --project services/gateway ruff check services/gateway
	uv run --frozen --project services/gateway pytest -q services/gateway/tests
