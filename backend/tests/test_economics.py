from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from option_arb.economics import (
    calculate_option_economics,
    days_to_expiry,
    sell_margin_per_unit,
)


def _calculate(**overrides: object):  # type: ignore[no-untyped-def]
    values = {
        "buy_price": Decimal("10"),
        "sell_price": Decimal("12"),
        "quantity": Decimal("2"),
        "buy_taker_fee_rate": Decimal("0.01"),
        "sell_taker_fee_rate": Decimal("0.02"),
        "spot": Decimal("100"),
        "strike": Decimal("80"),
        "option_type": "C",
        "days_to_expiry": Decimal("1"),
    }
    values.update(overrides)
    return calculate_option_economics(**values)  # type: ignore[arg-type]


def test_exact_economic_identities_with_asymmetric_fees() -> None:
    result = _calculate()
    assert result is not None
    assert result.buy_premium_usd == Decimal("20")
    assert result.sell_premium_usd == Decimal("24")
    assert result.gross_profit_usd == Decimal("4")
    assert result.fees_usd == Decimal("0.68")
    assert result.net_profit_usd == Decimal("3.32")
    assert result.estimated_short_margin_usd == Decimal("30.00")
    assert result.capital_required_usd == Decimal("50.00")
    assert result.price_spread_pct == Decimal("20.0")
    assert result.net_return_pct == Decimal("6.6400")
    assert result.apr_pct == Decimal("2423.6000")


def test_call_and_put_itm_otm_margin() -> None:
    spot = Decimal("100")
    assert sell_margin_per_unit(spot, Decimal("80"), "C") == Decimal("15.00")
    assert sell_margin_per_unit(spot, Decimal("120"), "C") == Decimal("10.00")
    assert sell_margin_per_unit(spot, Decimal("120"), "P") == Decimal("15.00")
    assert sell_margin_per_unit(spot, Decimal("80"), "P") == Decimal("10.00")


def test_quantity_scales_totals_but_not_returns() -> None:
    one = _calculate(quantity=Decimal("1"))
    three = _calculate(quantity=Decimal("3"))
    assert one is not None and three is not None
    for field in (
        "buy_premium_usd",
        "sell_premium_usd",
        "estimated_short_margin_usd",
        "capital_required_usd",
        "gross_profit_usd",
        "fees_usd",
        "net_profit_usd",
    ):
        assert getattr(three, field) == getattr(one, field) * Decimal(3)
    assert three.net_return_pct == one.net_return_pct
    assert three.apr_pct == one.apr_pct


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spot", None),
        ("spot", Decimal(0)),
        ("buy_price", Decimal(0)),
        ("sell_price", Decimal("NaN")),
        ("quantity", Decimal(0)),
        ("days_to_expiry", Decimal(0)),
        ("days_to_expiry", Decimal(-1)),
    ],
)
def test_invalid_inputs_do_not_produce_economics(field: str, value: object) -> None:
    assert _calculate(**{field: value}) is None


def test_days_to_expiry_uses_exact_decimal_duration() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert days_to_expiry(now + timedelta(days=2, hours=12), now) == Decimal("2.5")
