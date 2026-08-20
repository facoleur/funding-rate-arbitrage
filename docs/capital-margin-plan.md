# Capital réel & calcul de marge — Plan d'implémentation

## Problème

L'APR affiché est faussé : le système divise le profit par le `buy_premium` uniquement, en ignorant la marge initiale requise pour le **short leg** (leg sell). Sur Deribit, la marge initiale d'un short call est :

```
marge ≈ max(0.10 × spot × qty − OTM_amount, 0.075 × spot × qty)
```

Pour une option ATM, la marge est typiquement **3–10× la prime**. L'APR réel peut donc être **5–10× inférieur** à l'APR affiché.

Problème secondaire : l'executor ne vérifie pas les fonds disponibles sur l'exchange sell avant d'ordrer. Avec plusieurs trades simultanés, on peut dépasser la capacité réelle sans s'en rendre compte.

---

## Phase A — APR corrigé par la marge estimée

### A1. `Quote` dataclass → ajouter `underlying_price`

**Fichier** : `backend/src/option_arb/services/comparator.py`

```python
@dataclass(frozen=True)
class Quote:
    ...
    underlying_price: Decimal | None = None  # spot BTC/ETH price en USD
```

### A2. Screener → passer `underlying_price` dans Quote

**Fichier** : `backend/src/option_arb/services/screener.py`

Dans `_cached_to_quote()` :
```python
underlying_price=t.underlying_price,
```
(`CachedTicker.underlying_price` existe déjà.)

### A3. `ExchangeConfig` → ajouter `option_margin_ratio`

**Fichier** : `backend/src/option_arb/config.py`

```python
class ExchangeConfig(BaseModel):
    ...
    option_margin_ratio: float = 0.10  # fraction du spot × qty → marge estimée sell leg
```

Valeurs recommandées par défaut :
- Deribit inverse / linear : `0.10`
- Derive : `0.12`
- Aevo : `0.10`

### A4. Comparator → estimation marge + nouveaux champs dans `Spread`

**Fichier** : `backend/src/option_arb/services/comparator.py`

Ajouter dans le dataclass `Spread` :
```python
estimated_sell_margin_usd: Decimal   # marge initiale estimée du short leg
capital_required_usd: Decimal        # buy_ask_notional + estimated_sell_margin_usd
capital_apr_pct: Decimal             # profit / capital_required × 365 / days
```

Nouvelle fonction :
```python
def estimate_sell_margin(quote: Quote, qty: Decimal, margin_ratio: float) -> Decimal:
    """Formule Deribit si underlying_price disponible, sinon ratio × premium."""
    if quote.underlying_price and quote.underlying_price > 0:
        spot = quote.underlying_price
        if quote.option_type == "C":
            otm = max(Decimal(0), spot - quote.strike)
        else:
            otm = max(Decimal(0), quote.strike - spot)
        margin = max(
            Decimal("0.10") * spot * qty - otm * qty,
            Decimal("0.075") * spot * qty,
        )
        return max(margin, Decimal(0))
    # fallback : ratio × premium notional
    return quote.bid_price * qty * Decimal(str(1 + margin_ratio))
```

`compare_options()` reçoit un nouveau paramètre `exchange_margin_ratios: dict[str, float]`.

**Capital requis** :
```
capital_required = buy_ask × walked_size + estimated_sell_margin
capital_apr = (profit / capital_required) × (365 / days_to_expiry)
```

### A5. `Opportunity` → 3 nouveaux champs DB

**Fichier** : `backend/src/option_arb/db/models.py`

```python
class Opportunity(SQLModel, table=True):
    ...
    estimated_sell_margin_usd: float | None = None
    capital_required_usd: float | None = None
    capital_apr_pct: float | None = None
```

### A6. Migration Alembic

```bash
make migrate-new msg="add_capital_fields_to_opportunities"
```

### A7. Screener → passer les ratios au comparateur + écrire les nouveaux champs

**Fichier** : `backend/src/option_arb/services/screener.py`

```python
exchange_margin_ratios = {
    name: cfg.option_margin_ratio
    for name, cfg in self.config.exchanges.items()
}
spreads = compare_options(
    groups,
    size_threshold_usd=...,
    exchange_margin_ratios=exchange_margin_ratios,
)
```

Dans la création d'`Opportunity`, ajouter :
```python
estimated_sell_margin_usd=float(s.estimated_sell_margin_usd),
capital_required_usd=float(s.capital_required_usd),
capital_apr_pct=float(s.capital_apr_pct),
```

### A8. Frontend : afficher `capital_apr_pct`

- `api/tickers.py` : exposer `capital_apr_pct` dans `BookRow`
- `Book.tsx` : nouvelle colonne **"Cap.APR"** à côté de "Net%"
- Tooltip : "APR basé sur capital réel (prime achat + marge vente estimée)"

---

## Phase B — Vérification capital disponible pre-trade

### B1. `AbstractExchange` → `get_available_funds()` non-abstraite

**Fichier** : `backend/src/option_arb/exchanges/base.py`

```python
async def get_available_funds(self) -> dict[str, Decimal]:
    """Fonds disponibles pour nouvelles positions. Default: {} (no-op)."""
    return {}
```

