.PHONY: help up down restart logs ps build prod prod-down shell-backend \
	lint lint-backend lint-frontend format test test-backend test-frontend check \
	lock lock-frontend clean

# Pick up host ports from .env.
-include .env

COMPOSE := docker compose
PROD    := docker compose -f docker-compose.yml -f docker-compose.prod.yml
BACKEND := $(COMPOSE) run --rm --no-deps backend
FRONTEND := $(COMPOSE) run --rm --no-deps frontend

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env
	@echo "→ created .env from .env.example"

# --- Stack ---

up: .env ## Build and start the dev stack (detached), wait for health
	$(COMPOSE) up -d --build --renew-anon-volumes --wait
	@echo ""
	@echo "→ app        http://localhost:$(or $(FRONTEND_PORT),5174)"
	@echo "→ API docs   http://localhost:$(or $(BACKEND_PORT),8000)/docs"

down: ## Stop the dev stack (keeps data)
	$(COMPOSE) down

restart: down up ## Restart the dev stack

logs: ## Tail logs (make logs s=backend for one service)
	$(COMPOSE) logs -f $(s)

ps: ## Show service status
	$(COMPOSE) ps

build: ## Rebuild dev images
	$(COMPOSE) build

prod: .env ## Run production-shaped images (app on :8080)
	$(PROD) up -d --build --wait
	@echo "→ app  http://localhost:$(or $(PROD_FRONTEND_PORT),8080)"

prod-down: ## Stop the production-shaped stack
	$(PROD) down

shell-backend: ## Shell inside the backend container
	$(BACKEND) bash

# --- Quality (all in containers) ---

lint: lint-backend lint-frontend ## Lint + type-check everything

lint-backend:
	$(BACKEND) sh -c 'ruff check . && ruff format --check . && mypy app && lint-imports'

lint-frontend:
	$(FRONTEND) sh -c 'npm run lint && npm run format:check && npm run typecheck'

format: ## Auto-format backend + frontend
	$(BACKEND) sh -c 'ruff check --fix . && ruff format .'
	$(FRONTEND) npm run format

test: test-backend test-frontend ## Run all tests

test-backend:
	$(BACKEND) pytest

test-frontend:
	$(FRONTEND) npm test -- --run

check: lint test ## Lint + test everything (what CI should run)

# --- Dependencies ---

lock: ## Refresh backend/uv.lock after editing pyproject.toml, then rebuild
	$(BACKEND) uv lock
	$(COMPOSE) build backend

lock-frontend: ## Refresh package-lock.json after editing package.json, then rebuild
	$(FRONTEND) npm install
	$(COMPOSE) build frontend

clean: ## Stop everything and remove volumes
	$(COMPOSE) down -v
