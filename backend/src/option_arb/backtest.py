from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlmodel import select

from option_arb.config import load_config
from option_arb.db.models import Mode, Trade, TradeStatus
from option_arb.db.session import get_session, init_db
from option_arb.exchanges.base import Book, BookLevel, Instrument, TickerUpdate
from option_arb.exchanges.mock import MockExchange
from option_arb.exchanges.slippage import SlippageModel
from option_arb.market.book_cache import BookCache
from option_arb.services.executor import Executor
from option_arb.services.screener import Screener

log = logging.getLogger(__name__)


@dataclass
class Report:
    opportunities: int
    trades_executed: int
    trades_filled: int
    trades_hedged: int
    trades_failed: int
    total_pnl_usd: float
    avg_pnl_usd: float

    def to_dict(self) -> dict:
        return self.__dict__


def _load_snapshots(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _snap_to_book(snap: dict) -> Book:
    return Book(
        exchange=snap["exchange"],
        instrument=snap["instrument"],
        ts=datetime.fromisoformat(snap["ts"]),
        bids=[BookLevel(price=Decimal(p), size=Decimal(s)) for p, s in snap["bids"]],
        asks=[BookLevel(price=Decimal(p), size=Decimal(s)) for p, s in snap["asks"]],
    )


def _instrument_from_snap(snap: dict) -> Instrument:
    """Best-effort synthesize an Instrument from a snapshot record.

    Assumes normalized name `{UNDERLYING}-{YYYYMMDD}-{STRIKE}-{C|P}`."""
    name = snap["instrument"]
    parts = name.split("-")
    underlying, date_str, strike, side = parts[0], parts[1], parts[2], parts[3]
    return Instrument(
        exchange=snap["exchange"],
        instrument_name=name,
        normalized_name=name,
        underlying=underlying,
        expiry=datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC),
        strike=Decimal(strike),
        option_type=side,
        maker_fee_rate=Decimal("0.0001"),
        taker_fee_rate=Decimal("0.0003"),
    )


async def backtest(file: Path) -> Report:
    cfg = load_config()
    cfg.executor.mode = "backtest"

    # Build one MockExchange per exchange present in the file
    snaps = list(_load_snapshots(file))
    if not snaps:
        return Report(0, 0, 0, 0, 0, 0.0, 0.0)

    exchanges_names = sorted({s["exchange"] for s in snaps})
    slippage = SlippageModel(
        noise_stdev_bps=5, reject_prob=0.02, latency_min_sec=0, latency_max_sec=0.01
    )
    exchanges: dict[str, MockExchange] = {
        name: MockExchange(name, slippage=slippage) for name in exchanges_names
    }
    all_instruments: dict[str, dict[str, Instrument]] = {name: {} for name in exchanges_names}

    cache = BookCache()

    # register instruments so cache/executor recognise them
    for snap in snaps:
        inst = _instrument_from_snap(snap)
        all_instruments[snap["exchange"]][inst.normalized_name] = inst
        exchanges[snap["exchange"]].set_instruments([inst])
        cache.register_instruments([inst])

    screener = Screener(cache, cfg)
    executor = Executor(cfg, exchanges, all_instruments)  # type: ignore[arg-type]

    # Replay: for each snapshot, update the mock book + push a ticker into cache,
    # then tick screener + executor once.
    for snap in snaps:
        book = _snap_to_book(snap)
        exchanges[snap["exchange"]].set_book(snap["instrument"], book)
        top_bid = book.top_bid
        top_ask = book.top_ask
        cache.update(
            TickerUpdate(
                exchange=snap["exchange"],
                instrument=snap["instrument"],
                ts=book.ts,
                bid_price=top_bid.price if top_bid else None,
                bid_size=top_bid.size if top_bid else None,
                ask_price=top_ask.price if top_ask else None,
                ask_size=top_ask.size if top_ask else None,
            )
        )
        await screener._tick()
        await executor._tick()

    # Build the report from DB (only backtest-tagged rows)
    async with get_session() as sess:
        trades = list(
            (await sess.execute(select(Trade).where(Trade.mode == Mode.BACKTEST))).scalars()
        )

    filled = [t for t in trades if t.status == TradeStatus.FILLED]
    hedged = [t for t in trades if t.status == TradeStatus.HEDGED]
    failed = [t for t in trades if t.status in (TradeStatus.FAILED, TradeStatus.STUCK)]
    pnls = [t.net_pnl_usd or 0.0 for t in trades if t.net_pnl_usd is not None]
    total_pnl = sum(pnls)
    return Report(
        opportunities=len(snaps),
        trades_executed=len(trades),
        trades_filled=len(filled),
        trades_hedged=len(hedged),
        trades_failed=len(failed),
        total_pnl_usd=total_pnl,
        avg_pnl_usd=(total_pnl / len(pnls)) if pnls else 0.0,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(
        description="Replay recorded books through screener + mock executor."
    )
    ap.add_argument("--file", type=Path, required=True)
    args = ap.parse_args()

    async def _run() -> None:
        await init_db()
        report = await backtest(args.file)
        print(json.dumps(report.to_dict(), indent=2))

    asyncio.run(_run())


if __name__ == "__main__":
    main()
