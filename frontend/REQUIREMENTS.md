# Frontend — état actuel

Le frontend est implémenté. Stack : **Vite + React 19 + TypeScript + TanStack Query + React Router DOM + Tailwind CSS**.

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
| `/history` | `History.tsx` | Historique des opportunités |
| `/positions` | `Positions.tsx` | État par exchange : balance, positions ouvertes, WS status |
| `/executor` | `Executor.tsx` | État executor + kill-switches + boutons Kill/Resume |
| `/funding` | `Funding.tsx` | Données de funding rates |

## Composants partagés

- `Layout.tsx` — sidebar + navigation
- `StatusBadge.tsx` — badges status colorés
- `ConfirmModal.tsx` — modale de confirmation (Kill/Resume)

## Contract API consommé

| Endpoint | Méthode | Usage |
|---|---|---|
| `/api/opportunities?status=&min_apr=&limit=` | GET | Opportunities.tsx, History.tsx |
| `/api/opportunities/:id` | GET | Détail opp |
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

`opportunity_detected`, `trade_opened`, `trade_filled`, `trade_failed`, `trade_stuck`, `kill_switch_tripped`, `position_expiring`, `balance_low`, `exchange_unhealthy`, `perp_hedge_rebalanced`.
