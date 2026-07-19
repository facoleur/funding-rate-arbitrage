# backend — option arbitrage Python

Python + FastAPI + asyncio backend for cross-exchange option arbitrage.
Reference doc: **`backend/AGENTS.md`** and root **`AGENTS.md`** / **`CLAUDE.md`**.

## Repo layout (quick)

- `src/option_arb/` — application code (see `backend/AGENTS.md` for module map)
- `tests/` — pytest suite (69 tests currently green)
- `pyproject.toml` — uv-managed deps
- `alembic.ini` + `src/option_arb/db/migrations/` — schema migrations
- `Dockerfile` — image used by every backend container
- `scripts/` — one-off helpers (e.g. `derive_bootstrap.py`)

## Prereqs

- **uv** ≥ 0.11 (for Python deps): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **docker + docker compose** (for Postgres and the full stack)
- **`.env` at the repo root** — copy from `.env.example` and fill secrets. `chmod 600 .env`.
- **`config.yaml` at the repo root** — runtime knobs (thresholds, exchanges, mode).

The Makefile lives at the **root**. `backend/Makefile` is a thin proxy — every target works from either location.

## First-time setup (single command)

From the repo root OR from `backend/`:

```bash
uv sync          # install deps
make bootstrap   # starts Postgres, waits, applies migrations, verifies config loads
make test        # 69 tests should pass
```

If `make bootstrap` complains, run pieces one by one: `make db`, wait 5s, `make migrate`.

## Running the system locally

Three processes cooperate via Postgres. Each one is its own terminal in dev.

```bash
# terminal 1 — start / keep Postgres running
make db

# terminal 2 — screener + WS + rebalancer + alerter
make dev-worker

# terminal 3 — executor state machine
make dev-executor

# terminal 4 (optional) — REST + SSE API
make dev-api
# → http://127.0.0.1:8000/health
```

`dev-worker`, `dev-executor`, `dev-api` all have a `db-check` prerequisite: they fail immediately with a helpful message if Postgres isn't reachable, instead of a 60-line SQLAlchemy stack trace.

**Safety**: as long as `executor.mode: paper` in `config.yaml`, every exchange adapter is wrapped in `MockExchange`. `place_order` is intercepted and simulated via `SlippageModel` — **no real orders are ever sent**, even with live credentials in `.env`. This is enforced by unit tests in `tests/test_paper_mode_safety.py`.

## Running the full dockerized stack

```bash
make up            # postgres + migrate + api + workers + executor (background)
make logs svc=executor
make down
```

`docker-compose.yml` is at the repo root and wires everything together.

## Common commands (run from either dir)

| Command | What it does |
|---|---|
| `make bootstrap` | postgres + migrate + config sanity-check (once) |
| `make db` / `make db-shell` / `make db-reset` | manage Postgres container |
| `make dev-api` / `dev-worker` / `dev-executor` | local processes with hot reload / logs |
| `make migrate` / `make migrate-new msg="..."` | Alembic |
| `make test` / `lint` / `format` / `typecheck` | pytest, ruff, mypy |
| `make kill` / `make resume` | executor kill-switch |
| `make backtest file=…` / `make record ex=… dur=…` | offline replay + recording |
| `make up` / `make down` / `make paper` / `make live` | dockerized stack |

Run `make help` for the full annotated list.

## Environment (`.env` at repo root)

Minimum required for paper mode against real market data:
```
# Postgres URL (defaults are fine when postgres is dockerized on localhost)
DATABASE_URL=postgresql+asyncpg://option_arb:option_arb@localhost:5432/option_arb

# Telegram alerts (optional — leave empty to disable)
BOT_TOKEN=
CHAT_ID=

# Derive (Lyra V2) — see scripts/derive_bootstrap.py to fetch subaccount_id
DERIVE_WALLET_ADDRESS=       # SCW address from app.derive.xyz/developers, NOT your EOA
DERIVE_SUBACCOUNT_ID=
DERIVE_SESSION_PRIVATE_KEY=  # 0x… hex

# Deribit — test.deribit.com for testnet, deribit.com for mainnet
DERIBIT_CLIENT_ID=
DERIBIT_CLIENT_SECRET=
```

Config lookup: `.env` is loaded from the repo root first, then from CWD. Runs from anywhere.

## Fetching your Derive subaccount_id

If you don't know it, use the helper (needs `DERIVE_SESSION_PRIVATE_KEY` + `DERIVE_WALLET_ADDRESS` already set):

```bash
uv run python scripts/derive_bootstrap.py \
  --network mainnet \                          # or testnet
  --session-key "$DERIVE_SESSION_PRIVATE_KEY" \
  --wallet "$DERIVE_WALLET_ADDRESS"
# → prints JSON with subaccount_ids + the .env line to copy
```

## Troubleshooting

- **`Connect call failed ('::1', 5432, ..., ...)`** → Postgres not running. `make db`.
- **`Client error '403 Forbidden' ... nginx/1.22.1`** on Derive private endpoints → session key not registered on this wallet (nginx-level ecrecover check). Verify on `app.derive.xyz/developers` or `testnet.derive.xyz/developers`.
- **Tests fail on `test_build_authenticator_returns_noauth_when_creds_missing`** → your real `.env` at root is being loaded. This is expected in your local env; CI runs in a clean container.
- **Nothing appears in `opportunities` after 30s** → the market may not have cross-venue arb right now (rare with only 2 venues). Lower `thresholds.min_apr_pct` in `config.yaml` to `0.1` to sanity-check the pipeline detects at all.
- **`ImportError: derive_action_signing`** → `uv sync` again.

## Testing model

`pytest` uses SQLite in a temp directory per test (fast, isolated). Production runs on Postgres. Model code is DB-agnostic (SQLModel). See `tests/conftest.py::test_db` fixture.
