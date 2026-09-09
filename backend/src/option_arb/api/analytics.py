from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from sqlmodel import select

from option_arb.api.schemas import BacktestResponse, OpportunityResponse
from option_arb.config import Network
from option_arb.db.models import LiveStatus, Opportunity, OpportunityStatus
from option_arb.db.session import get_session
from option_arb.services.opportunity_backtest import BacktestPosition, simulate

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Bound the working set — the screener only persists materially-changed episodes
# and the worker prunes past `opportunity_retention_days`, so this is generous.
_MAX_ROWS = 10_000


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.get("/backtest", response_model=BacktestResponse)
async def backtest(
    days: int = Query(default=30, ge=1, le=365),
    symbol: str | None = None,
    buy_from: str | None = None,
    sell_to: str | None = None,
    network: Network | None = "mainnet",
    status: OpportunityStatus | None = None,
    live_status: LiveStatus | None = None,
    min_apr: float | None = None,
    min_profit: float | None = None,
    min_lifetime_sec: float = Query(default=0.0, ge=0.0),
    min_samples: int = Query(default=1, ge=1),
    one_position_per_instrument: bool = True,
    capital_budget_usd: float | None = Query(default=None, gt=0.0),
) -> dict[str, Any]:
    """Simulate a portfolio built from historical opportunities.

    Each opportunity is taken at ``detected_at``; ``capital_required`` is locked
    until the instrument ``expiry`` and ``net_profit`` realized there. See
    ``services.opportunity_backtest`` for the admission gates (dedup + budget).

    Every screener detection is a candidate regardless of executor ``status`` —
    ``REJECTED`` here usually just means the executor was disabled or capped, not
    that the dislocation was fake. Pass ``status`` to narrow (e.g. ``EXECUTED``).
    """
    now = datetime.now(UTC)
    since = now - timedelta(days=days)

    stmt = select(Opportunity).where(Opportunity.detected_at >= since)
    if symbol is not None:
        stmt = stmt.where(Opportunity.symbol == symbol)
    if buy_from is not None:
        stmt = stmt.where(Opportunity.buy_from == buy_from)
    if sell_to is not None:
        stmt = stmt.where(Opportunity.sell_to == sell_to)
    if network is not None:
        stmt = stmt.where(Opportunity.network == network)
    if status is not None:
        stmt = stmt.where(Opportunity.status == status)
    if live_status is not None:
        stmt = stmt.where(Opportunity.live_status == live_status)
    stmt = stmt.limit(_MAX_ROWS)

    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())

    positions: list[BacktestPosition] = []
    for row in rows:
        if row.samples_count < min_samples:
            continue
        detected = _aware(row.detected_at)
        expiry = _aware(row.expiry)
        if expiry <= detected:
            continue
        closed = _aware(row.closed_at) if row.closed_at else now
        if (closed - detected).total_seconds() < min_lifetime_sec:
            continue

        eco = OpportunityResponse.model_validate(row).effective
        if min_apr is not None and eco.apr_pct < min_apr:
            continue
        if min_profit is not None and eco.net_profit_usd < min_profit:
            continue
        if eco.capital_required_usd <= 0:
            continue

        positions.append(
            BacktestPosition(
                instrument=row.instrument,
                symbol=row.symbol,
                buy_from=row.buy_from,
                sell_to=row.sell_to,
                entry=detected,
                expiry=expiry,
                capital=Decimal(str(eco.capital_required_usd)),
                profit=Decimal(str(eco.net_profit_usd)),
                fees=Decimal(str(eco.fees_usd)),
            )
        )

    result = simulate(
        positions,
        capital_budget_usd=(
            Decimal(str(capital_budget_usd)) if capital_budget_usd is not None else None
        ),
        one_position_per_instrument=one_position_per_instrument,
        now=now,
    )
    return asdict(result)
