from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from option_arb.config import AppConfig
from option_arb.db.models import ExchangeState
from option_arb.db.session import get_session
from option_arb.events import Event, bus
from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    OrderResult,
)
from option_arb.services.rebalancer import Rebalancer


class _FakeEx(AbstractExchange):
    def __init__(
        self, name: str, *, balance: float, positions: list[dict], raise_: bool = False
    ) -> None:
        self.name = name
        self._balance = balance
        self._positions = positions
        self._raise = raise_

    async def get_balance_usd(self) -> Decimal:
        if self._raise:
            raise RuntimeError("down")
        return Decimal(str(self._balance))

    async def get_positions(self) -> list[dict[str, Any]]:
        if self._raise:
            raise RuntimeError("down")
        return self._positions

    # unused abstract methods
    async def list_instruments(self, u, m):
        return []

    async def get_orderbook_l2(self, i):
        return Book(exchange=self.name, instrument="", ts=datetime.now(UTC))

    def ws_channels(self, instruments):
        return []

    def parse_ws_message(self, raw):
        return None

    async def place_order(self, order):
        return OrderResult(status="REJECTED")

    async def cancel_order(self, x):
        return False


async def _collect_events(evt_type: str, timeout: float = 0.15) -> list[Event]:
    q = bus.subscribe()
    collected: list[Event] = []
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.02)
                if ev.type == evt_type:
                    collected.append(ev)
            except TimeoutError:
                continue
    finally:
        bus.unsubscribe(q)
    return collected


@pytest.mark.asyncio
async def test_rebalancer_alerts_on_low_balance(test_db: str) -> None:
    cfg = AppConfig()
    cfg.rebalancer.balance_low_threshold_usd = 500.0
    ex = _FakeEx("derive", balance=100.0, positions=[])
    reb = Rebalancer(cfg, {"derive": ex})

    q = bus.subscribe()
    await reb._tick()
    events: list[Event] = []
    while not q.empty():
        events.append(await q.get())
    bus.unsubscribe(q)

    low = [e for e in events if e.type == "balance_low"]
    assert len(low) == 1
    assert low[0].payload["exchange"] == "derive"

    # exchange_state row written
    async with get_session() as sess:
        state = await sess.get(ExchangeState, "derive")
    assert state is not None and state.balance_usd == 100.0


@pytest.mark.asyncio
async def test_rebalancer_alerts_on_position_expiring(test_db: str) -> None:
    cfg = AppConfig()
    cfg.rebalancer.expiry_warning_hours = 24
    soon = datetime.now(UTC) + timedelta(hours=12)
    ex = _FakeEx(
        "deribit",
        balance=5000.0,
        positions=[
            {"instrument": "BTC-…-C", "size": 1.0, "avg_price": 100, "expiry": soon.isoformat()}
        ],
    )
    reb = Rebalancer(cfg, {"deribit": ex})

    q = bus.subscribe()
    await reb._tick()
    events: list[Event] = []
    while not q.empty():
        events.append(await q.get())
    bus.unsubscribe(q)

    expiring = [e for e in events if e.type == "position_expiring"]
    assert len(expiring) == 1


@pytest.mark.asyncio
async def test_rebalancer_marks_unhealthy_on_fetch_error(test_db: str) -> None:
    cfg = AppConfig()
    ex = _FakeEx("aevo", balance=0, positions=[], raise_=True)
    reb = Rebalancer(cfg, {"aevo": ex})

    q = bus.subscribe()
    await reb._tick()
    events: list[Event] = []
    while not q.empty():
        events.append(await q.get())
    bus.unsubscribe(q)

    unhealthy = [e for e in events if e.type == "exchange_unhealthy"]
    assert len(unhealthy) == 1
    async with get_session() as sess:
        state = await sess.get(ExchangeState, "aevo")
    assert state is not None
    assert state.rest_status.value == "DOWN"
