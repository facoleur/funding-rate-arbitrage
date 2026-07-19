# AGENTS.md — Option Arbitrage

Cross-exchange **crypto options arbitrage** system. Detect + execute spreads where the highest bid on exchange A exceeds the lowest ask on exchange B for the same option instrument, net of taker fees. Nothing else.

Perpetual-funding arbitrage code was previously in this repo and has been deleted. Do not reintroduce it. The prior TypeScript prototype has also been deleted — the Python `backend/` is the sole source of truth.

---

## Repo layout

```
option_arbitrage/
├── AGENTS.md                    # this file
├── CLAUDE.md                    # Claude Code session pointer
├── backend/                     # Python (FastAPI + uv + asyncio)
│   ├── AGENTS.md                # backend internals
│   ├── src/option_arb/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                    # TanStack Start (not yet built)
│   └── REQUIREMENTS.md
├── data/                        # (formerly SQLite; now unused for runtime — pg volume owns state)
├── docker/                      # reserved for shared image layers if needed
├── docker-compose.yml           # postgres + api + workers + executor
├── Makefile                     # canonical local entry-points
├── config.yaml                  # runtime knobs (thresholds, limits, kill-switches)
└── .env.example
```

## Current state

- **Backend Python (`backend/`)** — all phases 1-12 landed.
  - REST + WS adapters for Deribit / Derive / Aevo (public data working; private orders reject cleanly until auth credentials provided).
  - Screener, executor (with 4 kill-switches + market-out on single-leg fill), rebalancer (monitoring only), alerter (Telegram), MockExchange with SlippageModel, backtest + record CLIs.
  - 60 tests passing.
- **Frontend (`frontend/`)** — not built. Spec in `frontend/REQUIREMENTS.md`. Target: TanStack Start, read-only via REST + SSE, no auth, localhost only.
- **Trigger.dev + Telegram TS legacy** — deleted. Telegram is re-implemented in `backend/src/option_arb/services/alerter.py`.

## Target architecture

**Stack**: FastAPI + uv + Pydantic + asyncio + httpx + websockets + SQLModel + Alembic + Postgres.

```
Data plane
├── screener        WS tickers → in-memory book_cache → detect → write opportunities
├── executor        picks PENDING opps → REST L2 refresh → 2 IOC limits → market-out on fail
├── rebalancer      monitors positions/balances/expiries — alerts only, no auto action
└── alerter         Telegram (+ future channels) via asyncio event bus

Storage
└── Postgres 16     shared by all backend services; frontend reads via REST only.
                    SQLite is retained ONLY for pytest (fast, isolated per test).

API surface
└── FastAPI         REST for lists/detail + admin kill/resume
                    SSE /api/stream for live push events
```

3 backend containers (option C — executor isolated): `api`, `workers`, `executor` + a `postgres` service and a one-shot `migrate`. See `docker-compose.yml`.

### Data fetching strategy

1. **REST bootstrap (every 6h)** — instrument metadata.
2. **WebSocket tickers (permanent)** — one connection per exchange, top-bid/ask push into `book_cache`.
3. **Screener** — reads cache in-memory every 500ms, groups by normalized name, writes `opportunities` PENDING.
4. **Executor** — before placing, does a fresh REST L2 fetch on both venues (200ms timeout), walks the book, re-verifies APR net of slippage, then places IOC limits.

### Authentication (per exchange)

Every adapter takes an optional `Authenticator` (see `backend/src/option_arb/exchanges/auth.py`). Public paths ignore it; private paths require it. Without one, adapters return `REJECTED` / empty instead of hitting the network.

| Exchange | Model | Class | Status |
|---|---|---|---|
| Deribit | OAuth 2.0 `client_credentials` | `DeribitOAuth` | ✅ implemented — token fetch + refresh (~1h TTL) |
| Derive (Lyra V2) | Session-key signing (custom digest: `keccak(0x1901 \|\| DOMAIN_SEPARATOR \|\| action_hash)`) | `DeriveAuth` (wraps official `derive_action_signing` lib) | ✅ implemented — signs trades + `X-LYRA*` REST headers |
| Aevo | EIP-712 signing key | — (public-only for now) | ⏳ deferred |

Runtime is **testnet by default** for every exchange (see `config.yaml`). Flip `network: mainnet` + swap the `rest_base_url` / `ws_url` in `config.yaml` to go live.

**Deribit** (see `AGENTS.md` step-by-step or `.env.example`):
- UI → Account → API → Add new key with scopes `trade:read_write` + `wallet:read_write`; IP allowlist recommended.
- `.env`: `DERIBIT_CLIENT_ID`, `DERIBIT_CLIENT_SECRET`.
- Token TTL ≈ 3600s, refreshed automatically 60s before expiry.

**Derive**:
- Deposit USDC on **app.derive.xyz** → creates SCW + subaccount.
- UI → Settings → API Keys → Create Session Key (admin, 30-day expiry).
- `.env`: `DERIVE_WALLET_ADDRESS` (SCW, not your EOA), `DERIVE_SUBACCOUNT_ID`, `DERIVE_SESSION_PRIVATE_KEY`.
- Protocol constants (DOMAIN_SEPARATOR, ACTION_TYPEHASH, TRADE_MODULE) are baked into `exchanges/derive_constants.py` for both mainnet + testnet.
- Signing is done via the official `derive-action-signing` package (already a dep). `DeriveAuth.sign_trade_action(...)` produces the payload that merges into `/private/order`.

