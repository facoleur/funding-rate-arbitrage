from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from option_arb.config import AppConfig, StructuredConfig, StructuredThresholds
from option_arb.db.models import (
    LiveStatus,
    Mode,
    StrategyType,
    StructuredOpportunity,
    StructuredOpportunitySnapshot,
)
from option_arb.db.session import get_session
from option_arb.exchanges.base import Instrument, TickerUpdate
from option_arb.market.book_cache import BookCache
from option_arb.structured.screener import StructuredScreener

EXPIRY = datetime.now(tz=UTC) + timedelta(days=30)


def _cfg(**structured: object) -> AppConfig:
    base = dict(
        enabled=True,
        thresholds=StructuredThresholds(
            min_total_profit_usd=-1e9, min_profit_per_unit_usd=-1e9, max_days_to_expiry=3650
        ),
    )
    base.update(structured)
    return AppConfig(structured=StructuredConfig(**base))  # type: ignore[arg-type]


def _inst(strike: str, option_type: str, exchange: str = "derive") -> Instrument:
    name = f"BTC-20260327-{strike}-{option_type}"
    return Instrument(
        exchange=exchange,
        instrument_name=name,
        normalized_name=name,
        underlying="BTC",
        expiry=EXPIRY,
        strike=Decimal(strike),
        option_type=option_type,
        maker_fee_rate=Decimal("0"),
        taker_fee_rate=Decimal("0"),
    )


def _tick(
    cache: BookCache, name: str, bid: str, ask: str, exchange: str = "derive", size: str = "5"
) -> None:
    cache.update(
        TickerUpdate(
            exchange=exchange,
            instrument=name,
            ts=datetime.now(tz=UTC),
            bid_price=Decimal(bid),
            bid_size=Decimal(size),
            ask_price=Decimal(ask),
            ask_size=Decimal(size),
            underlying_price=Decimal("100000"),
        )
    )


def _load_box(cache: BookCache) -> None:
    # entry = 21 + 16 - 9 - 9 = 19 ; width 20 ; edge/unit = 1 ; size 5 → total 5
    _tick(cache, "BTC-20260327-100-C", bid="20", ask="21")
    _tick(cache, "BTC-20260327-100-P", bid="9", ask="10")
    _tick(cache, "BTC-20260327-120-C", bid="9", ask="10")
    _tick(cache, "BTC-20260327-120-P", bid="15", ask="16")


def _fresh_cache() -> BookCache:
    cache = BookCache()
    cache.register_instruments(
        [_inst("100", "C"), _inst("100", "P"), _inst("120", "C"), _inst("120", "P")]
    )
    return cache


async def _all_opps() -> list[StructuredOpportunity]:
    async with get_session() as sess:
        return list((await sess.execute(select(StructuredOpportunity))).scalars())


async def _snaps(opp_id: int) -> list[StructuredOpportunitySnapshot]:
    async with get_session() as sess:
        return list(
            (
                await sess.execute(
                    select(StructuredOpportunitySnapshot)
                    .where(StructuredOpportunitySnapshot.opportunity_id == opp_id)
                    .order_by(StructuredOpportunitySnapshot.ts)
                )
            ).scalars()
        )


@pytest.mark.asyncio
async def test_writes_opportunity_and_first_snapshot(test_db: str) -> None:
    cache = _fresh_cache()
    _load_box(cache)
    await StructuredScreener(cache, _cfg())._tick()

    rows = await _all_opps()
    assert len(rows) == 1
    row = rows[0]
    assert row.strategy_type == StrategyType.BOX
    assert row.strikes == [100.0, 120.0]
    assert row.entry_cost == 19.0
    assert row.min_profit == 1.0
    assert row.max_total_profit_usd == 5.0
    assert row.samples_count == 1
    assert row.peak_total_profit_usd == 5.0
    assert row.spot == 100000.0
    assert row.live_status == LiveStatus.LIVE

    snaps = await _snaps(row.id)
    assert len(snaps) == 1
    assert snaps[0].entry_cost == 19.0
    assert snaps[0].underlying_price == 100000.0


@pytest.mark.asyncio
async def test_no_second_snapshot_within_interval_below_delta(test_db: str) -> None:
    cache = _fresh_cache()
    _load_box(cache)
    screener = StructuredScreener(
        cache, _cfg(snapshot_min_interval_sec=3600, snapshot_edge_delta_usd=1.0)
    )
    await screener._tick()
    opp_id = (await _all_opps())[0].id

    # nudge the edge by < $1 total (bid 9 → 9.05 on P@100 shifts entry by 0.05, total by 0.25)
    _tick(cache, "BTC-20260327-100-P", bid="9.05", ask="10")
    await screener._tick()

    rows = await _all_opps()
    assert len(rows) == 1
    assert rows[0].samples_count == 2  # still counted…
    assert len(await _snaps(opp_id)) == 1  # …but no new snapshot


