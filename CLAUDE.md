# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication style

- Be extremely concise. Get straight to the point, no preamble, no closing summary.
- Never repeat information already stated.
- No filler phrases, no "feel free to ask if...", no final recap that restates what was just said.
- Prefer bullet points over paragraphs when possible.
- If an explanation fits in one sentence, don't stretch it into three.
- Prioritize technical accuracy over prose fluency: a terse, exact answer beats a pleasant but padded one.

## Sole purpose

Cross-exchange **crypto options arbitrage**. Detect + execute spreads where the highest bid on exchange A exceeds the lowest ask on exchange B for the same option instrument, net of taker fees. Nothing else — perpetual-funding arbitrage code is intentionally gone, and the prior TypeScript prototype has been deleted.

## Depth docs

Always read the relevant doc before editing:

- `AGENTS.md` (root) — architecture, conventions, auth model, kill-switches.
- `backend/AGENTS.md` — Python backend internals (module map, contracts, testing).
- `frontend/REQUIREMENTS.md` — frontend pages, stack, and API contract.
- `docs/deribit-vs-derive-options.md` — exchange-specific pricing traps, settlement differences, auth latency.
- Full architecture plan: `~/.claude/plans/rippling-gathering-fountain.md`.

## Current state

- **Backend `backend/` (Python + Postgres)** is the sole source of truth. All phases 1-12 landed; 74 tests passing.
- Deribit adapter has full OAuth support (token fetch + refresh cached). Derive has full EIP-712 signing via `DeriveAuth`. Aevo uses **REST polling** (no WS option channels) — public data only, private auth deferred.
- **Frontend `frontend/`** is built: Vite + React + TanStack Query + React Router, 7 pages (Book, Executor, Funding, History, Opportunities, Positions, Trades). Served via nginx in the `frontend` Docker container.
- **Storage**: Postgres in production (docker-compose service `postgres`). SQLite retained ONLY inside pytest for speed/isolation. Model code is DB-agnostic.

## Common commands

Use the Makefile — it's canonical. Every project must have one with at minimum `make dev` (stack local hot-reload) and `make release VERSION=X.Y.Z` (tag + push pour déclencher le CI/CD).

```bash
# Docker stack (full)
make up                     # postgres + migrate + api + workers + executor (background)
make down
make dev                    # hot-reload stack (source mounted, no rebuild on change)
make dev-down               # stop dev stack
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
make test                   # pytest (74 tests, SQLite per-test)
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
- **Aevo** = `NoAuth` (public REST polling only — no WS option channels). Private signing deferred.

All exchanges are currently configured as **mainnet** in `config.yaml`. Change `network: testnet` + swap `rest_base_url`/`ws_url` to use testnet.

## VPS deployment

### Conventions

- Fichiers sur le VPS : `/srv/arbitrage/` (`docker-compose.yml`, `docker-compose.prod.yml`, `config.yaml`, `.env`)
- `.env` : chmod 600, jamais commité — généré à chaque deploy par le workflow CI
- Réseau Docker externe `proxy` (partagé avec Caddy dockerisé) — `api` et `frontend` rejoignent ce réseau via aliases (`arbitrage-api`, `arbitrage-frontend`)
- `docker-compose.prod.yml` déclare **toujours** `default:` dans la section `networks:` — sans ça, les services ne se trouvent pas entre eux (DNS interne cassé)
- Health check post-deploy : `curl http://localhost:8001/health` (port hôte) — les aliases réseau Docker ne sont pas résolvables depuis le host VPS
- Caddy dockerisé sur `/srv/caddy` ; snippet dans `/srv/caddy/sites/option-arb.caddy` (fichier `option-arb.caddy` à la racine du repo)
- Image : `ghcr.io/facoleur/option-arb:<git-sha>` — jamais le tag `latest` en prod

### Secrets GitHub requis

| Secret                      | Description                                            |
| --------------------------- | ------------------------------------------------------ |
| `VPS_IP`                    | IP du VPS                                              |
| `VPS_SSH_KEY`               | Clé SSH dédiée déploiement                             |
| `POSTGRES_PASSWORD`         | Mot de passe Postgres                                  |
| `DERIBIT_CLIENT_ID`         | OAuth Deribit                                          |
| `DERIBIT_CLIENT_SECRET`     | OAuth Deribit                                          |
| `DERIVE_WALLET_ADDRESS`     | Adresse SCW Derive                                     |
| `DERIVE_SUBACCOUNT_ID`      | Subaccount Derive                                      |
| `DERIVE_SESSION_PRIVATE_KEY`| Clé de session Derive                                  |
| `BOT_TOKEN`                 | Token Telegram                                         |
| `CHAT_ID`                   | Chat ID Telegram                                       |

Pas de secret GHCR séparé : le `GITHUB_TOKEN` du job est forwardé via SSH.

### Workflow CI/CD

- Déclenché sur tags `v*.*.*` uniquement (pas push master — déploiement auto sur executor live = trop risqué)
- **Job `build`** : build + push vers GHCR avec tag `${{ github.sha }}`
- **Job `deploy`** : génère `.env`, copie les fichiers, restart stagé avec kill-switch executor, copie snippet Caddy + reload

### Initialisation du serveur (première fois)

```bash
sudo mkdir -p /srv/arbitrage/data && sudo chown ubuntu:ubuntu /srv/arbitrage
docker network create proxy   # si pas déjà créé par une autre app
```

## Rules for changes

1. **Do not reintroduce funding-rate exchanges or services.**
2. **Frontend never touches Postgres directly.** All reads via REST.
3. **Any code that places real orders must have a MockExchange path** and unit tests covering the 4 kill-switches. Never wire the live executor without paper validation.
4. **The executor is the highest-blast-radius component.** State transitions must persist to `trades` + `orders` before the next await. Never skip kill-switch checks.
5. **`Decimal` for prices** in the comparator and executor. Float only for display / logging.
6. **When adding a new exchange**, implement `AbstractExchange`, add a config entry under `exchanges:` in `config.yaml`, add an `Authenticator` if it needs private auth, and register both in `exchanges/registry.py`.
7. **Migrations**: `make migrate-new msg="..."` — never edit past revisions.
8. **Signing keys never in code or logs.** Always via `settings` (env-loaded). `chmod 600 .env`.
