from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlmodel import select

from option_arb.config import AppConfig, settings
from option_arb.db.models import Mode, Opportunity, OpportunityStatus, TickerState
from option_arb.db.session import get_session
from option_arb.economics import meets_thresholds
from option_arb.events import Event, bus
from option_arb.market.book_cache import BookCache, CachedTicker
from option_arb.services.comparator import Quote, compare_options

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

        if not groups:
            return

        spreads = compare_options(
            groups,
            min_leg_premium_liquidity_usd=Decimal(
                str(self.config.thresholds.min_leg_premium_liquidity_usd)
            ),
        )
        if not spreads:
            return

        mode = Mode(self.config.executor.mode)

        rows: list[Opportunity] = []
        for s in spreads:
            if not meets_thresholds(
                self.config.thresholds,
                apr_pct=s.apr_pct,
                buy_premium_usd=s.buy_premium_usd,
                days_to_expiry=s.days_to_expiry,
                net_return_pct=s.net_return_pct,
                net_profit_usd=s.net_profit_usd,
            ):
                continue
            ex_cfg = self.config.exchanges.get(s.buy_from)
            network = ex_cfg.network if ex_cfg else "mainnet"
            rows.append(
                Opportunity(
                    detected_at=datetime.now(tz=UTC),
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
                )
            )

        if not rows:
            return

        cutoff = datetime.now(UTC) - timedelta(hours=1)
        new_rows: list[Opportunity] = []
        async with get_session() as sess:
            for row in rows:
                existing = (
                    await sess.execute(
                        select(Opportunity).where(
                            Opportunity.instrument == row.instrument,
                            Opportunity.buy_from == row.buy_from,
                            Opportunity.sell_to == row.sell_to,
                            Opportunity.status == OpportunityStatus.PENDING,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    existing.top_ask = row.top_ask
                    existing.top_bid = row.top_bid
                    existing.tradeable_size = row.tradeable_size
                    existing.buy_premium_usd = row.buy_premium_usd
                    existing.sell_premium_usd = row.sell_premium_usd
                    existing.estimated_short_margin_usd = row.estimated_short_margin_usd
                    existing.capital_required_usd = row.capital_required_usd
                    existing.gross_profit_usd = row.gross_profit_usd
                    existing.fees_usd = row.fees_usd
                    existing.net_profit_usd = row.net_profit_usd
                    existing.price_spread_pct = row.price_spread_pct
                    existing.net_return_pct = row.net_return_pct
                    existing.apr_pct = row.apr_pct
                    continue
                # don't recreate if already seen recently (any status)
                recent = (
                    await sess.execute(
                        select(Opportunity).where(
                            Opportunity.instrument == row.instrument,
                            Opportunity.buy_from == row.buy_from,
                            Opportunity.sell_to == row.sell_to,
                            Opportunity.detected_at >= cutoff,
                        )
                    )
                ).scalar_one_or_none()
                if recent is None:
                    sess.add(row)
                    new_rows.append(row)
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
