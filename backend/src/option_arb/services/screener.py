from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update
from sqlmodel import col, select

from option_arb.config import AppConfig, settings
from option_arb.db.models import (
    LiveStatus,
    Mode,
    Opportunity,
    OpportunitySnapshot,
    OpportunityStatus,
    TickerState,
)
from option_arb.db.session import get_session
from option_arb.economics import meets_thresholds
from option_arb.events import Event, bus
from option_arb.heartbeat import beat
from option_arb.market.book_cache import BookCache, CachedTicker
from option_arb.services.comparator import Quote, Spread, compare_options
from option_arb.services.snapshots import should_snapshot

log = logging.getLogger(__name__)


def _cached_to_quote(t: CachedTicker) -> Quote | None:
    if not (t.bid_price and t.ask_price and t.bid_size and t.ask_size):
        return None
    return Quote(
        exchange=t.instrument.exchange,
        normalized_name=t.instrument.normalized_name,
        instrument_name=t.instrument.instrument_name,
        underlying=t.instrument.underlying,
        strike=t.instrument.strike,
        option_type=t.instrument.option_type,
        expiry=t.instrument.expiry,
        taker_fee_rate=t.instrument.taker_fee_rate,
        bid_price=t.bid_price,
        bid_qty=t.bid_size,
        ask_price=t.ask_price,
        ask_qty=t.ask_size,
        underlying_price=t.underlying_price,
    )


