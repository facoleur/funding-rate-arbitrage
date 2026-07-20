from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from option_arb.config import load_config
from option_arb.db.models import TickerState
from option_arb.db.session import get_session

router = APIRouter(tags=["health"])

_STALE_THRESHOLD = timedelta(seconds=60)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/status")
async def status() -> dict[str, Any]:
    cfg = load_config()
    killed = Path(cfg.limits.kill_switch_file).exists()
    now = datetime.now(UTC)

    async with get_session() as sess:
        rows = (
            await sess.execute(
                select(
                    TickerState.exchange,
                    func.count().label("instruments"),
                    func.max(TickerState.updated_at).label("last_update"),
                ).group_by(TickerState.exchange)
            )
        ).all()

    exchanges: dict[str, Any] = {}
    for r in rows:
        last = r.last_update
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        live = last is not None and (now - last) < _STALE_THRESHOLD
        exchanges[r.exchange] = {
            "instruments": r.instruments,
            "last_update": last.isoformat() if last else None,
            "live": live,
        }

    return {
        "executor": "KILLED" if killed else "RUNNING",
        "mode": cfg.executor.mode,
        "exchanges": exchanges,
    }
