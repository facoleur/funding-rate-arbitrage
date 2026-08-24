# Structured Arbitrage — Architecture d'implémentation

Stratégies multi-jambes à payoff fixé ou borné, sans hedge dynamique. Profit locké à l'entrée si tenu jusqu'à expiry.

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
- Aevo (pas de WS → hors screener, REST polling trop coûteux pour multi-leg)
- Calendar spreads (2 expiries différentes) — possible à ajouter dans `strategies/calendar.py`
- Iron condor (4-jambe borné, extension naturelle de vertical + vertical)
