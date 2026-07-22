from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from option_arb.exchanges.base import AbstractExchange, Instrument, TickerUpdate

log = logging.getLogger(__name__)

TickerHandler = Callable[[TickerUpdate], Awaitable[None]]


@dataclass
class _ConnState:
    task: asyncio.Task[None] | None = None
    subscriptions: set[str] = field(default_factory=set)
    connected: bool = False
    reconnect_attempts: int = 0
    ack_total: int = 0


class WsManager:
    """One WebSocket connection per exchange, with auto-reconnect,
    re-subscribe after reconnect, and dispatch of parsed TickerUpdates
    to a single handler.

    Simple JSON subscribe/unsubscribe over the wire — exchange-specific
    quirks are hidden behind `AbstractExchange.parse_ws_message`."""

    def __init__(
        self,
        exchanges: dict[str, AbstractExchange],
        on_ticker: TickerHandler,
        *,
        max_backoff_sec: float = 60.0,
        ping_interval_sec: float = 20.0,
        ping_timeout_sec: float = 20.0,
    ) -> None:
        self._exchanges = exchanges
        self._on_ticker = on_ticker
        self._states: dict[str, _ConnState] = {name: _ConnState() for name in exchanges}
        self._max_backoff_sec = max_backoff_sec
        self._ping_interval_sec = ping_interval_sec
        self._ping_timeout_sec = ping_timeout_sec
        self._stop = asyncio.Event()

    def status(self, exchange: str) -> dict[str, object]:
        s = self._states[exchange]
        return {
            "connected": s.connected,
            "subscriptions": len(s.subscriptions),
            "reconnect_attempts": s.reconnect_attempts,
        }

    async def start(self, subscriptions: dict[str, list[Instrument]]) -> None:
        for name, instruments in subscriptions.items():
            if name not in self._exchanges:
                log.warning("no adapter for exchange %s, skipping", name)
                continue
            channels = self._exchanges[name].ws_channels(instruments)
            self._states[name].subscriptions = set(channels)
            self._states[name].task = asyncio.create_task(self._run_loop(name), name=f"ws-{name}")

    async def stop(self) -> None:
        self._stop.set()
        tasks = [s.task for s in self._states.values() if s.task]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_loop(self, exchange: str) -> None:
        state = self._states[exchange]
        ex = self._exchanges[exchange]
        url = getattr(ex, "ws_url", None)
        if not url:
            log.error("%s has no ws_url — dropping", exchange)
            return

        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    url,
                    ping_interval=self._ping_interval_sec,
                    ping_timeout=self._ping_timeout_sec,
                    max_size=2**23,  # 8MB — Deribit ack for 974 channels dépasse 32KB par défaut
                ) as ws:
                    state.connected = True
                    state.reconnect_attempts = 0
                    log.info("ws connected: %s", exchange)
                    await self._subscribe(ws, exchange, sorted(state.subscriptions))
                    await self._read_loop(ws, exchange)
            except (ConnectionClosed, OSError, TimeoutError) as e:
                log.warning("ws %s dropped: %s", exchange, e)
            except Exception as e:
                log.exception("ws %s unexpected error: %s", exchange, e)
            finally:
                state.connected = False

            if self._stop.is_set():
                break
            delay = min(self._max_backoff_sec, 2**state.reconnect_attempts)
            state.reconnect_attempts += 1
            log.info("ws %s reconnecting in %ds", exchange, int(delay))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
                break
            except TimeoutError:
                pass

    async def _read_loop(self, ws: Any, exchange: str) -> None:
        ex = self._exchanges[exchange]
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            # Log subscription acknowledgements (batched — each ACK covers one batch)
            if "result" in msg and isinstance(msg.get("result"), list) and msg.get("id") == 1:
                subscribed = msg["result"]
                state = self._states[exchange]
                state.ack_total += len(subscribed)
                if state.ack_total >= len(state.subscriptions):
                    log.info(
                        "ws %s: all %d channels confirmed",
                        exchange,
                        state.ack_total,
                    )
                continue
            update = ex.parse_ws_message(msg)
            if update is None:
                continue
            try:
                await self._on_ticker(update)
            except Exception as e:
                log.exception("ticker handler failed for %s: %s", exchange, e)

    async def _subscribe(
        self,
        ws: Any,
        exchange: str,
        channels: list[str],
    ) -> None:
        if not channels:
            return
        # Deribit rejects messages >32KB — split into batches of 200 channels.
        batch_size = 200 if exchange.startswith("deribit") else len(channels)
        for i in range(0, len(channels), batch_size):
            batch = channels[i : i + batch_size]
            if exchange == "deribit":
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "public/subscribe",
                    "params": {"channels": batch},
                }
            elif exchange == "derive":
                payload = {
                    "method": "subscribe",
                    "params": {"channels": batch},
                    "id": "1",
                }
            else:  # aevo & fallback
                payload = {"op": "subscribe", "data": batch}
            await ws.send(json.dumps(payload))
        log.info("subscribed %d channels on %s", len(channels), exchange)

    async def add_subscription(self, exchange: str, channel: str) -> None:
        self._states[exchange].subscriptions.add(channel)
        # A full re-subscribe happens on next reconnect; live subscription
        # deltas are out-of-scope for MVP.

    async def remove_subscription(self, exchange: str, channel: str) -> None:
        self._states[exchange].subscriptions.discard(channel)
