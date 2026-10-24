.PHONY: up down logs smoke
up:      ## start the live stack (run on the GCP VM)
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f --tail=100
smoke:   ## hour-0 smoke tests (build plan section 8)
	bash scripts/smoke.sh
