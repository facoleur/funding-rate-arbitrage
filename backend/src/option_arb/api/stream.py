from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from option_arb.events import Event, bus

router = APIRouter(prefix="/api", tags=["stream"])


@router.get("/stream")
async def stream(request: Request) -> EventSourceResponse:
    q = bus.subscribe()

    async def gen() -> AsyncIterator[dict[str, Any]]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: Event = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    # keep-alive comment; sse-starlette handles ping automatically
                    yield {"event": "ping", "data": ""}
                    continue
                yield {
                    "event": event.type,
                    "data": json.dumps(
                        {
                            "level": event.level,
                            "message": event.message,
                            "ts": event.ts.isoformat(),
                            "payload": event.payload,
                        }
                    ),
                }
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(gen())
