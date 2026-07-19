from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    BookLevel,
    Instrument,
    OrderRequest,
    OrderResult,
    TickerUpdate,
)
from option_arb.exchanges.slippage import SlippageModel


class MockExchange(AbstractExchange):
    """Mirrors a real exchange for READ operations (instruments + book)
    but intercepts `place_order()` and simulates fills via SlippageModel.

    Two source modes (`upstream` parameter):
      - a real AbstractExchange instance → mirror mode (live paper trading)
      - None → replay/manual mode (books injected via `set_book`)"""

    def __init__(
        self,
        name: str,
        upstream: AbstractExchange | None = None,
        slippage: SlippageModel | None = None,
    ) -> None:
        # Keep the original name so opportunities cross-match with the real
        # exchange names in book_cache / comparator. The `mode="paper"` tag
        # on trades already distinguishes paper from live.
        self.name = name
        self.upstream = upstream
        # Preserve ws_url so WsManager can still connect to the real venue
        # in paper mirror mode (we consume real ticker stream, we just don't
        # send orders).
        self.ws_url = getattr(upstream, "ws_url", None)
        self.slippage = slippage or SlippageModel()
        self._books: dict[str, Book] = {}
        self._instruments: dict[str, Instrument] = {}
        self._counter = 0

    def set_book(self, instrument_name: str, book: Book) -> None:
        self._books[instrument_name] = book

    def set_instruments(self, instruments: list[Instrument]) -> None:
        for i in instruments:
            self._instruments[i.instrument_name] = i

    async def list_instruments(self, underlying: str, max_expiries_ahead: int) -> list[Instrument]:
        if self.upstream is not None:
            instruments = await self.upstream.list_instruments(underlying, max_expiries_ahead)
            # cache them so `place_order` can look them up later
            for inst in instruments:
                self._instruments[inst.instrument_name] = inst
            return instruments
        return [i for i in self._instruments.values() if i.underlying == underlying.upper()][
            : max_expiries_ahead * 4
        ]

    async def get_orderbook_l2(self, instrument: Instrument) -> Book:
        if instrument.instrument_name in self._books:
            return self._books[instrument.instrument_name]
        if self.upstream is not None:
            return await self.upstream.get_orderbook_l2(instrument)
        return Book(
            exchange=self.name,
            instrument=instrument.normalized_name,
            ts=datetime.now(UTC),
            bids=[],
            asks=[],
        )

    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        # Proxy to upstream so WsManager subscribes to the real venue in
        # mirror mode. Read-only — we consume the stream, don't emit.
        if self.upstream is not None:
            return self.upstream.ws_channels(instruments)
        return []

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        if self.upstream is not None:
            return self.upstream.parse_ws_message(raw)
        return None

    async def place_order(self, order: OrderRequest) -> OrderResult:
        instrument = self._instruments.get(order.instrument)
        if instrument is None:
            # try to find by normalized_name
            for i in self._instruments.values():
                if i.normalized_name == order.instrument:
                    instrument = i
                    break
        if instrument is None:
            return OrderResult(status="REJECTED", reason="unknown_instrument")
        book = await self.get_orderbook_l2(instrument)
        return await self.slippage.simulate(order, book)

    async def cancel_order(self, exchange_order_id: str) -> bool:
        return True

    async def get_balance_usd(self) -> Decimal:
        return Decimal(10_000)  # arbitrary paper balance

    async def get_positions(self) -> list[dict[str, Any]]:
        return []


def make_book(
    exchange: str, instrument: str, bids: list[tuple[str, str]], asks: list[tuple[str, str]]
) -> Book:
    """Helper for tests / manual replay."""
    return Book(
        exchange=exchange,
        instrument=instrument,
        ts=datetime.now(UTC),
        bids=[BookLevel(price=Decimal(p), size=Decimal(s)) for p, s in bids],
        asks=[BookLevel(price=Decimal(p), size=Decimal(s)) for p, s in asks],
    )
