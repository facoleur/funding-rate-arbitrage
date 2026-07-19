from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

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
]

Level = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class Event:
    type: EventType
    level: Level
    message: str
    ts: datetime = field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """In-process asyncio fan-out. Each subscriber gets its own queue so
    slow consumers don't block others."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def publish(self, event: Event) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # drop for this subscriber rather than block producers
                pass


bus = EventBus()
