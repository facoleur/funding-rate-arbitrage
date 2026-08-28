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
    min_trade_amount: Decimal = Decimal(0)
    # venue-native fields needed for signed orders (Derive uses base_asset_address + sub_id).
    # Optional so Deribit/Aevo can leave them None.
    asset_address: str | None = None
    asset_sub_id: int | None = None


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    size: Decimal


def walk_book(size: Decimal, levels: list[BookLevel]) -> tuple[Decimal, Decimal]:
    """Consume `levels` until `size` is filled or the book runs out.

    Returns `(volume_weighted_price, filled_size)`; `(0, 0)` when nothing can
    be filled. Shared by the executor (sizing a real trade) and the paper
    SlippageModel (simulating the fill) — the two must not drift."""
    if not levels or size <= 0:
        return Decimal(0), Decimal(0)
    remaining = size
    total_cost = Decimal(0)
    total_filled = Decimal(0)
    for lvl in levels:
        take = min(lvl.size, remaining)
        total_cost += take * lvl.price
        total_filled += take
        remaining -= take
        if remaining <= 0:
            break
    if total_filled == 0:
        return Decimal(0), Decimal(0)
    return total_cost / total_filled, total_filled


@dataclass(frozen=True)
class Book:
    """L2 order book snapshot. `bids` sorted desc by price, `asks` sorted asc."""

    exchange: str
    instrument: str
    ts: datetime
    bids: list[BookLevel] = field(default_factory=list)
    asks: list[BookLevel] = field(default_factory=list)
    underlying_price: Decimal | None = None

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
    is_heartbeat: bool = False


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
    ws_url: str | None = None

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
    def ws_subscribe_payloads(self, channels: list[str]) -> list[dict[str, Any]]:
        """Return the messages that subscribe to `channels`, in send order.

        Batching belongs here: venues cap frame size (Deribit rejects
        messages over 32KB), and only the adapter knows its wire format."""

    @abstractmethod
    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | list[TickerUpdate] | None:
        """Parse a raw WS message into one or more ticker updates, or None if unrelated."""

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str) -> bool: ...

    @abstractmethod
    async def get_balances(self) -> dict[str, Decimal]:
        """Return per-token balances, e.g. {"BTC": Decimal("0.05"), "USDC": Decimal("50")}."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Return raw position dicts. Callers normalize into DB Position rows."""

    async def get_available_funds(self) -> dict[str, Decimal]:
        """Fonds disponibles pour de nouvelles positions (hors marge déjà engagée).
        Default no-op — les exchanges non-authentifiés retournent {}."""
        return {}

    async def aclose(self) -> None:
        """Release network resources. Default no-op — adapters holding a
        RestClient override it."""
        return None
