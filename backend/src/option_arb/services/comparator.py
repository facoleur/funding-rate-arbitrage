from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Quote:
    """Cross-venue comparable option quote. All prices in USD (quote currency)."""

    exchange: str
    normalized_name: str
    instrument_name: str
    underlying: str
    strike: Decimal
    option_type: str  # "C" | "P"
    expiry: datetime
    taker_fee_rate: Decimal  # fraction, e.g. 0.0003

    bid_price: Decimal
    bid_qty: Decimal
    ask_price: Decimal
    ask_qty: Decimal

    # Used for sell-leg margin calculation. None → fallback to premium-only denominator.
    underlying_price: Decimal | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Spread:
    normalized_name: str
    symbol: str  # underlying, e.g. "BTC"
    instrument: str  # same as normalized_name for now
    strike: Decimal
    option_type: str
    expiry: datetime
    days_to_expiry: float

    buy_from: str
    sell_to: str
    buy_ask: Decimal
    sell_bid: Decimal

    fee_pct: Decimal  # fees as % of capital_deployed (per unit)
    net_spread_pct: Decimal  # net profit as % of capital_deployed (per unit)
    apr_pct: Decimal
    max_notional_usd: Decimal
    capital_deployed_usd: Decimal  # capital per contract (buy premium + net sell margin)
    net_profit_usd: Decimal  # total absolute profit = per_unit x qty_traded


def group_by_instrument(quotes: list[Quote]) -> dict[str, list[Quote]]:
    """Group cross-venue quotes by their normalized instrument name."""
    grouped: dict[str, list[Quote]] = defaultdict(list)
    for q in quotes:
        grouped[q.normalized_name].append(q)
    return grouped


def _is_valid(q: Quote) -> bool:
    return q.bid_price > 0 and q.ask_price > 0 and q.bid_qty > 0 and q.ask_qty > 0


def sell_margin_per_unit(spot: Decimal, strike: Decimal, option_type: str) -> Decimal:
    """Net capital locked on the short leg (Deribit-style formula, same for all exchanges).

    IM = max(0.15 - OTM_fraction, 0.10) x spot
    Premium received offsets mark_price, so only the base rate x spot is truly locked."""
    if option_type == "C":
        otm_fraction = max(Decimal(0), (strike - spot) / spot)
    else:
        otm_fraction = max(Decimal(0), (spot - strike) / spot)
    base_rate = max(Decimal("0.15") - otm_fraction, Decimal("0.10"))
    return base_rate * spot


def _get_margin(quote: Quote, spot_override: Decimal | None = None) -> Decimal | None:
    spot = spot_override or quote.underlying_price
    if spot is None or spot <= 0:
        return None
    return sell_margin_per_unit(spot, quote.strike, quote.option_type)


def compare_options(
    groups: list[list[Quote]],
    *,
    size_threshold_usd: Decimal = Decimal("100"),
    now: datetime | None = None,
) -> list[Spread]:
    """For each group of cross-venue quotes for the same instrument, find
    the best buy (lowest ask on exchange A) and best sell (highest bid on
    exchange B) across DIFFERENT exchanges.

    Capital deployed = buy_premium + net_sell_margin, where net_sell_margin is
    the margin required for the short leg minus the premium received (since all
    exchanges credit premium immediately on fill). When underlying_price is
    unavailable, falls back to using only the buy premium as denominator."""
    now = now or datetime.now(UTC)
    results: list[Spread] = []

    for quotes in groups:
        if len(quotes) < 2:
            continue

        names = {q.normalized_name for q in quotes}
        if len(names) > 1:
            raise ValueError(f"mismatched instruments in group: {sorted(names)}")

        valid = [q for q in quotes if _is_valid(q)]
        valid = [q for q in valid if q.bid_price * q.bid_qty >= size_threshold_usd]
        if len(valid) < 2:
            continue

        lowest_ask = min(valid, key=lambda q: q.ask_price)
        highest_bid = max(valid, key=lambda q: q.bid_price)

        if lowest_ask.exchange == highest_bid.exchange:
            continue

        # Fees in USD: each leg pays taker_fee x premium on that leg
        fees_usd = (
            lowest_ask.taker_fee_rate * lowest_ask.ask_price
            + highest_bid.taker_fee_rate * highest_bid.bid_price
        )
        net_profit_per_unit = highest_bid.bid_price - lowest_ask.ask_price - fees_usd

        if net_profit_per_unit <= 0:
            continue

        # capital_deployed: sell margin only (binding capital constraint).
        # Both legs fill simultaneously; buy premium is immediately offset by sell premium
        # received. Only the margin locked on the short leg is truly committed capital.
        # Spot comes from whichever leg has it — Deribit always provides it.
        spot = highest_bid.underlying_price or lowest_ask.underlying_price
        sell_margin = _get_margin(highest_bid, spot_override=spot)
        if sell_margin is None:
            continue  # no spot price available — can't compute margin, skip
        capital_deployed = sell_margin

        fee_pct = fees_usd / capital_deployed * Decimal(100)
        net_spread_pct = net_profit_per_unit / capital_deployed * Decimal(100)

        if net_spread_pct <= 0:
            continue

        q0 = quotes[0]
        expiry_utc = q0.expiry if q0.expiry.tzinfo else q0.expiry.replace(tzinfo=UTC)
        days_to_exp = max((expiry_utc - now).total_seconds() / 86400.0, 1e-6)
        apr = (net_spread_pct / Decimal(str(days_to_exp))) * Decimal(365)

        ask_notional = lowest_ask.ask_qty * lowest_ask.ask_price
        bid_notional = highest_bid.bid_qty * highest_bid.bid_price
        max_notional = min(ask_notional, bid_notional)
        qty_traded = lowest_ask.ask_qty if ask_notional <= bid_notional else highest_bid.bid_qty
        net_profit_total = net_profit_per_unit * qty_traded

        results.append(
            Spread(
                normalized_name=q0.normalized_name,
                symbol=q0.underlying,
                instrument=q0.normalized_name,
                strike=q0.strike,
                option_type=q0.option_type,
                expiry=expiry_utc,
                days_to_expiry=days_to_exp,
                buy_from=lowest_ask.exchange,
                sell_to=highest_bid.exchange,
                buy_ask=lowest_ask.ask_price,
                sell_bid=highest_bid.bid_price,
                fee_pct=fee_pct,
                net_spread_pct=net_spread_pct,
                apr_pct=apr,
                max_notional_usd=max_notional,
                capital_deployed_usd=capital_deployed,
                net_profit_usd=net_profit_total,
            )
        )

    return results
