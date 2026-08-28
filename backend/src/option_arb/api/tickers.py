from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast

from fastapi import APIRouter
from sqlmodel import col, select

from option_arb.api.schemas import TickerResponse
from option_arb.config import Thresholds, load_config
from option_arb.db.models import TickerState
from option_arb.db.session import get_session
from option_arb.economics import calculate_option_economics, days_to_expiry, meets_thresholds

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("", response_model=list[TickerResponse])
async def list_tickers(
    underlying: str | None = None,
    exchange: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(TickerState).order_by(
        col(TickerState.underlying),
        col(TickerState.expiry),
        col(TickerState.strike),
        col(TickerState.exchange),
    )
    stmt = stmt.where(TickerState.expiry >= date.today())
    if underlying:
        stmt = stmt.where(TickerState.underlying == underlying)
    if exchange:
        stmt = stmt.where(TickerState.exchange == exchange)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return _group_and_compute(rows, load_config().thresholds)


def _group_and_compute(rows: list[TickerState], thresholds: Thresholds) -> list[dict[str, Any]]:
    by_instrument: dict[str, list[TickerState]] = defaultdict(list)
    for row in rows:
        by_instrument[row.instrument].append(row)

    now = datetime.now(UTC)
    stale_threshold = timedelta(seconds=60)
    output: list[dict[str, Any]] = []
    for instrument, tickers in by_instrument.items():
        sample = tickers[0]
        exchanges: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            timestamp = (
                ticker.updated_at
                if ticker.updated_at.tzinfo
                else ticker.updated_at.replace(tzinfo=UTC)
            )
            exchanges[ticker.exchange] = {
                "bid_price": ticker.bid_price,
                "bid_size": ticker.bid_size,
                "ask_price": ticker.ask_price,
                "ask_size": ticker.ask_size,
                "underlying_price": ticker.underlying_price,
                "taker_fee_rate": ticker.taker_fee_rate,
                "updated_at": timestamp.isoformat(),
                "is_stale": now - timestamp > stale_threshold,
            }

        expiry = sample.expiry if sample.expiry.tzinfo else sample.expiry.replace(tzinfo=UTC)
        dte = days_to_expiry(expiry, now)
        valid = [
            ticker
            for ticker in tickers
            if ticker.bid_price is not None
            and ticker.ask_price is not None
            and ticker.bid_size is not None
            and ticker.ask_size is not None
            and ticker.bid_price > 0
            and ticker.ask_price > 0
            and ticker.bid_size > 0
            and ticker.ask_size > 0
        ]

        best_pair: tuple[TickerState, TickerState] | None = None
        best_price_spread: Decimal | None = None
        for buy_ticker in valid:
            for sell_ticker in valid:
                if buy_ticker.exchange == sell_ticker.exchange:
                    continue
                buy_price = Decimal(str(buy_ticker.ask_price))
                sell_price = Decimal(str(sell_ticker.bid_price))
                price_spread = (sell_price - buy_price) / buy_price * Decimal(100)
                if best_price_spread is None or price_spread > best_price_spread:
                    best_price_spread = price_spread
                    best_pair = buy_ticker, sell_ticker

        metrics: dict[str, float | None] = {
            "price_spread_pct": float(best_price_spread) if best_price_spread is not None else None,
            "tradeable_size": None,
            "buy_premium_usd": None,
            "sell_premium_usd": None,
            "estimated_short_margin_usd": None,
            "capital_required_usd": None,
            "gross_profit_usd": None,
            "fees_usd": None,
            "net_profit_usd": None,
            "net_return_pct": None,
            "apr_pct": None,
        }
        buy_exchange = None
        sell_exchange = None
        eligible = False
        if best_pair is not None:
            buy_ticker, sell_ticker = best_pair
            spot_value = sell_ticker.underlying_price or buy_ticker.underlying_price
            economics = calculate_option_economics(
                buy_price=Decimal(str(buy_ticker.ask_price)),
                sell_price=Decimal(str(sell_ticker.bid_price)),
                quantity=min(
                    Decimal(str(buy_ticker.ask_size)),
                    Decimal(str(sell_ticker.bid_size)),
                ),
                buy_taker_fee_rate=Decimal(str(buy_ticker.taker_fee_rate)),
                sell_taker_fee_rate=Decimal(str(sell_ticker.taker_fee_rate)),
                spot=Decimal(str(spot_value)) if spot_value is not None else None,
                strike=Decimal(str(sell_ticker.strike)),
                option_type=cast(Literal["C", "P"], sell_ticker.option_type),
                days_to_expiry=dte,
            )
            if economics is not None:
                metrics = {field: float(getattr(economics, field)) for field in metrics}
                eligible = meets_thresholds(
                    thresholds,
                    apr_pct=economics.apr_pct,
                    buy_premium_usd=economics.buy_premium_usd,
                    days_to_expiry=dte,
                    net_return_pct=economics.net_return_pct,
                    net_profit_usd=economics.net_profit_usd,
                )
                if economics.net_profit_usd > 0:
                    buy_exchange = buy_ticker.exchange
                    sell_exchange = sell_ticker.exchange

        # A row's age is that of its STALEST leg, not its freshest: the metrics
        # below compare two venues, so the older quote is what bounds how much
        # the whole line can be trusted. Taking max() here read as "2s" while
        # one side was minutes old.
        oldest_timestamp = min(ticker.updated_at for ticker in tickers)
        if oldest_timestamp.tzinfo is None:
            oldest_timestamp = oldest_timestamp.replace(tzinfo=UTC)
        output.append(
            {
                "instrument": instrument,
                "underlying": sample.underlying,
                "expiry": expiry.isoformat(),
                "days_to_expiry": float(dte),
                "strike": sample.strike,
                "option_type": sample.option_type,
                "exchanges": exchanges,
                **metrics,
                "buy_exchange": buy_exchange,
                "sell_exchange": sell_exchange,
                "eligible": eligible,
                "updated_at": oldest_timestamp.isoformat(),
            }
        )
    return output
