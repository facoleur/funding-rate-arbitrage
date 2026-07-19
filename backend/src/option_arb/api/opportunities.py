from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from option_arb.db.models import Opportunity, OpportunityStatus
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("")
async def list_opportunities(
    status: OpportunityStatus | None = None,
    min_apr: float | None = None,
    limit: int = Query(default=100, le=1000),
) -> list[dict]:
    stmt = select(Opportunity).order_by(Opportunity.detected_at.desc()).limit(limit)  # type: ignore[attr-defined]
    if status is not None:
        stmt = stmt.where(Opportunity.status == status)
    if min_apr is not None:
        stmt = stmt.where(Opportunity.apr_pct >= min_apr)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return [_serialize(r) for r in rows]


@router.get("/{opp_id}")
async def get_opportunity(opp_id: int) -> dict:
    async with get_session() as sess:
        row = (
            await sess.execute(select(Opportunity).where(Opportunity.id == opp_id))
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return _serialize(row)


def _serialize(o: Opportunity) -> dict:
    return {
        "id": o.id,
        "detected_at": o.detected_at.isoformat(),
        "mode": o.mode.value,
        "instrument": o.instrument,
        "symbol": o.symbol,
        "expiry": o.expiry.isoformat(),
        "strike": o.strike,
        "option_type": o.option_type,
        "buy_from": o.buy_from,
        "sell_to": o.sell_to,
        "top_ask": o.top_ask,
        "top_bid": o.top_bid,
        "spread_pct": o.spread_pct,
        "apr_pct": o.apr_pct,
        "max_notional_usd": o.max_notional_usd,
        "status": o.status.value,
        "rejection_reason": o.rejection_reason,
    }
