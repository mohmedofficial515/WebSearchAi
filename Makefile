# WebSearchAi — common dev tasks
# Usage: `make <target>`. On Windows, use `make.bat` (in scripts/) or run targets directly.

PY := python
VENV := .venv
ACTIVATE := $(VENV)/bin/activate
ifeq ($(OS),Windows_NT)
ACTIVATE := $(VENV)/Scripts/activate
endif

.PHONY: help install install-dev format lint test test-unit test-integration test-cov \
        run serve clean build-docker run-docker docs venv

help: ## Show this help
	@echo "WebSearchAi — make targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create virtualenv
	$(PY) -m venv $(VENV)

install: ## Install runtime deps
	pip install -e .
	$(PY) -m playwright install chromium

install-dev: ## Install runtime + dev deps + pre-commit
	pip install -e ".[dev]"
	$(PY) -m playwright install chromium
	pre-commit install

format: ## Auto-format with ruff
	ruff format src tests
	ruff check --fix src tests

lint: ## Lint (no fix)
	ruff check src tests
	ruff format --check src tests
	mypy src

test: test-unit ## Default: run unit tests

test-unit: ## Fast unit tests
	pytest tests/unit -q

test-integration: ## Integration tests (real browser, needs network)
	pytest tests/integration -q -m "not slow and not e2e"

test-cov: ## Full test suite with coverage report
	pytest --cov=src --cov-report=term-missing --cov-report=html

run: ## Run CLI: make run GOAL="visit example.com"
	$(PY) run.py run "$(GOAL)"

serve: ## Start the API + Web UI
	$(PY) serve.py

clean: ## Remove caches & temp files
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +

clean-outputs: ## Remove all task outputs (sessions, reports, logs)
	rm -rf outputs/sessions outputs/reports outputs/cloned_sites outputs/websearchai.log

build-docker: ## Build Docker image
	docker build -t websearchai:latest .

run-docker: ## Run via Docker Compose
	docker compose up -d
	@echo "→ http://localhost:8000"

stop-docker: ## Stop Docker Compose stack
	docker compose down

docs: ## Open docs index
	@echo "See docs/:"
	@ls docs/
