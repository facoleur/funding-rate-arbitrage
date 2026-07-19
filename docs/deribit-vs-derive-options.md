# Deribit vs Derive — Différences options & risques pour le bot

## 1. Cotation des prix — piège #1

**Deribit** cote les options **en fraction de l'underlying** (BTC, ETH…), pas en USD.
- `best_bid_price = 0.025` sur `BTC-20251025-30000-C` = `0.025 × underlying_price` USD.
- L'adapter corrige ça (`Decimal(str(p)) * underlying_px`) — mais si un message WS arrive sans `underlying_price` (reconnexion partielle), `parse_ws_message` retourne `None` et le book_cache garde l'ancienne valeur.
- En cas de move rapide du spot, on peut comparer un prix Deribit stale contre un prix Derive frais → **spread fantôme**.

**Derive** cote directement **en USD**. Pas de conversion nécessaire.

---

## 2. Unité de taille / contrat

**Deribit** : `amount` = nombre de contrats, 1 contrat = 1 BTC (ou 1 ETH). Minimum 0.1 pour BTC options. La taille est en underlying, pas en notionnel USD.

**Derive** : taille directement en unité d'underlying (ex: 0.01 ETH minimum).

**Risque** : l'executor envoie `float(order.size)` sans vérifier `min_amount` ni `tick_size`. Si la taille calculée est sous le minimum, Deribit peut retourner `order_state = cancelled` (pas une erreur JSON explicite). `_parse_order_response` mappe ça en `CANCELLED` mais le hedge leg peut quand même partir si le premier retourne `PARTIAL`.

---

## 3. Settlement à l'expiry

**Deribit** : settlement **cash automatique en USDC** — règlement à l'index Deribit BTC-USD à 08:00 UTC le jour d'expiration. Rien à faire.

**Derive** : settlement **on-chain via smart contract** (OP Stack, chain_id 957 mainnet). Les positions non fermées avant expiry nécessitent une tx blockchain pour être exercées.

**Risque** : si le bot se retrouve STUCK sur une jambe Derive proche de l'expiry, la position peut expirer worthless faute de tx. Sur Deribit le cash settlement est automatique. Perte maximale asymétrique dans ce cas rare.

---

## 4. Auth et signing — source de latence

**Deribit** : OAuth2 standard, token mis en cache ~1h. Pas de signing par ordre. Latence d'auth = 0 après le premier token.

**Derive** : double signing par ordre —
1. Headers `X-LYRA*` signés avec l'heure UTC (timestamp en ms, expiration implicite ~30s côté serveur)
2. `sign_trade_action()` EIP-712 avec nonce unique et `signature_expiry_sec`

**Risque** : si la clock du VPS dérive de >30s, les headers `X-LYRATIMESTAMP` seront rejetés. À monitorer. Le signing lui-même est ~2-5ms (ECDSA Python), pas un goulot d'étranglement.

---

## 5. Nommage des instruments

**Deribit** : format natif `BTC-25OCT25-30000-C` → `normalize_deribit()` convertit en `BTC-20251025-30000-C`. Conversion correcte.

**Derive** : instrument_name déjà en format canonique `ETH-20251025-3000-C`. Pas de conversion.

**Risque** : les strikes Derive peuvent être décimaux (`3000.5`), ceux Deribit sont toujours entiers. `normalize_from_parts` gère ça, mais le matching cross-venue peut rater si un strike est `3000` chez l'un et `3000.0` chez l'autre (comparaison de strings).

---

## 6. Liquidité et book depth

**Deribit** : carnet profond, market makers actifs, spreads serrés sur BTC/ETH. `depth=20` fiable via REST et WS 100ms.

**Derive** : beaucoup moins liquide — souvent 1-2 niveaux dans le carnet. Fallback depth-1 déjà en place dans l'adapter. La latence entre screener et executor peut suffire pour que l'opportunité disparaisse. **Taux de faux positifs élevé côté Derive.**

---

## Récap des risques prioritaires

| Risque | Composant | Priorité |
|--------|-----------|----------|
| Prix Deribit stale si `underlying_price` absent du WS | `deribit.py:parse_ws_message` | Haute |
| Pas de vérification `min_amount` avant envoi ordre | executor / `OrderRequest` | Haute |
| Settlement on-chain Derive si STUCK proche expiry | executor / alerter | Moyenne |
| Strike decimal mismatch au matching cross-venue | `naming.py` | Moyenne |
| Clock drift VPS → `X-LYRATIMESTAMP` rejeté | `derive_auth.py:sign_rest` | Basse |
| Liquidité Derive faible = faux positifs screener | screener | Info |
