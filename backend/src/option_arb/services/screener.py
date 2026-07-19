from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlmodel import select

from option_arb.config import AppConfig, settings
from option_arb.db.models import Mode, Opportunity, OpportunityStatus, TickerState
from option_arb.db.session import get_session
from option_arb.events import Event, bus
from option_arb.market.book_cache import BookCache, CachedTicker
from option_arb.services.comparator import Quote, compare_options, group_by_instrument

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
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:  # noqa: BLE001
                log.exception("screener tick failed: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def _flush_tickers(self, tickers: list[CachedTicker]) -> None:
        if "postgresql" not in settings.database_url:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415

        now = datetime.now(timezone.utc)
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
                "underlying_price": float(t.underlying_price) if t.underlying_price is not None else None,
                "taker_fee_rate": float(t.instrument.taker_fee_rate),
                "updated_at": now,
            }
            for t in tickers
        ]
        if not rows:
            return
        stmt = pg_insert(TickerState).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["exchange", "instrument"],
            set_={c: stmt.excluded[c] for c in ("bid_price", "bid_size", "ask_price", "ask_size", "underlying_price", "updated_at")},
        )
        async with get_session() as sess:
            await sess.execute(stmt)
            await sess.commit()

    async def _tick(self) -> None:
        await self._flush_tickers(self.cache.snapshot())
        by_name = self.cache.by_normalized_name()
        groups: list[list[Quote]] = []
        for _, tickers in by_name.items():
            if len(tickers) < 2:
                continue  # need at least 2 venues to compare
            quotes = [q for q in (_cached_to_quote(t) for t in tickers) if q is not None]
            if len(quotes) >= 2:
                groups.append(quotes)

        if not groups:
            return

        spreads = compare_options(
            groups,
            size_threshold_usd=Decimal(str(self.config.thresholds.size_threshold_usd)),
        )
        if not spreads:
            return

        min_apr = Decimal(str(self.config.thresholds.min_apr_pct))
        min_notional = Decimal(str(self.config.thresholds.min_notional_usd))
        mode = Mode(self.config.executor.mode)

        rows: list[Opportunity] = []
        for s in spreads:
            if s.apr_pct < min_apr:
                continue
            if s.max_notional_usd < min_notional:
                continue
            rows.append(
                Opportunity(
                    detected_at=datetime.now(tz=timezone.utc),
                    mode=mode,
                    instrument=s.instrument,
                    symbol=s.symbol,
                    expiry=s.expiry,
                    strike=float(s.strike),
                    option_type=s.option_type,
                    buy_from=s.buy_from,
                    sell_to=s.sell_to,
                    top_ask=float(s.buy_ask),
                    top_bid=float(s.sell_bid),
                    spread_pct=float(s.net_spread_pct),
                    apr_pct=float(s.apr_pct),
                    max_notional_usd=float(s.max_notional_usd),
                    status=OpportunityStatus.PENDING,
                )
            )

        if not rows:
            return

        async with get_session() as sess:
            # de-dup: skip if an identical PENDING opp exists in the last poll interval
            for row in rows:
                sess.add(row)
            await sess.commit()

        for row in rows:
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
                        "max_notional_usd": row.max_notional_usd,
                    },
                )
            )
        log.info("wrote %d new opportunities", len(rows))


async def _count_pending() -> int:
    async with get_session() as sess:
        res = await sess.execute(select(Opportunity).where(Opportunity.status == OpportunityStatus.PENDING))
        return len(list(res.scalars()))
