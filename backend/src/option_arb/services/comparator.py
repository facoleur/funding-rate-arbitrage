from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass(frozen=True)
class Spread:
    normalized_name: str
    symbol: str            # underlying, e.g. "BTC"
    instrument: str        # same as normalized_name for now
    strike: Decimal
    option_type: str
    expiry: datetime
    days_to_expiry: float

    buy_from: str
    sell_to: str
    buy_ask: Decimal
    sell_bid: Decimal

    net_spread_pct: Decimal
    apr_pct: Decimal
    max_notional_usd: Decimal


def group_by_instrument(quotes: list[Quote]) -> dict[str, list[Quote]]:
    """Group cross-venue quotes by their normalized instrument name."""
    grouped: dict[str, list[Quote]] = defaultdict(list)
    for q in quotes:
        grouped[q.normalized_name].append(q)
    return grouped


def _is_valid(q: Quote) -> bool:
    return q.bid_price > 0 and q.ask_price > 0 and q.bid_qty > 0 and q.ask_qty > 0


def compare_options(
    groups: list[list[Quote]],
    *,
    size_threshold_usd: Decimal = Decimal("100"),
    now: datetime | None = None,
) -> list[Spread]:
    """For each group of cross-venue quotes for the same instrument, find
    the best buy (lowest ask on exchange A) and best sell (highest bid on
    exchange B) across DIFFERENT exchanges, subtract combined taker fees,
    and return a Spread when the net spread is positive.

    Ports the semantics of the TS `compareOptions` from the deleted prototype."""
    now = now or datetime.now(timezone.utc)
    results: list[Spread] = []

    for quotes in groups:
        if len(quotes) < 2:
            continue

        names = {q.normalized_name for q in quotes}
        if len(names) > 1:
            raise ValueError(f"mismatched instruments in group: {sorted(names)}")

        valid = [q for q in quotes if _is_valid(q)]
        # apply size floor: filter out illiquid quotes just like TS did
        valid = [
            q for q in valid
            if q.bid_price * q.bid_qty >= size_threshold_usd
        ]
        if len(valid) < 2:
            continue

        lowest_ask = min(valid, key=lambda q: q.ask_price)
        highest_bid = max(valid, key=lambda q: q.bid_price)

        if lowest_ask.exchange == highest_bid.exchange:
            continue  # no cross-exchange arb

        price_diff_pct = (
            (highest_bid.bid_price - lowest_ask.ask_price) / lowest_ask.ask_price
        ) * Decimal(100)
        fee_pct = (lowest_ask.taker_fee_rate + highest_bid.taker_fee_rate) * Decimal(100)
        net_diff_pct = price_diff_pct - fee_pct

        if net_diff_pct <= 0:
            continue

        q0 = quotes[0]
        expiry_utc = q0.expiry if q0.expiry.tzinfo else q0.expiry.replace(tzinfo=timezone.utc)
        days_to_exp = max((expiry_utc - now).total_seconds() / 86400.0, 1e-6)
        apr = (net_diff_pct / Decimal(str(days_to_exp))) * Decimal(365)

        max_notional = min(
            lowest_ask.ask_qty * lowest_ask.ask_price,
            highest_bid.bid_qty * highest_bid.bid_price,
        )

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
                net_spread_pct=net_diff_pct,
                apr_pct=apr,
                max_notional_usd=max_notional,
            )
        )

    return results
