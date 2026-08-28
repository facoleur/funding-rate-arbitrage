# Capital and margin economics

The former implementation plan in this file has been completed and superseded by the canonical calculator in `backend/src/option_arb/economics.py`.

For a common underlying/contract quantity `q`:

```text
buy_premium_usd = buy_price * q
sell_premium_usd = sell_price * q
gross_profit_usd = sell_premium_usd - buy_premium_usd
fees_usd = buy_premium_usd * buy_taker_fee_rate
         + sell_premium_usd * sell_taker_fee_rate
net_profit_usd = gross_profit_usd - fees_usd
estimated_short_margin_usd = sell_margin_per_unit(spot, strike, option_type) * q
capital_required_usd = estimated_short_margin_usd + buy_premium_usd
net_return_pct = net_profit_usd / capital_required_usd * 100
apr_pct = net_return_pct * 365 / days_to_expiry
```

The sell premium never offsets required capital. Missing or invalid spot, prices, quantity, capital, or nonpositive DTE produces no economics or APR.

The screener and Book endpoint use current top-of-book prices. Executor approval uses fresh worst IOC prices after walking the books:

```text
buy_limit = walked_ask * (1 + ioc_slippage_limit_pct / 100)
sell_limit = walked_bid * (1 - ioc_slippage_limit_pct / 100)
```

Top-of-book totals remain on the opportunity. Fresh approval totals are persisted separately under `verified_*` fields so the two economic snapshots cannot be conflated.

The short-margin formula remains a standalone estimate. Exchange-specific portfolio margin previews are deliberately out of scope.
