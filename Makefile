.PHONY: dev e2e contracts smoke
dev:        ## start every service natively on the Mac (Agent 1 implements the Procfile)
	@test -f Procfile || (echo "Procfile not created yet (Agent 1, plan §4)"; exit 1)
	honcho start
e2e:        ## headless clip -> calls -> Spacetime check (Agent 1, checkpoint C2)
	@echo "not implemented yet (Agent 1, checkpoint C2)"; exit 1
contracts:  ## regenerate TS + Pydantic types from packages/contracts (Agent 1, C0)
	@echo "not implemented yet (Agent 1, checkpoint C0)"; exit 1
smoke:      ## P0 spikes
	bash scripts/smoke.sh
