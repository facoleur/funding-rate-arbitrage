from __future__ import annotations

import asyncio

import pytest
from sqlmodel import select

from option_arb.config import AlertsConfig, TelegramConfig
from option_arb.db.models import Alert
from option_arb.db.session import get_session
from option_arb.events import Event, bus
from option_arb.services.alerter import Alerter, TelegramSender


class _FakeSender(TelegramSender):
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.bot_token = "x"
        self.chat_id = "y"

    async def send(self, text: str) -> bool:
        self.sent.append(text)
        return True

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_alerter_persists_events_to_db(test_db: str) -> None:
    sender = _FakeSender()
    alerts_cfg = AlertsConfig(telegram=TelegramConfig(enabled=False))
    alerter = Alerter(alerts_cfg, sender=sender)
    task = asyncio.create_task(alerter.run())
    await asyncio.sleep(0.02)  # let the alerter subscribe to the bus
    try:
        await bus.publish(Event(type="trade_filled", level="info", message="hello"))
        await asyncio.sleep(0.15)
    finally:
        await alerter.stop()
        await task

    async with get_session() as sess:
        rows = list((await sess.execute(select(Alert))).scalars())
    assert len(rows) == 1
    assert rows[0].level.value == "info"
    assert rows[0].message == "hello"
    assert "trade_filled" in (rows[0].meta or "")


@pytest.mark.asyncio
async def test_alerter_respects_apr_threshold(test_db: str) -> None:
    sender = _FakeSender()
    cfg = AlertsConfig(telegram=TelegramConfig(enabled=True, apr_threshold_pct=20))
    alerter = Alerter(cfg, sender=sender)
    task = asyncio.create_task(alerter.run())
    await asyncio.sleep(0.02)  # let the alerter subscribe to the bus
    try:
        # apr below threshold → not sent to telegram, but persisted
        await bus.publish(Event(type="opportunity_detected", level="info", message="low",
                                payload={"apr_pct": 5, "instrument": "x", "buy_from": "a", "sell_to": "b", "max_notional_usd": 1}))
        await bus.publish(Event(type="opportunity_detected", level="info", message="high",
                                payload={"apr_pct": 50, "instrument": "y", "buy_from": "a", "sell_to": "b", "max_notional_usd": 100}))
        await asyncio.sleep(0.2)
    finally:
        await alerter.stop()
        await task

    assert len(sender.sent) == 1
    assert "50" in sender.sent[0]

    async with get_session() as sess:
        rows = list((await sess.execute(select(Alert))).scalars())
    assert len(rows) == 2  # both persisted


@pytest.mark.asyncio
async def test_alerter_filters_by_level(test_db: str) -> None:
    sender = _FakeSender()
    cfg = AlertsConfig(telegram=TelegramConfig(enabled=True, apr_threshold_pct=0, levels=["error"]))
    alerter = Alerter(cfg, sender=sender)
    task = asyncio.create_task(alerter.run())
    await asyncio.sleep(0.02)  # let the alerter subscribe to the bus
    try:
        await bus.publish(Event(type="trade_filled", level="info", message="skip"))
        await bus.publish(Event(type="trade_stuck", level="error", message="alert!"))
        await asyncio.sleep(0.2)
    finally:
        await alerter.stop()
        await task

    assert len(sender.sent) == 1
    assert "alert" in sender.sent[0]
