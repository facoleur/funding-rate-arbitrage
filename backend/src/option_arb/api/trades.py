from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from option_arb.db.models import Mode, Order, Trade, TradeStatus
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
async def list_trades(
    mode: Mode | None = None,
    status: TradeStatus | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
) -> list[dict]:
    stmt = select(Trade).order_by(Trade.opened_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    if mode is not None:
        stmt = stmt.where(Trade.mode == mode)
    if status is not None:
        stmt = stmt.where(Trade.status == status)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return [_serialize(r) for r in rows]


@router.get("/{trade_id}")
async def get_trade(trade_id: int) -> dict:
    async with get_session() as sess:
        row = (await sess.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "not found")
        orders = list(
            (await sess.execute(select(Order).where(Order.trade_id == trade_id))).scalars()
        )
    return {**_serialize(row), "orders": [_serialize_order(o) for o in orders]}


def _serialize(t: Trade) -> dict:
    return {
        "id": t.id,
        "opportunity_id": t.opportunity_id,
        "opened_at": t.opened_at.isoformat(),
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "mode": t.mode.value,
        "status": t.status.value,
        "buy_exchange": t.buy_exchange,
        "sell_exchange": t.sell_exchange,
        "requested_size": t.requested_size,
        "buy_fill_price": t.buy_fill_price,
        "buy_fill_size": t.buy_fill_size,
        "sell_fill_price": t.sell_fill_price,
        "sell_fill_size": t.sell_fill_size,
        "net_pnl_usd": t.net_pnl_usd,
        "slippage_pct": t.slippage_pct,
        "fees_usd": t.fees_usd,
        "error": t.error,
    }


def _serialize_order(o: Order) -> dict:
    return {
        "id": o.id,
        "exchange": o.exchange,
        "side": o.side.value,
        "kind": o.kind.value,
        "requested_price": o.requested_price,
        "requested_size": o.requested_size,
        "filled_price": o.filled_price,
        "filled_size": o.filled_size,
        "status": o.status.value,
        "exchange_order_id": o.exchange_order_id,
        "placed_at": o.placed_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
    }
