from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from option_arb.db.models import Opportunity, OpportunityStatus
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("/stats")
async def opportunity_stats(
    days: int = Query(default=30, ge=1, le=365),
    symbol: str | None = None,
    network: str | None = None,
) -> list[dict[str, Any]]:
    """Opportunités agrégées par paire d'exchanges sur N jours."""
    from datetime import UTC, datetime, timedelta

    import sqlalchemy as sa

    since = datetime.now(UTC) - timedelta(days=days)
    clauses = ["detected_at >= :since", "status != 'REJECTED'"]
    params: dict[str, Any] = {"since": since}
    if symbol:
        clauses.append("symbol = :symbol")
        params["symbol"] = symbol
    if network:
        clauses.append("network = :network")
        params["network"] = network
    where = " AND ".join(clauses)
    sql = sa.text(
        f"""
        SELECT
            buy_from,
            sell_to,
            COUNT(*)                                              AS count,
            SUM(max_notional_usd * spread_pct / 100)             AS total_net_profit_usd,
            SUM(max_notional_usd * fee_pct    / 100)             AS total_fees_usd,
            AVG(apr_pct)                                          AS avg_apr_pct,
            MAX(max_notional_usd * spread_pct / 100)             AS best_net_profit_usd
        FROM opportunities
        WHERE {where}
        GROUP BY buy_from, sell_to
        ORDER BY total_net_profit_usd DESC
        """
    )

    async with get_session() as sess:
        rows = list((await sess.execute(sql, params)).mappings())

    return [
        {
            "buy_from": r["buy_from"],
            "sell_to": r["sell_to"],
            "pair": f"{r['buy_from']} → {r['sell_to']}",
            "count": int(r["count"]),
            "total_net_profit_usd": round(float(r["total_net_profit_usd"] or 0), 2),
            "total_fees_usd": round(float(r["total_fees_usd"] or 0), 2),
            "avg_apr_pct": round(float(r["avg_apr_pct"] or 0), 1),
            "best_net_profit_usd": round(float(r["best_net_profit_usd"] or 0), 2),
        }
        for r in rows
    ]


_SORT_COLS = {
    "detected_at": "detected_at",
    "apr_pct": "apr_pct",
    "spread_pct": "spread_pct",
    "net_profit_usd": "max_notional_usd * spread_pct / 100",
    "max_notional_usd": "max_notional_usd",
    "fees_usd": "max_notional_usd * fee_pct / 100",
}


@router.get("")
async def list_opportunities(
    status: OpportunityStatus | None = None,
    min_apr: float | None = None,
    min_profit: float | None = None,
    symbol: str | None = None,
    buy_from: str | None = None,
    sell_to: str | None = None,
    days: int | None = None,
    network: str | None = "mainnet",
    sort_by: str = Query(
        default="detected_at",
        pattern="^(detected_at|apr_pct|spread_pct|net_profit_usd|max_notional_usd|fees_usd)$",
    ),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    from datetime import UTC, datetime, timedelta

    import sqlalchemy as sa

    col_expr = sa.text(f"{_SORT_COLS[sort_by]} {sort_dir.upper()}")
    stmt = select(Opportunity).order_by(col_expr).limit(limit).offset(offset)
    if status is not None:
        stmt = stmt.where(Opportunity.status == status)
    if min_apr is not None:
        stmt = stmt.where(Opportunity.apr_pct >= min_apr)
    if min_profit is not None:
        stmt = stmt.where(
            sa.text("max_notional_usd * spread_pct / 100 >= :mp").bindparams(mp=min_profit)
        )
    if symbol is not None:
        stmt = stmt.where(Opportunity.symbol == symbol)
    if buy_from is not None:
        stmt = stmt.where(Opportunity.buy_from == buy_from)
    if sell_to is not None:
        stmt = stmt.where(Opportunity.sell_to == sell_to)
    if days is not None:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = stmt.where(sa.cast(Opportunity.detected_at, sa.DateTime(timezone=True)) >= since)
    if network is not None:
        stmt = stmt.where(Opportunity.network == network)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return [_serialize(r) for r in rows]


@router.get("/{opp_id}")
async def get_opportunity(opp_id: int) -> dict[str, Any]:
    async with get_session() as sess:
        row = (
            await sess.execute(select(Opportunity).where(Opportunity.id == opp_id))
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return _serialize(row)


def _serialize(o: Opportunity) -> dict[str, Any]:
    net_profit = o.max_notional_usd * o.spread_pct / 100
    fees = o.max_notional_usd * o.fee_pct / 100
    expiry_utc = o.expiry if o.expiry.tzinfo else o.expiry.replace(tzinfo=UTC)
    days_to_expiry = max((expiry_utc - datetime.now(UTC)).total_seconds() / 86400.0, 0)
    return {
        "id": o.id,
        "detected_at": o.detected_at.isoformat(),
        "mode": o.mode.value,
        "network": o.network,
        "instrument": o.instrument,
        "symbol": o.symbol,
        "expiry": o.expiry.isoformat(),
        "days_to_expiry": round(days_to_expiry, 2),
        "strike": o.strike,
        "option_type": o.option_type,
        "buy_from": o.buy_from,
        "sell_to": o.sell_to,
        "top_ask": o.top_ask,
        "top_bid": o.top_bid,
        "walked_ask": o.walked_ask,
        "walked_bid": o.walked_bid,
        "walked_size": o.walked_size,
        "spread_pct": o.spread_pct,
        "fee_pct": o.fee_pct,
        "apr_pct": o.apr_pct,
        "max_notional_usd": o.max_notional_usd,
        "net_profit_usd": round(net_profit, 2),
        "fees_usd": round(fees, 2),
        "gross_profit_usd": round(net_profit + fees, 2),
        "status": o.status.value,
        "rejection_reason": o.rejection_reason,
    }
