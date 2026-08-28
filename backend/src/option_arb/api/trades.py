from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from option_arb.api.schemas import (
    ErrorResponse,
    OrderResponse,
    TradeDetailResponse,
    TradeResponse,
)
from option_arb.db.models import Mode, Order, Trade, TradeStatus
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=list[TradeResponse])
async def list_trades(
    mode: Mode | None = None,
    status: TradeStatus | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
) -> list[Trade]:
    stmt = select(Trade).order_by(Trade.opened_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    if mode is not None:
        stmt = stmt.where(Trade.mode == mode)
    if status is not None:
        stmt = stmt.where(Trade.status == status)
    async with get_session() as sess:
        return list((await sess.execute(stmt)).scalars())


@router.get(
    "/{trade_id}",
    response_model=TradeDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_trade(trade_id: int) -> TradeDetailResponse:
    async with get_session() as sess:
        row = (await sess.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "not found")
        orders = list(
            (await sess.execute(select(Order).where(Order.trade_id == trade_id))).scalars()
        )
    # `Trade` has no `orders` relationship (no eager loading in the async
    # session), so the detail view composes the two response models.
    return TradeDetailResponse(
        **TradeResponse.model_validate(row).model_dump(),
        orders=[OrderResponse.model_validate(o) for o in orders],
    )
