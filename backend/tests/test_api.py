from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from option_arb.main import app


@pytest.mark.asyncio
async def test_health(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_opportunities_empty(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_executor_state_default(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/executor/state")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("RUNNING", "KILLED")
    assert "config" in body and "counters" in body


@pytest.mark.asyncio
async def test_executor_kill_and_resume(test_db: str, temp_config, tmp_path) -> None:
    kill_path = tmp_path / "KILL"
    temp_config.write_text(f"limits:\n  kill_switch_file: {kill_path}\n")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert not kill_path.exists()
        r = await ac.post("/api/executor/kill")
        assert r.status_code == 200
        assert kill_path.exists()
        r = await ac.post("/api/executor/resume")
        assert r.status_code == 200
        assert not kill_path.exists()
