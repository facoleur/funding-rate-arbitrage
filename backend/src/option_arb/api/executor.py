from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from option_arb.config import load_config
from option_arb.db.models import Trade, TradeStatus
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/executor", tags=["executor"])

ACTIVE_TRADE_STATES = (
    TradeStatus.PLACING,
    TradeStatus.LEG1_FILLED,
    TradeStatus.LEG2_FILLED,
    TradeStatus.HEDGING,
)


@router.get("/state")
async def state() -> dict[str, Any]:
    cfg = load_config()
    kill_file = Path(cfg.limits.kill_switch_file)
    killed = kill_file.exists()

    today_midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_session() as sess:
        open_count = (
            await sess.execute(
                select(func.count()).select_from(Trade).where(Trade.status.in_(ACTIVE_TRADE_STATES))  # type: ignore[attr-defined]
            )
        ).scalar_one()
        daily_pnl = (
            await sess.execute(
                select(func.coalesce(func.sum(Trade.net_pnl_usd), 0.0)).where(
                    Trade.opened_at >= today_midnight
                )
            )
        ).scalar_one()

    return {
        "status": "KILLED" if killed else "RUNNING",
        "kill_switch_file": str(kill_file),
        "config": {
            "mode": cfg.executor.mode,
            "min_apr_pct": cfg.thresholds.min_apr_pct,
            "min_notional_usd": cfg.thresholds.min_notional_usd,
            "max_notional_per_trade_usd": cfg.limits.max_notional_per_trade_usd,
            "max_positions_open": cfg.limits.max_positions_open,
            "max_daily_loss_usd": cfg.limits.max_daily_loss_usd,
        },
        "counters": {
            "open_positions": int(open_count),
            "daily_pnl_usd": float(daily_pnl or 0),
        },
    }


@router.post("/kill")
async def kill() -> dict[str, Any]:
    cfg = load_config()
    Path(cfg.limits.kill_switch_file).touch()
    return {"killed": True}


@router.post("/resume")
async def resume() -> dict[str, Any]:
    cfg = load_config()
    p = Path(cfg.limits.kill_switch_file)
    if p.exists():
        p.unlink()
    return {"killed": False}
