# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Sole purpose

Cross-exchange **crypto options arbitrage**. Detect + execute spreads where the highest bid on exchange A exceeds the lowest ask on exchange B for the same option instrument, net of taker fees. Nothing else — perpetual-funding arbitrage code is intentionally gone, and the prior TypeScript prototype has been deleted.

## Depth docs

Always read the relevant doc before editing:

- `AGENTS.md` (root) — architecture, conventions, auth model, kill-switches.
- `backend/AGENTS.md` — Python backend internals (module map, contracts, testing).
- `frontend/REQUIREMENTS.md` — spec for the future TanStack Start frontend.
- Full architecture plan: `~/.claude/plans/rippling-gathering-fountain.md`.

## Current state

- **Backend `backend/` (Python + Postgres)** is the sole source of truth. All phases 1-12 landed; 60 tests passing.
- Deribit adapter has full OAuth support (token fetch + refresh cached). Derive / Aevo have the EIP-712 framework wired but the venue-specific typed-data schema is not yet filled in — orders reject cleanly with reason `..._eip712_schema_not_implemented`.
- **Frontend `frontend/`** contains only `REQUIREMENTS.md` — TanStack Start app not built yet.
- **Storage**: Postgres in production (docker-compose service `postgres`). SQLite retained ONLY inside pytest for speed/isolation. Model code is DB-agnostic.

## Common commands

Use the Makefile — it's canonical.

```bash
# Docker stack (full)
make up                     # postgres + migrate + api + workers + executor (background)
make down
make paper                  # foreground, paper mode
make live                   # foreground, live mode (typed confirmation)
make logs svc=executor      # tail one service

# Local dev without full docker
make db                     # postgres only
make dev-api                # uvicorn hot reload
make dev-worker
make dev-executor

# DB
make migrate                # alembic upgrade head
make migrate-new msg="..."  # create new revision
make db-shell               # psql into postgres

# Test + lint
make test                   # pytest (60 tests, SQLite per-test)
make lint                   # ruff check
make format                 # ruff format
make typecheck              # mypy

# Executor safety
make kill                   # trip kill-switch
make resume                 # release

# Backtest + recording
make record ex=derive dur=1h
make backtest file=recordings/derive-*.jsonl
```

Env vars: `.env` at repo root (see `.env.example`). Runtime config: `config.yaml` at repo root, mounted read-only into every container.

## Architecture at a glance

```
Real exchanges (Derive, Deribit, Aevo)
   │
   ├── REST (metadata + L2 refresh + order placement)  → rate-limited httpx wrapper
   │                                                     with optional Authenticator
   └── WebSocket (ticker push) ─► book_cache in-memory (in the workers container)
                                        │
                                        ▼
                                   screener  (500ms loop)
                                        │  writes `opportunities` PENDING
                                        ▼  (Postgres, cross-service)
                                   executor  (isolated container, 200ms poll)
                                        │  - 4 kill-switches
                                        │  - fresh REST L2 fetch (both venues, 500ms timeout)
                                        │  - walk book + binary-search size
                                        │  - place 2 IOC limits in parallel
                                        │  - market-out on single-leg fill → HEDGED or STUCK
                                        ▼
                                   trades + orders in Postgres
                                        │
                                        ▼
                                   alerter → Telegram + SSE fan-out
```

3 backend containers (option C — executor isolated for independent restart): `api`, `workers`, `executor`. Plus `postgres` service and one-shot `migrate`.

## Invariants

- **Normalized instrument name** `{UNDERLYING}-{YYYYMMDD}-{STRIKE}-{C|P}` — every adapter emits this; cross-exchange matching depends on it.
- **Deribit prices** are in underlying units — adapter multiplies by `underlying_price` to convert to USD.
- **Fees** applied as `taker_fee_rate` (fraction) on both legs.
- `apr = (net_spread_pct / days_to_expiry) * 365`
- Every opportunity / trade tagged `mode ∈ {live, paper, backtest}` — same code path, different exchange adapter.

## Authentication per exchange

See `backend/src/option_arb/exchanges/auth.py` + `derive_auth.py`. Adapters take an optional `Authenticator`; without one, private methods return `REJECTED` cleanly.

- **Deribit** = `DeribitOAuth` (OAuth 2.0 client_credentials, token cached ~1h, auto-refresh). Env: `DERIBIT_CLIENT_ID`, `DERIBIT_CLIENT_SECRET`.
- **Derive** = `DeriveAuth` — specialized: wraps the official `derive-action-signing` package for order signing and produces `X-LYRA*` headers for REST auth. Constants baked in `exchanges/derive_constants.py` (mainnet chain_id=957, testnet 901). Env: `DERIVE_SESSION_PRIVATE_KEY`, `DERIVE_WALLET_ADDRESS` (SCW address), `DERIVE_SUBACCOUNT_ID`.
- **Aevo** = `NoAuth` for now (public read-only). Signing pattern deferred.

Every exchange defaults to **testnet** in `config.yaml`. Change `network: mainnet` + swap `rest_base_url`/`ws_url` to go live.

## Rules for changes

1. **Do not reintroduce funding-rate exchanges or services.**
2. **Frontend never touches Postgres directly.** All reads via REST.
3. **Any code that places real orders must have a MockExchange path** and unit tests covering the 4 kill-switches. Never wire the live executor without paper validation.
4. **The executor is the highest-blast-radius component.** State transitions must persist to `trades` + `orders` before the next await. Never skip kill-switch checks.
5. **`Decimal` for prices** in the comparator and executor. Float only for display / logging.
6. **When adding a new exchange**, implement `AbstractExchange`, add a config entry under `exchanges:` in `config.yaml`, add an `Authenticator` if it needs private auth, and register both in `exchanges/registry.py`.
7. **Migrations**: `make migrate-new msg="..."` — never edit past revisions.
8. **Signing keys never in code or logs.** Always via `settings` (env-loaded). `chmod 600 .env`.
