from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from freezegun import freeze_time

from option_arb.api.tickers import _group_and_compute
from option_arb.config import Thresholds
from option_arb.db.models import TickerState
from option_arb.exchanges.naming import normalize_deribit, normalize_from_parts
from option_arb.services.comparator import Quote, Spread, compare_options


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

    assert s.tradeable_size == Decimal("10")
    assert s.buy_premium_usd == Decimal("1010")
    assert s.sell_premium_usd == Decimal("1100")
    assert s.estimated_short_margin_usd == Decimal("75000.00")
    assert s.capital_required_usd == Decimal("76010.00")
    assert s.gross_profit_usd == Decimal("90")
    assert s.fees_usd == Decimal("0.6330")
    assert s.net_profit_usd == Decimal("89.3670")
    assert s.net_return_pct == s.net_profit_usd / s.capital_required_usd * 100


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


def test_capital_required_is_buy_premium_plus_unoffset_short_margin() -> None:
    """Capital required includes both the buy premium and standalone short margin.
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
    # q=10: margin=28,000 and buy premium=2,000. Sell premium does not offset either.
    assert s.estimated_short_margin_usd == pytest.approx(Decimal("28000"))
    assert s.capital_required_usd == pytest.approx(Decimal("30000"))
    assert Decimal("5") < s.net_return_pct < Decimal("10")
    assert s.apr_pct == pytest.approx(s.net_return_pct / s.days_to_expiry * Decimal(365))


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
    # q=10 and buy premium=2,000: ITM capital=45,000+2,000; OTM=30,000+2,000.
    assert itm[0].capital_required_usd == pytest.approx(Decimal("47000"), abs=Decimal("1"))
    assert otm[0].capital_required_usd == pytest.approx(Decimal("32000"), abs=Decimal("1"))
    assert itm[0].capital_required_usd > otm[0].capital_required_usd


def test_comparator_and_book_have_identical_economics() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    expiry = now + timedelta(days=30)
    buy_quote = Quote(
        **{
            **_q("derive", "100", "101", qty="2", underlying_price="1000").__dict__,
            "expiry": expiry,
        }
    )
    sell_quote = Quote(
        **{
            **_q("deribit", "110", "112", qty="3", underlying_price="1000").__dict__,
            "expiry": expiry,
        }
    )
    spread = compare_options([[buy_quote, sell_quote]], now=now)[0]
    rows = [
        TickerState(
            exchange=quote.exchange,
            instrument=quote.normalized_name,
            underlying=quote.underlying,
            expiry=expiry,
            strike=float(quote.strike),
            option_type=quote.option_type,
            bid_price=float(quote.bid_price),
            bid_size=float(quote.bid_qty),
            ask_price=float(quote.ask_price),
            ask_size=float(quote.ask_qty),
            underlying_price=float(quote.underlying_price or 0),
            taker_fee_rate=float(quote.taker_fee_rate),
            updated_at=now,
        )
        for quote in (buy_quote, sell_quote)
    ]
    with freeze_time(now):
        book_row = _group_and_compute(rows, Thresholds())[0]
    for field in (
        "tradeable_size",
        "buy_premium_usd",
        "sell_premium_usd",
        "estimated_short_margin_usd",
        "capital_required_usd",
        "gross_profit_usd",
        "fees_usd",
        "net_profit_usd",
        "price_spread_pct",
        "net_return_pct",
        "apr_pct",
    ):
        assert book_row[field] == pytest.approx(float(getattr(spread, field)))