@pytest.mark.asyncio
async def test_snapshot_written_when_edge_moves_past_delta(test_db: str) -> None:
    cache = _fresh_cache()
    _load_box(cache)
    screener = StructuredScreener(
        cache, _cfg(snapshot_min_interval_sec=3600, snapshot_edge_delta_usd=1.0)
    )
    await screener._tick()
    opp_id = (await _all_opps())[0].id

    _tick(cache, "BTC-20260327-100-P", bid="10", ask="11")  # entry 19→18, total 5→10
    await screener._tick()

    rows = await _all_opps()
    assert rows[0].entry_cost == 18.0
    assert rows[0].max_total_profit_usd == 10.0
    assert rows[0].peak_total_profit_usd == 10.0
    assert rows[0].detected_at == rows[0].detected_at  # unchanged reference
    snaps = await _snaps(opp_id)
    assert len(snaps) == 2
    assert snaps[-1].max_total_profit_usd == 10.0


@pytest.mark.asyncio
async def test_snapshot_written_when_venue_mix_changes(test_db: str) -> None:
    cache = BookCache()
    cache.register_instruments(
        [
            _inst("100", "C"),
            _inst("100", "P"),
            _inst("120", "C"),
            _inst("120", "P"),
            _inst("100", "C", "aevo"),
        ]
    )
    _load_box(cache)
    # aevo also quotes C@100 but worse → derive wins initially
    _tick(cache, "BTC-20260327-100-C", bid="20", ask="30", exchange="aevo")
    screener = StructuredScreener(
        cache, _cfg(snapshot_min_interval_sec=3600, snapshot_edge_delta_usd=1e9)
    )
    await screener._tick()
    opp_id = (await _all_opps())[0].id
    assert len(await _snaps(opp_id)) == 1

    # aevo now best ask on C@100 → winning venue for that leg flips, same economics tier
    _tick(cache, "BTC-20260327-100-C", bid="20", ask="21", exchange="aevo")
    _tick(cache, "BTC-20260327-100-C", bid="20", ask="21.5")  # derive slightly worse
    await screener._tick()

    snaps = await _snaps(opp_id)
    assert len(snaps) == 2
    c1 = next(leg for leg in snaps[-1].legs if leg["instrument"].endswith("100-C"))
    assert c1["exchange"] == "aevo"


@pytest.mark.asyncio
async def test_lifecycle_fields_track_across_ticks(test_db: str) -> None:
    cache = _fresh_cache()
    _load_box(cache)
    screener = StructuredScreener(cache, _cfg())
    await screener._tick()
    first = (await _all_opps())[0]

    _tick(cache, "BTC-20260327-100-P", bid="10", ask="11")  # total 5 → 10 (new peak)
    await screener._tick()
    _tick(cache, "BTC-20260327-100-P", bid="8", ask="9")  # total 10 → 0 (decayed)
    await screener._tick()

    row = (await _all_opps())[0]
    assert row.samples_count == 3
    assert row.peak_total_profit_usd == 10.0  # peak sticks
    assert row.max_total_profit_usd == 0.0  # current decayed
    assert row.last_seen_at >= first.last_seen_at


@pytest.mark.asyncio
async def test_close_sweep_marks_stale_and_expired(test_db: str) -> None:
    cache = _fresh_cache()
    _load_box(cache)
    screener = StructuredScreener(cache, _cfg(close_after_stale_sec=0))
    await screener._tick()
    assert (await _all_opps())[0].live_status == LiveStatus.LIVE

    # a separate opportunity that already expired, inserted straight to the DB
    async with get_session() as sess:
        sess.add(
            StructuredOpportunity(
                strategy_type=StrategyType.BOX,
                underlying="ETH",
                expiry=datetime.now(UTC) - timedelta(hours=1),
                strikes=[1.0, 2.0],
                legs=[],
                is_fixed_payoff=True,
                settlement_risk=False,
                min_payoff=1.0,
                max_payoff=1.0,
                entry_cost=0.9,
                max_fees=0.0,
                min_profit=0.1,
                max_profit=0.1,
                max_size=1.0,
                capital_required_usd=0.9,
                max_total_profit_usd=0.1,
                mode=Mode.PAPER,
                status=LiveStatus.LIVE,
            )
        )
        await sess.commit()

    # next tick: cache no longer fed → box goes stale; ETH row is past expiry
    cache._by_key.clear()
    await screener._tick()

    by_underlying = {o.underlying: o for o in await _all_opps()}
    assert by_underlying["BTC"].live_status == LiveStatus.STALE
    assert by_underlying["BTC"].close_reason == "stale"
    assert by_underlying["BTC"].closed_at is not None
    assert by_underlying["ETH"].live_status == LiveStatus.EXPIRED
    assert by_underlying["ETH"].close_reason == "expired"
