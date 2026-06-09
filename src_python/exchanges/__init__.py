from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExchangeName = Literal["derive", "deribit", "aevo"]


@dataclass(slots=True)
class OptionQuote:
    exchange: ExchangeName
    normalized_name: str
    instrument_name: str
    strike: float
    expiry: int
    option_type: str
    maker_fee_rate: float
    taker_fee_rate: float
    underlying_price: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    bid_price_raw: float | None = None
    ask_price_raw: float | None = None
    bid_qty: float | None = None
    ask_qty: float | None = None

