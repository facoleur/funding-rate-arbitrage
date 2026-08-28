from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
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
from option_arb.economics import OptionEconomics, calculate_option_economics, days_to_expiry
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
    3. walk book → recompute canonical economics at worst IOC prices
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
                select(Opportunity)
                .where(Opportunity.status == OpportunityStatus.PENDING)
                # prioritize by estimated gross profit in USD (notional * spread%)
                .order_by(sa.text("net_profit_usd DESC"))
                .limit(20)
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

        # 2. expiry pre-check; all economic thresholds are rechecked on fresh books.
        exp = opp.expiry if opp.expiry.tzinfo else opp.expiry.replace(tzinfo=UTC)
        days_remaining = days_to_expiry(exp, datetime.now(UTC))
        if days_remaining <= 0:
            await self._reject(opp, "expiry_invalid")
            return
        if days_remaining > Decimal(self.config.thresholds.max_days_to_expiry):
            await self._reject(opp, f"expiry_too_far({days_remaining:.0f}d)")
            return

        # 3. trade_enabled check per exchange
        for ex_name in (opp.buy_from, opp.sell_to):
            ex_cfg = self.config.exchanges.get(ex_name)
            if ex_cfg and not ex_cfg.trade_enabled:
                await self._reject(opp, f"trading_disabled({ex_name})")
                return

        # 3. fresh L2 refetch — parallel
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
            results = await asyncio.wait_for(
                asyncio.gather(
                    buy_ex.get_orderbook_l2(buy_inst),
                    sell_ex.get_orderbook_l2(sell_inst),
                    buy_ex.get_available_funds(),
                    sell_ex.get_available_funds(),
                    return_exceptions=True,
                ),
                timeout=timeout,
            )
        except (TimeoutError, Exception) as e:
            await self._reject(opp, f"stale_book:{type(e).__name__}")
            return

        if isinstance(results[0], BaseException) or isinstance(results[1], BaseException):
            await self._reject(opp, f"stale_book:{type(results[0]).__name__}")
            return
        buy_book: Book = results[0]
        sell_book: Book = results[1]
        buy_funds: dict[str, Decimal] = (
            results[2] if not isinstance(results[2], BaseException) else {}
        )
        sell_funds: dict[str, Decimal] = (
            results[3] if not isinstance(results[3], BaseException) else {}
        )

        spot = _valid_spot(buy_book.underlying_price) or _valid_spot(sell_book.underlying_price)
        buy_avail_usd = _available_funds_usd(buy_funds, buy_inst.underlying, spot)
        sell_avail_usd = _available_funds_usd(sell_funds, sell_inst.underlying, spot)

        # 3. walk book, recompute
        walked = self._walk_and_verify(
            opp, buy_book, sell_book, buy_inst, sell_inst, buy_avail_usd, sell_avail_usd
        )
        if isinstance(walked, str):
            await self._reject(opp, walked)
            return
        walked_ask, walked_bid, buy_limit, sell_limit, economics = walked
        walked_size = economics.tradeable_size

        # persist walked values on the opportunity + create Trade in PLACING
        async with get_session() as sess:
            opp2 = await sess.get(Opportunity, opp.id)
            assert opp2 is not None
            opp2.walked_ask = float(walked_ask)
            opp2.walked_bid = float(walked_bid)
            opp2.verified_buy_limit = float(buy_limit)
            opp2.verified_sell_limit = float(sell_limit)
            opp2.verified_tradeable_size = float(economics.tradeable_size)
            opp2.verified_buy_premium_usd = float(economics.buy_premium_usd)
            opp2.verified_sell_premium_usd = float(economics.sell_premium_usd)
            opp2.verified_estimated_short_margin_usd = float(economics.estimated_short_margin_usd)
            opp2.verified_capital_required_usd = float(economics.capital_required_usd)
            opp2.verified_gross_profit_usd = float(economics.gross_profit_usd)
            opp2.verified_fees_usd = float(economics.fees_usd)
            opp2.verified_net_profit_usd = float(economics.net_profit_usd)
            opp2.verified_net_return_pct = float(economics.net_return_pct)
            opp2.verified_apr_pct = float(economics.apr_pct)
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
            await self._finalize_filled(
                trade.id, opp, buy_res, sell_res, buy_inst, sell_inst, walked_ask, walked_bid
            )
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
        buy_avail_usd: Decimal | None = None,
        sell_avail_usd: Decimal | None = None,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, OptionEconomics] | str:
        cfg = self.config
        limits = cfg.limits
        min_apr = Decimal(str(cfg.thresholds.min_apr_pct))
        min_buy_premium = Decimal(str(cfg.thresholds.min_buy_premium_usd))
        min_net_profit = Decimal(str(cfg.thresholds.min_net_profit_usd))
        min_net_return = Decimal(str(cfg.thresholds.min_net_return_pct))
        cap = Decimal(str(limits.max_buy_premium_per_trade_usd))
        if buy_avail_usd is not None:
            cap = min(cap, buy_avail_usd)
            if cap <= 0:
                return f"insufficient_buy_funds({buy_avail_usd:.0f})"
        slippage = Decimal(str(cfg.executor.ioc_slippage_limit_pct)) / Decimal(100)
        max_contracts = (
            Decimal(str(limits.max_contracts_per_trade)) if limits.max_contracts_per_trade else None
        )
        spot = _valid_spot(buy_book.underlying_price) or _valid_spot(sell_book.underlying_price)
        if spot is None:
            return "margin_unavailable"
        expiry = opp.expiry if opp.expiry.tzinfo else opp.expiry.replace(tzinfo=UTC)
        dte = days_to_expiry(expiry, datetime.now(UTC))
        if dte <= 0:
            return "expiry_invalid"

        candidate_size = _max_size_within_cap(
            buy_book.asks,
            sell_book.bids,
            cap,
            max_contracts,
            buy_price_multiplier=Decimal(1) + slippage,
        )
        if candidate_size <= 0:
            return "empty_book"

        def evaluate(
            size: Decimal,
        ) -> tuple[Decimal, Decimal, Decimal, Decimal, OptionEconomics] | None:
            walked_ask, filled_ask = _walk(size, buy_book.asks)
            walked_bid, filled_bid = _walk(size, sell_book.bids)
            if filled_ask < size or filled_bid < size:
                return None
            buy_limit = walked_ask * (Decimal(1) + slippage)
            sell_limit = walked_bid * (Decimal(1) - slippage)
            economics = calculate_option_economics(
                buy_price=buy_limit,
                sell_price=sell_limit,
                quantity=size,
                buy_taker_fee_rate=buy_inst.taker_fee_rate,
                sell_taker_fee_rate=sell_inst.taker_fee_rate,
                spot=spot,
                strike=sell_inst.strike,
                option_type=sell_inst.option_type,
                days_to_expiry=dte,
            )
            if economics is None:
                return None
            return walked_ask, walked_bid, buy_limit, sell_limit, economics

        def passes_quality(
            result: tuple[Decimal, Decimal, Decimal, Decimal, OptionEconomics],
        ) -> bool:
            economics = result[4]
            return (
                economics.buy_premium_usd <= cap
                and economics.net_profit_usd > 0
                and economics.net_return_pct >= min_net_return
                and economics.apr_pct >= min_apr
            )

        candidate = evaluate(candidate_size)
        best = candidate if candidate is not None and passes_quality(candidate) else None
        low, high = Decimal(0), candidate_size
        for _ in range(20 if best is None else 0):
            mid = (low + high) / Decimal(2)
            if mid <= 0:
                break
            result = evaluate(mid)
            if result is not None and passes_quality(result):
                best = result
                low = mid
            else:
                high = mid

        if best is None:
            return "apr_dropped"
        economics = best[4]
        walked_size = economics.tradeable_size
        if economics.buy_premium_usd < min_buy_premium:
            return "size_too_small"
        if economics.net_profit_usd < min_net_profit:
            return "profit_too_small"
        min_size = max(buy_inst.min_trade_amount, sell_inst.min_trade_amount)
        if min_size > 0 and walked_size < min_size:
            return f"size_below_minimum({float(walked_size):.4f}<{float(min_size):.4f})"
        if sell_avail_usd is not None and sell_avail_usd < economics.estimated_short_margin_usd:
            return (
                f"insufficient_sell_funds({sell_avail_usd:.0f}"
                f"<{economics.estimated_short_margin_usd:.0f})"
            )
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
        self,
        trade_id: int,
        opp: Opportunity,
        buy_res: OrderResult,
        sell_res: OrderResult,
        buy_inst: Instrument,
        sell_inst: Instrument,
        walked_ask: Decimal,
        walked_bid: Decimal,
    ) -> None:
        gross_pnl = (
            sell_res.filled_size * sell_res.filled_price
            - buy_res.filled_size * buy_res.filled_price
        )
        buy_fees = buy_res.filled_size * buy_res.filled_price * buy_inst.taker_fee_rate
        sell_fees = sell_res.filled_size * sell_res.filled_price * sell_inst.taker_fee_rate
        total_fees = buy_fees + sell_fees
        net_pnl = gross_pnl - total_fees

        # slippage: écart moyen entre walked price et fill réel, en %
        buy_slip = (
            (buy_res.filled_price - walked_ask) / walked_ask * Decimal(100)
            if walked_ask
            else Decimal(0)
        )
        sell_slip = (
            (walked_bid - sell_res.filled_price) / walked_bid * Decimal(100)
            if walked_bid
            else Decimal(0)
        )
        slippage_pct = float((buy_slip + sell_slip) / 2)

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
                trade.net_pnl_usd = float(net_pnl)
                trade.fees_usd = float(total_fees)
                trade.slippage_pct = slippage_pct
                opp_row.status = OpportunityStatus.EXECUTED
                await sess.commit()
        await bus.publish(
            Event(
                type="trade_filled",
                level="info",
                message=f"trade {trade_id} filled pnl=${float(net_pnl):.2f}",
                payload={"trade_id": trade_id, "pnl_usd": float(net_pnl)},
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
        slip = Decimal(str(self.config.executor.ioc_slippage_limit_pct)) / Decimal(100)
        limit = mid * (Decimal(1) - slip if side == "SELL" else Decimal(1) + slip)
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


def _max_size_within_cap(
    asks: list[BookLevel],
    bids: list[BookLevel],
    cap_usd: Decimal,
    max_contracts: Decimal | None = None,
    buy_price_multiplier: Decimal = Decimal(1),
) -> Decimal:
    """Maximum size allowed by book depth, the worst-price buy-premium cap, and contracts."""
    if not asks or not bids:
        return Decimal(0)
    ask_size_total = sum((lvl.size for lvl in asks), Decimal(0))
    bid_size_total = sum((lvl.size for lvl in bids), Decimal(0))
    liquidity_size = min(ask_size_total, bid_size_total)
    effective_buy_price = asks[0].price * buy_price_multiplier
    cap_size = cap_usd / effective_buy_price if effective_buy_price > 0 else Decimal(0)
    result = min(liquidity_size, cap_size)
    if max_contracts is not None:
        result = min(result, max_contracts)
    return result


def _valid_spot(spot: Decimal | None) -> Decimal | None:
    if spot is None or not spot.is_finite() or spot <= 0:
        return None
    return spot


def _available_funds_usd(
    funds: dict[str, Decimal], underlying: str, spot: Decimal | None
) -> Decimal | None:
    relevant_assets = {"USDC", "USD", underlying.upper()}
    if not relevant_assets.intersection(funds):
        return None
    stable_funds = funds.get("USDC", Decimal(0)) + funds.get("USD", Decimal(0))
    underlying_funds = funds.get(underlying.upper(), Decimal(0))
    if underlying_funds and spot is None:
        return None
    return stable_funds + underlying_funds * (spot or Decimal(0))


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
        for underlying in cfg.screener.underlyings:
            for name, ex in exchanges.items():
                try:
                    instruments = await ex.list_instruments(
                        underlying, cfg.screener.max_expiries_ahead
                    )
                    for inst in instruments:
                        exec_.register_instrument(name, inst)
                    log.info(
                        "executor bootstrap: %s/%s → %d instruments",
                        name,
                        underlying,
                        len(instruments),
                    )
                except Exception as e:
                    log.warning("executor bootstrap %s/%s failed: %s", name, underlying, e)
        await exec_.run()
    finally:
        await close_exchanges(exchanges)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
