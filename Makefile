.DEFAULT_GOAL := help

.PHONY: help install test lint fmt env

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Sync all dependencies (incl. dev)
	uv sync --group dev

test: ## Run tests with coverage gate
	uv run pytest

lint: ## Ruff check + format check
	uv run ruff check src tests
	uv run ruff format --check src tests

fmt: ## Ruff format + autofix
	uv run ruff format src tests
	uv run ruff check --fix src tests

env: ## Render flat .env from config templates
	bash config/.env-render.sh
