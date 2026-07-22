from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlmodel import select

from option_arb.db.models import ExchangeState, Position
from option_arb.db.session import get_session

router = APIRouter(prefix="/api", tags=["positions"])


@router.get("/positions")
async def list_positions() -> list[dict[str, Any]]:
    async with get_session() as sess:
        rows = list((await sess.execute(select(Position))).scalars())
    return [
        {
            "id": p.id,
            "exchange": p.exchange,
            "instrument": p.instrument,
            "size": p.size,
            "avg_price": p.avg_price,
            "opened_at": p.opened_at.isoformat(),
            "last_seen_at": p.last_seen_at.isoformat(),
        }
        for p in rows
    ]


@router.get("/exchanges")
async def list_exchange_state() -> list[dict[str, Any]]:
    async with get_session() as sess:
        rows = list((await sess.execute(select(ExchangeState))).scalars())
    return [
        {
            "exchange": e.exchange,
            "balance_usd": e.balance_usd,
            "balances": e.balances or {},
            "margin_used_usd": e.margin_used_usd,
            "ws_status": e.ws_status.value,
            "rest_status": e.rest_status.value,
            "updated_at": e.updated_at.isoformat(),
        }
        for e in rows
    ]