class Screener:
    """Reads BookCache every poll_interval_ms, groups by normalized_name,
    runs the comparator, and writes new opportunities to the DB."""

    def __init__(self, cache: BookCache, config: AppConfig) -> None:
        self.cache = cache
        self.config = config
        self._stop = asyncio.Event()

    async def run(self) -> None:
        interval = self.config.screener.poll_interval_ms / 1000.0
        log.info("screener started (interval=%.2fs)", interval)
        if "postgresql" in settings.database_url:
            from sqlalchemy import text

            async with get_session() as sess:
                await sess.execute(text("DELETE FROM ticker_state"))
                await sess.commit()
            log.info("screener: ticker_state cleared on startup")
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                log.exception("screener tick failed: %s", e)
            beat("screener")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    # asyncpg caps bound parameters at 32767; TickerState has 13 columns → 2520 rows/batch
    _FLUSH_BATCH = 2520

    async def _flush_tickers(self, tickers: list[CachedTicker]) -> None:
        if "postgresql" not in settings.database_url:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        rows = [
            {
                "exchange": t.instrument.exchange,
                "instrument": t.instrument.normalized_name,
                "underlying": t.instrument.underlying,
                "expiry": t.instrument.expiry,
                "strike": float(t.instrument.strike),
                "option_type": t.instrument.option_type,
                "bid_price": float(t.bid_price) if t.bid_price is not None else None,
                "bid_size": float(t.bid_size) if t.bid_size is not None else None,
                "ask_price": float(t.ask_price) if t.ask_price is not None else None,
                "ask_size": float(t.ask_size) if t.ask_size is not None else None,
                "underlying_price": float(t.underlying_price)
                if t.underlying_price is not None
                else None,
                "taker_fee_rate": float(t.instrument.taker_fee_rate),
                "updated_at": t.ts if t.ts.tzinfo else t.ts.replace(tzinfo=UTC),
            }
            for t in tickers
        ]
        if not rows:
            return
        async with get_session() as sess:
            for i in range(0, len(rows), self._FLUSH_BATCH):
                batch = rows[i : i + self._FLUSH_BATCH]
                stmt = pg_insert(TickerState).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["exchange", "instrument"],
                    set_={
                        c: stmt.excluded[c]
                        for c in (
                            "bid_price",
                            "bid_size",
                            "ask_price",
                            "ask_size",
                            "underlying_price",
                            "updated_at",
                        )
                    },
                )
                await sess.execute(stmt)
            await sess.commit()

    async def _tick(self) -> None:
        await self._flush_tickers(self.cache.snapshot())
        now = datetime.now(UTC)
        by_name = self.cache.by_normalized_name()
        groups: list[list[Quote]] = []
        for _, tickers in by_name.items():
            if len(tickers) < 2:
                continue  # need at least 2 venues to compare
            quotes = [
                q
                for q in (_cached_to_quote(t) for t in tickers)
                if q is not None and q.expiry > now
            ]
            if len(quotes) >= 2:
                groups.append(quotes)

        spreads = (
            compare_options(
                groups,
                min_leg_premium_liquidity_usd=Decimal(
                    str(self.config.thresholds.min_leg_premium_liquidity_usd)
                ),
            )
            if groups
            else []
        )
        if not spreads:
            # still age out opportunities that stopped being detected
            async with get_session() as sess:
                await self._close_stale(sess, now)
                await sess.commit()
            return

        mode = Mode(self.config.executor.mode)
        scfg = self.config.screener

        built: list[Spread] = [
            s
            for s in spreads
            if meets_thresholds(
                self.config.thresholds,
                apr_pct=s.apr_pct,
                buy_premium_usd=s.buy_premium_usd,
                days_to_expiry=s.days_to_expiry,
                net_return_pct=s.net_return_pct,
                net_profit_usd=s.net_profit_usd,
            )
        ]
        if not built:
            async with get_session() as sess:
                await self._close_stale(sess, now)
                await sess.commit()
            return

        cutoff = now - timedelta(hours=1)
        new_rows: list[Opportunity] = []
        async with get_session() as sess:
            for s in built:
                match = (
                    (
                        await sess.execute(
                            select(Opportunity)
                            .where(
                                Opportunity.instrument == s.instrument,
                                Opportunity.buy_from == s.buy_from,
                                Opportunity.sell_to == s.sell_to,
                                Opportunity.live_status != LiveStatus.EXPIRED,
                                Opportunity.detected_at >= cutoff,
                            )
                            .order_by(col(Opportunity.detected_at).desc())
                        )
                    )
                    .scalars()
                    .first()
                )

                if match is not None:
                    if match.live_status == LiveStatus.STALE:  # flickered back
                        match.live_status = LiveStatus.LIVE
                        match.closed_at = None
                        match.close_reason = None
                    take_snap = should_snapshot(
                        last_snapshot_at=match.last_snapshot_at,
                        last_value=match.last_snapshot_net_profit_usd,
                        new_value=float(s.net_profit_usd),
                        now=now,
                        min_interval_sec=scfg.snapshot_min_interval_sec,
                        delta=scfg.snapshot_delta_usd,
                    )
                    _apply_economics(match, s)
                    match.last_seen_at = now
                    match.samples_count += 1
                    match.peak_net_profit_usd = max(
                        match.peak_net_profit_usd, float(s.net_profit_usd)
                    )
                    match.peak_apr_pct = max(match.peak_apr_pct, float(s.apr_pct))
                    if take_snap:
                        sess.add(_snapshot(match.id, s, now))
                        match.last_snapshot_at = now
                        match.last_snapshot_net_profit_usd = float(s.net_profit_usd)
                    continue

                ex_cfg = self.config.exchanges.get(s.buy_from)
                row = _new_opportunity(s, mode, ex_cfg.network if ex_cfg else "mainnet", now)
                sess.add(row)
                await sess.flush()  # need row.id for the snapshot FK
                sess.add(_snapshot(row.id, s, now))
                new_rows.append(row)

            await self._close_stale(sess, now)
            await sess.commit()

        for row in new_rows:
            max_profit_usd = round(row.net_profit_usd, 2)
            await bus.publish(
                Event(
                    type="opportunity_detected",
                    level="info",
                    message=f"{row.instrument} {row.apr_pct:.1f}% APR",
                    payload={
                        "instrument": row.instrument,
                        "apr_pct": row.apr_pct,
                        "buy_from": row.buy_from,
                        "sell_to": row.sell_to,
                        "max_notional_usd": row.buy_premium_usd,
                        "max_profit_usd": max_profit_usd,
                    },
                )
            )
        if new_rows:
            log.info("wrote %d new opportunities", len(new_rows))

    async def _close_stale(self, sess: object, now: datetime) -> None:
        """Age out opportunities the screener no longer detects. Touches only
        `live_status` / `closed_at` / `close_reason` — never the executor's
        `status`. `synchronize_session=False`: the targeted rows are precisely
        the ones NOT seen this tick."""
        opts = {"synchronize_session": False}
        cutoff = now - timedelta(seconds=self.config.screener.close_after_stale_sec)
        await sess.execute(  # type: ignore[attr-defined]
            update(Opportunity)
            .where(
                col(Opportunity.live_status) == LiveStatus.LIVE,
                col(Opportunity.expiry) < now,
            )
            .values(live_status=LiveStatus.EXPIRED, closed_at=now, close_reason="expired"),
            execution_options=opts,
        )
        await sess.execute(  # type: ignore[attr-defined]
            update(Opportunity)
            .where(
                col(Opportunity.live_status) == LiveStatus.LIVE,
                col(Opportunity.last_seen_at) < cutoff,
            )
            .values(live_status=LiveStatus.STALE, closed_at=now, close_reason="stale"),
            execution_options=opts,
        )


