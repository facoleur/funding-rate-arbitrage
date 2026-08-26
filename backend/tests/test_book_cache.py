from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from option_arb.exchanges.base import Instrument, TickerUpdate
from option_arb.market.book_cache import BookCache


def _inst(exchange: str, name: str = "BTC-20260101-30000-C", expiry_days: int = 30) -> Instrument:
    return Instrument(
        exchange=exchange,
        instrument_name=name,
        normalized_name=name,
        underlying="BTC",
        expiry=datetime.now(tz=UTC) + timedelta(days=expiry_days),
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0003"),
    )


def _upd(exchange: str, name: str = "BTC-20260101-30000-C", age_ms: int = 0) -> TickerUpdate:
    ts = datetime.now(UTC) - timedelta(milliseconds=age_ms)
    return TickerUpdate(
        exchange=exchange,
        instrument=name,
        ts=ts,
        bid_price=Decimal("100"),
        bid_size=Decimal("1"),
        ask_price=Decimal("101"),
        ask_size=Decimal("1"),
    )


def test_fresh_ticker_appears_in_snapshot() -> None:
    cache = BookCache(ttl_ms=5000)
    cache.register_instruments([_inst("derive")])
    cache.update(_upd("derive", age_ms=100))
    assert len(cache.snapshot()) == 1


def test_stale_ticker_excluded_from_snapshot() -> None:
    cache = BookCache(ttl_ms=5000)
    cache.register_instruments([_inst("derive")])
    cache.update(_upd("derive", age_ms=6000))
    assert cache.snapshot() == []


def test_ticker_near_boundary_is_included() -> None:
    cache = BookCache(ttl_ms=5000)
    cache.register_instruments([_inst("derive")])
    cache.update(_upd("derive", age_ms=4900))
    assert len(cache.snapshot()) == 1


def test_stale_ticker_excluded_from_by_normalized_name() -> None:
    cache = BookCache(ttl_ms=5000)
    cache.register_instruments([_inst("derive"), _inst("deribit")])
    cache.update(_upd("derive", age_ms=100))
    cache.update(_upd("deribit", age_ms=6000))
    groups = cache.by_normalized_name()
    tickers = groups.get("BTC-20260101-30000-C", [])
    assert len(tickers) == 1
    assert tickers[0].instrument.exchange == "derive"


def test_evict_expired_removes_past_instruments() -> None:
    cache = BookCache(ttl_ms=5000)
    live = _inst("derive", expiry_days=30)
    expired = _inst("deribit", name="BTC-20200101-10000-C", expiry_days=-1)
    cache.register_instruments([live, expired])
    cache.update(_upd("derive", age_ms=100))
    cache.update(_upd("deribit", name="BTC-20200101-10000-C", age_ms=100))

    evicted = cache.evict_expired()

    assert evicted == 1
    assert len(cache.snapshot()) == 1
    assert cache.snapshot()[0].instrument.exchange == "derive"


def test_evict_expired_returns_zero_when_nothing_to_evict() -> None:
    cache = BookCache()
    cache.register_instruments([_inst("derive", expiry_days=10)])
    cache.update(_upd("derive", age_ms=100))
    assert cache.evict_expired() == 0


def test_registered_names_reflects_eviction() -> None:
    cache = BookCache()
    expired = _inst("deribit", name="BTC-20200101-10000-C", expiry_days=-1)
    cache.register_instruments([expired])
    cache.evict_expired()
    assert "BTC-20200101-10000-C" not in cache.registered_names("deribit")
