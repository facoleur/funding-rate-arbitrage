from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from option_arb.db.models import StrategyType

# Settlement class per exchange. Deribit options are inverse (coin-settled);
# every other venue we trade is linear (USD/USDC-settled). A box whose legs span
# both classes is NOT USD-fixed at expiry — flag `settlement_risk`.
_INVERSE_EXCHANGES = frozenset({"deribit"})


def settlement_class(exchange: str) -> Literal["inverse", "linear"]:
    return "inverse" if exchange in _INVERSE_EXCHANGES else "linear"


@dataclass(frozen=True)
class Leg:
    exchange: str
    instrument: str  # normalized_name, e.g. BTC-20260327-60000-C
    side: Literal["buy", "sell"]
    price: Decimal  # ask for buy legs, bid for sell legs
    qty: Decimal
    taker_fee_rate: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "instrument": self.instrument,
            "side": self.side,
            "price": float(self.price),
            "qty": float(self.qty),
            "taker_fee_rate": float(self.taker_fee_rate),
        }


@dataclass(frozen=True)
class StructuredOpportunityDTO:
    strategy_type: StrategyType
    underlying: str
    expiry: datetime
    strikes: list[Decimal]  # [K1, K2] ascending
    legs: list[Leg]  # 4 legs

    is_fixed_payoff: bool
    settlement_risk: bool

    width: Decimal  # K2 - K1 (== min_payoff == max_payoff for a box)
    entry_cost: Decimal  # net debit per unit
    max_fees: Decimal  # per unit, sum of the 4 legs
    min_profit_per_unit: Decimal  # width - entry_cost - max_fees
    max_size: Decimal
    capital_required: Decimal  # max(entry_cost, 0) * max_size
    max_total_profit: Decimal  # min_profit_per_unit * max_size
    spot: Decimal | None = None  # underlying price at detection (moneyness on the payoff chart)

    @property
    def dedup_key(self) -> tuple[Any, ...]:
        # Identity is the structure itself — the winning venue mix is evolving
        # state captured in snapshots, not a distinct opportunity.
        return (
            self.strategy_type,
            self.underlying,
            self.expiry,
            tuple(float(k) for k in self.strikes),
        )
