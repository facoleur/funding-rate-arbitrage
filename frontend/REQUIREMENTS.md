# Frontend — état actuel

Le frontend est implémenté. Stack : **Vite + React 19 + TypeScript + TanStack Query + React Router DOM + Tailwind CSS**. Charts : **recharts** (vues détail `/opportunites/:id` et `/structured/:id`).

Servi via nginx dans le container Docker `frontend` (port 3000 → port 80 interne). Le container est inclus dans `docker-compose.yml` et `docker-compose.dev.yml`.

## Contraintes (toujours en vigueur)

- **Read-only du backend** via API REST + SSE. Jamais d'accès direct à Postgres.
- **Pas d'auth.** Bind sur `127.0.0.1` uniquement en local / Caddy en prod.
- **Monitoring pur** : pas d'actions de trading depuis l'UI. Seules actions autorisées : kill / resume executor.
- **Minimal et précis** : tables + indicateurs simples, pas de charts complexes.

## Pages implémentées (7)

| Route | Fichier | Description |
|---|---|---|
| `/` | `Opportunities.tsx` | Table des opps PENDING + récentes, update SSE + polling 5s |
| `/book` | `Book.tsx` | Carnets d'ordres live par exchange |
| `/trades` | `Trades.tsx` | Historique des trades, filtres mode/status, pagination |
| `/history` | `History.tsx` | Historique des opportunités : + lifetime, decay %, samples, `live_status` ; lignes cliquables → détail |
| `/opportunites/:id` | `opportunities/Detail.tsx` | Évolution d'une opp 1:1 : courbe de profit net + slider + chart de convergence bid/ask (recharts) + table des deltas |
| `/structured/live` | `structured/Live.tsx` | Table box spreads `LIVE` (même chrome que Opportunités/Live via `ui/PageToolbar`), colonnes strikes/venues/entry/edge/profit/pts, tri serveur, clic → détail (4 jambes) |
| `/structured/historique` | `structured/History.tsx` | Table des opportunités structurées passées : lifetime, peak vs dernier profit, decay %, samples, `live_status` ; clic → détail |
| `/structured/:id` | `structured/Detail.tsx` | Évolution d'une opportunité : courbe de decay + slider temporel + diagramme de payoff des 2 spreads (recharts) + table des deltas |
| `/positions` | `Positions.tsx` | État par exchange : balance, positions ouvertes, WS status |
| `/executor` | `Executor.tsx` | État executor + kill-switches + boutons Kill/Resume |
| `/funding` | `Funding.tsx` | Données de funding rates |

## Composants partagés

- `Layout.tsx` — sidebar + navigation
- `StatusBadge.tsx` — badges status colorés
- `ConfirmModal.tsx` — modale de confirmation (Kill/Resume)
- `ui/PageToolbar.tsx` — barre compteur + filtres, partagée par les pages liste ; le titre de section vit dans le layout (`OpportunitiesLayout`, `StructuredLayout`)

## Contract API consommé

| Endpoint | Méthode | Usage |
|---|---|---|
| `/api/opportunities?status=&live_status=&days=&min_apr=&sort_by=&limit=` | GET | Opportunities.tsx, History.tsx |
| `/api/opportunities/:id` | GET | opportunities/Detail.tsx |
| `/api/opportunities/:id/snapshots` | GET | opportunities/Detail.tsx (série d'évolution) |
| `/api/structured-opportunities?live_status=&days=&min_profit_usd=&cross_exchange_only=&exclude_settlement_risk=&sort_by=&limit=` | GET | structured/Live.tsx, structured/History.tsx |
| `/api/structured-opportunities/:id` | GET | structured/Detail.tsx |
| `/api/structured-opportunities/:id/snapshots` | GET | structured/Detail.tsx (série d'évolution) |
| `/api/trades?mode=&status=&limit=&offset=` | GET | Trades.tsx |
| `/api/trades/:id` | GET | Détail trade + orders |
| `/api/positions` | GET | Positions.tsx |
| `/api/exchanges` | GET | Positions.tsx (WS/REST status) |
| `/api/executor/state` | GET | Executor.tsx |
| `/api/executor/kill` | POST | Executor.tsx (bouton Kill) |
| `/api/executor/resume` | POST | Executor.tsx (bouton Resume) |
| `/api/perp-hedge/state` | GET | état hedger BTC-PERP (enabled, paused, config) |
| `/api/perp-hedge/pause` | POST | pause le hedger (crée kill switch file) |
| `/api/perp-hedge/resume` | POST | reprend le hedger (supprime kill switch file) |
| `/api/alerts?level=&limit=` | GET | Executor.tsx (alertes récentes) |
| `/api/stream` | GET (SSE) | Push events temps réel |
| `/health` | GET | StatusBadge, monitoring |

## Events SSE consommés

`opportunity_detected`, `trade_opened`, `trade_filled`, `trade_failed`, `trade_stuck`, `kill_switch_tripped`, `position_expiring`, `balance_low`, `exchange_unhealthy`, `perp_hedge_rebalanced`, `structured_opportunity_detected`.
