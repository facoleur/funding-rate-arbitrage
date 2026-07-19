"""Edge-case tests for the executor state machine — the paths that the
happy-path test in test_executor.py doesn't cover."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel import select

from option_arb.config import AppConfig
from option_arb.db.models import Mode, Opportunity, OpportunityStatus, Trade, TradeStatus
from option_arb.db.session import get_session
from option_arb.exchanges.base import Instrument, OrderRequest, OrderResult
from option_arb.exchanges.mock import MockExchange, make_book
from option_arb.exchanges.slippage import SlippageModel
from option_arb.services.executor import Executor


def _inst(exchange: str, name: str = "BTC-20260101-30000-C", *, expiry_days: int = 30) -> Instrument:
    return Instrument(
        exchange=exchange, instrument_name=name, normalized_name=name,
        underlying="BTC",
        expiry=datetime.now(tz=timezone.utc) + timedelta(days=expiry_days),
        strike=Decimal("30000"), option_type="C",
        maker_fee_rate=Decimal("0.0001"), taker_fee_rate=Decimal("0.0003"),
    )


def _executor(a: MockExchange, b: MockExchange, ia: Instrument, ib: Instrument, cfg: AppConfig | None = None) -> Executor:
    return Executor(
        cfg or AppConfig(),
        {"mock-derive": a, "mock-deribit": b},
        {"mock-derive": {ia.normalized_name: ia}, "mock-deribit": {ib.normalized_name: ib}},
    )


async def _make_pending_opp(*, expiry_days: int = 30) -> int:
    async with get_session() as sess:
        opp = Opportunity(
            detected_at=datetime.now(timezone.utc), mode=Mode.PAPER,
            instrument="BTC-20260101-30000-C", symbol="BTC",
            expiry=datetime.now(tz=timezone.utc) + timedelta(days=expiry_days),
            strike=30000.0, option_type="C",
            buy_from="mock-derive", sell_to="mock-deribit",
            top_ask=101.0, top_bid=115.0,
            spread_pct=13.8, apr_pct=160.0, max_notional_usd=1000.0,
            status=OpportunityStatus.PENDING,
        )
        sess.add(opp)
        await sess.commit()
        await sess.refresh(opp)
        return opp.id


def _pair(bids=("100", "10"), asks=("101", "10"), other_bids=("115", "10"), other_asks=("116", "10")) -> tuple:
    ia, ib = _inst("derive"), _inst("deribit")
    a = MockExchange("derive", slippage=SlippageModel(noise_stdev_bps=0, reject_prob=0, latency_min_sec=0, latency_max_sec=0, rng_seed=1))
    b = MockExchange("deribit", slippage=SlippageModel(noise_stdev_bps=0, reject_prob=0, latency_min_sec=0, latency_max_sec=0, rng_seed=2))
    a.set_instruments([ia]); b.set_instruments([ib])
    a.set_book(ia.instrument_name, make_book("derive", ia.normalized_name, bids=[bids], asks=[asks]))
    b.set_book(ib.instrument_name, make_book("deribit", ib.normalized_name, bids=[other_bids], asks=[other_asks]))
    return a, b, ia, ib


@pytest.mark.asyncio
async def test_stale_book_rejects_on_fetch_timeout(test_db: str) -> None:
    a, b, ia, ib = _pair()

    async def _slow_book(inst):
        await asyncio.sleep(1.0)
        raise TimeoutError("simulated")

    b.get_orderbook_l2 = _slow_book  # type: ignore[method-assign]
    cfg = AppConfig()
    cfg.executor.fresh_fetch_timeout_ms = 50
    await _make_pending_opp()
    await _executor(a, b, ia, ib, cfg)._tick()

    async with get_session() as sess:
        opp = (await sess.execute(select(Opportunity))).scalars().first()
    assert opp.status == OpportunityStatus.REJECTED
    assert "stale_book" in (opp.rejection_reason or "")


@pytest.mark.asyncio
async def test_apr_dropped_rejects_when_spread_narrows(test_db: str) -> None:
    """Books that no longer offer a real cross-venue arb after fresh fetch."""
    a, b, ia, ib = _pair(
        bids=("100", "10"), asks=("101", "10"),
        other_bids=("100.05", "10"), other_asks=("101.05", "10"),  # tiny spread — apr drops below 10%
    )
    await _make_pending_opp()
    await _executor(a, b, ia, ib)._tick()

    async with get_session() as sess:
        opp = (await sess.execute(select(Opportunity))).scalars().first()
    assert opp.status == OpportunityStatus.REJECTED
    assert "apr_dropped" in (opp.rejection_reason or "") or "size_too_small" in (opp.rejection_reason or "")


@pytest.mark.asyncio
async def test_empty_book_rejects(test_db: str) -> None:
    ia, ib = _inst("derive"), _inst("deribit")
    a = MockExchange("derive"); b = MockExchange("deribit")
    a.set_instruments([ia]); b.set_instruments([ib])
    a.set_book(ia.instrument_name, make_book("derive", ia.normalized_name, bids=[], asks=[]))
    b.set_book(ib.instrument_name, make_book("deribit", ib.normalized_name, bids=[], asks=[]))
    await _make_pending_opp()
    await _executor(a, b, ia, ib)._tick()

    async with get_session() as sess:
        opp = (await sess.execute(select(Opportunity))).scalars().first()
    assert opp.status == OpportunityStatus.REJECTED
    assert "empty_book" in (opp.rejection_reason or "") or "apr_dropped" in (opp.rejection_reason or "")


@pytest.mark.asyncio
async def test_max_daily_loss_kill_switch_blocks(test_db: str) -> None:
    a, b, ia, ib = _pair()
    cfg = AppConfig()
    cfg.limits.max_daily_loss_usd = 50.0

    # Pre-seed a trade with a big loss today
    async with get_session() as sess:
        losing = Trade(
            opportunity_id=1, mode=Mode.PAPER, status=TradeStatus.FILLED,
            buy_exchange="a", sell_exchange="b", requested_size=1.0, net_pnl_usd=-100.0,
        )
        sess.add(losing)
        await sess.commit()

    await _make_pending_opp()
    await _executor(a, b, ia, ib, cfg)._tick()

    async with get_session() as sess:
        opps = list((await sess.execute(select(Opportunity))).scalars())
        blocked = [o for o in opps if o.status == OpportunityStatus.REJECTED]
    assert len(blocked) == 1
    assert "max_daily_loss" in (blocked[0].rejection_reason or "")


@pytest.mark.asyncio
async def test_stuck_when_market_out_also_fails(test_db: str) -> None:
    """Buy fills, sell fails, market-out also fails → STUCK + critical alert."""
    a, b, ia, ib = _pair()

    # Force sell to reject
    async def _reject(order: OrderRequest) -> OrderResult:
        return OrderResult(status="REJECTED", reason="forced")
    b.place_order = _reject  # type: ignore[method-assign]

    # Force market-out (on venue a, SELL side) to also fail
    original_place = a.place_order
    call_count = 0
    async def _reject_second_call(order: OrderRequest) -> OrderResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return await original_place(order)  # first call = the BUY leg (fills)
        return OrderResult(status="REJECTED", reason="market_out_fail")
    a.place_order = _reject_second_call  # type: ignore[method-assign]

    await _make_pending_opp()
    await _executor(a, b, ia, ib)._tick()

    async with get_session() as sess:
        trades = list((await sess.execute(select(Trade))).scalars())
    stuck = [t for t in trades if t.status == TradeStatus.STUCK]
    assert len(stuck) == 1
    assert stuck[0].error and "market_out" in stuck[0].error
