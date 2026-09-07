from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from option_arb.config import AppConfig, ScreenerConfig
from option_arb.db.models import (
    LiveStatus,
    Opportunity,
    OpportunitySnapshot,
    OpportunityStatus,
)
from option_arb.db.session import get_session
from option_arb.exchanges.base import Instrument, TickerUpdate
from option_arb.market.book_cache import BookCache
from option_arb.services.screener import Screener

NAME = "BTC-20260101-30000-C"
EXPIRY = datetime.now(tz=UTC) + timedelta(days=30)


def _cfg(**screener: object) -> AppConfig:
    return AppConfig(screener=ScreenerConfig(**screener))  # type: ignore[arg-type]


def _inst(exchange: str) -> Instrument:
    return Instrument(
        exchange=exchange,
        instrument_name=NAME,
        normalized_name=NAME,
        underlying="BTC",
        expiry=EXPIRY,
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0003"),
    )


def _quote(cache: BookCache, exchange: str, bid: str, ask: str) -> None:
    cache.update(
        TickerUpdate(
            exchange=exchange,
            instrument=NAME,
            ts=datetime.now(tz=UTC),
            bid_price=Decimal(bid),
            bid_size=Decimal("10"),
            ask_price=Decimal(ask),
            ask_size=Decimal("10"),
            underlying_price=Decimal("1000"),
        )
    )


def _load(cache: BookCache, buy_ask: str = "101", sell_bid: str = "110") -> None:
    # buy on derive @ ask, sell on deribit @ bid → spread, spot 1000
    _quote(cache, "derive", bid="100", ask=buy_ask)
    _quote(cache, "deribit", bid=sell_bid, ask="112")


def _fresh_cache() -> BookCache:
    cache = BookCache()
    cache.register_instruments([_inst("derive"), _inst("deribit")])
    return cache


async def _opps() -> list[Opportunity]:
    async with get_session() as sess:
        return list((await sess.execute(select(Opportunity))).scalars())


async def _snaps(opp_id: int) -> list[OpportunitySnapshot]:
    async with get_session() as sess:
        return list(
            (
                await sess.execute(
                    select(OpportunitySnapshot)
                    .where(OpportunitySnapshot.opportunity_id == opp_id)
                    .order_by(OpportunitySnapshot.ts)
                )
            ).scalars()
        )


@pytest.mark.asyncio
async def test_first_snapshot_and_lifecycle_init(test_db: str) -> None:
    cache = _fresh_cache()
    _load(cache)
    await Screener(cache, _cfg())._tick()

    rows = await _opps()
    assert len(rows) == 1
    o = rows[0]
    assert o.status == OpportunityStatus.PENDING
    assert o.live_status == LiveStatus.LIVE
    assert o.samples_count == 1
    assert o.peak_net_profit_usd == o.net_profit_usd

    snaps = await _snaps(o.id)
    assert len(snaps) == 1
    assert snaps[0].net_profit_usd == o.net_profit_usd
    assert snaps[0].top_ask == 101.0
    assert snaps[0].underlying_price == 1000.0


@pytest.mark.asyncio
async def test_snapshot_gating_by_interval_and_delta(test_db: str) -> None:
    cache = _fresh_cache()
    _load(cache)
    scr = Screener(cache, _cfg(snapshot_min_interval_sec=3600, snapshot_delta_usd=0.5))
    await scr._tick()
    oid = (await _opps())[0].id

    # tiny move → no new snapshot, but samples_count bumps
    _load(cache, sell_bid="110.01")
    await scr._tick()
    assert (await _opps())[0].samples_count == 2
    assert len(await _snaps(oid)) == 1

    # big move → new snapshot
    _load(cache, sell_bid="140")
    await scr._tick()
    assert len(await _snaps(oid)) == 2


@pytest.mark.asyncio
async def test_peak_and_last_seen_track(test_db: str) -> None:
    cache = _fresh_cache()
    _load(cache, sell_bid="140")
    scr = Screener(cache, _cfg())
    await scr._tick()
    first = (await _opps())[0]
    peak = first.peak_net_profit_usd

    _load(cache, sell_bid="110")  # profit decays
    await scr._tick()
    o = (await _opps())[0]
    assert o.peak_net_profit_usd == peak  # sticks
    assert o.net_profit_usd < peak
    assert o.last_seen_at >= first.last_seen_at
    assert o.samples_count == 2


@pytest.mark.asyncio
async def test_close_sweep_leaves_executor_status_untouched(test_db: str) -> None:
    cache = _fresh_cache()
    _load(cache)
    scr = Screener(cache, _cfg(close_after_stale_sec=0))
    await scr._tick()

    # pretend the executor took it
    async with get_session() as sess:
        o = (await sess.execute(select(Opportunity))).scalar_one()
        o.status = OpportunityStatus.EXECUTED
        await sess.commit()

    # a separate already-expired opportunity
    async with get_session() as sess:
        sess.add(
            Opportunity(
                mode=o.mode,
                network="mainnet",
                instrument="ETH-20200101-2000-C",
                symbol="ETH",
                expiry=datetime.now(UTC) - timedelta(hours=1),
                strike=2000.0,
                option_type="C",
                buy_from="derive",
                sell_to="deribit",
                top_ask=1.0,
                top_bid=1.2,
                tradeable_size=1.0,
                buy_premium_usd=1.0,
                sell_premium_usd=1.2,
                estimated_short_margin_usd=1.0,
                capital_required_usd=2.0,
                gross_profit_usd=0.2,
                fees_usd=0.0,
                net_profit_usd=0.2,
                price_spread_pct=20.0,
                net_return_pct=10.0,
                apr_pct=100.0,
                status=OpportunityStatus.PENDING,
                live_status=LiveStatus.LIVE,
            )
        )
        await sess.commit()

    cache._by_key.clear()  # nothing detected next tick
    await scr._tick()

    by_sym = {o.symbol: o for o in await _opps()}
    assert by_sym["BTC"].live_status == LiveStatus.STALE
    assert by_sym["BTC"].close_reason == "stale"
    assert by_sym["BTC"].status == OpportunityStatus.EXECUTED  # workflow state preserved
    assert by_sym["ETH"].live_status == LiveStatus.EXPIRED
    assert by_sym["ETH"].close_reason == "expired"


@pytest.mark.asyncio
async def test_stale_opportunity_revives_when_redetected(test_db: str) -> None:
    cache = _fresh_cache()
    _load(cache)
    scr = Screener(cache, _cfg(close_after_stale_sec=0))
    await scr._tick()
    oid = (await _opps())[0].id

    cache._by_key.clear()
    await scr._tick()  # → STALE
    assert (await _opps())[0].live_status == LiveStatus.STALE

    _load(cache)  # reappears within the 1h dedup window
    await scr._tick()
    o = (await _opps())[0]
    assert len(await _opps()) == 1  # revived, not duplicated
    assert o.id == oid
    assert o.live_status == LiveStatus.LIVE
    assert o.closed_at is None
    assert o.close_reason is None
