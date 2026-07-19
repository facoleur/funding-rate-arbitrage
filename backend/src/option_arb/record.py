from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from option_arb.config import load_config
from option_arb.db.models import BookSnapshot
from option_arb.db.session import get_session, init_db
from option_arb.exchanges.base import Instrument
from option_arb.exchanges.registry import build_exchanges, close_exchanges

log = logging.getLogger(__name__)


async def record(
    exchange: str,
    duration_sec: int,
    underlying: str,
    max_expiries_ahead: int,
    to_db: bool,
    to_file: Path | None,
) -> int:
    cfg = load_config()
    exchanges = build_exchanges(cfg)
    ex = exchanges[exchange]
    try:
        instruments = await ex.list_instruments(underlying, max_expiries_ahead)
        log.info("recording %d instruments on %s for %ds", len(instruments), exchange, duration_sec)

        deadline = asyncio.get_event_loop().time() + duration_sec
        count = 0
        fh = to_file.open("a") if to_file else None
        try:
            while asyncio.get_event_loop().time() < deadline:
                for inst in instruments:
                    try:
                        book = await ex.get_orderbook_l2(inst)
                    except Exception as e:  # noqa: BLE001
                        log.warning("skip %s: %s", inst.instrument_name, e)
                        continue
                    record_dict = _book_to_dict(inst, book)
                    if fh:
                        fh.write(json.dumps(record_dict) + "\n")
                    if to_db:
                        await _persist_snapshot(inst, record_dict)
                    count += 1
                await asyncio.sleep(1.0)
        finally:
            if fh:
                fh.close()
        return count
    finally:
        await close_exchanges(exchanges)


def _book_to_dict(inst: Instrument, book) -> dict:
    return {
        "exchange": inst.exchange,
        "instrument": inst.normalized_name,
        "ts": book.ts.isoformat(),
        "bids": [[str(lvl.price), str(lvl.size)] for lvl in book.bids],
        "asks": [[str(lvl.price), str(lvl.size)] for lvl in book.asks],
    }


async def _persist_snapshot(inst: Instrument, d: dict) -> None:
    async with get_session() as sess:
        sess.add(BookSnapshot(
            exchange=inst.exchange,
            instrument=inst.normalized_name,
            ts=datetime.fromisoformat(d["ts"]),
            bids_json=json.dumps(d["bids"]),
            asks_json=json.dumps(d["asks"]),
        ))
        await sess.commit()


def _parse_duration(s: str) -> int:
    """`30s`, `10m`, `2h`, `1d` → seconds."""
    m = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = s[-1]
    if unit in m:
        return int(s[:-1]) * m[unit]
    return int(s)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Record order-book snapshots.")
    ap.add_argument("--exchange", required=True)
    ap.add_argument("--duration", default="1h")
    ap.add_argument("--underlying", default="BTC")
    ap.add_argument("--max-expiries-ahead", type=int, default=4)
    ap.add_argument("--to-db", action="store_true")
    ap.add_argument("--to-file", type=Path, default=None)
    args = ap.parse_args()

    async def _run() -> None:
        await init_db()
        n = await record(
            args.exchange,
            _parse_duration(args.duration),
            args.underlying,
            args.max_expiries_ahead,
            args.to_db,
            args.to_file,
        )
        log.info("recorded %d snapshots", n)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
