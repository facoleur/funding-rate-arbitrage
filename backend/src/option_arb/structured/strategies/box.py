"""Box spread detection.

A box = ``Long C(K1) + Short P(K1) + Short C(K2) + Long P(K2)`` with ``K1 < K2``.
Payoff at expiry is exactly ``K2 - K1`` for every ``S_T`` (put-call parity on both
strikes). It is an arb when the net debit paid to enter, plus taker fees, is less
than that width — the difference is locked profit if held to expiry.

Each of the 4 legs is priced at the best quote available across venues
(lowest ask for the long legs, highest bid for the short legs); this is the
optimal entry cost and mirrors how ``services.comparator.compare_options`` picks
its two legs. No cross-venue combinatorial search.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

from option_arb.config import StructuredThresholds
from option_arb.db.models import StrategyType
from option_arb.economics import days_to_expiry
from option_arb.services.comparator import Quote, _is_valid
from option_arb.structured.types import Leg, StructuredOpportunityDTO, settlement_class

# (underlying, expiry) -> quotes for every strike/type on every venue in that group
GroupKey = tuple[str, datetime]


def detect_boxes(
    groups: Mapping[GroupKey, list[Quote]],
    thresholds: StructuredThresholds,
    *,
    now: datetime | None = None,
) -> list[StructuredOpportunityDTO]:
    now = now or datetime.now(UTC)
    min_pu = Decimal(str(thresholds.min_profit_per_unit_usd))
    min_total = Decimal(str(thresholds.min_total_profit_usd))
    max_dte = Decimal(thresholds.max_days_to_expiry)

    out: list[StructuredOpportunityDTO] = []
    for (underlying, expiry), quotes in groups.items():
        expiry_utc = expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)
        dte = days_to_expiry(expiry_utc, now)
        if dte <= 0 or dte > max_dte:
            continue

        # (strike, option_type) -> valid quotes
        by_st: dict[tuple[Decimal, str], list[Quote]] = {}
        for q in quotes:
            if not _is_valid(q):
                continue
            by_st.setdefault((q.strike, q.option_type), []).append(q)

        strikes = sorted({s for (s, _t) in by_st})
        for i, k1 in enumerate(strikes):
            for k2 in strikes[i + 1 :]:
                dto = _try_box(underlying, expiry_utc, k1, k2, by_st, min_pu, min_total)
                if dto is not None:
                    out.append(dto)
    return out


def _best_ask(quotes: list[Quote] | None) -> Quote | None:
    return min(quotes, key=lambda q: q.ask_price) if quotes else None


def _best_bid(quotes: list[Quote] | None) -> Quote | None:
    return max(quotes, key=lambda q: q.bid_price) if quotes else None


def _try_box(
    underlying: str,
    expiry: datetime,
    k1: Decimal,
    k2: Decimal,
    by_st: dict[tuple[Decimal, str], list[Quote]],
    min_pu: Decimal,
    min_total: Decimal,
) -> StructuredOpportunityDTO | None:
    long_c1 = _best_ask(by_st.get((k1, "C")))  # buy call K1
    long_p2 = _best_ask(by_st.get((k2, "P")))  # buy put  K2
    short_c2 = _best_bid(by_st.get((k2, "C")))  # sell call K2
    short_p1 = _best_bid(by_st.get((k1, "P")))  # sell put  K1
    if long_c1 is None or long_p2 is None or short_c2 is None or short_p1 is None:
        return None

    width = k2 - k1
    entry_cost = long_c1.ask_price + long_p2.ask_price - short_c2.bid_price - short_p1.bid_price
    max_fees = (
        long_c1.ask_price * long_c1.taker_fee_rate
        + long_p2.ask_price * long_p2.taker_fee_rate
        + short_c2.bid_price * short_c2.taker_fee_rate
        + short_p1.bid_price * short_p1.taker_fee_rate
    )
    min_profit_per_unit = width - entry_cost - max_fees
    if min_profit_per_unit <= min_pu:
        return None

    max_size = min(long_c1.ask_qty, long_p2.ask_qty, short_c2.bid_qty, short_p1.bid_qty)
    max_total_profit = min_profit_per_unit * max_size
    if max_total_profit < min_total:
        return None

    legs = [
        Leg(
            long_c1.exchange,
            long_c1.normalized_name,
            "buy",
            long_c1.ask_price,
            long_c1.ask_qty,
            long_c1.taker_fee_rate,
        ),
        Leg(
            short_p1.exchange,
            short_p1.normalized_name,
            "sell",
            short_p1.bid_price,
            short_p1.bid_qty,
            short_p1.taker_fee_rate,
        ),
        Leg(
            short_c2.exchange,
            short_c2.normalized_name,
            "sell",
            short_c2.bid_price,
            short_c2.bid_qty,
            short_c2.taker_fee_rate,
        ),
        Leg(
            long_p2.exchange,
            long_p2.normalized_name,
            "buy",
            long_p2.ask_price,
            long_p2.ask_qty,
            long_p2.taker_fee_rate,
        ),
    ]
    exchanges = {leg.exchange for leg in legs}
    spot = (
        long_c1.underlying_price
        or short_p1.underlying_price
        or short_c2.underlying_price
        or long_p2.underlying_price
    )
    return StructuredOpportunityDTO(
        strategy_type=StrategyType.BOX,
        underlying=underlying,
        expiry=expiry,
        strikes=[k1, k2],
        legs=legs,
        is_fixed_payoff=len(exchanges) == 1,
        settlement_risk=len({settlement_class(e) for e in exchanges}) > 1,
        width=width,
        entry_cost=entry_cost,
        max_fees=max_fees,
        min_profit_per_unit=min_profit_per_unit,
        max_size=max_size,
        capital_required=max(entry_cost, Decimal(0)) * max_size,
        max_total_profit=max_total_profit,
        spot=spot,
    )
