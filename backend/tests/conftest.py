from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

# Import models so metadata is registered before any table create.
from option_arb.db import models  # noqa: F401


@pytest_asyncio.fixture
async def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """Give each test its own SQLite file and re-point the shared engine at it."""
    url = f"sqlite+aiosqlite:///{tmp_path}/t.db"

    engine = create_async_engine(url, future=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    from option_arb.db import session as sess_mod
    monkeypatch.setattr(sess_mod, "engine", engine)
    monkeypatch.setattr(sess_mod, "SessionLocal", SessionLocal)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield url

    await engine.dispose()


@pytest.fixture
def temp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CONFIG_PATH at a per-test YAML the test can freely overwrite."""
    p = tmp_path / "cfg.yaml"
    p.write_text("")
    monkeypatch.setenv("CONFIG_PATH", str(p))
    return p
