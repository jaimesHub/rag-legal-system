.PHONY: help up down logs sync fetch verify golden ingest index search eval smoke test lint fmt clean
.DEFAULT_GOAL := help

# Number of corpus documents ingest/smoke pull in. T0 smoke scope is 500 per
# docs/plan.md; LIMIT=0 means the full corpus (T2+ uses that).
LIMIT ?= 500
K ?= 10

# SPLIT=test is the benchmark split for every week — nothing here trains on
# anything, so there's no tuning-then-final-check split to protect (CLAUDE.md
# "Bất biến" #1). RETRIEVER=vector is the only retriever wired at T0 (bm25
# lands at T2). PROVIDER is read straight from the environment by
# config/settings.py — run e.g. `PROVIDER=fake make smoke` for a fully
# offline run (no GEMINI_API_KEY needed).
SPLIT ?= test
RETRIEVER ?= vector
LABEL ?=

EVAL_ARGS = --retriever $(RETRIEVER) --k $(K)
ifneq ($(strip $(LABEL)),)
EVAL_ARGS += --label $(LABEL)
endif

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

fetch: ## Pre-download the dataset into data/raw/ (optional; commands fetch on demand)
	uv run python -m src.cli fetch

verify: ## Download the pinned dataset and assert its schema and counts
	uv run python -m src.cli verify-dataset

golden: ## Build dev/test golden splits (test is the benchmark split; dev is not evaluated)
	uv run python -m src.cli build-golden

ingest: ## Clean, chunk, and write processed passages. LIMIT=0 = full corpus (T2+)
	uv run python -m src.cli ingest --limit $(LIMIT)

index: ## Embed and upsert all processed passages into Qdrant
	uv run python -m src.cli index --limit 0

search: ## Ad-hoc query, e.g. make search Q="quay đầu xe trên cao tốc"
	uv run python -m src.cli search --query "$(Q)" --k $(K)

eval: ## Evaluate on split=test, e.g. make eval RETRIEVER=vector LABEL=t0-baseline
	uv run python -m src.cli evaluate --split $(SPLIT) $(EVAL_ARGS)

smoke: ## T0 deliverable: verify -> golden -> ingest -> index -> evaluate, one command. LIMIT=0 = full corpus
	uv run python -m src.cli smoke --limit $(LIMIT) --k $(K)

test: ## Run the offline test suite (tests marked `live` are deselected by default)
	uv run pytest --cov=src --cov=config --cov-report=term-missing -q

lint: ## Lint and format check
	uv run ruff check src config tests
	uv run ruff format --check src config tests

fmt: ## Autoformat
	uv run ruff format src config tests
	uv run ruff check --fix src config tests

clean: ## Remove derived artifacts and caches (never touches data/raw or data/golden)
	rm -rf data/processed artifacts .pytest_cache .ruff_cache
