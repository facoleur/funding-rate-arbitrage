# Structured Arbitrage — Architecture d'implémentation

Stratégies multi-jambes à payoff fixé ou borné, sans hedge dynamique. Profit locké à l'entrée si tenu jusqu'à expiry.

---

## État d'implémentation

- **Box spread — LIVRÉ (Phase 1 + 2).** Module `backend/src/option_arb/structured/` (types + `strategies/box.py` + `screener.py`), tables `structured_opportunities` + `structured_opportunity_snapshots` (migrations `3a975f04ade8`, `ccd09cc5a4d8`), API `GET /api/structured-opportunities` (+ `/{id}`, `/{id}/snapshots`), **page frontend autonome `/structured`** (onglets Live / Historique + vue détail `/structured/:id`). Détecteur branché dans `worker.py` derrière `structured.enabled` (config `structured:`, **off par défaut**).
- **Vertical credit / butterfly négatif — pas encore.** L'enum `StrategyType` et le dossier `strategies/` sont prévus pour les accueillir sans refonte.

Écarts vs le design initial ci-dessous :
- **Best-venue par jambe** au lieu d'énumérer les combos d'exchanges : pour chaque paire `(K1, K2)`, chaque jambe prend le meilleur prix dispo toutes venues confondues (min ask / max bid), comme `comparator.compare_options`. O(N² · V) au lieu de O(N² · V⁴), et c'est l'optimum du coût d'entrée.
- **`sa.JSON`** pour `strikes` / `legs` (pas `JSONB` / `FLOAT[]`) → même modèle sous SQLite en pytest.
- Pas encore de champ `min_profit` / `max_profit` distincts pour le box (payoff déterministe → `min == max`).

## Cycle de vie & snapshots (Phase 2)

