from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast, get_args

log = logging.getLogger(__name__)

EventType = Literal[
    "opportunity_detected",
    "trade_opened",
    "trade_filled",
    "trade_failed",
    "trade_stuck",
    "kill_switch_tripped",
    "position_expiring",
    "balance_low",
    "exchange_unhealthy",
    "perp_hedge_rebalanced",
]

Level = Literal["info", "warn", "error"]

_EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))
_LEVELS: frozenset[str] = frozenset(get_args(Level))


@dataclass(frozen=True)
class Event:
    type: EventType
    level: Level
    message: str
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "level": self.level,
                "message": self.message,
                "ts": self.ts.isoformat(),
                "payload": self.payload,
            }
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Event | None:
        """Rebuild an Event received from another process. Returns None on
        anything malformed — a bad payload must never kill the listener."""
        if raw.get("type") not in _EVENT_TYPES or raw.get("level") not in _LEVELS:
            return None
        try:
            ts = datetime.fromisoformat(raw["ts"])
        except (KeyError, TypeError, ValueError):
            ts = datetime.now(UTC)
        payload = raw.get("payload")
        return cls(
            type=cast(EventType, raw["type"]),
            level=cast(Level, raw["level"]),
            message=str(raw.get("message", "")),
            ts=ts if ts.tzinfo else ts.replace(tzinfo=UTC),
            payload=payload if isinstance(payload, dict) else {},
        )


Relay = Callable[[Event], Awaitable[None]]


class EventBus:
    """In-process asyncio fan-out. Each subscriber gets its own queue so
    slow consumers don't block others.

    The backend runs as three separate containers (`api`, `workers`,
    `executor`), so an in-process bus alone would strand every event in the
    process that emitted it. Attaching a relay (see `db.event_relay`) makes
    `publish()` also cross the process boundary; `deliver_local()` is the
    entry-point the relay uses for events arriving from elsewhere."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._relay: Relay | None = None

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def attach_relay(self, relay: Relay | None) -> None:
        """Route locally-published events to other processes too."""
        self._relay = relay

    def deliver_local(self, event: Event) -> None:
        """Fan out to this process's subscribers only. Never re-enters the
        relay — that would bounce the event back and forth forever."""
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    async def publish(self, event: Event) -> None:
        self.deliver_local(event)
        if self._relay is not None:
            try:
                await self._relay(event)
            except Exception as e:
                # A broken relay must never break the emitter (the executor
                # publishes mid state-machine).
                log.warning("event relay failed for %s: %s", event.type, e)


bus = EventBus()
