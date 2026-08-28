from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from option_arb.api.schemas import ExchangeStateResponse, PositionResponse
from option_arb.db.models import ExchangeState, Position
from option_arb.db.session import get_session

router = APIRouter(prefix="/api", tags=["positions"])


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions() -> list[Position]:
    async with get_session() as sess:
        return list((await sess.execute(select(Position))).scalars())


@router.get("/exchanges", response_model=list[ExchangeStateResponse])
async def list_exchange_state() -> list[ExchangeState]:
    async with get_session() as sess:
        return list((await sess.execute(select(ExchangeState))).scalars())
