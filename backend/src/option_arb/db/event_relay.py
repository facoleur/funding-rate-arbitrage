"""Cross-process transport for the event bus.

The backend runs as three containers (`api`, `workers`, `executor`) that
share nothing but Postgres. `events.EventBus` fans out inside one process;
this relay carries the same events between processes over Postgres
LISTEN/NOTIFY, so `/api/stream` (in `api`) and the Alerter (in `workers`)
both see what the executor emits.

No-op on anything other than Postgres — pytest runs on SQLite and the
backtest CLI is single-process, and both keep a purely local bus."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from types import TracebackType
from typing import Any

import asyncpg

from option_arb.config import settings
from option_arb.events import Event, EventBus, bus

log = logging.getLogger(__name__)

CHANNEL = "option_arb_events"

# Postgres caps a NOTIFY payload at 8000 bytes; stay clear of the edge.
_MAX_PAYLOAD_BYTES = 7000
_RECONNECT_BACKOFF_SEC = (1.0, 2.0, 5.0, 10.0, 30.0)


def _asyncpg_dsn(database_url: str) -> str | None:
    """Return a plain libpq DSN, or None if this isn't Postgres."""
    if not database_url.startswith("postgresql"):
        return None
    return database_url.replace("+asyncpg", "").replace("+psycopg2", "")


class PostgresEventRelay:
    """Bridges one process's EventBus to every other process.

    Owns a dedicated connection: a connection in LISTEN mode must stay open
    and must never go back to the application pool. NOTIFY goes out on that
    same connection so it fires immediately rather than at the next COMMIT
    of some unrelated transaction."""

    def __init__(self, target: EventBus = bus, database_url: str | None = None) -> None:
        self._bus = target
        self._dsn = _asyncpg_dsn(database_url or settings.database_url)
        self._origin = uuid.uuid4().hex
        self._conn: asyncpg.Connection[Any] | None = None
        self._task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._stop = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._dsn is not None

    async def start(self) -> None:
        if not self.enabled:
            log.info("event relay disabled (non-postgres database) — bus stays process-local")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._supervise(), name="event-relay")
        self._bus.attach_relay(self.forward)

    async def stop(self) -> None:
        self._bus.attach_relay(None)
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close_conn()

    async def __aenter__(self) -> PostgresEventRelay:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()

    # ---------------- outgoing ----------------

    async def forward(self, event: Event) -> None:
        """Publish to the other processes. The local fan-out already happened
        in EventBus.publish, so we tag the origin and drop our own echo."""
        conn = self._conn
        if conn is None:
            log.debug("event relay not connected, dropping %s", event.type)
            return
        payload = self._encode(event)
        async with self._send_lock:
            await conn.execute("SELECT pg_notify($1, $2)", CHANNEL, payload)

    def _encode(self, event: Event) -> str:
        body = json.loads(event.to_json())
        body["origin"] = self._origin
        encoded = json.dumps(body)
        if len(encoded.encode()) <= _MAX_PAYLOAD_BYTES:
            return encoded
        # Oversized payloads come from raw exchange dicts (e.g. position_expiring).
        # The message and type matter more than the blob — keep those.
        body["payload"] = {"_truncated": True}
        return json.dumps(body)

    # ---------------- incoming ----------------

    def _on_notify(self, _conn: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            log.warning("event relay: undecodable notify payload")
            return
        if not isinstance(raw, dict) or raw.get("origin") == self._origin:
            return  # our own echo
        event = Event.from_dict(raw)
        if event is None:
            log.warning("event relay: malformed event dropped")
            return
        self._bus.deliver_local(event)

    # ---------------- connection lifecycle ----------------

    async def _supervise(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                assert self._dsn is not None
                conn: asyncpg.Connection[Any] = await asyncpg.connect(self._dsn)
                await conn.add_listener(CHANNEL, self._on_notify)
                self._conn = conn
                attempt = 0
                log.info("event relay connected (origin=%s)", self._origin[:8])
                await self._wait_until_closed(conn)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("event relay connection failed: %s", e)
            finally:
                await self._close_conn()

            if self._stop.is_set():
                break
            delay = _RECONNECT_BACKOFF_SEC[min(attempt, len(_RECONNECT_BACKOFF_SEC) - 1)]
            attempt += 1
            log.info("event relay reconnecting in %.0fs", delay)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)

    async def _wait_until_closed(self, conn: asyncpg.Connection[Any]) -> None:
        """Hold the connection open until it drops or we're told to stop."""
        while not self._stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=5.0)
                return
            if conn.is_closed():
                log.warning("event relay: connection closed by server")
                return

    async def _close_conn(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        with contextlib.suppress(Exception):
            await conn.remove_listener(CHANNEL, self._on_notify)
        with contextlib.suppress(Exception):
            await conn.close()
