"""Critical safety tests: in paper mode, `place_order` must never touch
the real exchange, even when auth is configured and the executor picks up
a real opportunity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from option_arb.config import AppConfig, ExchangeConfig
from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    BookLevel,
    Instrument,
    OrderRequest,
    OrderResult,
    TickerUpdate,
)
from option_arb.exchanges.mock import MockExchange
from option_arb.exchanges.registry import build_exchanges
from option_arb.exchanges.slippage import SlippageModel


class _SpyRealExchange(AbstractExchange):
    """Records every call so we can assert place_order was never called."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ws_url = "ws://fake"
        self.place_order_called = 0
        self.cancel_order_called = 0

    async def list_instruments(self, underlying, max_expiries_ahead):
        return [Instrument(
            exchange=self.name,
            instrument_name=f"{underlying}-20261225-30000-C",
            normalized_name=f"{underlying}-20261225-30000-C",
            underlying=underlying,
            expiry=datetime.now(tz=timezone.utc) + timedelta(days=90),
            strike=Decimal("30000"), option_type="C",
            maker_fee_rate=Decimal("0"), taker_fee_rate=Decimal("0"),
        )]

    async def get_orderbook_l2(self, instrument):
        return Book(
            exchange=self.name, instrument=instrument.normalized_name,
            ts=datetime.now(tz=timezone.utc),
            bids=[BookLevel(price=Decimal("100"), size=Decimal("10"))],
            asks=[BookLevel(price=Decimal("101"), size=Decimal("10"))],
        )

    def ws_channels(self, instruments): return [f"ticker.{i.instrument_name}" for i in instruments]  # noqa: E704
    def parse_ws_message(self, raw): return None  # noqa: E704

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self.place_order_called += 1
        return OrderResult(status="FILLED", filled_size=order.size, filled_price=order.limit_price)

    async def cancel_order(self, exchange_order_id: str) -> bool:
        self.cancel_order_called += 1
        return True

    async def get_balance_usd(self): return Decimal(10_000)  # noqa: E704
    async def get_positions(self): return []  # noqa: E704


@pytest.mark.asyncio
async def test_paper_mode_never_calls_upstream_place_order() -> None:
    """The single most important safety test: even with a real upstream
    exchange wired in and executor.mode=paper, place_order MUST NOT touch it."""
    spy = _SpyRealExchange("deribit")
    mock = MockExchange(name="deribit", upstream=spy, slippage=SlippageModel(
        noise_stdev_bps=0, reject_prob=0, latency_min_sec=0, latency_max_sec=0, rng_seed=1,
    ))
    instruments = await mock.list_instruments("BTC", 4)
    inst = instruments[0]

    # Try placing many orders through the mock
    for _ in range(10):
        r = await mock.place_order(OrderRequest(
            exchange="deribit", instrument=inst.instrument_name,
            side="BUY", size=Decimal(1), limit_price=Decimal("110"),
            time_in_force="IOC",
        ))
        assert r.status in ("FILLED", "PARTIAL", "REJECTED")

    # The spy MUST have zero place_order calls
    assert spy.place_order_called == 0, (
        f"paper mode leaked {spy.place_order_called} orders to the real upstream!"
    )


@pytest.mark.asyncio
async def test_build_exchanges_wraps_all_in_mock_when_paper() -> None:
    """In paper mode, every configured exchange comes back wrapped in MockExchange."""
    cfg = AppConfig()
    cfg.executor.mode = "paper"
    cfg.screener.exchanges = ["deribit"]
    cfg.exchanges["deribit"] = ExchangeConfig(
        network="testnet", rest_rate_limit_per_sec=20, ws_max_subscriptions=500,
        rest_base_url="https://test.deribit.com/api/v2",
        ws_url="wss://test.deribit.com/ws/api/v2",
    )
    exchanges = build_exchanges(cfg)
    assert isinstance(exchanges["deribit"], MockExchange)
    assert exchanges["deribit"].upstream is not None  # real venue is behind it for reads


@pytest.mark.asyncio
async def test_build_exchanges_does_not_wrap_when_live() -> None:
    from option_arb.exchanges.deribit import DeribitExchange
    cfg = AppConfig()
    cfg.executor.mode = "live"
    cfg.screener.exchanges = ["deribit"]
    cfg.exchanges["deribit"] = ExchangeConfig(
        network="testnet", rest_rate_limit_per_sec=20, ws_max_subscriptions=500,
        rest_base_url="https://test.deribit.com/api/v2",
        ws_url="wss://test.deribit.com/ws/api/v2",
    )
    exchanges = build_exchanges(cfg)
    assert isinstance(exchanges["deribit"], DeribitExchange)
    assert not isinstance(exchanges["deribit"], MockExchange)
