from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast

from option_arb.economics import calculate_option_economics, days_to_expiry


@dataclass(frozen=True)
class Quote:
    """Cross-venue comparable option quote. All prices are in USD."""

    exchange: str
    normalized_name: str
    instrument_name: str
    underlying: str
    strike: Decimal
    option_type: str
    expiry: datetime
    taker_fee_rate: Decimal
    bid_price: Decimal
    bid_qty: Decimal
    ask_price: Decimal
    ask_qty: Decimal
    underlying_price: Decimal | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Spread:
    normalized_name: str
    symbol: str
    instrument: str
    strike: Decimal
    option_type: str
    expiry: datetime
    days_to_expiry: Decimal
    buy_from: str
    sell_to: str
    buy_ask: Decimal
    sell_bid: Decimal
    tradeable_size: Decimal
    buy_premium_usd: Decimal
    sell_premium_usd: Decimal
    estimated_short_margin_usd: Decimal
    capital_required_usd: Decimal
    gross_profit_usd: Decimal
    fees_usd: Decimal
    net_profit_usd: Decimal
    price_spread_pct: Decimal
    net_return_pct: Decimal
    apr_pct: Decimal


def _is_valid(quote: Quote) -> bool:
    return (
        quote.bid_price.is_finite()
        and quote.ask_price.is_finite()
        and quote.bid_qty.is_finite()
        and quote.ask_qty.is_finite()
        and quote.bid_price > 0
        and quote.ask_price > 0
        and quote.bid_qty > 0
        and quote.ask_qty > 0
    )


def compare_options(
    groups: list[list[Quote]],
    *,
    min_leg_premium_liquidity_usd: Decimal = Decimal("100"),
    now: datetime | None = None,
) -> list[Spread]:
    """Select the lowest ask and highest bid on different venues per instrument."""
    now = now or datetime.now(UTC)
    results: list[Spread] = []

    for quotes in groups:
        if len(quotes) < 2:
            continue
        names = {quote.normalized_name for quote in quotes}
        if len(names) > 1:
            raise ValueError(f"mismatched instruments in group: {sorted(names)}")

        valid = [quote for quote in quotes if _is_valid(quote)]
        valid = [
            quote
            for quote in valid
            if quote.bid_price * quote.bid_qty >= min_leg_premium_liquidity_usd
        ]
        if len(valid) < 2:
            continue

        lowest_ask = min(valid, key=lambda quote: quote.ask_price)
        highest_bid = max(valid, key=lambda quote: quote.bid_price)
        if lowest_ask.exchange == highest_bid.exchange:
            continue

        expiry = quotes[0].expiry
        expiry_utc = expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)
        dte = days_to_expiry(expiry_utc, now)
        quantity = min(lowest_ask.ask_qty, highest_bid.bid_qty)
        spot = highest_bid.underlying_price or lowest_ask.underlying_price
        economics = calculate_option_economics(
            buy_price=lowest_ask.ask_price,
            sell_price=highest_bid.bid_price,
            quantity=quantity,
            buy_taker_fee_rate=lowest_ask.taker_fee_rate,
            sell_taker_fee_rate=highest_bid.taker_fee_rate,
            spot=spot,
            strike=highest_bid.strike,
            option_type=cast(Literal["C", "P"], highest_bid.option_type),
            days_to_expiry=dte,
        )
        if economics is None or economics.net_profit_usd <= 0:
            continue

        sample = quotes[0]
        results.append(
            Spread(
                normalized_name=sample.normalized_name,
                symbol=sample.underlying,
                instrument=sample.normalized_name,
                strike=sample.strike,
                option_type=sample.option_type,
                expiry=expiry_utc,
                days_to_expiry=dte,
                buy_from=lowest_ask.exchange,
                sell_to=highest_bid.exchange,
                buy_ask=lowest_ask.ask_price,
                sell_bid=highest_bid.bid_price,
                tradeable_size=economics.tradeable_size,
                buy_premium_usd=economics.buy_premium_usd,
                sell_premium_usd=economics.sell_premium_usd,
                estimated_short_margin_usd=economics.estimated_short_margin_usd,
                capital_required_usd=economics.capital_required_usd,
                gross_profit_usd=economics.gross_profit_usd,
                fees_usd=economics.fees_usd,
                net_profit_usd=economics.net_profit_usd,
                price_spread_pct=economics.price_spread_pct,
                net_return_pct=economics.net_return_pct,
                apr_pct=economics.apr_pct,
            )
        )

    return results
