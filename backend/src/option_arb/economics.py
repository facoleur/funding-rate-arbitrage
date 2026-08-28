from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class OptionEconomics:
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


def sell_margin_per_unit(spot: Decimal, strike: Decimal, option_type: Literal["C", "P"]) -> Decimal:
    """Standalone estimated short margin before any sell-premium offset."""
    if option_type == "C":
        otm_fraction = max(Decimal(0), (strike - spot) / spot)
    else:
        otm_fraction = max(Decimal(0), (spot - strike) / spot)
    base_rate = max(Decimal("0.15") - otm_fraction, Decimal("0.10"))
    return base_rate * spot


def days_to_expiry(expiry: datetime, now: datetime) -> Decimal:
    delta = expiry - now
    total_microseconds = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return Decimal(total_microseconds) / Decimal(86_400_000_000)


def calculate_option_economics(
    *,
    buy_price: Decimal,
    sell_price: Decimal,
    quantity: Decimal,
    buy_taker_fee_rate: Decimal,
    sell_taker_fee_rate: Decimal,
    spot: Decimal | None,
    strike: Decimal,
    option_type: Literal["C", "P"],
    days_to_expiry: Decimal,
) -> OptionEconomics | None:
    values = (
        buy_price,
        sell_price,
        quantity,
        buy_taker_fee_rate,
        sell_taker_fee_rate,
        strike,
        days_to_expiry,
    )
    if spot is None or not spot.is_finite() or spot <= 0:
        return None
    if any(not value.is_finite() for value in values):
        return None
    if buy_price <= 0 or sell_price <= 0 or quantity <= 0 or days_to_expiry <= 0:
        return None
    if strike < 0 or buy_taker_fee_rate < 0 or sell_taker_fee_rate < 0:
        return None

    buy_premium = buy_price * quantity
    sell_premium = sell_price * quantity
    gross_profit = sell_premium - buy_premium
    fees = buy_premium * buy_taker_fee_rate + sell_premium * sell_taker_fee_rate
    net_profit = gross_profit - fees
    short_margin = sell_margin_per_unit(spot, strike, option_type) * quantity
    capital_required = short_margin + buy_premium
    if not capital_required.is_finite() or capital_required <= 0:
        return None

    net_return = net_profit / capital_required * Decimal(100)
    return OptionEconomics(
        tradeable_size=quantity,
        buy_premium_usd=buy_premium,
        sell_premium_usd=sell_premium,
        estimated_short_margin_usd=short_margin,
        capital_required_usd=capital_required,
        gross_profit_usd=gross_profit,
        fees_usd=fees,
        net_profit_usd=net_profit,
        price_spread_pct=gross_profit / buy_premium * Decimal(100),
        net_return_pct=net_return,
        apr_pct=net_return * Decimal(365) / days_to_expiry,
    )
