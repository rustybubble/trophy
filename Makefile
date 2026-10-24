.PHONY: dev e2e contracts fixtures check smoke
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
smoke:      ## P0 spikes
	bash scripts/smoke.sh

.PHONY: tt-demo tt-demo-build tt-demo-test
tt-demo:    ## local, recorded two-camera review demo; no external services needed
	bash scripts/tt-demo.sh
tt-demo-build: ## conservative classical baseline + browser previews from originals
	$${TROPHY_PYTHON:-python3} tools/build_tt_demo.py
tt-demo-test: ## deterministic rules, geometry, PTS and replay-state checks
	$${TROPHY_PYTHON:-python3} -m pytest tests -q
