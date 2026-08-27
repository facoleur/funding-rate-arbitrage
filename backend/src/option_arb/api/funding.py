from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Query

from option_arb.api.schemas import FundingHistoryResponse

router = APIRouter(prefix="/api/funding", tags=["funding"])

_DERIBIT_REST = "https://www.deribit.com/api/v2"
_VALID_INSTRUMENTS = {"BTC-PERPETUAL", "ETH-PERPETUAL"}


@router.get("", response_model=list[FundingHistoryResponse])
async def funding_history(
    instrument: str = Query(default="BTC-PERPETUAL"),
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    if instrument not in _VALID_INSTRUMENTS:
        instrument = "BTC-PERPETUAL"

    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    start_ms = int(since.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_DERIBIT_REST}/public/get_funding_rate_history",
            params={
                "instrument_name": instrument,
                "start_timestamp": start_ms,
                "end_timestamp": end_ms,
            },
        )
        r.raise_for_status()
        data = r.json()

    rows = data.get("result", [])
    return [
        {
            "ts": row["timestamp"],
            "rate_8h": round(float(row["interest_8h"]) * 100, 6),  # % per 8h
            "rate_ann": round(float(row["interest_8h"]) * 3 * 365 * 100, 2),  # % annualisé
            "index_price": round(float(row["index_price"]), 2),
        }
        for row in rows
    ]
