from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from option_arb.config import load_config
from option_arb.db.session import init_db
from option_arb.exchanges.base import Instrument, TickerUpdate
from option_arb.exchanges.registry import build_exchanges, close_exchanges
from option_arb.market.book_cache import BookCache
from option_arb.market.ws_manager import WsManager
from option_arb.services.alerter import Alerter
from option_arb.services.rebalancer import Rebalancer
from option_arb.services.screener import Screener

log = logging.getLogger(__name__)


async def _amain() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    log.info("worker booting…")

    await init_db()
    cfg = load_config()
    exchanges = build_exchanges(cfg)

    # 1. bootstrap instrument metadata for every configured underlying/exchange
    subscriptions: dict[str, list[Instrument]] = {}
    cache = BookCache()
    for underlying in cfg.screener.underlyings:
        for name, ex in exchanges.items():
            try:
                instruments = await ex.list_instruments(underlying, cfg.screener.max_expiries_ahead)
            except Exception as e:
                log.warning("bootstrap %s/%s failed: %s", name, underlying, e)
                continue
            cache.register_instruments(instruments)
            subscriptions.setdefault(name, []).extend(instruments)
            log.info("bootstrap: %s %s → %d instruments", name, underlying, len(instruments))

    # 2. WS manager (streams tickers → cache)
    ws = WsManager(exchanges, on_ticker=lambda upd: _push(cache, upd))
    await ws.start(subscriptions)

    # 3. screener + alerter + rebalancer (concurrent)
    screener = Screener(cache, cfg)
    alerter = Alerter(cfg.alerts)
    rebalancer = Rebalancer(cfg, exchanges)

    stop = asyncio.Event()

    def _shutdown(*_: object) -> None:
        log.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _shutdown)

    tasks = [
        asyncio.create_task(screener.run(), name="screener"),
        asyncio.create_task(alerter.run(), name="alerter"),
        asyncio.create_task(rebalancer.run(), name="rebalancer"),
    ]

    await stop.wait()
    log.info("stopping tasks…")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await ws.stop()
    await close_exchanges(exchanges)
    log.info("worker stopped")


async def _push(cache: BookCache, upd: TickerUpdate) -> None:
    cache.update(upd)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
