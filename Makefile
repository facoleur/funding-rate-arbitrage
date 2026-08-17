SHELL := /bin/bash
.DEFAULT_GOAL := help

VPS     ?= ubuntu@195.15.243.68
VPS_DIR ?= /opt/option_arbitrage

# ---------- Deploy ----------

deploy: ## Sync code + restart stack on VPS (usage: VPS=user@host make deploy)
	npm run build --prefix frontend
	rsync -avz --delete \
		--exclude='.git/' \
		--filter='+ /frontend/dist/' \
		--filter='+ /frontend/dist/***' \
		--filter=':- .gitignore' \
		. $(VPS):$(VPS_DIR)/
	ssh $(VPS) "cd $(VPS_DIR) && doppler run -- docker compose up -d --build"

deploy-env: ## Push only .env to VPS (update secrets without full rebuild)
	rsync -avz .env $(VPS):$(VPS_DIR)/.env
	@echo "→ .env pushed. Run 'make deploy' or 'ssh $(VPS) cd $(VPS_DIR) && docker compose restart' to apply."

# ---------- Docker stack ----------

up: ## Start the full stack in background (postgres + api + workers + executor)
	docker compose up -d --build

dev: ## Start dev stack with hot-reload on all services (source mounted, no rebuild needed)
	docker compose -f docker-compose.dev.yml up --build

dev-down: ## Stop the dev stack
	docker compose -f docker-compose.dev.yml down

down: ## Stop the stack
	docker compose down

logs: ## Tail logs for one service (usage: make logs svc=api)
	docker compose logs -f $(svc)

live: ## Start stack in LIVE trading mode (requires typed confirmation)
	@read -p "LIVE mode. Confirm with 'yes': " c && [ "$$c" = "yes" ] && EXECUTOR_MODE=live docker compose up --build

# ---------- Local dev ----------

db: ## Start only Postgres
	docker compose up -d postgres

db-shell: ## psql shell into Postgres
	docker compose exec postgres psql -U option_arb -d option_arb

dev-api: ## Run API locally with hot reload
	cd backend && uv run uvicorn option_arb.main:app --reload

dev-worker: ## Run workers locally with hot reload
	cd backend && uv run watchfiles "python -m option_arb.worker" src/

dev-executor: ## Run executor locally with hot reload (paper mode only — never use in live)
	cd backend && uv run watchfiles "python -m option_arb.services.executor" src/

# ---------- DB migrations ----------

migrate: ## Apply Alembic migrations
	cd backend && uv run alembic upgrade head

migrate-new: ## Create new migration (usage: make migrate-new msg="add foo")
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

# ---------- Tests & lint ----------

test: ## Run backend tests
	cd backend && uv run pytest

lint: ## Ruff lint
	cd backend && uv run ruff check src tests

format: ## Ruff format
	cd backend && uv run ruff format src tests

typecheck: ## Mypy
	cd backend && uv run mypy src

# ---------- Backtest / recording ----------

record: ## Record order books (usage: make record ex=derive dur=1h)
	cd backend && uv run python -m option_arb.record --exchange $(ex) --duration $(dur)

backtest: ## Replay a book snapshot file (usage: make backtest file=recordings/foo.jsonl)
	cd backend && uv run python -m option_arb.backtest --file $(file)

# ---------- Executor kill-switch ----------

kill: ## Trip the executor kill-switch
	touch data/EXECUTOR_DISABLED

resume: ## Release the kill-switch
	rm -f data/EXECUTOR_DISABLED

# ---------- Help ----------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: up down logs live db db-shell dev-api dev-worker dev-executor \
        migrate migrate-new test lint format typecheck record backtest \
        kill resume deploy deploy-env help
