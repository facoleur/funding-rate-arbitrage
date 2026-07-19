from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from option_arb.exchanges.naming import normalize_deribit, normalize_from_parts
from option_arb.services.comparator import Quote, compare_options, group_by_instrument


def _q(exchange: str, bid: str, ask: str, qty: str = "10", fee: str = "0.0003") -> Quote:
    return Quote(
        exchange=exchange,
        normalized_name="BTC-20260101-30000-C",
        instrument_name="BTC-1JAN26-30000-C",
        underlying="BTC",
        strike=Decimal("30000"),
        option_type="C",
        expiry=datetime(2026, 1, 1, tzinfo=timezone.utc),
        taker_fee_rate=Decimal(fee),
        bid_price=Decimal(bid),
        bid_qty=Decimal(qty),
        ask_price=Decimal(ask),
        ask_qty=Decimal(qty),
    )


def test_normalize_deribit() -> None:
    assert normalize_deribit("BTC-25OCT25-30000-C") == "BTC-20251025-30000-C"
    assert normalize_deribit("ETH-1DEC25-4000-P") == "ETH-20251201-4000-P"


def test_normalize_from_parts() -> None:
    name = normalize_from_parts(
        "BTC",
        datetime(2025, 10, 25, tzinfo=timezone.utc),
        Decimal("30000"),
        "C",
    )
    assert name == "BTC-20251025-30000-C"


def test_group_by_instrument() -> None:
    a = _q("derive", "100", "101")
    b = _q("deribit", "102", "103")
    grouped = group_by_instrument([a, b])
    assert set(grouped) == {"BTC-20260101-30000-C"}
    assert len(grouped["BTC-20260101-30000-C"]) == 2


def test_spread_detected_when_cross_venue_and_positive_net() -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    a = _q("derive", "100", "101")     # ask 101
    b = _q("deribit", "110", "112")    # bid 110 → spread = (110-101)/101 ≈ 8.91%
    spreads = compare_options([[a, b]], now=now)
    assert len(spreads) == 1
    s = spreads[0]
    assert s.buy_from == "derive"
    assert s.sell_to == "deribit"
    assert s.buy_ask == Decimal("101")
    assert s.sell_bid == Decimal("110")
    assert s.net_spread_pct > 0


def test_no_spread_when_same_exchange_is_both_best() -> None:
    # derive has the highest bid AND the lowest ask → no cross-venue arb
    a = _q("derive", "110", "101")
    b = _q("deribit", "100", "112")
    spreads = compare_options([[a, b]])
    assert spreads == []


def test_illiquid_quotes_filtered_by_size_threshold() -> None:
    # bid_price * bid_qty must be >= size_threshold_usd
    a = _q("derive", "1", "2", qty="1")  # notional 1$ — below default 100
    b = _q("deribit", "3", "4", qty="1")
    assert compare_options([[a, b]]) == []


def test_fees_erase_thin_spread() -> None:
    # tiny spread 1% but fees 2% total → net negative
    a = _q("derive", "100", "100", fee="0.01")
    b = _q("deribit", "101", "101", fee="0.01")
    assert compare_options([[a, b]]) == []


def test_apr_scales_with_time_to_expiry() -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    exp_soon = now + timedelta(days=1)
    exp_later = now + timedelta(days=365)

    def _pair(expiry: datetime) -> list[Quote]:
        a = _q("derive", "100", "101")
        b = _q("deribit", "110", "111")
        return [
            Quote(**{**a.__dict__, "expiry": expiry}),
            Quote(**{**b.__dict__, "expiry": expiry}),
        ]

    s_soon = compare_options([_pair(exp_soon)], now=now)[0]
    s_later = compare_options([_pair(exp_later)], now=now)[0]
    assert s_soon.apr_pct > s_later.apr_pct  # same spread, shorter time = higher APR
