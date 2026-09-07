from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from option_arb.config import StructuredThresholds
from option_arb.services.comparator import Quote
from option_arb.structured.strategies import detect_boxes

EXPIRY = datetime.now(UTC) + timedelta(days=30)
LOOSE = StructuredThresholds(
    min_total_profit_usd=0.0, min_profit_per_unit_usd=0.0, max_days_to_expiry=60
)


def _q(
    exchange: str,
    strike: str,
    option_type: str,
    *,
    bid: str,
    ask: str,
    bid_qty: str = "5",
    ask_qty: str = "5",
    fee: str = "0",
) -> Quote:
    name = f"BTC-20260327-{strike}-{option_type}"
    return Quote(
        exchange=exchange,
        normalized_name=name,
        instrument_name=name,
        underlying="BTC",
        strike=Decimal(strike),
        option_type=option_type,
        expiry=EXPIRY,
        taker_fee_rate=Decimal(fee),
        bid_price=Decimal(bid),
        bid_qty=Decimal(bid_qty),
        ask_price=Decimal(ask),
        ask_qty=Decimal(ask_qty),
        underlying_price=Decimal("100000"),
    )


def _group(quotes: list[Quote]) -> dict[tuple[str, datetime], list[Quote]]:
    return {("BTC", EXPIRY): quotes}


# entry_cost = ask(C K1) + ask(P K2) - bid(C K2) - bid(P K1)
# width = K2 - K1 ; profit/unit = width - entry_cost - fees


def test_detects_profitable_box() -> None:
    quotes = [
        _q("derive", "100", "C", bid="20", ask="21"),
        _q("derive", "100", "P", bid="8", ask="9"),
        _q("derive", "120", "C", bid="9", ask="10"),
        _q("derive", "120", "P", bid="15", ask="16"),
    ]
    # entry = 21 + 16 - 9 - 8 = 20 ... not profitable; tune P100 bid up
    quotes[1] = _q("derive", "100", "P", bid="9", ask="10")
    # entry = 21 + 16 - 9 - 9 = 19 ; width 20 ; profit/unit = 1
    out = detect_boxes(_group(quotes), LOOSE)
    assert len(out) == 1
    box = out[0]
    assert box.strikes == [Decimal("100"), Decimal("120")]
    assert box.width == Decimal("20")
    assert box.entry_cost == Decimal("19")
    assert box.min_profit_per_unit == Decimal("1")
    assert box.max_size == Decimal("5")
    assert box.max_total_profit == Decimal("5")
    assert box.is_fixed_payoff is True
    assert box.settlement_risk is False
    assert {leg.side for leg in box.legs} == {"buy", "sell"}
    assert len(box.legs) == 4


def test_rejects_when_no_edge() -> None:
    quotes = [
        _q("derive", "100", "C", bid="20", ask="22"),
        _q("derive", "100", "P", bid="8", ask="9"),
        _q("derive", "120", "C", bid="9", ask="10"),
        _q("derive", "120", "P", bid="15", ask="16"),
    ]
    # entry = 22 + 16 - 9 - 8 = 21 > width 20 → profit/unit = -1
    assert detect_boxes(_group(quotes), LOOSE) == []


def test_fees_can_kill_the_edge() -> None:
    quotes = [
        _q("derive", "100", "C", bid="20", ask="21", fee="0.05"),
        _q("derive", "100", "P", bid="9", ask="10", fee="0.05"),
        _q("derive", "120", "C", bid="9", ask="10", fee="0.05"),
        _q("derive", "120", "P", bid="15", ask="16", fee="0.05"),
    ]
    # entry = 19, edge before fees = 1 ; fees = 0.05*(21+16+9+9) = 2.75 → negative
    assert detect_boxes(_group(quotes), LOOSE) == []


def test_picks_best_venue_per_leg() -> None:
    quotes = [
        _q("aevo", "100", "C", bid="1", ask="25"),
        _q("derive", "100", "C", bid="1", ask="21"),  # best ask for the long call
        _q("deribit_linear", "100", "C", bid="1", ask="23"),
        _q("derive", "100", "P", bid="9", ask="10"),
        _q("aevo", "100", "P", bid="12", ask="10"),  # best bid for the short put
        _q("derive", "120", "C", bid="9", ask="10"),
        _q("deribit_linear", "120", "C", bid="11", ask="10"),  # best bid for short call
        _q("derive", "120", "P", bid="15", ask="16"),
    ]
    out = detect_boxes(_group(quotes), LOOSE)
    assert len(out) == 1
    box = out[0]
    # entry = 21 (derive C100 ask) + 16 (derive P120 ask) - 11 (deribit_linear C120 bid) - 12 (aevo P100 bid) = 14
    assert box.entry_cost == Decimal("14")
    legs = {(leg.instrument, leg.side): leg for leg in box.legs}
    assert legs[("BTC-20260327-100-C", "buy")].exchange == "derive"
    assert legs[("BTC-20260327-100-P", "sell")].exchange == "aevo"
    assert legs[("BTC-20260327-120-C", "sell")].exchange == "deribit_linear"
    # all linear venues → no settlement risk, but cross-exchange → not fixed payoff
    assert box.settlement_risk is False
    assert box.is_fixed_payoff is False


def test_settlement_risk_when_inverse_and_linear_mixed() -> None:
    quotes = [
        _q("deribit", "100", "C", bid="1", ask="21"),  # inverse venue
        _q("derive", "100", "P", bid="9", ask="10"),
        _q("derive", "120", "C", bid="9", ask="10"),
        _q("derive", "120", "P", bid="15", ask="16"),
    ]
    out = detect_boxes(_group(quotes), LOOSE)
    assert len(out) == 1
    assert out[0].settlement_risk is True
    assert out[0].is_fixed_payoff is False


def test_max_size_is_least_liquid_leg_and_total_threshold_filters() -> None:
    quotes = [
        _q("derive", "100", "C", bid="20", ask="21", ask_qty="4"),
        _q("derive", "100", "P", bid="9", ask="10", bid_qty="1.5"),  # tightest
        _q("derive", "120", "C", bid="9", ask="10", bid_qty="9"),
        _q("derive", "120", "P", bid="15", ask="16", ask_qty="3"),
    ]
    out = detect_boxes(_group(quotes), LOOSE)
    assert out[0].max_size == Decimal("1.5")
    assert out[0].max_total_profit == Decimal("1.5")  # 1 * 1.5

    strict = StructuredThresholds(
        min_total_profit_usd=5.0, min_profit_per_unit_usd=0.0, max_days_to_expiry=60
    )
    assert detect_boxes(_group(quotes), strict) == []


def test_skips_group_beyond_max_dte() -> None:
    far = datetime.now(UTC) + timedelta(days=90)
    quotes = [
        Quote(
            exchange="derive",
            normalized_name=f"BTC-20260327-{k}-{t}",
            instrument_name=f"BTC-20260327-{k}-{t}",
            underlying="BTC",
            strike=Decimal(k),
            option_type=t,
            expiry=far,
            taker_fee_rate=Decimal("0"),
            bid_price=Decimal(b),
            bid_qty=Decimal("5"),
            ask_price=Decimal(a),
            ask_qty=Decimal("5"),
            underlying_price=Decimal("100000"),
        )
        for k, t, b, a in [
            ("100", "C", "20", "21"),
            ("100", "P", "9", "10"),
            ("120", "C", "9", "10"),
            ("120", "P", "15", "16"),
        ]
    ]
    assert detect_boxes({("BTC", far): quotes}, LOOSE) == []