> **Uniformisé** : le statut de liveness s'appelle `live_status` et utilise l'enum partagé
> `LiveStatus = LIVE | STALE | EXPIRED` (`db/models.py`) — le même sur `opportunities`
> (où il est orthogonal au `status` workflow de l'executor) et `structured_opportunities`
> (où c'est le seul statut). La gate de snapshot est le helper partagé
> `services/snapshots.py::should_snapshot`.


- **Identité d'une opportunité** = `(strategy_type, underlying, expiry, strikes)`. Le mix de venues gagnantes n'entre PAS dans la clé : il évolue et est capturé dans les snapshots.
- **Statuts** (`live_status`) : `LIVE` (détectée au dernier tick) → `STALE` (`close_reason="stale"`, plus vue depuis `close_after_stale_sec`, défaut 30 s) ou `EXPIRED` (`close_reason="expired"`, `expiry` passée). Balayage à chaque tick du screener (2 `UPDATE` groupés, `synchronize_session=False`).
- **Colonnes lifecycle** sur `structured_opportunities` : `detected_at` (= first seen), `last_seen_at`, `samples_count`, `peak_total_profit_usd`, `peak_min_profit`, `spot`, `closed_at`, `close_reason`, `last_snapshot_at`, `last_snapshot_total_profit_usd`.
- **Table `structured_opportunity_snapshots`** : série temporelle `(opportunity_id FK ON DELETE CASCADE, ts, entry_cost, max_fees, min_profit, max_size, capital_required_usd, max_total_profit_usd, legs JSON, underlying_price)`.
- **Cadence de snapshot** (`_should_snapshot`) : un snapshot à la détection, puis un nouveau seulement si `now - last_snapshot_at ≥ snapshot_min_interval_sec` (défaut 10) **ou** `|Δ max_total_profit_usd| ≥ snapshot_edge_delta_usd` (défaut 1) **ou** le mix de venues a changé.
- **Rétention** (`worker.py::_retention_loop`, quotidien) : snapshots `> snapshot_retention_days` (défaut 30) ; lignes parentes `STALE`/`EXPIRED` `> retention_days` (défaut 14), snapshots en cascade.
- **API** : `GET /api/structured-opportunities` accepte `live_status` (défaut = tous), `days`, tris `detected_at`/`last_seen_at`/`peak_total_profit_usd`/`samples_count`/… ; réponse enrichie de `lifetime_sec` + `decay_pct` (computed). `GET /api/structured-opportunities/{id}/snapshots` → série triée par `ts`.
- **Frontend détail** (`pages/structured/Detail.tsx`, **recharts**) : courbe de decay (`max_total_profit_usd` dans le temps), slider temporel qui sélectionne un snapshot, diagramme de payoff des 2 spreads (`payoff.ts::payoffSeries` — bull call `clamp(S−K1,0,W)−Dc`, bear put `clamp(K2−S,0,W)−Dp`, box plat `W−entry_cost−fees`) + marqueur spot, table des deltas snapshot-à-snapshot.

---

## Taxonomie des stratégies

### Payoff vraiment fixé (déterministe à expiry, ∀ S_T)

**Box spread** — la seule structure à payoff garanti:
- `Long C(K1) + Short P(K1) + Short C(K2) + Long P(K2)` avec K1 < K2
- Payoff = toujours exactement `K2 - K1`, quelle que soit S_T
- Arb si `entry_cost + fees < K2 - K1`
- Peut être décomposé en bull call spread + bear put spread, chaque paire sur des exchanges différents

### Payoff borné, profit max connu à l'entrée (pas de rebalancing)

**Vertical credit arb** — arb garanti si entry est un crédit:
- Bull call spread cross-exchange: `ask(C(K1))@A < bid(C(K2))@B` → crédit reçu, payoff min = 0 → profit = crédit
- Bear put spread cross-exchange: `ask(P(K2))@A < bid(P(K1))@B` → même logique

**Butterfly négatif** — arb si les wings sont sous-évaluées vs le centre:
- `bid(C(K1)) + bid(C(K3)) - 2 × ask(C(K2)) > fees` → crédit reçu > 0, profit garanti
- Équivalent: vendre le "hump" si le marché le paye trop cher

---

## Le piège capital: settlement cross-exchange

**Deribit inverse** (settled en BTC) vs **Derive linear** (settled on-chain USDC) = un box spread cross-exchange N'EST PAS à payoff fixé en USD — il reste un risque BTC/USD résiduel.

Règles:
- Box intra-exchange (tout sur Deribit ou tout sur Derive) → payoff fixé propre
- Box cross-exchange Deribit/Derive → flagger `settlement_risk = True`, afficher l'exposition résiduelle
- Verticals cross-exchange sont propres car chaque jambe est auto-contenue (une seule option)

---

## Algorithme de détection

### Grouping

```
BookCache → group par (underlying, expiry)
              └── pour chaque groupe: map {(exchange, strike, option_type) → CachedTicker}
```

### Box spread — O(N²) paires de strikes

Pour chaque paire `(K1, K2)` avec K1 < K2:
1. Chercher toutes les combinaisons d'exchanges pour les 4 jambes
2. Calculer `entry_cost = ask(C(K1)) + ask(P(K2)) - bid(C(K2)) - bid(P(K1))`
3. Si `entry_cost + fees < K2 - K1` → opportunité
4. `max_size = min(ask_qty(C(K1)), ask_qty(P(K2)), bid_qty(C(K2)), bid_qty(P(K1)))`

Pour 50 strikes BTC → ~1225 paires → rapide.

### Vertical credit — O(N²) paires

Pour chaque paire `(K1, K2)` et chaque type `C` ou `P`:
- Bull call: pour chaque combo `(exA, exB)`: `ask(C(K1))@A - bid(C(K2))@B < 0`
- Bear put: pour chaque combo `(exA, exB)`: `ask(P(K2))@A - bid(P(K1))@B < 0`

### Butterfly négatif — O(N³) triples, filtrage nécessaire

Pré-filtre: ne checker que les triples "équilibrés" (`K3-K2 = K2-K1`, i.e. multiples du step standard de strikes). Pour BTC steps de 1000/2000 USD → réduit drastiquement.

Condition: `bid(C(K1)) + bid(C(K3)) > 2 × ask(C(K2)) + fees`

**Optimisation globale**: mid-price check d'abord, bid/ask seulement pour les candidats positifs.

---

## Architecture module

```
backend/src/option_arb/
├── structured/
│   ├── __init__.py
│   ├── types.py           # StrategyType enum, Leg dataclass, StructuredOpportunity
│   ├── screener.py        # boucle 1s, lit BookCache, orchestre les détecteurs
│   ├── strategies/
│   │   ├── box.py         # BoxDetector
│   │   ├── vertical.py    # VerticalDetector (bull call + bear put)
│   │   └── butterfly.py   # ButterflyDetector
│   └── models.py          # SQLModel StructuredOpportunity
├── api/
│   └── structured.py      # GET /api/structured-opportunities
```

- Lancé dans le container `workers` à côté du `Screener` existant — même `BookCache`, pas de duplication réseau
- **Aucune modification du screener 1-1 existant**
- Table séparée `structured_opportunities` dans Postgres

---

## Schema DB — table `structured_opportunities`

```sql
CREATE TABLE structured_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identité de la structure
    strategy_type   VARCHAR(32)   NOT NULL,  -- BOX | BULL_CALL | BEAR_PUT | BUTTERFLY_NEG
    underlying      VARCHAR(16)   NOT NULL,
    expiry          TIMESTAMPTZ   NOT NULL,
    strikes         FLOAT[]       NOT NULL,  -- [K1, K2] ou [K1, K2, K3]

    -- Jambes (snapshot au moment de la détection)
    -- [{exchange, instrument, side: buy|sell, price: ask ou bid, qty}]
    legs            JSONB         NOT NULL,

    -- Payoff
    is_fixed_payoff BOOLEAN       NOT NULL,  -- True seulement pour BOX intra-exchange
    min_payoff      FLOAT         NOT NULL,  -- pire cas à expiry (0 pour vertical, K2-K1 pour box)
    max_payoff      FLOAT         NOT NULL,

    -- Coût d'entrée (par unité d'underlying)
    entry_cost      FLOAT         NOT NULL,  -- net premium (négatif = crédit reçu)
    max_fees        FLOAT         NOT NULL,

    -- Edge (par unité)
    min_profit      FLOAT         NOT NULL,  -- min_payoff - entry_cost - max_fees
    max_profit      FLOAT         NOT NULL,

    -- Taille
    max_size        FLOAT         NOT NULL,  -- limité par la jambe la moins liquide
    capital_required FLOAT        NOT NULL,  -- entry_cost * max_size (si négatif = crédit)
    max_total_profit FLOAT        NOT NULL,  -- min_profit * max_size

    -- Risque
    settlement_risk BOOLEAN       NOT NULL DEFAULT false,  -- True si exchanges à settlement différent

    -- Metadata
    mode            VARCHAR(16)   NOT NULL,
    detected_at     TIMESTAMPTZ   NOT NULL,
    updated_at      TIMESTAMPTZ   NOT NULL,
    status          VARCHAR(16)   NOT NULL DEFAULT 'OPEN'  -- OPEN | EXPIRED
);

CREATE INDEX ON structured_opportunities (status, detected_at DESC);
CREATE INDEX ON structured_opportunities (underlying, expiry, strategy_type);
```

Dédup: upsert sur `(strategy_type, underlying, expiry, strikes, legs exchanges+instruments)` — update prix si status = OPEN.

---

## API

`GET /api/structured-opportunities`

Query params:
- `strategy_type` (optionnel)
- `underlying` (optionnel)
- `min_profit_usd` (optionnel)
- `cross_exchange_only` bool (optionnel)
- `exclude_settlement_risk` bool (optionnel)
- `limit` (défaut 50)

Response: liste de `StructuredOpportunityRead` avec toutes les jambes.

---

## Frontend — page "Structured"

Nouvelle page `StructuredOpportunities.tsx`, route `/structured`.

### Card par opportunité

```
┌ BOX SPREAD — BTC 28 Mar 2025 ──────────────────── payoff fixé ┐
│ K1: 60,000   K2: 70,000   Payoff: $10,000 / unité             │
│                                                                 │
│  BUY  BTC-20250328-60000-C  Deribit  ask $2,100  liq: 5.0 BTC │
│  SELL BTC-20250328-70000-C  Deribit  bid  $800   liq: 8.0 BTC │
│  BUY  BTC-20250328-70000-P  Derive   ask $8,200  liq: 3.0 BTC │
│  SELL BTC-20250328-60000-P  Derive   bid  $350   liq: 6.0 BTC │
│                                                                 │
│  Taille max: 3.0 BTC   Capital: $29,250   Profit: $750 (2.6%) │
│  ⚠ Settlement risk: Deribit USDC ≠ Derive on-chain            │
└────────────────────────────────────────────────────────────────┘
```

### Colonnes de tri / filtres UI

- Filtres: stratégie, underlying, profit min USD, intra/cross exchange, exclure settlement_risk
- Tri: profit total, profit %, taille max, détecté à
- Badge couleur: vert = payoff fixé, jaune = payoff borné conditionnel, orange = settlement_risk

---

## Ordre d'implémentation suggéré

1. `structured/types.py` + `structured/models.py` + migration Alembic
2. `strategies/box.py` (la plus valuable — payoff fixé, logique claire)
3. `strategies/vertical.py`
4. `strategies/butterfly.py`
5. `structured/screener.py` — brancher sur le `BookCache` existant, lancer dans `worker.py`
6. `api/structured.py` + wiring dans `main.py`
7. Frontend `StructuredOpportunities.tsx`

---

## Ce qui est hors scope pour cette phase

- Execution multi-jambes (4 IOC en parallèle avec rollback partiel)
- Aevo (WebSocket public agrégé `book-ticker` + `index`; trading privé non implémenté)
- Calendar spreads (2 expiries différentes) — possible à ajouter dans `strategies/calendar.py`
- Iron condor (4-jambe borné, extension naturelle de vertical + vertical)
