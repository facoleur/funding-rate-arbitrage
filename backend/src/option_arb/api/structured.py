from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from option_arb.api.schemas import (
    ErrorResponse,
    SortDirection,
    StructuredOpportunityResponse,
    StructuredSnapshotResponse,
    StructuredSortBy,
)
from option_arb.config import Network
from option_arb.db.models import (
    LiveStatus,
    StrategyType,
    StructuredOpportunity,
    StructuredOpportunitySnapshot,
)
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/structured-opportunities", tags=["structured"])

_SORT_COLS = {
    "detected_at": "detected_at",
    "last_seen_at": "last_seen_at",
    "max_total_profit_usd": "max_total_profit_usd",
    "peak_total_profit_usd": "peak_total_profit_usd",
    "min_profit": "min_profit",
    "max_size": "max_size",
    "capital_required_usd": "capital_required_usd",
    "samples_count": "samples_count",
}


@router.get("", response_model=list[StructuredOpportunityResponse])
async def list_structured_opportunities(
    strategy_type: StrategyType | None = None,
    underlying: str | None = None,
    min_profit_usd: float | None = None,
    cross_exchange_only: bool = False,
    exclude_settlement_risk: bool = False,
    live_status: LiveStatus | None = None,  # None = every status
    days: int | None = Query(default=None, ge=1, le=365),
    network: Network | None = "mainnet",
    sort_by: StructuredSortBy = "detected_at",
    sort_dir: SortDirection = "desc",
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[StructuredOpportunity]:
    col_expr = sa.text(f"{_SORT_COLS[sort_by]} {sort_dir.upper()}")
    stmt = select(StructuredOpportunity).order_by(col_expr).limit(limit).offset(offset)
    if strategy_type is not None:
        stmt = stmt.where(StructuredOpportunity.strategy_type == strategy_type)
    if underlying is not None:
        stmt = stmt.where(StructuredOpportunity.underlying == underlying)
    if min_profit_usd is not None:
        stmt = stmt.where(StructuredOpportunity.peak_total_profit_usd >= min_profit_usd)
    if cross_exchange_only:
        stmt = stmt.where(StructuredOpportunity.is_fixed_payoff == False)  # noqa: E712
    if exclude_settlement_risk:
        stmt = stmt.where(StructuredOpportunity.settlement_risk == False)  # noqa: E712
    if live_status is not None:
        stmt = stmt.where(StructuredOpportunity.live_status == live_status)
    if days is not None:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = stmt.where(
            sa.cast(StructuredOpportunity.detected_at, sa.DateTime(timezone=True)) >= since
        )
    if network is not None:
        stmt = stmt.where(StructuredOpportunity.network == network)
    async with get_session() as sess:
        return list((await sess.execute(stmt)).scalars())


@router.get(
    "/{opp_id}",
    response_model=StructuredOpportunityResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_structured_opportunity(opp_id: int) -> StructuredOpportunity:
    async with get_session() as sess:
        row = (
            await sess.execute(
                select(StructuredOpportunity).where(StructuredOpportunity.id == opp_id)
            )
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.get(
    "/{opp_id}/snapshots",
    response_model=list[StructuredSnapshotResponse],
    responses={404: {"model": ErrorResponse}},
)
async def get_structured_snapshots(opp_id: int) -> list[StructuredOpportunitySnapshot]:
    async with get_session() as sess:
        exists = (
            await sess.execute(
                select(StructuredOpportunity.id).where(StructuredOpportunity.id == opp_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(404, "not found")
        return list(
            (
                await sess.execute(
                    select(StructuredOpportunitySnapshot)
                    .where(StructuredOpportunitySnapshot.opportunity_id == opp_id)
                    .order_by(sa.text("ts ASC"))
                )
            ).scalars()
        )
