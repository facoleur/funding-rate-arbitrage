from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import sqlalchemy as sa
from sqlmodel import select

from option_arb.config import AppConfig, load_config
from option_arb.db.event_relay import PostgresEventRelay
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
    walk_book,
)
from option_arb.services.limits import kill_switch_reason

log = logging.getLogger(__name__)

_BINARY_SEARCH_STEPS = 20


@dataclass(frozen=True)
class WalkedTrade:
    """A size that clears every gate, priced at the worst IOC limits."""

    walked_ask: Decimal
    walked_bid: Decimal
    buy_limit: Decimal
    sell_limit: Decimal
    economics: OptionEconomics


@dataclass(frozen=True)
class _Venues:
    """Both sides of one opportunity, resolved to live adapters + metadata."""

    buy_ex: AbstractExchange
    sell_ex: AbstractExchange
    buy_inst: Instrument
    sell_inst: Instrument


@dataclass(frozen=True)
class _FreshMarket:
    """Books refetched over REST right before placing, plus usable funds."""

    buy_book: Book
    sell_book: Book
    buy_avail_usd: Decimal | None
    sell_avail_usd: Decimal | None


@dataclass(frozen=True)
class _Gates:
    """Config thresholds as Decimals, resolved once per opportunity."""

    min_apr: Decimal
    min_buy_premium: Decimal
    min_net_profit: Decimal
    min_net_return: Decimal
    max_contracts: Decimal | None
    slippage: Decimal
    cap: Decimal


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
        killed_reason = await kill_switch_reason(self.config.limits)
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

        blocked = self._static_checks(opp)
        if blocked:
            await self._reject(opp, blocked)
            return

        venues = self._resolve_venues(opp)
        if isinstance(venues, str):
            await self._reject(opp, venues)
            return

        market = await self._fetch_fresh_market(venues)
        if isinstance(market, str):
            await self._reject(opp, market)
            return

        walked = self._walk_and_verify(
            opp,
            market.buy_book,
            market.sell_book,
            venues.buy_inst,
            venues.sell_inst,
            market.buy_avail_usd,
            market.sell_avail_usd,
        )
        if isinstance(walked, str):
            await self._reject(opp, walked)
            return

        trade = await self._open_trade(opp, walked)
        await bus.publish(
            Event(
                type="trade_opened",
                level="info",
                message=(
                    f"trade {trade.id} placing {walked.economics.tradeable_size} {opp.instrument}"
                ),
                payload={"trade_id": trade.id, "opportunity_id": opp.id},
            )
        )
        buy_res, sell_res = await self._place_legs(trade, opp, venues, walked)
        await self._dispatch_outcome(trade, opp, venues, walked, buy_res, sell_res)

    # -----------------------------------------------------------------

    def _static_checks(self, opp: Opportunity) -> str | None:
        """Cheap gates that need no network. Economic thresholds are NOT
        checked here — they're rechecked on fresh books in _walk_and_verify."""
        exp = opp.expiry if opp.expiry.tzinfo else opp.expiry.replace(tzinfo=UTC)
        days_remaining = days_to_expiry(exp, datetime.now(UTC))
        if days_remaining <= 0:
            return "expiry_invalid"
        if days_remaining > Decimal(self.config.thresholds.max_days_to_expiry):
            return f"expiry_too_far({days_remaining:.0f}d)"
        for ex_name in (opp.buy_from, opp.sell_to):
            ex_cfg = self.config.exchanges.get(ex_name)
            if ex_cfg and not ex_cfg.trade_enabled:
                return f"trading_disabled({ex_name})"
        return None

    def _resolve_venues(self, opp: Opportunity) -> _Venues | str:
        buy_ex = self.exchanges.get(opp.buy_from)
        sell_ex = self.exchanges.get(opp.sell_to)
        if not buy_ex or not sell_ex:
            return f"unknown_exchange({opp.buy_from},{opp.sell_to})"
        buy_inst = self._instruments_by_name.get(opp.buy_from, {}).get(opp.instrument)
        sell_inst = self._instruments_by_name.get(opp.sell_to, {}).get(opp.instrument)
        if not buy_inst or not sell_inst:
            return "instrument_metadata_missing"
        return _Venues(buy_ex, sell_ex, buy_inst, sell_inst)

    async def _fetch_fresh_market(self, venues: _Venues) -> _FreshMarket | str:
        """Refetch both books (and balances) in parallel under one timeout.
        A stale book is a rejection: the screener's snapshot is not enough."""
        timeout = self.config.executor.fresh_fetch_timeout_ms / 1000.0
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    venues.buy_ex.get_orderbook_l2(venues.buy_inst),
                    venues.sell_ex.get_orderbook_l2(venues.sell_inst),
                    venues.buy_ex.get_available_funds(),
                    venues.sell_ex.get_available_funds(),
                    return_exceptions=True,
                ),
                timeout=timeout,
            )
        except Exception as e:
            return f"stale_book:{type(e).__name__}"

        buy_book, sell_book = results[0], results[1]
        for book in (buy_book, sell_book):
            if isinstance(book, BaseException):
                return f"stale_book:{type(book).__name__}"
        assert isinstance(buy_book, Book) and isinstance(sell_book, Book)

        # Balances are best-effort: a failure only means we can't tighten the cap.
        buy_funds = results[2] if not isinstance(results[2], BaseException) else {}
        sell_funds = results[3] if not isinstance(results[3], BaseException) else {}
        spot = _valid_spot(buy_book.underlying_price) or _valid_spot(sell_book.underlying_price)
        return _FreshMarket(
            buy_book=buy_book,
            sell_book=sell_book,
            buy_avail_usd=_available_funds_usd(buy_funds, venues.buy_inst.underlying, spot),
            sell_avail_usd=_available_funds_usd(sell_funds, venues.sell_inst.underlying, spot),
        )

    async def _open_trade(self, opp: Opportunity, walked: WalkedTrade) -> Trade:
        """Record what the fresh books actually justified, then open the trade
        in PLACING — both in one transaction, before any order goes out."""
        economics = walked.economics
        async with get_session() as sess:
            row = await sess.get(Opportunity, opp.id)
            assert row is not None
            row.walked_ask = float(walked.walked_ask)
            row.walked_bid = float(walked.walked_bid)
            row.verified_buy_limit = float(walked.buy_limit)
            row.verified_sell_limit = float(walked.sell_limit)
            row.verified_tradeable_size = float(economics.tradeable_size)
            row.verified_buy_premium_usd = float(economics.buy_premium_usd)
            row.verified_sell_premium_usd = float(economics.sell_premium_usd)
            row.verified_estimated_short_margin_usd = float(economics.estimated_short_margin_usd)
            row.verified_capital_required_usd = float(economics.capital_required_usd)
            row.verified_gross_profit_usd = float(economics.gross_profit_usd)
            row.verified_fees_usd = float(economics.fees_usd)
            row.verified_net_profit_usd = float(economics.net_profit_usd)
            row.verified_net_return_pct = float(economics.net_return_pct)
            row.verified_apr_pct = float(economics.apr_pct)
            row.status = OpportunityStatus.APPROVED
            trade = Trade(
                opportunity_id=opp.id,
                opened_at=datetime.now(UTC),
                mode=Mode(self.config.executor.mode),
                status=TradeStatus.PLACING,
                buy_exchange=opp.buy_from,
                sell_exchange=opp.sell_to,
                requested_size=float(economics.tradeable_size),
            )
            sess.add(trade)
            await sess.commit()
            await sess.refresh(trade)
            assert trade.id is not None
            return trade

    async def _place_legs(
        self, trade: Trade, opp: Opportunity, venues: _Venues, walked: WalkedTrade
    ) -> tuple[OrderResult, OrderResult]:
        """Both IOC limits go out together — sequential placement would let
        one side move while the other is in flight."""
        size = walked.economics.tradeable_size
        buy_req = OrderRequest(
            exchange=opp.buy_from,
            instrument=venues.buy_inst.instrument_name,
            side="BUY",
            size=size,
            limit_price=walked.buy_limit,
            time_in_force="IOC",
        )
        sell_req = OrderRequest(
            exchange=opp.sell_to,
            instrument=venues.sell_inst.instrument_name,
            side="SELL",
            size=size,
            limit_price=walked.sell_limit,
            time_in_force="IOC",
        )
        buy_order = await self._create_order(trade.id, buy_req, OrderKind.IOC_LIMIT)
        sell_order = await self._create_order(trade.id, sell_req, OrderKind.IOC_LIMIT)

        buy_res, sell_res = await asyncio.gather(
            venues.buy_ex.place_order(buy_req),
            venues.sell_ex.place_order(sell_req),
            return_exceptions=True,
        )
        if isinstance(buy_res, BaseException):
            buy_res = OrderResult(status="REJECTED", reason=str(buy_res))
        if isinstance(sell_res, BaseException):
            sell_res = OrderResult(status="REJECTED", reason=str(sell_res))

        await self._update_order(buy_order.id, buy_res)
        await self._update_order(sell_order.id, sell_res)
        return buy_res, sell_res

    async def _dispatch_outcome(
        self,
        trade: Trade,
        opp: Opportunity,
        venues: _Venues,
        walked: WalkedTrade,
        buy_res: OrderResult,
        sell_res: OrderResult,
    ) -> None:
        buy_ok = buy_res.status in ("FILLED", "PARTIAL") and buy_res.filled_size > 0
        sell_ok = sell_res.status in ("FILLED", "PARTIAL") and sell_res.filled_size > 0
        assert trade.id is not None

        if buy_ok and sell_ok:
            await self._finalize_filled(
                trade.id,
                opp,
                buy_res,
                sell_res,
                venues.buy_inst,
                venues.sell_inst,
                walked.walked_ask,
                walked.walked_bid,
            )
        elif buy_ok ^ sell_ok:  # exactly one leg filled — we're naked, hedge out
            await self._market_out(
                trade, opp, buy_ok, buy_res, sell_res, venues.buy_inst, venues.sell_inst
            )
        else:
            await self._finalize_failed(trade.id, opp, buy_res, sell_res)

    # -----------------------------------------------------------------

    def _gates(self, buy_avail_usd: Decimal | None) -> _Gates | str:
        """Thresholds for this attempt. Available funds tighten the premium cap."""
        cfg = self.config
        cap = Decimal(str(cfg.limits.max_buy_premium_per_trade_usd))
        if buy_avail_usd is not None:
            cap = min(cap, buy_avail_usd)
            if cap <= 0:
                return f"insufficient_buy_funds({buy_avail_usd:.0f})"
        return _Gates(
            min_apr=Decimal(str(cfg.thresholds.min_apr_pct)),
            min_buy_premium=Decimal(str(cfg.thresholds.min_buy_premium_usd)),
            min_net_profit=Decimal(str(cfg.thresholds.min_net_profit_usd)),
            min_net_return=Decimal(str(cfg.thresholds.min_net_return_pct)),
            max_contracts=(
                Decimal(str(cfg.limits.max_contracts_per_trade))
                if cfg.limits.max_contracts_per_trade
                else None
            ),
            slippage=Decimal(str(cfg.executor.ioc_slippage_limit_pct)) / Decimal(100),
            cap=cap,
        )

    def _walk_and_verify(
        self,
        opp: Opportunity,
        buy_book: Book,
        sell_book: Book,
        buy_inst: Instrument,
        sell_inst: Instrument,
        buy_avail_usd: Decimal | None = None,
        sell_avail_usd: Decimal | None = None,
    ) -> WalkedTrade | str:
        """Largest size that still clears every gate at the worst IOC price,
        or a rejection reason. Runs on freshly-fetched books, so it — not the
        screener's estimate — is what authorises the trade."""
        gates = self._gates(buy_avail_usd)
        if isinstance(gates, str):
            return gates

        spot = _valid_spot(buy_book.underlying_price) or _valid_spot(sell_book.underlying_price)
        if spot is None:
            return "margin_unavailable"
        expiry = opp.expiry if opp.expiry.tzinfo else opp.expiry.replace(tzinfo=UTC)
        dte = days_to_expiry(expiry, datetime.now(UTC))
        if dte <= 0:
            return "expiry_invalid"

        largest = _max_size_within_cap(
            buy_book.asks,
            sell_book.bids,
            gates.cap,
            gates.max_contracts,
            buy_price_multiplier=Decimal(1) + gates.slippage,
        )
        if largest <= 0:
            return "empty_book"

        def evaluate(size: Decimal) -> WalkedTrade | None:
            return self._price_at_size(
                size, buy_book, sell_book, buy_inst, sell_inst, gates, spot, dte
            )

        best = _largest_passing_size(largest, evaluate, lambda t: _clears_gates(t, gates))
        if best is None:
            return "apr_dropped"
        return _final_checks(best, gates, buy_inst, sell_inst, sell_avail_usd)

    @staticmethod
    def _price_at_size(
        size: Decimal,
        buy_book: Book,
        sell_book: Book,
        buy_inst: Instrument,
        sell_inst: Instrument,
        gates: _Gates,
        spot: Decimal,
        dte: Decimal,
    ) -> WalkedTrade | None:
        """Walk both books for `size` and price the pair at the worst IOC
        limits. None when the books can't fill it or economics don't compute."""
        walked_ask, filled_ask = walk_book(size, buy_book.asks)
        walked_bid, filled_bid = walk_book(size, sell_book.bids)
        if filled_ask < size or filled_bid < size:
            return None
        buy_limit = walked_ask * (Decimal(1) + gates.slippage)
        sell_limit = walked_bid * (Decimal(1) - gates.slippage)
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
        return WalkedTrade(walked_ask, walked_bid, buy_limit, sell_limit, economics)

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


