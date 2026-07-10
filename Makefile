.DEFAULT_GOAL := help
BACKEND_DIR := packages/backend
SRC_DIR := $(BACKEND_DIR)/src
TESTS_DIR := $(BACKEND_DIR)/tests

.PHONY: help install install-dev dev test test-unit test-integration coverage \
        lint format typecheck check clean build docker-build docker-up \
        docker-down docker-logs forge-init forge-run setup-ollama \
        test-watch format-check docker-clean

help: ## Show this help message
	@echo '\033[1;36mForge — The AI Execution Layer\033[0m'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install backend in production mode
	cd $(BACKEND_DIR) && pip install .

install-dev: ## Install backend with dev dependencies
	cd $(BACKEND_DIR) && pip install -e ".[dev]"

dev: ## Start FastAPI dev server with hot-reload
	uvicorn forge.presentation.api.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run all tests
	cd $(BACKEND_DIR) && pytest $(TESTS_DIR) -v

test-unit: ## Run unit tests only
	cd $(BACKEND_DIR) && pytest $(TESTS_DIR)/unit -v

test-integration: ## Run integration tests only
	cd $(BACKEND_DIR) && pytest $(TESTS_DIR)/integration -v

coverage: ## Run tests with HTML coverage report
	cd $(BACKEND_DIR) && pytest $(TESTS_DIR) --cov=forge \
		--cov-report=html --cov-report=term-missing -v

test-watch: ## Run tests in watch mode (requires pytest-watch)
	cd $(BACKEND_DIR) && ptw $(TESTS_DIR) -- -v

lint: ## Run ruff linter
	ruff check $(SRC_DIR)/

format: ## Format code with ruff
	ruff format $(SRC_DIR)/ $(TESTS_DIR)/

format-check: ## Check formatting without changes
	ruff format --check $(SRC_DIR)/

typecheck: ## Run mypy type checker
	mypy $(SRC_DIR)/forge/ --ignore-missing-imports

check: lint typecheck format-check ## Run all quality checks

clean: ## Remove build artifacts, caches, .db files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	find . -name '*.pyc' -delete 2>/dev/null; true
	find . -name 'forge.db' -delete 2>/dev/null; true
	find . -name 'htmlcov' -exec rm -rf {} + 2>/dev/null; true

build: ## Build Python distribution packages
	cd $(BACKEND_DIR) && pip install build && python -m build

docker-build: ## Build Docker image
	docker build -t forge:latest -t forge:1.0.0 .

docker-up: ## Start services with docker-compose
	docker compose up -d
	docker compose logs -f forge-api

docker-down: ## Stop and remove containers
	docker compose down

docker-logs: ## Tail docker-compose logs
	docker compose logs -f

docker-clean: ## Remove containers, volumes, images
	docker compose down -v --remove-orphans
	docker rmi forge:latest forge:1.0.0 2>/dev/null; true

forge-init: ## Run forge init in current directory
	forge init

forge-run: ## Run forge with TEST_GOAL (default: "echo hello world")
	forge run "$(TEST_GOAL)"

setup-ollama: ## Pull default Ollama model (llama3.2)
	ollama pull llama3.2
