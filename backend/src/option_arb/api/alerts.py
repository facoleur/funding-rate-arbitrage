from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlmodel import select

from option_arb.db.models import Alert, AlertLevel
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    level: AlertLevel | None = None,
    limit: int = Query(default=50, le=500),
) -> list[dict[str, Any]]:
    stmt = select(Alert).order_by(Alert.sent_at.desc()).limit(limit)  # type: ignore[attr-defined]
    if level is not None:
        stmt = stmt.where(Alert.level == level)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return [
        {
            "id": a.id,
            "level": a.level.value,
            "channel": a.channel,
            "message": a.message,
            "sent_at": a.sent_at.isoformat(),
            "meta": a.meta,
        }
        for a in rows
    ]
