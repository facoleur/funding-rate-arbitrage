from __future__ import annotations

import asyncio
import json
import os

import asyncpg
import pytest

from option_arb.db.event_relay import CHANNEL, PostgresEventRelay, _asyncpg_dsn
from option_arb.events import Event, EventBus

PG_URL = "postgresql+asyncpg://u:p@h:5432/d"


def _event(**kw: object) -> Event:
    base: dict[str, object] = {
        "type": "trade_stuck",
        "level": "error",
        "message": "trade 1 STUCK",
        "payload": {"trade_id": 1},
    }
    base.update(kw)
    return Event(**base)  # type: ignore[arg-type]


def test_dsn_strips_sqlalchemy_driver() -> None:
    assert _asyncpg_dsn(PG_URL) == "postgresql://u:p@h:5432/d"
    assert _asyncpg_dsn("postgresql+psycopg2://u:p@h/d") == "postgresql://u:p@h/d"


def test_relay_is_noop_off_postgres() -> None:
    assert PostgresEventRelay(database_url="sqlite+aiosqlite:///t.db").enabled is False
    assert PostgresEventRelay(database_url=PG_URL).enabled is True


async def test_start_on_sqlite_leaves_bus_local() -> None:
    """pytest and the backtest CLI run single-process — no relay attached,
    and publish() must still reach local subscribers."""
    b = EventBus()
    relay = PostgresEventRelay(b, database_url="sqlite+aiosqlite:///t.db")
    await relay.start()
    q = b.subscribe()
    await b.publish(_event())
    assert q.get_nowait().type == "trade_stuck"
    await relay.stop()


async def test_publish_forwards_to_relay_and_local_subscribers() -> None:
    b = EventBus()
    q = b.subscribe()
    seen: list[Event] = []

    async def relay(e: Event) -> None:
        seen.append(e)

    b.attach_relay(relay)
    await b.publish(_event())

    assert q.get_nowait().message == "trade 1 STUCK"
    assert [e.type for e in seen] == ["trade_stuck"]


async def test_deliver_local_does_not_re_enter_relay() -> None:
    """A relayed event fanned out locally must not be re-broadcast, or two
    processes would bounce it forever."""
    b = EventBus()
    calls = 0

    async def relay(_e: Event) -> None:
        nonlocal calls
        calls += 1

    b.attach_relay(relay)
    q = b.subscribe()
    b.deliver_local(_event())

    assert q.get_nowait().type == "trade_stuck"
    assert calls == 0


async def test_relay_failure_does_not_break_the_emitter() -> None:
    """The executor publishes mid state-machine; a dead relay must not
    propagate an exception into it."""
    b = EventBus()
    q = b.subscribe()

    async def relay(_e: Event) -> None:
        raise RuntimeError("connection gone")

    b.attach_relay(relay)
    await b.publish(_event())
    assert q.get_nowait().type == "trade_stuck"


async def test_incoming_notify_reaches_local_subscribers() -> None:
    b = EventBus()
    relay = PostgresEventRelay(b, database_url=PG_URL)
    q = b.subscribe()

    payload = json.loads(_event().to_json())
    payload["origin"] = "some-other-process"
    relay._on_notify(None, 0, CHANNEL, json.dumps(payload))

    got = q.get_nowait()
    assert got.type == "trade_stuck"
    assert got.payload == {"trade_id": 1}
    assert got.ts.tzinfo is not None


async def test_own_echo_is_dropped() -> None:
    """Postgres delivers NOTIFY back to the sender too — the emitter already
    fanned it out locally, so the echo must be ignored."""
    b = EventBus()
    relay = PostgresEventRelay(b, database_url=PG_URL)
    q = b.subscribe()

    relay._on_notify(None, 0, CHANNEL, relay._encode(_event()))

    assert q.empty()


async def test_malformed_notify_is_ignored() -> None:
    b = EventBus()
    relay = PostgresEventRelay(b, database_url=PG_URL)
    q = b.subscribe()

    relay._on_notify(None, 0, CHANNEL, "not json")
    relay._on_notify(None, 0, CHANNEL, json.dumps({"type": "bogus", "level": "info"}))
    relay._on_notify(None, 0, CHANNEL, json.dumps([1, 2, 3]))

    assert q.empty()


def test_oversized_payload_is_truncated_not_dropped() -> None:
    """NOTIFY caps at 8000 bytes; position_expiring carries a raw exchange
    dict. Keep the message, drop the blob."""
    relay = PostgresEventRelay(EventBus(), database_url=PG_URL)
    fat = _event(type="position_expiring", level="warn", payload={"junk": "x" * 20_000})

    encoded = relay._encode(fat)

    assert len(encoded.encode()) < 8000
    body = json.loads(encoded)
    assert body["payload"] == {"_truncated": True}
    assert body["type"] == "position_expiring"
    assert body["message"] == "trade 1 STUCK"


async def test_forward_without_connection_is_silent() -> None:
    """Relay task still connecting — publishing must not raise."""
    relay = PostgresEventRelay(EventBus(), database_url=PG_URL)
    await relay.forward(_event())


async def test_stop_detaches_relay_from_bus() -> None:
    b = EventBus()
    relay = PostgresEventRelay(b, database_url="sqlite+aiosqlite:///t.db")
    await relay.start()
    await relay.stop()
    assert b._relay is None


async def test_concurrent_publishes_all_reach_subscriber() -> None:
    b = EventBus()
    q = b.subscribe()
    await asyncio.gather(*(b.publish(_event(message=f"m{i}")) for i in range(10)))
    assert q.qsize() == 10


# --------------------------------------------------------------------------
# Integration — needs a live Postgres. Skipped otherwise (CI runs on SQLite).
# --------------------------------------------------------------------------

_PG_IT_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+asyncpg://option_arb:option_arb@localhost:5432/option_arb"
)


async def _postgres_available() -> bool:
    dsn = _asyncpg_dsn(_PG_IT_URL)
    if dsn is None:
        return False
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=2.0)
    except Exception:
        return False
    await conn.close()
    return True


@pytest.mark.asyncio
async def test_event_crosses_processes_over_postgres() -> None:
    """The whole point of the relay: what the executor publishes must reach
    the api container's SSE stream and the workers' Alerter."""
    if not await _postgres_available():
        pytest.skip("no Postgres reachable")

    bus_exec, bus_api = EventBus(), EventBus()
    relay_exec = PostgresEventRelay(bus_exec, database_url=_PG_IT_URL)
    relay_api = PostgresEventRelay(bus_api, database_url=_PG_IT_URL)
    await relay_exec.start()
    await relay_api.start()
    try:
        await asyncio.sleep(1.0)  # let both LISTENs settle
        q_exec, q_api = bus_exec.subscribe(), bus_api.subscribe()

        await bus_exec.publish(_event(payload={"trade_id": 42}))

        received = await asyncio.wait_for(q_api.get(), timeout=5.0)
        assert received.type == "trade_stuck"
        assert received.payload == {"trade_id": 42}
        # the emitter fanned out locally, exactly once — no echo from Postgres
        assert q_exec.get_nowait().type == "trade_stuck"
        await asyncio.sleep(0.5)
        assert q_exec.empty()
    finally:
        await relay_exec.stop()
        await relay_api.stop()
