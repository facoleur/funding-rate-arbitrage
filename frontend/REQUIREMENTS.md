# Frontend REQUIREMENTS

Cahier des charges du frontend monitoring pour le système d'arbitrage d'options. Le frontend n'est pas encore implémenté — ce fichier définit le périmètre et le contrat à respecter quand il le sera.

## Stack pressenti

TanStack Start (Vinxi + Vite + React 19) + TanStack Router file-based + TanStack Query + Tailwind. À valider au moment de démarrer le frontend, pas maintenant. Le squelette Next.js actuel dans `frontend/` sera remplacé.

## Contraintes non négociables

- **Read-only du backend** via API REST + SSE. **JAMAIS d'accès direct SQLite.**
- **Pas d'auth.** Bind sur `127.0.0.1` uniquement en local.
- **Monitoring pur** : PAS d'actions de trading depuis l'UI. Les seules actions autorisées sont admin (kill / resume executor).
- **Minimal et précis** : pas de dashboards fancy, pas de charts complexes. Tables + indicateurs simples.

## Pages MVP (4)

### 1. `/` — Opportunités live

- Table temps réel des opportunités `PENDING` + récentes.
- Colonnes : symbole, expiry, buy_from, sell_to, top_ask, top_bid, spread%, APR%, max_size, status, timestamp.
- Filtres : min APR, min notional, ticker (BTC/ETH), exchange pair.
- Update via SSE (`opportunity_detected` event) + fallback polling 5s.
- Highlight visuel des opps qui vont être exécutées (APR > threshold).

### 2. `/trades` — Historique

- Table des trades avec status (`FILLED`, `HEDGED`, `STUCK`, `FAILED`).
- Colonnes : opened_at, instrument, buy_ex/sell_ex, size, fill prices, slippage%, PnL, mode (live/paper/backtest).
- Filtre par mode (live | paper | backtest).
- Filtre par status.
- Pagination (50 par page).
- Update via SSE (`trade_*` events).

### 3. `/positions` — État par exchange

- Card par exchange : balance USD, margin used, positions ouvertes (count).
- Sous-table positions ouvertes : instrument, size, avg_price, expiry (highlight rouge si <24h).
- Statuts connectivité : WS status (CONNECTED / RECONNECTING / UNHEALTHY), REST status.
- Update polling 10s.

### 4. `/executor` — État + admin

- Status executor : `RUNNING` / `KILLED`, dernier heartbeat.
- Config actuelle (readonly display) : min_apr, min_notional, max_notional_per_trade, max_positions, max_daily_loss.
- État kill-switches : nb positions ouvertes, PnL journalier, fichier KILL présent.
- Boutons : `Kill` (POST /api/executor/kill), `Resume` (POST /api/executor/resume). Confirmation modale.
- Alertes récentes (dernières 50) depuis table `alerts`.

## Contract API à consommer

| Endpoint | Méthode | Description |
|---|---|---|
| `/api/opportunities?status=&min_apr=&limit=` | GET | Liste opps avec filtres |
| `/api/opportunities/:id` | GET | Détail opp |
| `/api/trades?mode=&status=&limit=&offset=` | GET | Liste trades paginée |
| `/api/trades/:id` | GET | Détail trade + orders |
| `/api/positions` | GET | Positions ouvertes par exchange |
| `/api/exchanges` | GET | État exchanges (balance, WS/REST status) |
| `/api/executor/state` | GET | Status executor + kill-switches state |
| `/api/executor/kill` | POST | Active kill-switch |
| `/api/executor/resume` | POST | Désactive kill-switch |
| `/api/alerts?level=&limit=` | GET | Historique alerts |
| `/api/stream` | GET (SSE) | Push events |

## Events SSE à consommer

`opportunity_detected`, `trade_opened`, `trade_filled`, `trade_failed`, `trade_stuck`, `kill_switch_tripped`, `position_expiring`, `balance_low`, `exchange_unhealthy`.

## Layout

Sidebar minimale (4 liens), main content full-width, dark mode par défaut.

## Non-goals

Mobile-first, i18n, accessibilité fine (usage personnel local), animations, graphes de courbes (une simple sparkline PnL suffit).
