.PHONY: help up down logs sync
.DEFAULT_GOAL := help

# NOTE: This Makefile is intentionally partial — Phase 1 (T0 steps 1-6) only
# needs Qdrant lifecycle + dep sync. Targets for verify/golden/ingest/index/
# search/eval/smoke/test/lint land as their src/cli.py commands are built in
# later phases (see docs/t0.md steps 7-19).

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start Qdrant
	docker compose up -d qdrant
	@echo "Qdrant dashboard: http://localhost:6333/dashboard"

down: ## Stop Qdrant (keeps the named volume)
	docker compose down

logs: ## Tail Qdrant logs
	docker compose logs -f qdrant

sync: ## Install/sync Python deps
	uv sync
