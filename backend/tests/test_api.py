from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from option_arb.db.models import Mode, Opportunity, OpportunityStatus
from option_arb.db.session import get_session
from option_arb.main import app


async def _insert_opportunity(**kwargs) -> Opportunity:  # type: ignore[no-untyped-def]
    defaults = dict(
        mode=Mode.PAPER,
        network="mainnet",
        instrument="BTC-20260101-30000-C",
        symbol="BTC",
        expiry=datetime.now(UTC) + timedelta(days=30),
        strike=30000.0,
        option_type="C",
        buy_from="derive",
        sell_to="deribit",
        top_ask=101.0,
        top_bid=110.0,
        spread_pct=8.85,
        fee_pct=0.06,
        apr_pct=107.0,
        max_notional_usd=1010.0,
        status=OpportunityStatus.PENDING,
    )
    defaults.update(kwargs)
    opp = Opportunity(**defaults)
    async with get_session() as sess:
        sess.add(opp)
        await sess.commit()
        await sess.refresh(opp)
    return opp


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
async def test_opportunity_serialization_includes_profit_fields(test_db: str) -> None:
    # Use clean numbers to avoid floating-point rounding mismatch
    await _insert_opportunity(max_notional_usd=1000.0, spread_pct=10.0, fee_pct=0.10)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    opp = body[0]
    assert "fee_pct" in opp
    assert "net_profit_usd" in opp
    assert "fees_usd" in opp
    assert "gross_profit_usd" in opp
    assert opp["fee_pct"] == pytest.approx(0.10)
    assert opp["net_profit_usd"] == pytest.approx(100.0, abs=0.01)  # 1000 * 10% / 100
    assert opp["fees_usd"] == pytest.approx(1.0, abs=0.01)  # 1000 * 0.10% / 100
    assert opp["gross_profit_usd"] == pytest.approx(101.0, abs=0.01)  # net + fees


@pytest.mark.asyncio
async def test_opportunity_stats_groups_by_pair(test_db: str) -> None:
    await _insert_opportunity(
        buy_from="derive", sell_to="deribit", max_notional_usd=1000.0, spread_pct=10.0, fee_pct=0.06
    )
    await _insert_opportunity(
        buy_from="derive", sell_to="deribit", max_notional_usd=500.0, spread_pct=5.0, fee_pct=0.06
    )
    await _insert_opportunity(
        buy_from="derive",
        sell_to="deribit_linear",
        max_notional_usd=200.0,
        spread_pct=8.0,
        fee_pct=0.06,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities/stats?days=30")
    assert r.status_code == 200
    stats = {s["pair"]: s for s in r.json()}

    assert "derive → deribit" in stats
    assert "derive → deribit_linear" in stats
    # derive → deribit: 1000*10/100 + 500*5/100 = 100 + 25 = 125
    assert stats["derive → deribit"]["total_net_profit_usd"] == pytest.approx(125.0, abs=0.01)
    assert stats["derive → deribit"]["count"] == 2
    assert stats["derive → deribit"]["best_net_profit_usd"] == pytest.approx(100.0, abs=0.01)
    # fees: (1000 + 500) * 0.06 / 100 = 0.90
    assert stats["derive → deribit"]["total_fees_usd"] == pytest.approx(0.90, abs=0.01)


@pytest.mark.asyncio
async def test_opportunity_stats_empty(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities/stats")
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
