from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
    Fed by `WsManager` via the on_ticker callback; read by the screener.

    `ttl_ms`: tickers older than this are excluded from snapshot/by_normalized_name.
    `evict_expired()` removes instruments whose expiry has passed from the cache entirely."""

    def __init__(self, ttl_ms: int = 5000) -> None:
        self._ttl_ms = ttl_ms
        self._by_key: dict[tuple[str, str], CachedTicker] = {}
        self._instruments: dict[tuple[str, str], Instrument] = {}

    def register_instruments(self, instruments: list[Instrument]) -> None:
        for inst in instruments:
            self._instruments[(inst.exchange, inst.normalized_name)] = inst

    def update(self, upd: TickerUpdate) -> None:
        key = (upd.exchange, upd.instrument)
        inst = self._instruments.get(key)
        if inst is None:
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

    def evict_expired(self) -> int:
        """Remove instruments whose expiry has passed. Returns count removed."""
        now = datetime.now(UTC)
        expired_keys = [
            key
            for key, inst in self._instruments.items()
            if (inst.expiry if inst.expiry.tzinfo else inst.expiry.replace(tzinfo=UTC)) < now
        ]
        for key in expired_keys:
            self._instruments.pop(key, None)
            self._by_key.pop(key, None)
        return len(expired_keys)

    def registered_names(self, exchange: str) -> set[str]:
        return {name for (ex, name) in self._instruments if ex == exchange}

    def _is_fresh(self, ticker: CachedTicker) -> bool:
        ts = ticker.ts if ticker.ts.tzinfo else ticker.ts.replace(tzinfo=UTC)
        age_ms = (datetime.now(UTC) - ts).total_seconds() * 1000
        return age_ms <= self._ttl_ms

    def snapshot(self) -> list[CachedTicker]:
        return [t for t in self._by_key.values() if self._is_fresh(t)]

    def by_normalized_name(self) -> dict[str, list[CachedTicker]]:
        out: dict[str, list[CachedTicker]] = {}
        for ticker in self._by_key.values():
            if self._is_fresh(ticker):
                out.setdefault(ticker.instrument.normalized_name, []).append(ticker)
        return out
