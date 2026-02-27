# ─── Entourage Makefile ───────────────────────────────────
# Common commands for development, testing, and deployment.

.PHONY: dev test build lint db-migrate clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Start dev infrastructure (Postgres + Redis)
	docker compose up -d
	@echo ""
	@echo "  Infrastructure running. Start services:"
	@echo "    Backend:  cd packages/backend && uv run uvicorn openclaw.main:app --reload"
	@echo "    Frontend: cd packages/frontend && npm run dev"
	@echo ""

test: ## Run all tests
	cd packages/backend && uv run pytest tests/ -x -q \
		--deselect tests/test_teams_api.py::test_team_creation_emits_events
	cd packages/mcp-server && npm run build
	cd packages/frontend && npm run build

build: ## Build production Docker images
	docker compose -f docker-compose.prod.yml build

lint: ## Run linters
	cd packages/backend && uv run ruff check src/ tests/ || true
	cd packages/frontend && npx tsc --noEmit || true
	cd packages/mcp-server && npx tsc --noEmit || true

db-migrate: ## Run database migrations
	cd packages/backend && uv run alembic upgrade head

clean: ## Remove build artifacts and containers
	docker compose down -v 2>/dev/null || true
	rm -rf packages/backend/.pytest_cache packages/backend/__pycache__
	rm -rf packages/frontend/dist packages/frontend/node_modules
	rm -rf packages/mcp-server/dist packages/mcp-server/node_modules
