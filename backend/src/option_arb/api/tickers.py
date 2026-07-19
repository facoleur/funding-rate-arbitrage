from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlmodel import select

from option_arb.db.models import TickerState
from option_arb.db.session import get_session

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("")
async def list_tickers(
    underlying: str | None = None,
    exchange: str | None = None,
) -> list[dict]:
    stmt = select(TickerState).order_by(
        TickerState.underlying, TickerState.expiry, TickerState.strike, TickerState.exchange
    )
    if underlying:
        stmt = stmt.where(TickerState.underlying == underlying)
    if exchange:
        stmt = stmt.where(TickerState.exchange == exchange)
    async with get_session() as sess:
        rows = list((await sess.execute(stmt)).scalars())
    return _group_and_compute(rows)


def _group_and_compute(rows: list[TickerState]) -> list[dict]:
    # Group by instrument
    by_instrument: dict[str, list[TickerState]] = defaultdict(list)
    for r in rows:
        by_instrument[r.instrument].append(r)

    out: list[dict] = []
    for instrument, tickers in by_instrument.items():
        sample = tickers[0]

        now = datetime.now(timezone.utc)
        stale_threshold = timedelta(seconds=60)

        exchanges: dict[str, dict] = {}
        for t in tickers:
            ts = t.updated_at if t.updated_at.tzinfo else t.updated_at.replace(tzinfo=timezone.utc)
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

        # Compute cross-exchange spread (same logic as comparator.py)
        gross_spread_pct = None
        net_spread_pct = None
        buy_exchange = None
        sell_exchange = None

        valid = [
            t for t in tickers
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
        if best_gross is not None and best_buy_t and best_sell_t:
            fees = (best_buy_t.taker_fee_rate + best_sell_t.taker_fee_rate) * 100
            net = best_gross - fees
            gross_spread_pct = round(best_gross, 4)
            if net > 0:
                net_spread_pct = round(float(net), 4)
                buy_exchange = best_buy_t.exchange
                sell_exchange = best_sell_t.exchange
                ask_sz = best_buy_t.ask_size or 0.0
                bid_sz = best_sell_t.bid_size or 0.0
                tradeable_size = min(ask_sz, bid_sz)
                max_profit_usd = round(net / 100 * (best_buy_t.ask_price or 0.0) * tradeable_size, 2)

        latest_ts = max(t.updated_at for t in tickers)
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)

        out.append({
            "instrument": instrument,
            "underlying": sample.underlying,
            "expiry": (
                sample.expiry.isoformat()
                if sample.expiry.tzinfo
                else sample.expiry.replace(tzinfo=timezone.utc).isoformat()
            ),
            "strike": sample.strike,
            "option_type": sample.option_type,
            "exchanges": exchanges,
            "gross_spread_pct": gross_spread_pct,
            "net_spread_pct": net_spread_pct,
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "max_profit_usd": max_profit_usd,
            "updated_at": latest_ts.isoformat(),
        })

    return out
