from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from option_arb.api.schemas import ExecutorStateResponse, ExecutorToggleResponse
from option_arb.config import load_config
from option_arb.services.limits import is_killed, read_counters

router = APIRouter(prefix="/api/executor", tags=["executor"])


@router.get("/state", response_model=ExecutorStateResponse)
async def state() -> dict[str, Any]:
    cfg = load_config()
    counters = await read_counters()
    return {
        "status": "KILLED" if is_killed(cfg.limits) else "RUNNING",
        "kill_switch_file": cfg.limits.kill_switch_file,
        "config": {
            "mode": cfg.executor.mode,
            "min_apr_pct": cfg.thresholds.min_apr_pct,
            "min_buy_premium_usd": cfg.thresholds.min_buy_premium_usd,
            "min_leg_premium_liquidity_usd": cfg.thresholds.min_leg_premium_liquidity_usd,
            "max_days_to_expiry": cfg.thresholds.max_days_to_expiry,
            "min_net_profit_usd": cfg.thresholds.min_net_profit_usd,
            "min_net_return_pct": cfg.thresholds.min_net_return_pct,
            "max_buy_premium_per_trade_usd": cfg.limits.max_buy_premium_per_trade_usd,
            "ioc_slippage_limit_pct": cfg.executor.ioc_slippage_limit_pct,
            "max_positions_open": cfg.limits.max_positions_open,
            "max_daily_loss_usd": cfg.limits.max_daily_loss_usd,
        },
        "counters": {
            "open_positions": counters.open_positions,
            "daily_pnl_usd": counters.daily_pnl_usd,
        },
    }


@router.post("/kill", response_model=ExecutorToggleResponse)
async def kill() -> dict[str, Any]:
    Path(load_config().limits.kill_switch_file).touch()
    return {"killed": True}


@router.post("/resume", response_model=ExecutorToggleResponse)
async def resume() -> dict[str, Any]:
    Path(load_config().limits.kill_switch_file).unlink(missing_ok=True)
    return {"killed": False}