_ECON_FIELDS = (
    "tradeable_size",
    "buy_premium_usd",
    "sell_premium_usd",
    "estimated_short_margin_usd",
    "capital_required_usd",
    "gross_profit_usd",
    "fees_usd",
    "net_profit_usd",
    "price_spread_pct",
    "net_return_pct",
    "apr_pct",
)


def _apply_economics(opp: Opportunity, s: Spread) -> None:
    opp.top_ask = float(s.buy_ask)
    opp.top_bid = float(s.sell_bid)
    for f in _ECON_FIELDS:
        setattr(opp, f, float(getattr(s, f)))


def _new_opportunity(s: Spread, mode: Mode, network: str, now: datetime) -> Opportunity:
    opp = Opportunity(
        detected_at=now,
        mode=mode,
        network=network,
        instrument=s.instrument,
        symbol=s.symbol,
        expiry=s.expiry,
        strike=float(s.strike),
        option_type=s.option_type,
        buy_from=s.buy_from,
        sell_to=s.sell_to,
        top_ask=float(s.buy_ask),
        top_bid=float(s.sell_bid),
        tradeable_size=float(s.tradeable_size),
        buy_premium_usd=float(s.buy_premium_usd),
        sell_premium_usd=float(s.sell_premium_usd),
        estimated_short_margin_usd=float(s.estimated_short_margin_usd),
        capital_required_usd=float(s.capital_required_usd),
        gross_profit_usd=float(s.gross_profit_usd),
        fees_usd=float(s.fees_usd),
        net_profit_usd=float(s.net_profit_usd),
        price_spread_pct=float(s.price_spread_pct),
        net_return_pct=float(s.net_return_pct),
        apr_pct=float(s.apr_pct),
        status=OpportunityStatus.PENDING,
        live_status=LiveStatus.LIVE,
        last_seen_at=now,
        samples_count=1,
        peak_net_profit_usd=float(s.net_profit_usd),
        peak_apr_pct=float(s.apr_pct),
        last_snapshot_at=now,
        last_snapshot_net_profit_usd=float(s.net_profit_usd),
    )
    return opp


def _snapshot(opp_id: int | None, s: Spread, ts: datetime) -> OpportunitySnapshot:
    return OpportunitySnapshot(
        opportunity_id=opp_id or 0,
        ts=ts,
        top_ask=float(s.buy_ask),
        top_bid=float(s.sell_bid),
        tradeable_size=float(s.tradeable_size),
        buy_premium_usd=float(s.buy_premium_usd),
        sell_premium_usd=float(s.sell_premium_usd),
        capital_required_usd=float(s.capital_required_usd),
        fees_usd=float(s.fees_usd),
        net_profit_usd=float(s.net_profit_usd),
        net_return_pct=float(s.net_return_pct),
        apr_pct=float(s.apr_pct),
        price_spread_pct=float(s.price_spread_pct),
        underlying_price=float(s.underlying_price) if s.underlying_price is not None else None,
    )
