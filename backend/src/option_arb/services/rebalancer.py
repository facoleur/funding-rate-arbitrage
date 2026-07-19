from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import select

from option_arb.config import AppConfig
from option_arb.db.models import ExchangeState, Position, RestStatus, WsStatus
from option_arb.db.session import get_session
from option_arb.events import Event, bus
from option_arb.exchanges.base import AbstractExchange

log = logging.getLogger(__name__)


class Rebalancer:
    """Monitoring-only rebalancer. Every N seconds:
      1. Refresh balances + positions per exchange (writes exchange_state + positions).
      2. Emit alerts for: positions expiring < N hours, low balance, delta imbalance.

    No auto action (no fund transfers, no auto close). MVP scope."""

    def __init__(self, config: AppConfig, exchanges: dict[str, AbstractExchange]) -> None:
        self.config = config
        self.exchanges = exchanges
        self._stop = asyncio.Event()

    async def run(self) -> None:
        interval = self.config.rebalancer.poll_interval_sec
        log.info("rebalancer started (interval=%ds)", interval)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                log.exception("rebalancer tick failed: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def _tick(self) -> None:
        cfg = self.config.rebalancer
        threshold = cfg.balance_low_threshold_usd
        expiry_h = cfg.expiry_warning_hours
        now = datetime.now(UTC)
        expiry_cutoff = now + timedelta(hours=expiry_h)

        for name, ex in self.exchanges.items():
            try:
                balance = await ex.get_balance_usd()
                positions = await ex.get_positions()
            except Exception as e:
                log.warning("rebalancer fetch failed for %s: %s", name, e)
                await self._mark_unhealthy(name)
                await bus.publish(
                    Event(
                        type="exchange_unhealthy",
                        level="warn",
                        message=f"exchange {name} unreachable: {e}",
                        payload={"exchange": name},
                    )
                )
                continue

            await self._upsert_exchange_state(name, float(balance))

            if float(balance) < threshold:
                await bus.publish(
                    Event(
                        type="balance_low",
                        level="warn",
                        message=f"{name} balance ${float(balance):.2f} < ${threshold}",
                        payload={"exchange": name, "balance_usd": float(balance)},
                    )
                )

            for pos in positions:
                await self._upsert_position(name, pos, now)
                exp_raw = pos.get("expiry")
                if exp_raw:
                    exp = _to_dt(exp_raw)
                    if exp and exp <= expiry_cutoff:
                        await bus.publish(
                            Event(
                                type="position_expiring",
                                level="warn",
                                message=f"{name} {pos.get('instrument')} expires at {exp.isoformat()}",
                                payload={"exchange": name, **pos},
                            )
                        )

    async def _upsert_exchange_state(self, exchange: str, balance_usd: float) -> None:
        async with get_session() as sess:
            existing = await sess.get(ExchangeState, exchange)
            if existing is None:
                sess.add(
                    ExchangeState(
                        exchange=exchange,
                        balance_usd=balance_usd,
                        ws_status=WsStatus.CONNECTED,
                        rest_status=RestStatus.OK,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                existing.balance_usd = balance_usd
                existing.rest_status = RestStatus.OK
                existing.updated_at = datetime.now(UTC)
            await sess.commit()

    async def _mark_unhealthy(self, exchange: str) -> None:
        async with get_session() as sess:
            existing = await sess.get(ExchangeState, exchange)
            if existing is None:
                sess.add(
                    ExchangeState(
                        exchange=exchange,
                        rest_status=RestStatus.DOWN,
                        ws_status=WsStatus.UNHEALTHY,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                existing.rest_status = RestStatus.DOWN
                existing.updated_at = datetime.now(UTC)
            await sess.commit()

    async def _upsert_position(self, exchange: str, pos: dict[str, Any], now: datetime) -> None:
        instrument = pos.get("instrument")
        if not instrument:
            return
        async with get_session() as sess:
            row = (
                await sess.execute(
                    select(Position).where(
                        Position.exchange == exchange, Position.instrument == instrument
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                sess.add(
                    Position(
                        exchange=exchange,
                        instrument=instrument,
                        size=float(pos.get("size") or 0),
                        avg_price=float(pos.get("avg_price") or 0),
                        opened_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                row.size = float(pos.get("size") or 0)
                row.avg_price = float(pos.get("avg_price") or row.avg_price)
                row.last_seen_at = now
            await sess.commit()


def _to_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OSError, ValueError):
            return None
    return None
