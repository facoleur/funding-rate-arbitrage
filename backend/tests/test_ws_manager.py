from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    Instrument,
    OrderRequest,
    OrderResult,
    TickerUpdate,
)
from option_arb.market.ws_manager import WsManager


class _FakeExchange(AbstractExchange):
    """Minimal fake — captures ws_channels + parse_ws_message calls."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ws_url = "ws://fake"
        self.parsed: list[dict[str, Any]] = []

    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        return [f"ticker.{i.instrument_name}.100ms" for i in instruments]

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        self.parsed.append(raw)
        if raw.get("type") == "tick":
            return TickerUpdate(
                exchange=self.name,
                instrument=raw["instrument"],
                ts=datetime.now(timezone.utc),
                bid_price=Decimal("100"), bid_size=Decimal("1"),
                ask_price=Decimal("101"), ask_size=Decimal("1"),
            )
        return None

    async def list_instruments(self, underlying: str, max_expiries_ahead: int) -> list[Instrument]: return []  # noqa: E704
    async def get_orderbook_l2(self, instrument): return Book(exchange=self.name, instrument="", ts=datetime.now(timezone.utc))  # noqa: E704
    async def place_order(self, order: OrderRequest) -> OrderResult: return OrderResult(status="REJECTED")  # noqa: E704
    async def cancel_order(self, exchange_order_id: str) -> bool: return False  # noqa: E704
    async def get_balance_usd(self) -> Decimal: return Decimal(0)  # noqa: E704
    async def get_positions(self) -> list[dict[str, Any]]: return []  # noqa: E704


def _inst(name: str = "BTC-20260101-30000-C") -> Instrument:
    return Instrument(
        exchange="fake", instrument_name=name, normalized_name=name,
        underlying="BTC", expiry=datetime.now(tz=timezone.utc) + timedelta(days=30),
        strike=Decimal("30000"), option_type="C",
        maker_fee_rate=Decimal("0"), taker_fee_rate=Decimal("0"),
    )


class _FakeWS:
    """Minimal websocket stub compatible with websockets>=13 client API."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self.sent: list[str] = []
        self.closed = False

    async def __aenter__(self) -> _FakeWS:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    async def send(self, msg: str) -> None:
        self.sent.append(msg)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


@pytest.mark.asyncio
async def test_subscribe_payload_uses_exchange_shape(monkeypatch) -> None:
    """WsManager should send the right subscribe shape per exchange
    (JSON-RPC for deribit/derive, `op:subscribe` for the fallback/aevo)."""
    ex = _FakeExchange("deribit")
    inst = _inst()

    fake = _FakeWS([json.dumps({"type": "tick", "instrument": inst.normalized_name})])

    def _fake_connect(url, **kwargs):
        return fake

    monkeypatch.setattr("option_arb.market.ws_manager.websockets.connect", _fake_connect)

    received: list[TickerUpdate] = []
    async def on_ticker(upd: TickerUpdate) -> None:
        received.append(upd)

    mgr = WsManager({"deribit": ex}, on_ticker=on_ticker, ping_interval_sec=1000, ping_timeout_sec=1000)
    await mgr.start({"deribit": [inst]})
    # give the read loop a chance to process the fake message + exit
    await asyncio.sleep(0.05)
    await mgr.stop()

    assert len(fake.sent) == 1
    subscribe = json.loads(fake.sent[0])
    assert subscribe["method"] == "public/subscribe"
    assert subscribe["params"]["channels"] == [f"ticker.{inst.instrument_name}.100ms"]
    assert len(received) == 1
    assert received[0].instrument == inst.normalized_name


@pytest.mark.asyncio
async def test_ws_manager_status_reflects_connection(monkeypatch) -> None:
    ex = _FakeExchange("aevo")
    inst = _inst()

    fake = _FakeWS([])  # no messages → loop exits immediately after subscribe

    def _fake_connect(url, **kwargs):
        return fake

    monkeypatch.setattr("option_arb.market.ws_manager.websockets.connect", _fake_connect)

    async def on_ticker(upd: TickerUpdate) -> None: return None
    mgr = WsManager({"aevo": ex}, on_ticker=on_ticker)
    await mgr.start({"aevo": [inst]})
    # let it connect + read one message + disconnect
    await asyncio.sleep(0.05)
    # aevo uses op:subscribe shape
    payload = json.loads(fake.sent[0])
    assert payload["op"] == "subscribe"
    await mgr.stop()


@pytest.mark.asyncio
async def test_ws_manager_reconnects_after_drop(monkeypatch) -> None:
    """When the ws exits (message iter ends), the manager should reconnect."""
    ex = _FakeExchange("deribit")
    inst = _inst()

    call_count = 0

    def _fake_connect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeWS([])  # empty → loop exits fast

    monkeypatch.setattr("option_arb.market.ws_manager.websockets.connect", _fake_connect)

    async def on_ticker(upd: TickerUpdate) -> None: return None
    mgr = WsManager({"deribit": ex}, on_ticker=on_ticker)
    # aggressive: make backoff essentially zero for testing
    mgr._max_backoff_sec = 0.01
    await mgr.start({"deribit": [inst]})
    await asyncio.sleep(0.15)
    await mgr.stop()

    assert call_count >= 2  # reconnected at least once