Storage rules (both):
- Local dev: `.env` at repo root, `chmod 600 .env`. Not committed.
- Prod: proper secrets manager (Vault / Doppler / AWS Secrets Manager). Never bake into an image.
- Rotate Derive session keys every 30 days.

## Conventions

- **Normalized instrument name**: `{UNDERLYING}-{YYYYMMDD}-{STRIKE}-{C|P}` (e.g. `BTC-20251025-30000-C`). Every adapter MUST emit this.
- **Prices** in quote currency (USD). Deribit returns bid/ask in underlying units — the adapter multiplies by `underlying_price` to convert.
- **Fees** applied as `taker_fee_rate` (fraction) on both legs.
- **APR** = `(net_spread_pct / days_to_expiry) * 365`.
- **Liquidity floor**: `bid_price * bid_qty >= size_threshold_usd` (default $100).
- **Decimal, not float** for prices in the comparator + executor.
- **Modes**: every opportunity / trade tagged `mode ∈ {live, paper, backtest}`.

## Runtime config

Central YAML at `config.yaml` (mounted read-only into every container). Env `.env` holds only secrets + `DATABASE_URL` + `CONFIG_PATH`.

Key knobs:
- `thresholds.min_apr_pct`, `min_notional_usd`, `size_threshold_usd`
- `executor.mode` (paper|live), `max_slippage_pct`, `walk_book`
- `limits.max_notional_per_trade_usd`, `max_positions_open`, `max_daily_loss_usd`, `kill_switch_file`
- `exchanges.*.rest_rate_limit_per_sec`, `ws_max_subscriptions`

## Executor kill-switches (4, all active)

1. **Max notional per trade** — refuses if `walked_size > cap`.
2. **Max open positions** — refuses when active-trade count is at cap.
3. **Max daily loss** — refuses if realised PnL since midnight UTC is below `-cap`.
4. **Manual** — file `data/EXECUTOR_DISABLED` OR `POST /api/executor/kill`. Checked every loop iteration.

## Testing model

**Mandatory paper mode before live.** `MockExchange` mirrors real books but simulates fills via `SlippageModel` (walks the book, gaussian noise, random rejection, latency, respects limit price). Same screener + executor code runs in both modes.

**Backtest CLI** replays recorded `book_snapshots` through the pipeline, tagged `mode=backtest`.

**Test DB**: pytest uses SQLite for speed and isolation (fresh `.db` file per test via `test_db` fixture in `backend/tests/conftest.py`). Production runs on Postgres. Model code is DB-agnostic (SQLModel + SQLAlchemy).

Coverage: 60 tests across comparator, HTTP rate limit / retry / circuit, screener, executor (happy path + all 4 kill-switches + stale book + apr dropped + empty book + STUCK on failed market-out), mock exchange, alerter (persistence + threshold + level filter), rebalancer (low balance + expiring + unhealthy), auth (NoAuth + Deribit OAuth token cache + EIP-712 signer), WS manager (subscribe payload per exchange + reconnect), adapters (WS ticker parsing per exchange).

## Local dev entry-points (Makefile)

```
make up               # docker compose up -d (full stack: postgres + api + workers + executor)
make down
make paper            # foreground, paper mode
make live             # foreground, live mode (typed confirmation)
make logs svc=api     # tail one service

# Local dev without full docker:
make db               # start only postgres
make dev-api          # api on host (uvicorn hot reload)
make dev-worker
make dev-executor

# Tests + lint:
make test             # pytest (uses SQLite per-test)
make lint             # ruff check
make format           # ruff format
make typecheck        # mypy

# DB:
make migrate          # alembic upgrade head
make migrate-new msg="…"
make db-shell         # psql into the postgres container

# Executor safety:
make kill / make resume

# Backtest + record:
make record ex=derive dur=1h
make backtest file=recordings/derive-*.jsonl
```

## For AI agents working here

1. **Read `backend/AGENTS.md`** for backend internals before editing.
2. **Do not reintroduce funding-rate code.**
3. **Frontend never touches Postgres directly** — read-only via REST.
4. **When adding a new exchange**, implement `AbstractExchange` (`backend/src/option_arb/exchanges/base.py`): rate-limited HTTP via the shared wrapper, WS subscribe, `normalized_name` output, optional `Authenticator` for private paths.
5. **Any code touching order placement** must have a `MockExchange` path and unit tests covering the 4 kill-switches. Never wire the live executor without paper validation.
6. **The executor is the highest-blast-radius component.** State transitions persist to `trades` + `orders` before the next await; kill-switches are honoured every loop.
7. **Reference plan**: `~/.claude/plans/rippling-gathering-fountain.md`.

## Open decisions

- [ ] Fill Derive + Aevo EIP-712 schemas (blocks live trading on those venues).
- [ ] Where to source recorded order-book data for long-window backtests.
- [ ] Slippage-model coefficients — empirical calibration once we have real fills.
- [ ] Secrets manager choice for prod session keys (Vault vs Doppler vs env-only).
