from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlmodel import col, select

from option_arb.config import AppConfig
from option_arb.db.models import (
    LiveStatus,
    Mode,
    StructuredOpportunity,
    StructuredOpportunitySnapshot,
)
from option_arb.db.session import get_session
from option_arb.events import Event, bus
from option_arb.heartbeat import beat
from option_arb.market.book_cache import BookCache
from option_arb.services.comparator import Quote
from option_arb.services.screener import _cached_to_quote
from option_arb.services.snapshots import should_snapshot
from option_arb.structured.strategies import detect_boxes
from option_arb.structured.types import StructuredOpportunityDTO

log = logging.getLogger(__name__)


class StructuredScreener:
    """Reads the shared `BookCache` every `structured.poll_interval_ms`, groups
    quotes by (underlying, expiry), runs the box detector, and maintains
    `structured_opportunities` + a `structured_opportunity_snapshots` time series.
    Independent of the 1:1 `Screener` and the executor — different tables, no
    shared state beyond the read-only cache.

    Identity of an opportunity is `(strategy_type, underlying, expiry, strikes)`.
    The winning venue mix is evolving state, captured in snapshots.
    """

    def __init__(self, cache: BookCache, config: AppConfig) -> None:
        self.cache = cache
        self.config = config
        self._stop = asyncio.Event()

    async def run(self) -> None:
        interval = self.config.structured.poll_interval_ms / 1000.0
        log.info("structured screener started (interval=%.2fs)", interval)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                log.exception("structured tick failed: %s", e)
            beat("structured")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    def _group_quotes(self) -> dict[tuple[str, datetime], list[Quote]]:
        now = datetime.now(UTC)
        groups: dict[tuple[str, datetime], list[Quote]] = {}
        for tickers in self.cache.by_normalized_name().values():
            for t in tickers:
                q = _cached_to_quote(t)
                if q is None or q.expiry <= now:
                    continue
                expiry = q.expiry if q.expiry.tzinfo else q.expiry.replace(tzinfo=UTC)
                groups.setdefault((q.underlying, expiry), []).append(q)
        # a box needs 4 legs → at least 4 quotes in the group
        return {k: v for k, v in groups.items() if len(v) >= 4}

    def _network_for(self, dto: StructuredOpportunityDTO) -> str:
        buy_leg = next((leg for leg in dto.legs if leg.side == "buy"), dto.legs[0])
        ex_cfg = self.config.exchanges.get(buy_leg.exchange)
        return ex_cfg.network if ex_cfg else "mainnet"

    def _new_row(self, dto: StructuredOpportunityDTO, now: datetime) -> StructuredOpportunity:
        total = float(dto.max_total_profit)
        edge = float(dto.min_profit_per_unit)
        return StructuredOpportunity(
            strategy_type=dto.strategy_type,
            underlying=dto.underlying,
            expiry=dto.expiry,
            strikes=[float(k) for k in dto.strikes],
            legs=[leg.as_dict() for leg in dto.legs],
            is_fixed_payoff=dto.is_fixed_payoff,
            settlement_risk=dto.settlement_risk,
            min_payoff=float(dto.width),
            max_payoff=float(dto.width),
            entry_cost=float(dto.entry_cost),
            max_fees=float(dto.max_fees),
            min_profit=edge,
            max_profit=edge,
            max_size=float(dto.max_size),
            capital_required_usd=float(dto.capital_required),
            max_total_profit_usd=total,
            spot=float(dto.spot) if dto.spot is not None else None,
            mode=Mode(self.config.executor.mode),
            network=self._network_for(dto),
            detected_at=now,
            updated_at=now,
            last_seen_at=now,
            samples_count=1,
            peak_total_profit_usd=total,
            peak_min_profit=edge,
            last_snapshot_at=now,
            last_snapshot_total_profit_usd=total,
            live_status=LiveStatus.LIVE,
        )

    @staticmethod
    def _snapshot(
        opp_id: int | None, dto: StructuredOpportunityDTO, ts: datetime
    ) -> StructuredOpportunitySnapshot:
        return StructuredOpportunitySnapshot(
            opportunity_id=opp_id or 0,
            ts=ts,
            entry_cost=float(dto.entry_cost),
            max_fees=float(dto.max_fees),
            min_profit=float(dto.min_profit_per_unit),
            max_size=float(dto.max_size),
            capital_required_usd=float(dto.capital_required),
            max_total_profit_usd=float(dto.max_total_profit),
            legs=[leg.as_dict() for leg in dto.legs],
            underlying_price=float(dto.spot) if dto.spot is not None else None,
        )

    def _should_snapshot(
        self, parent: StructuredOpportunity, dto: StructuredOpportunityDTO, now: datetime
    ) -> bool:
        cfg = self.config.structured
        return should_snapshot(
            last_snapshot_at=parent.last_snapshot_at,
            last_value=parent.last_snapshot_total_profit_usd,
            new_value=float(dto.max_total_profit),
            now=now,
            min_interval_sec=cfg.snapshot_min_interval_sec,
            delta=cfg.snapshot_edge_delta_usd,
            extra_trigger=_leg_ids(parent.legs) != _dto_leg_ids(dto),  # venue mix changed
        )

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        groups = self._group_quotes()
        dtos = detect_boxes(groups, self.config.structured.thresholds) if groups else []

        new_rows: list[StructuredOpportunity] = []
        async with get_session() as sess:
            for dto in dtos:
                strikes = [float(k) for k in dto.strikes]
                parent = (
                    await sess.execute(
                        select(StructuredOpportunity).where(
                            StructuredOpportunity.strategy_type == dto.strategy_type,
                            StructuredOpportunity.underlying == dto.underlying,
                            StructuredOpportunity.expiry == dto.expiry,
                            StructuredOpportunity.live_status == LiveStatus.LIVE,
                        )
                    )
                ).scalars()
                match = next((p for p in parent if p.strikes == strikes), None)

                if match is None:
                    row = self._new_row(dto, now)
                    sess.add(row)
                    await sess.flush()  # need row.id for the snapshot FK
                    sess.add(self._snapshot(row.id, dto, now))
                    new_rows.append(row)
                    continue

                take_snap = self._should_snapshot(match, dto, now)
                total = float(dto.max_total_profit)
                edge = float(dto.min_profit_per_unit)
                match.legs = [leg.as_dict() for leg in dto.legs]
                match.is_fixed_payoff = dto.is_fixed_payoff
                match.settlement_risk = dto.settlement_risk
                match.entry_cost = float(dto.entry_cost)
                match.max_fees = float(dto.max_fees)
                match.min_profit = edge
                match.max_profit = edge
                match.max_size = float(dto.max_size)
                match.capital_required_usd = float(dto.capital_required)
                match.max_total_profit_usd = total
                match.spot = float(dto.spot) if dto.spot is not None else match.spot
                match.updated_at = now
                match.last_seen_at = now
                match.samples_count += 1
                match.peak_total_profit_usd = max(match.peak_total_profit_usd, total)
                match.peak_min_profit = max(match.peak_min_profit, edge)
                if take_snap:
                    sess.add(self._snapshot(match.id, dto, now))
                    match.last_snapshot_at = now
                    match.last_snapshot_total_profit_usd = total

            await self._close_stale(sess, now)
            await sess.commit()

        for row in new_rows:
            await bus.publish(
                Event(
                    type="structured_opportunity_detected",
                    level="info",
                    message=(
                        f"{row.strategy_type} {row.underlying} "
                        f"{'/'.join(str(int(k)) for k in row.strikes)} "
                        f"${row.max_total_profit_usd:.0f}"
                    ),
                    payload={
                        "strategy_type": row.strategy_type,
                        "underlying": row.underlying,
                        "strikes": row.strikes,
                        "max_total_profit_usd": round(row.max_total_profit_usd, 2),
                        "settlement_risk": row.settlement_risk,
                        "is_fixed_payoff": row.is_fixed_payoff,
                    },
                )
            )
        if new_rows:
            log.info("structured: wrote %d new opportunities", len(new_rows))

    async def _close_stale(self, sess: Any, now: datetime) -> None:
        # Targets only rows NOT touched this tick (stale / past expiry), so we
        # don't need in-session sync — and "evaluate" trips over SQLite's
        # naive datetimes in tests.
        opts = {"synchronize_session": False}
        cutoff = now - timedelta(seconds=self.config.structured.close_after_stale_sec)
        await sess.execute(
            update(StructuredOpportunity)
            .where(
                col(StructuredOpportunity.live_status) == LiveStatus.LIVE,
                col(StructuredOpportunity.expiry) < now,
            )
            .values(live_status=LiveStatus.EXPIRED, closed_at=now, close_reason="expired"),
            execution_options=opts,
        )
        await sess.execute(
            update(StructuredOpportunity)
            .where(
                col(StructuredOpportunity.live_status) == LiveStatus.LIVE,
                col(StructuredOpportunity.last_seen_at) < cutoff,
            )
            .values(live_status=LiveStatus.STALE, closed_at=now, close_reason="stale"),
            execution_options=opts,
        )


def _leg_ids(legs: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple((leg["exchange"], leg["instrument"], leg["side"]) for leg in legs)


def _dto_leg_ids(dto: StructuredOpportunityDTO) -> tuple[Any, ...]:
    return tuple((leg.exchange, leg.instrument, leg.side) for leg in dto.legs)
