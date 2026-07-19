from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from option_arb.config import AppConfig
from option_arb.db.models import Opportunity
from option_arb.db.session import get_session
from option_arb.exchanges.base import Instrument, TickerUpdate
from option_arb.market.book_cache import BookCache
from option_arb.services.screener import Screener


def _inst(exchange: str, expiry_days: int = 30) -> Instrument:
    return Instrument(
        exchange=exchange,
        instrument_name="BTC-20260101-30000-C",
        normalized_name="BTC-20260101-30000-C",
        underlying="BTC",
        expiry=datetime.now(tz=UTC) + timedelta(days=expiry_days),
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0003"),
    )


@pytest.mark.asyncio
async def test_screener_writes_opportunity_when_thresholds_met(test_db: str) -> None:
    cache = BookCache()
    cache.register_instruments([_inst("derive"), _inst("deribit")])
    now = datetime.now(tz=UTC)
    cache.update(
        TickerUpdate(
            exchange="derive",
            instrument="BTC-20260101-30000-C",
            ts=now,
            bid_price=Decimal("100"),
            bid_size=Decimal("10"),
            ask_price=Decimal("101"),
            ask_size=Decimal("10"),
        )
    )
    cache.update(
        TickerUpdate(
            exchange="deribit",
            instrument="BTC-20260101-30000-C",
            ts=now,
            bid_price=Decimal("110"),
            bid_size=Decimal("10"),
            ask_price=Decimal("112"),
            ask_size=Decimal("10"),
        )
    )

    await Screener(cache, AppConfig())._tick()

    async with get_session() as sess:
        rows = list((await sess.execute(select(Opportunity))).scalars())
    assert len(rows) == 1
    assert rows[0].buy_from == "derive"
    assert rows[0].sell_to == "deribit"


@pytest.mark.asyncio
async def test_screener_skips_when_apr_below_threshold(test_db: str) -> None:
    cache = BookCache()
    d = _inst("derive", expiry_days=365)
    b = _inst("deribit", expiry_days=365)
    cache.register_instruments([d, b])
    now = datetime.now(tz=UTC)
    cache.update(
        TickerUpdate(
            exchange="derive",
            instrument=d.normalized_name,
            ts=now,
            bid_price=Decimal("100"),
            bid_size=Decimal("10"),
            ask_price=Decimal("100.5"),
            ask_size=Decimal("10"),
        )
    )
    cache.update(
        TickerUpdate(
            exchange="deribit",
            instrument=b.normalized_name,
            ts=now,
            bid_price=Decimal("101"),
            bid_size=Decimal("10"),
            ask_price=Decimal("102"),
            ask_size=Decimal("10"),
        )
    )

    await Screener(cache, AppConfig())._tick()

    async with get_session() as sess:
        rows = list((await sess.execute(select(Opportunity))).scalars())
    assert rows == []
