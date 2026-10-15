.DEFAULT_GOAL := help
API_DIR := services/api
VENV := $(API_DIR)/.venv
BIN := $(VENV)/bin

.PHONY: help setup lock up down migrate test lint format typecheck audit

help: ## Show available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Create the virtualenv and install API dependencies
	uv venv $(VENV)
	uv pip install --python $(BIN)/python -e "$(API_DIR)[dev]"

lock: ## Generate/update services/api/uv.lock (commit it; the Docker build installs from it)
	cd $(API_DIR) && uv lock

up: ## Start Postgres, run migrations, start the API (needs .env and uv.lock)
	docker compose up --build

down: ## Stop containers
	docker compose down

migrate: ## Apply migrations using MIGRATION_DATABASE_URL
	cd $(API_DIR) && ../../$(BIN)/alembic upgrade head

test: ## Run the API tests (needs Postgres, see README)
	cd $(API_DIR) && ../../$(BIN)/pytest -q

lint: ## Lint and check formatting
	cd $(API_DIR) && ../../$(BIN)/ruff check . && ../../$(BIN)/ruff format --check .

format: ## Auto-format
	cd $(API_DIR) && ../../$(BIN)/ruff check --fix . && ../../$(BIN)/ruff format .

typecheck: ## Static type check (strict)
	cd $(API_DIR) && ../../$(BIN)/mypy app

audit: ## Scan dependencies for known vulnerabilities
	cd $(API_DIR) && ../../$(BIN)/pip-audit