def _clears_gates(trade: WalkedTrade, gates: _Gates) -> bool:
    e = trade.economics
    return (
        e.buy_premium_usd <= gates.cap
        and e.net_profit_usd > 0
        and e.net_return_pct >= gates.min_net_return
        and e.apr_pct >= gates.min_apr
    )


def _largest_passing_size(
    largest: Decimal,
    evaluate: Callable[[Decimal], WalkedTrade | None],
    passes: Callable[[WalkedTrade], bool],
) -> WalkedTrade | None:
    """Take the biggest size the book allows; if it fails the gates, binary
    search downward for the largest size that clears them."""
    candidate = evaluate(largest)
    if candidate is not None and passes(candidate):
        return candidate

    best: WalkedTrade | None = None
    low, high = Decimal(0), largest
    for _ in range(_BINARY_SEARCH_STEPS):
        mid = (low + high) / Decimal(2)
        if mid <= 0:
            break
        result = evaluate(mid)
        if result is not None and passes(result):
            best = result
            low = mid
        else:
            high = mid
    return best


def _final_checks(
    trade: WalkedTrade,
    gates: _Gates,
    buy_inst: Instrument,
    sell_inst: Instrument,
    sell_avail_usd: Decimal | None,
) -> WalkedTrade | str:
    """Absolute floors, checked once on the winning size."""
    e = trade.economics
    if e.buy_premium_usd < gates.min_buy_premium:
        return "size_too_small"
    if e.net_profit_usd < gates.min_net_profit:
        return "profit_too_small"
    min_size = max(buy_inst.min_trade_amount, sell_inst.min_trade_amount)
    if min_size > 0 and e.tradeable_size < min_size:
        return f"size_below_minimum({float(e.tradeable_size):.4f}<{float(min_size):.4f})"
    if sell_avail_usd is not None and sell_avail_usd < e.estimated_short_margin_usd:
        return f"insufficient_sell_funds({sell_avail_usd:.0f}<{e.estimated_short_margin_usd:.0f})"
    return trade


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
    # Without the relay every executor event (trade_stuck included) would die
    # in this process — the Alerter and /api/stream live in other containers.
    relay = PostgresEventRelay()
    await relay.start()
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
        await relay.stop()
        await close_exchanges(exchanges)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
