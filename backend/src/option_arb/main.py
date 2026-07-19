from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from option_arb.api import (
    alerts,
    executor,
    health,
    opportunities,
    positions,
    stream,
    tickers,
    trades,
)
from option_arb.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(
    title="option-arb API",
    version="0.1.0",
    lifespan=lifespan,
)

for router in (
    health.router,
    opportunities.router,
    trades.router,
    positions.router,
    executor.router,
    alerts.router,
    tickers.router,
    stream.router,
):
    app.include_router(router)
