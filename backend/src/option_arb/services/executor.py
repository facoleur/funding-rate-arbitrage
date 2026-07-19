from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy import func
from sqlmodel import select

from option_arb.config import AppConfig, load_config
from option_arb.db.models import (
    Mode,
    Opportunity,
    OpportunityStatus,
    Order,
    OrderKind,
    OrderStatus,
    Side,
    Trade,
    TradeStatus,
)
from option_arb.db.session import get_session, init_db
from option_arb.events import Event, bus
from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    BookLevel,
    Instrument,
    OrderRequest,
    OrderResult,
)

log = logging.getLogger(__name__)

ACTIVE_TRADE_STATES = (
    TradeStatus.PLACING,
    TradeStatus.LEG1_FILLED,
    TradeStatus.LEG2_FILLED,
    TradeStatus.HEDGING,
)


class Executor:
    """State machine per PENDING opportunity:
    1. kill-switches
    2. fresh REST L2 refetch on both venues
    3. walk book → recompute walked_size + APR net of slippage
    4. place both IOC limits in parallel
    5. handle {both filled | single leg | none}
    6. persist every transition to trades + orders
    """

    def __init__(
        self,
        config: AppConfig,
        exchanges: dict[str, AbstractExchange],
        instruments_by_name: dict[str, dict[str, Instrument]] | None = None,
    ) -> None:
        self.config = config
        self.exchanges = exchanges
        self._instruments_by_name = instruments_by_name or {name: {} for name in exchanges}
        self._stop = asyncio.Event()

    def register_instrument(self, exchange: str, inst: Instrument) -> None:
        self._instruments_by_name.setdefault(exchange, {})[inst.normalized_name] = inst

    async def run(self) -> None:
        interval = self.config.executor.poll_interval_ms / 1000.0
        log.info("executor started (mode=%s, interval=%.2fs)", self.config.executor.mode, interval)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                log.exception("executor tick failed: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    # -----------------------------------------------------------------

    async def _tick(self) -> None:
        async with get_session() as sess:
            stmt = (
                select(Opportunity).where(Opportunity.status == OpportunityStatus.PENDING).limit(20)
            )
            pending = list((await sess.execute(stmt)).scalars())
        for opp in pending:
            await self._process(opp)

    async def _process(self, opp: Opportunity) -> None:
        # 1. kill-switches
        killed_reason = await self._kill_switch_check()
        if killed_reason:
            await self._reject(opp, killed_reason)
            await bus.publish(
                Event(
                    type="kill_switch_tripped",
                    level="warn",
                    message=f"opp {opp.id} rejected: {killed_reason}",
                    payload={"opportunity_id": opp.id},
                )
            )
            return

        # 2. fresh L2 refetch — parallel
        buy_ex = self.exchanges.get(opp.buy_from)
        sell_ex = self.exchanges.get(opp.sell_to)
        if not buy_ex or not sell_ex:
            await self._reject(opp, f"unknown_exchange({opp.buy_from},{opp.sell_to})")
            return
        buy_inst = self._instruments_by_name.get(opp.buy_from, {}).get(opp.instrument)
        sell_inst = self._instruments_by_name.get(opp.sell_to, {}).get(opp.instrument)
        if not buy_inst or not sell_inst:
            await self._reject(opp, "instrument_metadata_missing")
            return

        timeout = self.config.executor.fresh_fetch_timeout_ms / 1000.0
        try:
            buy_book, sell_book = await asyncio.wait_for(
                asyncio.gather(
                    buy_ex.get_orderbook_l2(buy_inst),
                    sell_ex.get_orderbook_l2(sell_inst),
                ),
                timeout=timeout,
            )
        except (TimeoutError, Exception) as e:
            await self._reject(opp, f"stale_book:{type(e).__name__}")
            return

        # 3. walk book, recompute
        walked = self._walk_and_verify(opp, buy_book, sell_book, buy_inst, sell_inst)
        if isinstance(walked, str):
            await self._reject(opp, walked)
            return
        walked_ask, walked_bid, walked_size = walked

        # persist walked values on the opportunity + create Trade in PLACING
        async with get_session() as sess:
            opp2 = await sess.get(Opportunity, opp.id)
            assert opp2 is not None
            opp2.walked_ask = float(walked_ask)
            opp2.walked_bid = float(walked_bid)
            opp2.walked_size = float(walked_size)
            opp2.status = OpportunityStatus.APPROVED
            trade = Trade(
                opportunity_id=opp.id,
                opened_at=datetime.now(UTC),
                mode=Mode(self.config.executor.mode),
                status=TradeStatus.PLACING,
                buy_exchange=opp.buy_from,
                sell_exchange=opp.sell_to,
                requested_size=float(walked_size),
            )
            sess.add(trade)
            await sess.commit()
            await sess.refresh(trade)
            assert trade.id is not None

        await bus.publish(
            Event(
                type="trade_opened",
                level="info",
                message=f"trade {trade.id} placing {walked_size} {opp.instrument}",
                payload={"trade_id": trade.id, "opportunity_id": opp.id},
            )
        )

        # 4. place both IOC limits in parallel
        slip = Decimal(str(self.config.executor.max_slippage_pct)) / Decimal(100)
        buy_limit = walked_ask * (Decimal(1) + slip)
        sell_limit = walked_bid * (Decimal(1) - slip)

        buy_req = OrderRequest(
            exchange=opp.buy_from,
            instrument=buy_inst.instrument_name,
            side="BUY",
            size=walked_size,
            limit_price=buy_limit,
            time_in_force="IOC",
        )
        sell_req = OrderRequest(
            exchange=opp.sell_to,
            instrument=sell_inst.instrument_name,
            side="SELL",
            size=walked_size,
            limit_price=sell_limit,
            time_in_force="IOC",
        )

        buy_order = await self._create_order(trade.id, buy_req, OrderKind.IOC_LIMIT)
        sell_order = await self._create_order(trade.id, sell_req, OrderKind.IOC_LIMIT)

        buy_res, sell_res = await asyncio.gather(
            buy_ex.place_order(buy_req),
            sell_ex.place_order(sell_req),
            return_exceptions=True,
        )
        if isinstance(buy_res, BaseException):
            buy_res = OrderResult(status="REJECTED", reason=str(buy_res))
        if isinstance(sell_res, BaseException):
            sell_res = OrderResult(status="REJECTED", reason=str(sell_res))

        await self._update_order(buy_order.id, buy_res)
        await self._update_order(sell_order.id, sell_res)

        # 5. dispatch on outcome
        buy_ok = buy_res.status in ("FILLED", "PARTIAL") and buy_res.filled_size > 0
        sell_ok = sell_res.status in ("FILLED", "PARTIAL") and sell_res.filled_size > 0

        if buy_ok and sell_ok:
            await self._finalize_filled(trade.id, opp, buy_res, sell_res)
        elif buy_ok ^ sell_ok:  # exactly one filled
            await self._market_out(trade, opp, buy_ok, buy_res, sell_res, buy_inst, sell_inst)
        else:
            await self._finalize_failed(trade.id, opp, buy_res, sell_res)

    # -----------------------------------------------------------------

    async def _kill_switch_check(self) -> str | None:
        limits = self.config.limits
        if Path(limits.kill_switch_file).exists():
            return "kill_switch_file"

        async with get_session() as sess:
            open_count = (
                await sess.execute(
                    select(func.count())
                    .select_from(Trade)
                    .where(Trade.status.in_(ACTIVE_TRADE_STATES))  # type: ignore[attr-defined]
                )
            ).scalar_one()
            if open_count >= limits.max_positions_open:
                return f"max_positions_open({open_count})"

            midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            daily_pnl = (
                await sess.execute(
                    select(func.coalesce(func.sum(Trade.net_pnl_usd), 0.0)).where(
                        Trade.opened_at >= midnight
                    )
                )
            ).scalar_one()
            if float(daily_pnl or 0) <= -limits.max_daily_loss_usd:
                return f"max_daily_loss({daily_pnl:.2f})"

        return None

    def _walk_and_verify(
        self,
        opp: Opportunity,
        buy_book: Book,
        sell_book: Book,
        buy_inst: Instrument,
        sell_inst: Instrument,
    ) -> tuple[Decimal, Decimal, Decimal] | str:
        cfg = self.config
        limits = cfg.limits
        min_apr = Decimal(str(cfg.thresholds.min_apr_pct))
        min_notional = Decimal(str(cfg.thresholds.min_notional_usd))
        cap = Decimal(str(limits.max_notional_per_trade_usd))

        # Progressive size search: try increasing sizes; stop before APR drops.
        candidate_size = _max_size_within_cap(buy_book.asks, sell_book.bids, cap)
        if candidate_size <= 0:
            return "empty_book"

        # binary-shrink to find the largest size that keeps APR >= threshold
        low, high = Decimal("0"), candidate_size
        best: tuple[Decimal, Decimal, Decimal] | None = None
        for _ in range(20):
            mid = (low + high) / Decimal(2)
            if mid <= 0:
                break
            walked_ask, filled_ask = _walk(mid, buy_book.asks)
            walked_bid, filled_bid = _walk(mid, sell_book.bids)
            if filled_ask < mid or filled_bid < mid:
                high = mid - Decimal("0.0001")
                continue
            spread_pct = (walked_bid - walked_ask) / walked_ask * Decimal(100)
            fee_pct = (buy_inst.taker_fee_rate + sell_inst.taker_fee_rate) * Decimal(100)
            net_pct = spread_pct - fee_pct
            exp = opp.expiry if opp.expiry.tzinfo else opp.expiry.replace(tzinfo=UTC)
            days = max((exp - datetime.now(UTC)).total_seconds() / 86400.0, 1e-6)
            apr = net_pct / Decimal(str(days)) * Decimal(365)
            if apr >= min_apr and net_pct > 0:
                best = (walked_ask, walked_bid, mid)
                low = mid + Decimal("0.0001")
            else:
                high = mid - Decimal("0.0001")

        if best is None:
            return "apr_dropped"
        walked_ask, walked_bid, walked_size = best
        notional = walked_size * walked_ask
        if notional < min_notional:
            return "size_too_small"
        return best

    async def _reject(self, opp: Opportunity, reason: str) -> None:
        async with get_session() as sess:
            row = await sess.get(Opportunity, opp.id)
            if row:
                row.status = OpportunityStatus.REJECTED
                row.rejection_reason = reason
                await sess.commit()
        log.info("opp %s rejected: %s", opp.id, reason)

    async def _create_order(
        self, trade_id: int | None, req: OrderRequest, kind: OrderKind
    ) -> Order:
        assert trade_id is not None
        async with get_session() as sess:
            order = Order(
                trade_id=trade_id,
                exchange=req.exchange,
                side=Side(req.side),
                kind=kind,
                requested_price=float(req.limit_price),
                requested_size=float(req.size),
                status=OrderStatus.PLACING,
            )
            sess.add(order)
            await sess.commit()
            await sess.refresh(order)
            return order

    async def _update_order(self, order_id: int | None, res: OrderResult) -> None:
        assert order_id is not None
        async with get_session() as sess:
            order = await sess.get(Order, order_id)
            if not order:
                return
            order.status = OrderStatus(
                res.status if res.status in {s.value for s in OrderStatus} else "REJECTED"
            )
            order.filled_price = float(res.filled_price) if res.filled_price else None
            order.filled_size = float(res.filled_size) if res.filled_size else None
            order.exchange_order_id = res.exchange_order_id
            order.updated_at = datetime.now(UTC)
            order.raw_response = str(res.raw_response) if res.raw_response else None
            await sess.commit()

    async def _finalize_filled(
        self, trade_id: int, opp: Opportunity, buy_res: OrderResult, sell_res: OrderResult
    ) -> None:
        pnl = float(
            sell_res.filled_size * sell_res.filled_price
            - buy_res.filled_size * buy_res.filled_price
        )
        async with get_session() as sess:
            trade = await sess.get(Trade, trade_id)
            opp_row = await sess.get(Opportunity, opp.id)
            if trade and opp_row:
                trade.status = TradeStatus.FILLED
                trade.closed_at = datetime.now(UTC)
                trade.buy_fill_price = float(buy_res.filled_price)
                trade.buy_fill_size = float(buy_res.filled_size)
                trade.sell_fill_price = float(sell_res.filled_price)
                trade.sell_fill_size = float(sell_res.filled_size)
                trade.net_pnl_usd = pnl
                opp_row.status = OpportunityStatus.EXECUTED
                await sess.commit()
        await bus.publish(
            Event(
                type="trade_filled",
                level="info",
                message=f"trade {trade_id} filled pnl=${pnl:.2f}",
                payload={"trade_id": trade_id, "pnl_usd": pnl},
            )
        )

    async def _finalize_failed(
        self, trade_id: int, opp: Opportunity, buy_res: OrderResult, sell_res: OrderResult
    ) -> None:
        async with get_session() as sess:
            trade = await sess.get(Trade, trade_id)
            opp_row = await sess.get(Opportunity, opp.id)
            if trade and opp_row:
                trade.status = TradeStatus.FAILED
                trade.closed_at = datetime.now(UTC)
                trade.error = f"buy={buy_res.reason} sell={sell_res.reason}"
                opp_row.status = OpportunityStatus.REJECTED
                opp_row.rejection_reason = "both_legs_failed"
                await sess.commit()
        await bus.publish(
            Event(
                type="trade_failed",
                level="info",
                message=f"trade {trade_id} failed: both legs rejected",
                payload={"trade_id": trade_id},
            )
        )

    async def _market_out(
        self,
        trade: Trade,
        opp: Opportunity,
        buy_filled: bool,
        buy_res: OrderResult,
        sell_res: OrderResult,
        buy_inst: Instrument,
        sell_inst: Instrument,
    ) -> None:
        """Exactly one leg filled — emergency market-out on the other side of
        the venue that filled. Uses a very permissive IOC limit (±5%)."""
        # Mark trade in HEDGING while we try to close
        async with get_session() as sess:
            t = await sess.get(Trade, trade.id)
            if t:
                t.status = TradeStatus.HEDGING
                await sess.commit()

        side: Literal["BUY", "SELL"]
        if buy_filled:
            # we now own `buy_res.filled_size` on the buy venue → SELL it back
            ex_name = opp.buy_from
            inst = buy_inst
            side = "SELL"
            filled_size = buy_res.filled_size
            entry_price = buy_res.filled_price
        else:
            ex_name = opp.sell_to
            inst = sell_inst
            side = "BUY"
            filled_size = sell_res.filled_size
            entry_price = sell_res.filled_price

        ex = self.exchanges[ex_name]
        try:
            book = await ex.get_orderbook_l2(inst)
        except Exception as e:
            await self._mark_stuck(trade.id, f"market_out_book_fetch: {e}")
            return

        mid = _mid_or(entry_price, book)
        limit = mid * (Decimal("0.95") if side == "SELL" else Decimal("1.05"))
        req = OrderRequest(
            exchange=ex_name,
            instrument=inst.instrument_name,
            side=side,
            size=filled_size,
            limit_price=limit,
            time_in_force="IOC",
        )
        order_row = await self._create_order(trade.id, req, OrderKind.MARKET_OUT)
        try:
            res = await ex.place_order(req)
        except Exception as e:
            res = OrderResult(status="REJECTED", reason=str(e))
        await self._update_order(order_row.id, res)

        if res.status in ("FILLED", "PARTIAL") and res.filled_size > 0:
            # compute hedge PnL
            hedge_pnl = float((res.filled_price - entry_price) * res.filled_size)
            # SELL: bought at entry, sold at filled → positive; BUY hedge: reversed
            pnl = hedge_pnl if side == "SELL" else -hedge_pnl
            async with get_session() as sess:
                t = await sess.get(Trade, trade.id)
                opp_row = await sess.get(Opportunity, opp.id)
                if t and opp_row:
                    t.status = TradeStatus.HEDGED
                    t.closed_at = datetime.now(UTC)
                    t.net_pnl_usd = pnl
                    t.error = "single_leg_hedged"
                    opp_row.status = OpportunityStatus.EXECUTED
                    await sess.commit()
            await bus.publish(
                Event(
                    type="trade_filled",
                    level="warn",
                    message=f"trade {trade.id} hedged pnl=${pnl:.2f}",
                    payload={"trade_id": trade.id, "pnl_usd": pnl, "hedged": True},
                )
            )
        else:
            await self._mark_stuck(trade.id, f"market_out_rejected:{res.reason}")

    async def _mark_stuck(self, trade_id: int | None, reason: str) -> None:
        assert trade_id is not None
        async with get_session() as sess:
            t = await sess.get(Trade, trade_id)
            if t:
                t.status = TradeStatus.STUCK
                t.error = reason
                await sess.commit()
        await bus.publish(
            Event(
                type="trade_stuck",
                level="error",
                message=f"trade {trade_id} STUCK: {reason} — MANUAL INTERVENTION REQUIRED",
                payload={"trade_id": trade_id, "reason": reason},
            )
        )


# ---------- helpers ----------


def _walk(size: Decimal, levels: list[BookLevel]) -> tuple[Decimal, Decimal]:
    if not levels or size <= 0:
        return Decimal(0), Decimal(0)
    remaining = size
    total_cost = Decimal(0)
    total_filled = Decimal(0)
    for lvl in levels:
        take = min(lvl.size, remaining)
        total_cost += take * lvl.price
        total_filled += take
        remaining -= take
        if remaining <= 0:
            break
    if total_filled == 0:
        return Decimal(0), Decimal(0)
    return total_cost / total_filled, total_filled


def _max_size_within_cap(asks: list[BookLevel], bids: list[BookLevel], cap_usd: Decimal) -> Decimal:
    """Maximum size that (a) can be filled on both sides and (b) stays under the notional cap."""
    if not asks or not bids:
        return Decimal(0)
    ask_size_total = sum((lvl.size for lvl in asks), Decimal(0))
    bid_size_total = sum((lvl.size for lvl in bids), Decimal(0))
    liquidity_size = min(ask_size_total, bid_size_total)
    # cap by notional: cap / worst-case ask
    cap_size = cap_usd / asks[0].price if asks[0].price > 0 else Decimal(0)
    return min(liquidity_size, cap_size)


def _mid_or(fallback: Decimal, book: Book) -> Decimal:
    top_bid = book.top_bid
    top_ask = book.top_ask
    if top_bid and top_ask:
        return (top_bid.price + top_ask.price) / Decimal(2)
    if top_bid:
        return top_bid.price
    if top_ask:
        return top_ask.price
    return fallback


# ---------- entry-point for executor container ----------


async def _amain() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    cfg = load_config()
    from option_arb.exchanges.registry import build_exchanges, close_exchanges

    exchanges = build_exchanges(cfg)
    try:
        exec_ = Executor(cfg, exchanges)
        await exec_.run()
    finally:
        await close_exchanges(exchanges)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
