from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from option_arb.config import load_config

router = APIRouter(prefix="/api/perp-hedge", tags=["perp-hedge"])


@router.get("/state")
async def state() -> dict[str, Any]:
    cfg = load_config()
    kill_file = Path(cfg.perp_hedge.kill_switch_file)
    return {
        "enabled": cfg.perp_hedge.enabled,
        "paused": kill_file.exists(),
        "kill_switch_file": str(kill_file),
        "config": {
            "rebalance_threshold_usd": cfg.perp_hedge.rebalance_threshold_usd,
            "poll_interval_sec": cfg.perp_hedge.poll_interval_sec,
        },
    }


@router.post("/pause")
async def pause() -> dict[str, Any]:
    cfg = load_config()
    Path(cfg.perp_hedge.kill_switch_file).touch()
    return {"paused": True}


@router.post("/resume")
async def resume() -> dict[str, Any]:
    cfg = load_config()
    p = Path(cfg.perp_hedge.kill_switch_file)
    if p.exists():
        p.unlink()
    return {"paused": False}
