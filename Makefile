# Enterprise Knowledge Copilot — developer task runner
# Usage: `make <target>`. Requires Docker + Docker Compose. Python targets need a local venv.

COMPOSE := docker compose -f infra/docker-compose.yml
BACKEND := cd backend &&

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Docker stack
# ---------------------------------------------------------------------------
.PHONY: up
up: ## Build and start the full local stack (API, workers, Postgres, Redis)
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Show running services
	$(COMPOSE) ps

# ---------------------------------------------------------------------------
# Backend (local)
# ---------------------------------------------------------------------------
.PHONY: install
install: ## Install backend with dev dependencies (editable)
	$(BACKEND) pip install -e ".[dev]"

.PHONY: dev
dev: ## Run the API locally with autoreload
	$(BACKEND) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: lint
lint: ## Lint with ruff
	$(BACKEND) ruff check app tests

.PHONY: fmt
fmt: ## Auto-format with ruff
	$(BACKEND) ruff check --fix app tests && ruff format app tests

.PHONY: typecheck
typecheck: ## Static type-check with mypy
	$(BACKEND) mypy app

.PHONY: test
test: ## Run the backend test suite
	$(BACKEND) pytest

.PHONY: check
check: lint typecheck test ## Run lint + typecheck + tests
