from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class Instrument:
    exchange: str
    instrument_name: str  # exchange-native
    normalized_name: str  # "{UNDERLYING}-{YYYYMMDD}-{STRIKE}-{C|P}"
    underlying: str
    expiry: datetime
    strike: Decimal
    option_type: Literal["C", "P"]
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    # venue-native fields needed for signed orders (Derive uses base_asset_address + sub_id).
    # Optional so Deribit/Aevo can leave them None.
    asset_address: str | None = None
    asset_sub_id: int | None = None


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class Book:
    """L2 order book snapshot. `bids` sorted desc by price, `asks` sorted asc."""

    exchange: str
    instrument: str
    ts: datetime
    bids: list[BookLevel] = field(default_factory=list)
    asks: list[BookLevel] = field(default_factory=list)

    @property
    def top_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def top_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True)
class TickerUpdate:
    """WS ticker push: top-of-book snapshot."""

    exchange: str
    instrument: str
    ts: datetime
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None
    underlying_price: Decimal | None = None


@dataclass(frozen=True)
class OrderRequest:
    exchange: str
    instrument: str
    side: Literal["BUY", "SELL"]
    size: Decimal
    limit_price: Decimal
    time_in_force: Literal["IOC", "GTC", "FOK"] = "IOC"


@dataclass(frozen=True)
class OrderResult:
    status: Literal["FILLED", "PARTIAL", "REJECTED", "CANCELLED"]
    filled_size: Decimal = Decimal(0)
    filled_price: Decimal = Decimal(0)
    exchange_order_id: str | None = None
    reason: str | None = None
    raw_response: dict[str, Any] | None = None


class AbstractExchange(ABC):
    """Common interface for real + mock exchanges. All adapters MUST
    emit `normalized_name = {UNDERLYING}-{YYYYMMDD}-{STRIKE}-{C|P}`
    so cross-venue matching works.

    Adapters take an optional `Authenticator` (see `exchanges.auth`).
    Public paths never touch it. Private paths (`place_order`, `cancel_order`,
    `get_balance_usd`, `get_positions`) MUST call it; without one, they
    must return REJECTED / empty results instead of hitting the network."""

    name: str

    @abstractmethod
    async def list_instruments(
        self, underlying: str, max_expiries_ahead: int
    ) -> list[Instrument]: ...

    @abstractmethod
    async def get_orderbook_l2(self, instrument: Instrument) -> Book: ...

    @abstractmethod
    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        """Return the WS channel names to subscribe for the given instruments."""

    @abstractmethod
    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        """Parse a raw WS message into a ticker update, or None if unrelated."""

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str) -> bool: ...

    @abstractmethod
    async def get_balance_usd(self) -> Decimal: ...

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Return raw position dicts. Callers normalize into DB Position rows."""
