from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from option_arb.exchanges.base import Instrument, TickerUpdate


@dataclass
class CachedTicker:
    instrument: Instrument
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None
    underlying_price: Decimal | None
    ts: datetime


class BookCache:
    """In-memory cache of top-of-book tickers per (exchange, normalized_name).
    Fed by `WsManager` via the on_ticker callback; read by the screener."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], CachedTicker] = {}
        self._instruments: dict[tuple[str, str], Instrument] = {}

    def register_instruments(self, instruments: list[Instrument]) -> None:
        for inst in instruments:
            self._instruments[(inst.exchange, inst.normalized_name)] = inst

    def update(self, upd: TickerUpdate) -> None:
        key = (upd.exchange, upd.instrument)
        inst = self._instruments.get(key)
        if inst is None:
            # unknown instrument — ignore (either not registered yet or stale)
            return
        self._by_key[key] = CachedTicker(
            instrument=inst,
            bid_price=upd.bid_price,
            bid_size=upd.bid_size,
            ask_price=upd.ask_price,
            ask_size=upd.ask_size,
            underlying_price=upd.underlying_price,
            ts=upd.ts,
        )

    def snapshot(self) -> list[CachedTicker]:
        return list(self._by_key.values())

    def by_normalized_name(self) -> dict[str, list[CachedTicker]]:
        out: dict[str, list[CachedTicker]] = {}
        for ticker in self._by_key.values():
            out.setdefault(ticker.instrument.normalized_name, []).append(ticker)
        return out