Non-abstraite → ne casse aucune implémentation existante.

### B2. `DeribitExchange` → implémenter `get_available_funds()`

**Fichier** : `backend/src/option_arb/exchanges/deribit.py`

Extraire `available_funds` de `private/get_account_summary` (même endpoint que `get_balances()`).

```python
async def get_available_funds(self) -> dict[str, Decimal]:
    if isinstance(self.auth, NoAuth):
        return {}
    currencies = ["USDC"] if self._linear else ["BTC", "ETH"]
    out: dict[str, Decimal] = {}
    for currency in currencies:
        try:
            res = await self._rpc("private/get_account_summary", {"currency": currency})
            out[currency] = Decimal(str(res.get("available_funds", 0)))
        except Exception as e:
            log.warning("get_available_funds(%s) failed: %s", currency, e)
    return out
```

Pour l'inverse (BTC/ETH), les fonds sont en crypto → multiplier par l'index price pour avoir l'équivalent USD dans le check executor.

### B3. `MockExchange` → déléguer à upstream

**Fichier** : `backend/src/option_arb/exchanges/mock.py`

```python
async def get_available_funds(self) -> dict[str, Decimal]:
    if self.upstream is not None:
        return await self.upstream.get_available_funds()
    return {}
```

### B4. `Limits` → `min_available_funds_usd`

**Fichier** : `backend/src/option_arb/config.py`

```python
class Limits(BaseModel):
    ...
    min_available_funds_usd: float = 50.0  # buffer minimum à maintenir sur chaque exchange
```

### B5. Executor → check capital pre-trade

**Fichier** : `backend/src/option_arb/services/executor.py`

Dans `_process()`, après le check `trade_enabled`, avant le L2 refetch :

```python
# Vérifier les fonds disponibles sur l'exchange sell
sell_funds = await sell_ex.get_available_funds()
sell_funds_usd = _funds_to_usd(sell_funds, opp.sell_to)
if sell_funds_usd < Decimal(str(self.config.limits.min_available_funds_usd)):
    await self._reject(opp, f"insufficient_funds({opp.sell_to}:{sell_funds_usd:.0f}$)")
    return
```

Helper `_funds_to_usd()` : pour les exchanges inverse, chercher le BTC index price ; pour USDC/linear, somme directe.

### B6. Rebalancer → populer `ExchangeState.margin_used_usd`

**Fichier** : `backend/src/option_arb/services/rebalancer.py`

Lors du tick, appeler `get_available_funds()` en plus de `get_balances()` :
```python
available = await ex.get_available_funds()
available_usd = _funds_to_usd(available, name)
margin_used_usd = balance_usd - available_usd
# écrire ExchangeState.margin_used_usd = margin_used_usd
```

---

## Fichiers modifiés (résumé)

| Fichier | Phase | Changement |
|---|---|---|
| `services/comparator.py` | A | `underlying_price` dans Quote, `estimate_sell_margin()`, 3 champs dans Spread |
| `services/screener.py` | A | passer `underlying_price`, `exchange_margin_ratios`, écrire nouveaux champs |
| `config.py` | A+B | `option_margin_ratio` dans ExchangeConfig, `min_available_funds_usd` dans Limits |
| `db/models.py` | A | 3 champs sur Opportunity |
| migration | A | `add_capital_fields_to_opportunities` |
| `api/tickers.py` | A | exposer `capital_apr_pct` dans BookRow |
| `frontend/src/pages/Book.tsx` | A | colonne Cap.APR |
| `exchanges/base.py` | B | `get_available_funds()` default `{}` |
| `exchanges/deribit.py` | B | `get_available_funds()` réel |
| `exchanges/mock.py` | B | déléguer à upstream |
| `services/executor.py` | B | check pre-trade sur available_funds |
| `services/rebalancer.py` | B | populer `margin_used_usd` |

## `config.yaml` — ajouts

```yaml
exchanges:
  deribit:
    option_margin_ratio: 0.10
  deribit_linear:
    option_margin_ratio: 0.10
  derive:
    option_margin_ratio: 0.12
  aevo:
    option_margin_ratio: 0.10

limits:
  min_available_funds_usd: 50.0
```

## Vérification

```bash
make test
# 74 tests passent (phases A et B n'affectent pas les tests existants)

# Book frontend :
# → colonne Cap.APR ≠ Net% APR (typiquement 5–10× inférieur)

# Executor logs :
# → "insufficient_funds(deribit:30$)" si balance trop faible avant trade

# /api/status :
# → ExchangeState.margin_used_usd non-nul après premier rebalancer tick
```

---

## Notes importantes

- **Phase A** et **Phase B** sont indépendantes — peuvent être implémentées séparément.
- La formule Deribit est une **estimation** — la vraie marge dépend du portfolio margin de l'exchange. Pour une précision maximale, utiliser `public/get_margin` (endpoint Deribit) au moment de l'exécution.
- Pour Derive, la formule de marge est différente — le `option_margin_ratio` sert de fallback configurable.
- `capital_apr_pct` remplace l'APR comme **métrique de ranking** principale une fois implémenté.
