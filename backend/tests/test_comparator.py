from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from option_arb.exchanges.naming import normalize_deribit, normalize_from_parts
from option_arb.services.comparator import Quote, Spread, compare_options, group_by_instrument


def _q(
    exchange: str,
    bid: str,
    ask: str,
    qty: str = "10",
    fee: str = "0.0003",
    underlying_price: str | None = None,
    strike: str = "30000",
    option_type: str = "C",
) -> Quote:
    return Quote(
        exchange=exchange,
        normalized_name="BTC-20260101-30000-C",
        instrument_name="BTC-1JAN26-30000-C",
        underlying="BTC",
        strike=Decimal(strike),
        option_type=option_type,
        expiry=datetime(2026, 1, 1, tzinfo=UTC),
        taker_fee_rate=Decimal(fee),
        bid_price=Decimal(bid),
        bid_qty=Decimal(qty),
        ask_price=Decimal(ask),
        ask_qty=Decimal(qty),
        underlying_price=Decimal(underlying_price) if underlying_price else None,
    )


def test_normalize_deribit() -> None:
    assert normalize_deribit("BTC-25OCT25-30000-C") == "BTC-20251025-30000-C"
    assert normalize_deribit("ETH-1DEC25-4000-P") == "ETH-20251201-4000-P"


def test_normalize_from_parts() -> None:
    name = normalize_from_parts(
        "BTC",
        datetime(2025, 10, 25, tzinfo=UTC),
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
    now = datetime(2025, 1, 1, tzinfo=UTC)
    # spot=50000, strike=30000 → ITM call, OTM_frac=0, base_rate=0.15, margin=7500
    a = _q("derive", "100", "101", fee="0.0003", underlying_price="50000")
    b = _q("deribit", "110", "112", fee="0.0003", underlying_price="50000")
    spreads = compare_options([[a, b]], now=now)
    assert len(spreads) == 1
    s = spreads[0]
    assert s.buy_from == "derive"
    assert s.sell_to == "deribit"
    assert s.buy_ask == Decimal("101")
    assert s.sell_bid == Decimal("110")

    # capital = sell margin = 0.15 * 50000 = 7500
    # fees_usd = 0.0003*101 + 0.0003*110 = 0.0633
    expected_fee_pct = Decimal("0.0633") / Decimal("7500") * 100
    assert s.fee_pct == pytest.approx(expected_fee_pct, abs=Decimal("0.001"))  # type: ignore[call-overload]

    # net_profit_per_unit = 8.9367; qty_traded=10 (ask_notional=1010 <= bid_notional=1100)
    expected_net_pct = Decimal("8.9367") / Decimal("7500") * 100
    assert s.net_spread_pct == pytest.approx(expected_net_pct, abs=Decimal("0.001"))  # type: ignore[call-overload]

    assert s.capital_deployed_usd == pytest.approx(Decimal("7500"), abs=Decimal("1"))  # type: ignore[call-overload]
    assert s.net_profit_usd == pytest.approx(Decimal("8.9367") * 10, abs=Decimal("0.001"))  # type: ignore[call-overload]


def test_no_spread_when_no_underlying_price() -> None:
    """Without underlying_price on any leg, margin can't be computed — skip."""
    a = _q("derive", "100", "101")
    b = _q("deribit", "110", "112")
    assert compare_options([[a, b]]) == []


def test_no_spread_when_same_exchange_is_both_best() -> None:
    a = _q("derive", "110", "101")
    b = _q("deribit", "100", "112")
    spreads = compare_options([[a, b]])
    assert spreads == []


def test_illiquid_quotes_filtered_by_size_threshold() -> None:
    a = _q("derive", "1", "2", qty="1")  # notional 1$ — below default 100
    b = _q("deribit", "3", "4", qty="1")
    assert compare_options([[a, b]]) == []


def test_fees_erase_thin_spread() -> None:
    # spread 1 USD, fees = 0.01*100 + 0.01*101 = 2.01 → net negative
    a = _q("derive", "100", "100", fee="0.01")
    b = _q("deribit", "101", "101", fee="0.01")
    assert compare_options([[a, b]]) == []


def test_apr_scales_with_time_to_expiry() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    exp_soon = now + timedelta(days=1)
    exp_later = now + timedelta(days=365)

    def _pair(expiry: datetime) -> list[Quote]:
        a = _q("derive", "100", "101", underlying_price="50000")
        b = _q("deribit", "110", "111", underlying_price="50000")
        return [
            Quote(**{**a.__dict__, "expiry": expiry}),
            Quote(**{**b.__dict__, "expiry": expiry}),
        ]

    s_soon = compare_options([_pair(exp_soon)], now=now)[0]
    s_later = compare_options([_pair(exp_later)], now=now)[0]
    assert s_soon.apr_pct > s_later.apr_pct


def test_capital_deployed_is_sell_margin_only_when_underlying_known() -> None:
    """capital_deployed = sell margin only (not premium + margin).
    OTM call: strike=30000, spot=28000 → OTM_frac=(30000-28000)/28000≈0.0714
    base_rate = max(0.15-0.0714, 0.10) = max(0.0786, 0.10) = 0.10
    margin_sell = 0.10 * 28000 = 2800"""
    now = datetime(2025, 1, 1, tzinfo=UTC)
    spot = "28000"
    a = _q("derive", "100", "200", underlying_price=spot, strike="30000", option_type="C")
    b = _q(
        "deribit",
        "400",
        "500",
        fee="0.0003",
        underlying_price=spot,
        strike="30000",
        option_type="C",
    )
    spreads = compare_options([[a, b]], now=now)
    assert len(spreads) == 1
    s = spreads[0]
    # capital = sell margin only = 0.10 * 28000 = 2800 (premium excluded)
    assert s.capital_deployed_usd == pytest.approx(Decimal("2800"), abs=Decimal("0.01"))  # type: ignore[call-overload]
    # net_spread_pct relative to capital (2800): (400-200-fees)/2800*100 ≈ 7.1%
    assert Decimal("5") < s.net_spread_pct < Decimal("10")
    # apr annualises net_spread_pct — consistent denominator
    assert pytest.approx(float(s.apr_pct), rel=1e-3) == float(
        s.net_spread_pct / Decimal(str(s.days_to_expiry)) * 365
    )  # type: ignore[call-overload]


def test_itm_call_has_higher_margin_than_otm() -> None:
    """ITM call: strike < spot → OTM_frac=0, base_rate=0.15. OTM: base_rate=0.10."""
    now = datetime(2025, 1, 1, tzinfo=UTC)
    spot = "30000"

    def _pair(strike: str) -> list[Spread]:
        a = _q("derive", "100", "200", underlying_price=spot, strike=strike, option_type="C")
        b = _q("deribit", "400", "500", underlying_price=spot, strike=strike, option_type="C")
        return compare_options([[a, b]], now=now)

    itm = _pair("25000")  # strike < spot → ITM → OTM_frac=0 → base_rate=0.15
    otm = _pair("35000")  # strike > spot → OTM → base_rate=max(0.15-0.167,0.10)=0.10

    assert len(itm) == 1 and len(otm) == 1
    # ITM capital = margin only = 0.15*30000=4500; OTM = 0.10*30000=3000
    assert itm[0].capital_deployed_usd == pytest.approx(Decimal("4500"), abs=Decimal("1"))  # type: ignore[call-overload]
    assert otm[0].capital_deployed_usd == pytest.approx(Decimal("3000"), abs=Decimal("1"))  # type: ignore[call-overload]
    assert itm[0].capital_deployed_usd > otm[0].capital_deployed_usd
