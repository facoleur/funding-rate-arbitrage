from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from option_arb.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _configure_connection(dbapi_conn, connection_record) -> None:  # type: ignore[no-untyped-def]
    """Per-driver connection tuning. SQLite → WAL + busy_timeout so pytest
    (or any dev use of sqlite) doesn't deadlock. Postgres → nothing needed."""
    # Detect SQLite vs Postgres by looking at driver connection type
    module = type(dbapi_conn).__module__
    if "sqlite" in module or "aiosqlite" in module:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA busy_timeout=5000;")
        finally:
            cursor.close()


SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables directly from SQLModel metadata (dev/test only).
    Production must use Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
