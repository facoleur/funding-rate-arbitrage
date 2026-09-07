from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from option_arb.config import AppConfig, load_config, settings
from option_arb.db.event_relay import PostgresEventRelay
from option_arb.db.session import get_session, init_db
from option_arb.exchanges.base import AbstractExchange, Instrument, TickerUpdate
from option_arb.exchanges.deribit import DeribitExchange
from option_arb.exchanges.registry import build_exchanges, close_exchanges
from option_arb.market.book_cache import BookCache
from option_arb.market.ws_manager import WsManager
from option_arb.services.alerter import Alerter
from option_arb.services.perp_hedger import PerpHedger
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
    relay = PostgresEventRelay()
    await relay.start()
    exchanges = build_exchanges(cfg)

    # 1. bootstrap instrument metadata for every configured underlying/exchange
    subscriptions: dict[str, list[Instrument]] = {}
    cache = BookCache(ttl_ms=cfg.screener.book_cache_ttl_ms)
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

    # track known instruments per exchange for the refresh diff
    known: dict[str, set[str]] = {
        name: {i.normalized_name for i in insts} for name, insts in subscriptions.items()
    }

    # 3. screener + alerter + rebalancer (concurrent)
    screener = Screener(cache, cfg)
    alerter = Alerter(cfg.alerts)
    rebalancer = Rebalancer(cfg, exchanges)

    # 3b. structured screener (box spreads) — optional, shares the cache
    structured = None
    if cfg.structured.enabled:
        from option_arb.structured.screener import StructuredScreener

        structured = StructuredScreener(cache, cfg)
        log.info("structured screener: enabled")

    # 4. perp hedger (optional — Deribit inverse only)
    perp_hedger: PerpHedger | None = None
    if cfg.perp_hedge.enabled and "deribit" in exchanges:
        raw = exchanges["deribit"]
        upstream = getattr(raw, "upstream", raw)
        if isinstance(upstream, DeribitExchange) and not upstream._linear:
            dry_run = cfg.executor.mode != "live"
            perp_hedger = PerpHedger(upstream, cfg.perp_hedge, dry_run=dry_run)
            log.info("perp_hedger: enabled (dry_run=%s)", dry_run)

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
        asyncio.create_task(
            _metadata_refresh_loop(exchanges, cfg, cache, ws, known, stop),
            name="metadata_refresh",
        ),
        asyncio.create_task(_retention_loop(cfg, stop), name="retention"),
        *(
            [asyncio.create_task(perp_hedger.run(), name="perp_hedger")]
            if perp_hedger is not None
            else []
        ),
        *(
            [asyncio.create_task(structured.run(), name="structured")]
            if structured is not None
            else []
        ),
    ]
    await stop.wait()
    log.info("stopping tasks…")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await ws.stop()
    await close_exchanges(exchanges)
    await relay.stop()
    log.info("worker stopped")


async def _push(cache: BookCache, upd: TickerUpdate) -> None:
    cache.update(upd)


async def _retention_loop(cfg: AppConfig, stop: asyncio.Event) -> None:
    """Prune old rows once a day to keep Postgres disk bounded."""
    opp_days = cfg.screener.opportunity_retention_days
    opp_snap_days = cfg.screener.snapshot_retention_days
    struct_on = cfg.structured.enabled
    struct_days = cfg.structured.retention_days if struct_on else 0
    struct_snap_days = cfg.structured.snapshot_retention_days if struct_on else 0
    if (opp_days <= 0 and opp_snap_days <= 0 and struct_days <= 0 and struct_snap_days <= 0) or (
        "postgresql" not in settings.database_url
    ):
        return
    from sqlalchemy import text

    # (label, SQL, params) — each runs in its own transaction, best-effort.
    stmts: list[tuple[str, str, dict[str, int]]] = []
    if opp_snap_days > 0:
        stmts.append(
            (
                "opportunity_snapshots",
                "DELETE FROM opportunity_snapshots WHERE ts < now() - make_interval(days => :d)",
                {"d": opp_snap_days},
            )
        )
    if opp_days > 0:
        # snapshots of pruned parents cascade via the FK
        stmts.append(
            (
                "opportunities",
                "DELETE FROM opportunities WHERE detected_at < now() - make_interval(days => :d)",
                {"d": opp_days},
            )
        )
    if struct_snap_days > 0:
        stmts.append(
            (
                "structured_opportunity_snapshots",
                "DELETE FROM structured_opportunity_snapshots "
                "WHERE ts < now() - make_interval(days => :d)",
                {"d": struct_snap_days},
            )
        )
    if struct_days > 0:
        # only finished opportunities; snapshots cascade via the FK
        stmts.append(
            (
                "structured_opportunities",
                "DELETE FROM structured_opportunities "
                "WHERE live_status IN ('STALE', 'EXPIRED') "
                "AND detected_at < now() - make_interval(days => :d)",
                {"d": struct_days},
            )
        )
    log.info("retention: pruning %s, daily", ", ".join(s[0] for s in stmts))
    while not stop.is_set():
        for label, sql, params in stmts:
            try:
                async with get_session() as sess:
                    res = await sess.execute(text(sql), params)
                    await sess.commit()
                log.info("retention: pruned %s %s rows", getattr(res, "rowcount", "?"), label)
            except Exception as e:
                log.warning("retention prune of %s failed: %s", label, e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=86400)
            break
        except TimeoutError:
            pass


async def _metadata_refresh_loop(
    exchanges: dict[str, AbstractExchange],
    cfg: AppConfig,
    cache: BookCache,
    ws: WsManager,
    known: dict[str, set[str]],
    stop: asyncio.Event,
) -> None:
    interval = cfg.screener.metadata_refresh_hours * 3600
    log.info("metadata_refresh: will re-scan every %.0fh", cfg.screener.metadata_refresh_hours)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except TimeoutError:
            pass
        for underlying in cfg.screener.underlyings:
            for name, ex in exchanges.items():
                try:
                    instruments = await ex.list_instruments(
                        underlying, cfg.screener.max_expiries_ahead
                    )
                except Exception as e:
                    log.warning("metadata_refresh %s/%s failed: %s", name, underlying, e)
                    continue
                ex_known = known.setdefault(name, set())
                new_insts = [i for i in instruments if i.normalized_name not in ex_known]
                if not new_insts:
                    continue
                cache.register_instruments(new_insts)
                for inst in new_insts:
                    for ch in ex.ws_channels([inst]):
                        await ws.add_subscription(name, ch)
                ex_known.update(i.normalized_name for i in new_insts)
                log.info(
                    "metadata_refresh: %s %s → %d new instruments",
                    name,
                    underlying,
                    len(new_insts),
                )
        evicted = cache.evict_expired()
        if evicted:
            log.info("metadata_refresh: evicted %d expired instruments from cache", evicted)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
