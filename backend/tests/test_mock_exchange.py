from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from option_arb.exchanges.base import Instrument, OrderRequest
from option_arb.exchanges.mock import MockExchange, make_book
from option_arb.exchanges.slippage import SlippageModel


def _inst(name: str = "BTC-20260101-30000-C") -> Instrument:
    return Instrument(
        exchange="mock",
        instrument_name=name,
        normalized_name=name,
        underlying="BTC",
        expiry=datetime.now(tz=UTC) + timedelta(days=30),
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0003"),
    )


@pytest.mark.asyncio
async def test_slippage_walks_the_book() -> None:
    model = SlippageModel(
        noise_stdev_bps=0, reject_prob=0, latency_min_sec=0, latency_max_sec=0, rng_seed=42
    )
    ex = MockExchange("derive", slippage=model)
    inst = _inst()
    ex.set_instruments([inst])
    ex.set_book(
        inst.instrument_name,
        make_book(
            "mock",
            inst.normalized_name,
            bids=[("100", "10"), ("99", "10")],
            asks=[("101", "3"), ("102", "10")],  # 3 units at 101, then 102
        ),
    )

    order = OrderRequest(
        exchange="mock",
        instrument=inst.instrument_name,
        side="BUY",
        size=Decimal("5"),
        limit_price=Decimal("110"),
    )
    result = await ex.place_order(order)
    assert result.status == "FILLED"
    # 3@101 + 2@102 = (303+204)/5 = 101.4
    assert result.filled_size == Decimal("5")
    assert result.filled_price == Decimal("101.4")


@pytest.mark.asyncio
async def test_slippage_respects_limit_price() -> None:
    model = SlippageModel(
        noise_stdev_bps=0, reject_prob=0, latency_min_sec=0, latency_max_sec=0, rng_seed=1
    )
    ex = MockExchange("derive", slippage=model)
    inst = _inst()
    ex.set_instruments([inst])
    ex.set_book(
        inst.instrument_name, make_book("mock", inst.normalized_name, bids=[], asks=[("105", "10")])
    )
    order = OrderRequest(
        exchange="mock",
        instrument=inst.instrument_name,
        side="BUY",
        size=Decimal("1"),
        limit_price=Decimal("100"),
    )
    r = await ex.place_order(order)
    assert r.status == "REJECTED"
    assert r.reason == "limit_price_missed"


@pytest.mark.asyncio
async def test_partial_fill_when_book_shallow() -> None:
    model = SlippageModel(
        noise_stdev_bps=0, reject_prob=0, latency_min_sec=0, latency_max_sec=0, rng_seed=7
    )
    ex = MockExchange("derive", slippage=model)
    inst = _inst()
    ex.set_instruments([inst])
    ex.set_book(
        inst.instrument_name, make_book("mock", inst.normalized_name, bids=[], asks=[("101", "2")])
    )
    order = OrderRequest(
        exchange="mock",
        instrument=inst.instrument_name,
        side="BUY",
        size=Decimal("10"),
        limit_price=Decimal("110"),
    )
    r = await ex.place_order(order)
    assert r.status == "PARTIAL"
    assert r.filled_size == Decimal("2")


@pytest.mark.asyncio
async def test_random_rejection_honoured() -> None:
    model = SlippageModel(reject_prob=1.0, latency_min_sec=0, latency_max_sec=0, rng_seed=1)
    ex = MockExchange("derive", slippage=model)
    inst = _inst()
    ex.set_instruments([inst])
    ex.set_book(
        inst.instrument_name,
        make_book("mock", inst.normalized_name, bids=[("100", "10")], asks=[("101", "10")]),
    )
    order = OrderRequest(
        exchange="mock",
        instrument=inst.instrument_name,
        side="BUY",
        size=Decimal("1"),
        limit_price=Decimal("110"),
    )
    r = await ex.place_order(order)
    assert r.status == "REJECTED"
    assert r.reason == "random_reject"
