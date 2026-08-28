from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import select

from option_arb.db.models import BookSnapshot
from option_arb.db.session import get_session
from option_arb.exchanges.base import Book, BookLevel, Instrument
from option_arb.record import _book_to_dict, _persist_snapshot


def _instrument() -> Instrument:
    return Instrument(
        exchange="derive",
        instrument_name="BTC-20270101-30000-C",
        normalized_name="BTC-20270101-30000-C",
        underlying="BTC",
        expiry=datetime(2027, 1, 1, tzinfo=UTC),
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal(0),
        taker_fee_rate=Decimal("0.0003"),
    )


@pytest.mark.asyncio
async def test_database_recording_preserves_underlying_price(test_db: str) -> None:
    instrument = _instrument()
    book = Book(
        exchange="derive",
        instrument=instrument.normalized_name,
        ts=datetime.now(UTC),
        bids=[BookLevel(price=Decimal("100"), size=Decimal("2"))],
        asks=[BookLevel(price=Decimal("101"), size=Decimal("2"))],
        underlying_price=Decimal("50000.25"),
    )

    record = _book_to_dict(instrument, book)
    await _persist_snapshot(instrument, record)

    async with get_session() as session:
        snapshot = (await session.execute(select(BookSnapshot))).scalar_one()
    assert snapshot.underlying_price == pytest.approx(50000.25)
