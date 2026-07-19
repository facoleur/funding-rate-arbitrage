from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel import select

from option_arb.config import AppConfig
from option_arb.db.models import (
    Mode,
    Opportunity,
    OpportunityStatus,
    Trade,
    TradeStatus,
)
from option_arb.db.session import get_session
from option_arb.exchanges.base import Instrument, OrderRequest, OrderResult
from option_arb.exchanges.mock import MockExchange, make_book
from option_arb.exchanges.slippage import SlippageModel
from option_arb.services.executor import Executor


def _inst(exchange: str, name: str = "BTC-20260101-30000-C", *, expiry_days: int = 30) -> Instrument:
    return Instrument(
        exchange=exchange,
        instrument_name=name,
        normalized_name=name,
        underlying="BTC",
        expiry=datetime.now(tz=timezone.utc) + timedelta(days=expiry_days),
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0003"),
    )


def _mock_pair(
    *,
    reject_prob: float = 0.0,
    seed_a: int = 1,
    seed_b: int = 2,
) -> tuple[MockExchange, MockExchange, Instrument, Instrument]:
    inst_a = _inst("derive")
    inst_b = _inst("deribit")
    a = MockExchange("derive", slippage=SlippageModel(reject_prob=reject_prob, noise_stdev_bps=0, latency_min_sec=0, latency_max_sec=0, rng_seed=seed_a))
    b = MockExchange("deribit", slippage=SlippageModel(reject_prob=reject_prob, noise_stdev_bps=0, latency_min_sec=0, latency_max_sec=0, rng_seed=seed_b))
    a.set_instruments([inst_a])
    b.set_instruments([inst_b])
    a.set_book(inst_a.instrument_name, make_book("derive", inst_a.normalized_name,
        bids=[("100", "10")], asks=[("101", "10")]))
    b.set_book(inst_b.instrument_name, make_book("deribit", inst_b.normalized_name,
        bids=[("115", "10")], asks=[("116", "10")]))
    return a, b, inst_a, inst_b


async def _make_pending_opp(inst: str = "BTC-20260101-30000-C") -> int:
    async with get_session() as sess:
        opp = Opportunity(
            detected_at=datetime.now(timezone.utc),
            mode=Mode.PAPER,
            instrument=inst,
            symbol="BTC",
            expiry=datetime.now(tz=timezone.utc) + timedelta(days=30),
            strike=30000.0,
            option_type="C",
            buy_from="mock-derive",
            sell_to="mock-deribit",
            top_ask=101.0,
            top_bid=115.0,
            spread_pct=13.8,
            apr_pct=160.0,
            max_notional_usd=1000.0,
            status=OpportunityStatus.PENDING,
        )
        sess.add(opp)
        await sess.commit()
        await sess.refresh(opp)
        return opp.id


@pytest.mark.asyncio
async def test_executor_fills_both_legs_happy_path(test_db: str) -> None:
    a, b, ia, ib = _mock_pair()
    exchanges = {"mock-derive": a, "mock-deribit": b}
    cfg = AppConfig()
    ex = Executor(cfg, exchanges, {"mock-derive": {ia.normalized_name: ia},
                                    "mock-deribit": {ib.normalized_name: ib}})
    opp_id = await _make_pending_opp()
    await ex._tick()

    async with get_session() as sess:
        trades = list((await sess.execute(select(Trade))).scalars())
        opp = await sess.get(Opportunity, opp_id)
    assert len(trades) == 1
    assert trades[0].status == TradeStatus.FILLED
    assert trades[0].net_pnl_usd is not None and trades[0].net_pnl_usd > 0
    assert opp.status == OpportunityStatus.EXECUTED


@pytest.mark.asyncio
async def test_executor_kill_switch_file_blocks(test_db: str, tmp_path, monkeypatch) -> None:
    kill_path = tmp_path / "KILL"
    kill_path.touch()
    cfg = AppConfig()
    cfg.limits.kill_switch_file = str(kill_path)
    a, b, ia, ib = _mock_pair()
    ex = Executor(cfg, {"mock-derive": a, "mock-deribit": b},
                  {"mock-derive": {ia.normalized_name: ia},
                   "mock-deribit": {ib.normalized_name: ib}})
    opp_id = await _make_pending_opp()
    await ex._tick()

    async with get_session() as sess:
        opp = await sess.get(Opportunity, opp_id)
        trades = list((await sess.execute(select(Trade))).scalars())
    assert opp.status == OpportunityStatus.REJECTED
    assert "kill_switch_file" in (opp.rejection_reason or "")
    assert trades == []


@pytest.mark.asyncio
async def test_executor_max_positions_open_blocks(test_db: str) -> None:
    cfg = AppConfig()
    cfg.limits.max_positions_open = 0  # cap immediately
    a, b, ia, ib = _mock_pair()
    ex = Executor(cfg, {"mock-derive": a, "mock-deribit": b},
                  {"mock-derive": {ia.normalized_name: ia},
                   "mock-deribit": {ib.normalized_name: ib}})
    opp_id = await _make_pending_opp()
    await ex._tick()
    async with get_session() as sess:
        opp = await sess.get(Opportunity, opp_id)
    assert opp.status == OpportunityStatus.REJECTED
    assert "max_positions_open" in (opp.rejection_reason or "")


@pytest.mark.asyncio
async def test_executor_single_leg_fill_triggers_market_out(test_db: str) -> None:
    a, b, ia, ib = _mock_pair()
    # Force sell leg to reject deterministically
    async def _reject_sell(order: OrderRequest) -> OrderResult:
        return OrderResult(status="REJECTED", reason="forced_test_reject")
    b.place_order = _reject_sell  # type: ignore[method-assign]

    cfg = AppConfig()
    ex = Executor(cfg, {"mock-derive": a, "mock-deribit": b},
                  {"mock-derive": {ia.normalized_name: ia},
                   "mock-deribit": {ib.normalized_name: ib}})
    await _make_pending_opp()
    await ex._tick()

    async with get_session() as sess:
        trades = list((await sess.execute(select(Trade))).scalars())
    assert len(trades) == 1
    # buy leg filled, sell rejected → market-out on buy venue (SELL)
    # market-out uses same MockExchange 'a' with permissive limit → likely fills
    assert trades[0].status in (TradeStatus.HEDGED, TradeStatus.STUCK)
