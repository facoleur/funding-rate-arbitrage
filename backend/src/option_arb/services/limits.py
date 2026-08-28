"""Executor trading limits — the single definition of the risk gates.

Both the executor (which enforces them) and `/api/executor/state` (which
reports them) read from here. Keeping two copies meant the UI could report
RUNNING while the executor refused every opportunity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlmodel import select

from option_arb.config import Limits
from option_arb.db.models import Trade, TradeStatus
from option_arb.db.session import get_session

ACTIVE_TRADE_STATES = (
    TradeStatus.PLACING,
    TradeStatus.LEG1_FILLED,
    TradeStatus.LEG2_FILLED,
    TradeStatus.HEDGING,
)


@dataclass(frozen=True)
class ExecutorCounters:
    open_positions: int
    daily_pnl_usd: float


def is_killed(limits: Limits) -> bool:
    """Manual kill-switch — the file is created by `POST /api/executor/kill`
    or `make kill`."""
    return Path(limits.kill_switch_file).exists()


async def read_counters() -> ExecutorCounters:
    """Open-position count and realised PnL since midnight UTC, in one session."""
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_session() as sess:
        open_count = (
            await sess.execute(
                select(func.count()).select_from(Trade).where(Trade.status.in_(ACTIVE_TRADE_STATES))  # type: ignore[attr-defined]
            )
        ).scalar_one()
        daily_pnl = (
            await sess.execute(
                select(func.coalesce(func.sum(Trade.net_pnl_usd), 0.0)).where(
                    Trade.opened_at >= midnight
                )
            )
        ).scalar_one()
    return ExecutorCounters(int(open_count), float(daily_pnl or 0))


async def kill_switch_reason(limits: Limits) -> str | None:
    """Return why trading is blocked, or None when all gates are clear.
    Checked on every executor loop iteration."""
    if is_killed(limits):
        return "kill_switch_file"
    counters = await read_counters()
    if counters.open_positions >= limits.max_positions_open:
        return f"max_positions_open({counters.open_positions})"
    if counters.daily_pnl_usd <= -limits.max_daily_loss_usd:
        return f"max_daily_loss({counters.daily_pnl_usd:.2f})"
    return None
