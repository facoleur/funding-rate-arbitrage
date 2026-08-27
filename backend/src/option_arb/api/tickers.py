from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from sqlmodel import col, select

from option_arb.api.schemas import TickerResponse
from option_arb.db.models import TickerState
from option_arb.db.session import get_session
from option_arb.services.comparator import sell_margin_per_unit

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
    today = date.today()
    stmt = stmt.where(TickerState.expiry >= today)
    if underlying:
        stmt = stmt.where(TickerState.underlying == underlying)
    if exchange:
        stmt = stmt.where(TickerState.exchange == exchange)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return _group_and_compute(rows)


def _group_and_compute(rows: list[TickerState]) -> list[dict[str, Any]]:
    # Group by instrument
    by_instrument: dict[str, list[TickerState]] = defaultdict(list)
    for r in rows:
        by_instrument[r.instrument].append(r)

    now = datetime.now(UTC)
    stale_threshold = timedelta(seconds=60)

    out: list[dict[str, Any]] = []
    for instrument, tickers in by_instrument.items():
        sample = tickers[0]

        exchanges: dict[str, dict[str, Any]] = {}
        for t in tickers:
            ts = t.updated_at if t.updated_at.tzinfo else t.updated_at.replace(tzinfo=UTC)
            is_stale = (now - ts) > stale_threshold
            exchanges[t.exchange] = {
                "bid_price": t.bid_price,
                "bid_size": t.bid_size,
                "ask_price": t.ask_price,
                "ask_size": t.ask_size,
                "underlying_price": t.underlying_price,
                "taker_fee_rate": t.taker_fee_rate,
                "updated_at": ts.isoformat(),
                "is_stale": is_stale,
            }

        expiry_dt = sample.expiry if sample.expiry.tzinfo else sample.expiry.replace(tzinfo=UTC)
        days_to_expiry = (expiry_dt - now).total_seconds() / 86400.0

        # Compute cross-exchange spread (same logic as comparator.py)
        gross_spread_pct = None
        net_spread_pct = None
        buy_exchange = None
        sell_exchange = None

        valid = [
            t
            for t in tickers
            if t.bid_price and t.ask_price and t.bid_price > 0 and t.ask_price > 0
        ]
        # Try all cross-exchange pairs and pick the best gross spread
        best_gross: float | None = None
        best_buy_t = None
        best_sell_t = None
        for buy_t in valid:
            for sell_t in valid:
                if buy_t.exchange == sell_t.exchange:
                    continue
                g = (sell_t.bid_price - buy_t.ask_price) / buy_t.ask_price * 100  # type: ignore[operator]
                if best_gross is None or g > best_gross:
                    best_gross = g
                    best_buy_t = buy_t
                    best_sell_t = sell_t
        max_profit_usd = None
        sell_collateral_usd = None
        apr_pct = None
        max_notional_usd = None
        if best_gross is not None and best_buy_t and best_sell_t:
            gross_spread_pct = round(best_gross, 4)
            buy_ask = best_buy_t.ask_price or 0.0
            sell_bid = best_sell_t.bid_price or 0.0
            fees_usd = best_buy_t.taker_fee_rate * buy_ask + best_sell_t.taker_fee_rate * sell_bid
            net_profit_per_unit = sell_bid - buy_ask - fees_usd

            if net_profit_per_unit > 0:
                spot = best_sell_t.underlying_price or best_buy_t.underlying_price
                if spot:
                    margin = float(
                        sell_margin_per_unit(
                            Decimal(str(spot)),
                            Decimal(str(best_sell_t.strike)),
                            best_sell_t.option_type,
                        )
                    )
                    net_spread_pct = round(net_profit_per_unit / margin * 100, 4)
                    days_to_exp = max((expiry_dt - now).total_seconds() / 86400.0, 1e-6)
                    apr_pct = round(net_spread_pct / days_to_exp * 365, 2)
                    buy_exchange = best_buy_t.exchange
                    sell_exchange = best_sell_t.exchange
                    ask_sz = best_buy_t.ask_size or 0.0
                    bid_sz = best_sell_t.bid_size or 0.0
                    tradeable_size = min(ask_sz, bid_sz)
                    max_notional_usd = round(tradeable_size * buy_ask, 2)
                    max_profit_usd = round(net_profit_per_unit * tradeable_size, 2)
                    sell_collateral_usd = round(margin * tradeable_size, 2)

        latest_ts = max(t.updated_at for t in tickers)
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=UTC)

        out.append(
            {
                "instrument": instrument,
                "underlying": sample.underlying,
                "expiry": expiry_dt.isoformat(),
                "days_to_expiry": round(days_to_expiry, 2),
                "strike": sample.strike,
                "option_type": sample.option_type,
                "exchanges": exchanges,
                "gross_spread_pct": gross_spread_pct,
                "net_spread_pct": net_spread_pct,
                "apr_pct": apr_pct,
                "buy_exchange": buy_exchange,
                "sell_exchange": sell_exchange,
                "max_notional_usd": max_notional_usd,
                "max_profit_usd": max_profit_usd,
                "sell_collateral_usd": sell_collateral_usd,
                "updated_at": latest_ts.isoformat(),
            }
        )

    return out
