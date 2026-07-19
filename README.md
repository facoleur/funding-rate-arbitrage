# Option Arbitrage

Cross-exchange crypto options arbitrage. Detects and executes spreads where the highest bid on exchange A exceeds the lowest ask on exchange B for the same instrument, net of taker fees.

Supported exchanges: Derive (Lyra V2), Deribit, Aevo (read-only for now).

## Prerequisites

- Docker and Docker Compose
- [uv](https://astral.sh/uv) >= 0.11

## First-time setup

```bash
cp .env.example .env
# Fill in credentials (see "Credentials" section below)
chmod 600 .env

uv sync          # install Python deps
make bootstrap   # start Postgres, run migrations, verify config
make test        # 60+ tests should pass
```

## Running in paper mode (safe, no real orders)

Paper mode is the default (`executor.mode: paper` in `config.yaml`). The `MockExchange` intercepts all order placement and simulates fills locally regardless of credentials.

**Option 1: Docker stack (recommended)**

```bash
make up                  # start all services in background
make logs svc=executor   # tail executor
make down
```

**Option 2: Local processes (3 terminals)**

```bash
# terminal 1
make db

# terminal 2
make dev-worker    # screener + WS connections + alerter

# terminal 3
make dev-executor  # executor state machine

# terminal 4 (optional)
make dev-api       # REST + SSE API at http://127.0.0.1:8000
```

## Going live

1. Set credentials in `.env` for the exchanges you want to trade.
2. In `config.yaml`, change `executor.mode: paper` to `executor.mode: live` and flip `network: mainnet` + swap URLs for each exchange.
3. Run `make live` (prompts for typed confirmation before starting).

**The executor will not place orders until you have done both steps.**

## Executor kill-switches

Any of these halts the executor immediately:

- `make kill` (creates `data/EXECUTOR_DISABLED`)
- `POST /api/executor/kill`
- Max notional per trade exceeded
- Max open positions exceeded
- Max daily loss exceeded

Release with `make resume` or `DELETE /api/executor/kill`.

## Credentials

Copy `.env.example` to `.env` and fill in:

**Derive (Lyra V2)**

1. Deposit USDC on [app.derive.xyz](https://app.derive.xyz) to create a smart-contract wallet and subaccount.
2. Go to Settings > API Keys > Create Session Key (admin scope, 30-day expiry).
3. Set `DERIVE_WALLET_ADDRESS` (SCW address, not your EOA), `DERIVE_SUBACCOUNT_ID`, `DERIVE_SESSION_PRIVATE_KEY`.

If you do not know your subaccount ID:

```bash
uv run python scripts/derive_bootstrap.py \
  --network mainnet \
  --session-key "$DERIVE_SESSION_PRIVATE_KEY" \
  --wallet "$DERIVE_WALLET_ADDRESS"
```

**Deribit**

1. Account > API > Add new key with scopes `trade:read_write` and `wallet:read_write`.
2. Set `DERIBIT_CLIENT_ID` and `DERIBIT_CLIENT_SECRET`.

**Telegram alerts (optional)**

Set `BOT_TOKEN` and `CHAT_ID` to receive trade alerts. Leave empty to disable.

## Common commands

```bash
make test                      # pytest (SQLite, fast)
make lint / format / typecheck # ruff + mypy
make migrate                   # apply pending Alembic migrations
make migrate-new msg="..."     # create a new migration
make db-shell                  # psql into the Postgres container
make record ex=derive dur=1h   # record live book snapshots to file
make backtest file=recordings/derive-*.jsonl  # replay through the pipeline
```

## Architecture

See `AGENTS.md` for the full architecture, module map, and conventions.














  docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps api uv run alembic stamp head


  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps api workers executor
