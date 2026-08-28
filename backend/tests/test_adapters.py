from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from option_arb.exchanges.aevo import AevoExchange
from option_arb.exchanges.base import Instrument
from option_arb.exchanges.deribit import DeribitExchange
from option_arb.exchanges.derive import DeriveExchange
from option_arb.exchanges.http import RestClient
from option_arb.exchanges.naming import normalize_deribit

# ---------- WS message parsing (offline, no network) ----------


def _rest_stub() -> RestClient:
    return RestClient("stub", "https://stub.local", rate_limit_per_sec=100)


def _rest_instrument(exchange: str) -> Instrument:
    return Instrument(
        exchange=exchange,
        instrument_name="BTC-1JAN27-30000-C",
        normalized_name="BTC-20270101-30000-C",
        underlying="BTC",
        expiry=datetime(2027, 1, 1, tzinfo=UTC),
        strike=Decimal("30000"),
        option_type="C",
        maker_fee_rate=Decimal(0),
        taker_fee_rate=Decimal("0.001"),
    )


def test_deribit_parses_ws_ticker() -> None:
    ex = DeribitExchange(_rest_stub())
    raw = {
        "jsonrpc": "2.0",
        "method": "subscription",
        "params": {
            "channel": "ticker.BTC-25OCT25-30000-C.100ms",
            "data": {
                "instrument_name": "BTC-25OCT25-30000-C",
                "underlying_price": 60000.0,
                "best_bid_price": 0.05,
                "best_ask_price": 0.06,
                "best_bid_amount": 1.5,
                "best_ask_amount": 2.0,
                "timestamp": 1_700_000_000_000,
            },
        },
    }
    upd = ex.parse_ws_message(raw)
    assert upd is not None
    assert upd.instrument == "BTC-20251025-30000-C"
    # 0.05 * 60000 = 3000 USD
    assert upd.bid_price == Decimal("3000.00")
    assert upd.ask_price == Decimal("3600.00")
    assert upd.underlying_price == Decimal("60000.0")


def test_deribit_parse_returns_none_on_unrelated() -> None:
    ex = DeribitExchange(_rest_stub())
    assert ex.parse_ws_message({"foo": "bar"}) is None
    assert ex.parse_ws_message({"params": {"channel": "other.thing"}}) is None


def test_derive_parses_ws_ticker() -> None:
    ex = DeriveExchange(_rest_stub())
    raw = {
        "params": {
            "channel": "ticker_slim.BTC-20260101-30000-C.1000",
            "data": {
                "timestamp": 1784344891643,
                "instrument_ticker": {
                    "b": "3100.5",  # bid price
                    "B": "2.5",  # bid size
                    "a": "3105.0",  # ask price
                    "A": "1.0",  # ask size
                    "I": "60050.0",  # underlying price
                },
            },
        }
    }
    upd = ex.parse_ws_message(raw)
    assert upd is not None
    assert upd.instrument == "BTC-20260101-30000-C"
    assert upd.bid_price == Decimal("3100.5")
    assert upd.ask_price == Decimal("3105.0")


def test_aevo_ws_channels_use_aggregate_book_and_index_channels() -> None:
    ex = AevoExchange(_rest_stub())
    instruments = [
        _instrument("BTC", "BTC-28AUG26-60000-C"),
        _instrument("BTC", "BTC-28AUG26-65000-C"),
        _instrument("ETH", "ETH-28AUG26-3000-P"),
    ]

    assert ex.ws_channels(instruments) == [
        "book-ticker:BTC:OPTION",
        "book-ticker:ETH:OPTION",
        "index:BTC",
        "index:ETH",
    ]


def _instrument(underlying: str, name: str):
    from option_arb.exchanges.base import Instrument

    return Instrument(
        exchange="aevo",
        instrument_name=name,
        normalized_name=normalize_deribit(name),
        underlying=underlying,
        expiry=datetime(2026, 8, 28, 8, tzinfo=UTC),
        strike=Decimal(name.split("-")[2]),
        option_type=name.rsplit("-", 1)[1],
        maker_fee_rate=Decimal("0"),
        taker_fee_rate=Decimal("0"),
    )


def test_aevo_parses_batched_book_tickers_with_index_price() -> None:
    ex = AevoExchange(_rest_stub())
    heartbeat = ex.parse_ws_message(
        {
            "channel": "index:ETH",
            "data": {"price": "2508.50", "timestamp": "1787904000000000000"},
        }
    )
    assert heartbeat is not None and not isinstance(heartbeat, list)
    assert heartbeat.is_heartbeat
    assert heartbeat.instrument == "ETH"
    assert heartbeat.underlying_price == Decimal("2508.50")

    updates = ex.parse_ws_message(
        {
            "channel": "book-ticker:ETH:OPTION",
            "data": {
                "timestamp": "1787904000123456789",
                "tickers": [
                    {
                        "instrument_name": "ETH-28AUG26-3000-C",
                        "bid": {"price": "12.5", "amount": "3"},
                        "ask": {"price": "13", "amount": "2"},
                    },
                    {
                        "instrument_name": "ETH-28AUG26-3000-P",
                        "bid": {},
                        "ask": {"price": "505", "amount": "1.5"},
                    },
                ],
            },
        }
    )

    assert updates is not None
    assert len(updates) == 2
    assert updates[0].instrument == "ETH-20260828-3000-C"
    assert updates[0].bid_price == Decimal("12.5")
    assert updates[0].ask_size == Decimal("2")
    assert updates[1].bid_price is None
    assert updates[1].ask_price == Decimal("505")


def test_aevo_normalized_name() -> None:
    # Aevo native name BTC-17AUG26-56000-C → canonical BTC-20260817-56000-C
    assert normalize_deribit("BTC-17AUG26-56000-C") == "BTC-20260817-56000-C"
    assert normalize_deribit("ETH-04SEP26-2000-P") == "ETH-20260904-2000-P"


def test_normalize_deribit_various_shapes() -> None:
    # 1-digit day
    assert normalize_deribit("BTC-1JAN26-30000-C") == "BTC-20260101-30000-C"
    # ETH put
    assert normalize_deribit("ETH-15DEC25-4000-P") == "ETH-20251215-4000-P"
    # linear USDC — _USDC stripped, same canonical name as inverse
    assert normalize_deribit("BTC_USDC-25OCT25-30000-C") == "BTC-20251025-30000-C"
    assert normalize_deribit("ETH_USDC-15DEC25-4000-P") == "ETH-20251215-4000-P"


def test_deribit_linear_name_and_no_price_multiplication() -> None:
    ex = DeribitExchange(_rest_stub(), linear=True)
    assert ex.name == "deribit_linear"

    raw = {
        "jsonrpc": "2.0",
        "method": "subscription",
        "params": {
            "channel": "ticker.BTC_USDC-25OCT25-30000-C.100ms",
            "data": {
                "instrument_name": "BTC_USDC-25OCT25-30000-C",
                "underlying_price": 60000.0,
                # linear prices are already in USD — must NOT be multiplied
                "best_bid_price": 3000.0,
                "best_ask_price": 3600.0,
                "best_bid_amount": 1.5,
                "best_ask_amount": 2.0,
                "timestamp": 1_700_000_000_000,
            },
        },
    }
    upd = ex.parse_ws_message(raw)
    assert upd is not None
    assert upd.exchange == "deribit_linear"
    assert upd.instrument == "BTC-20251025-30000-C"
    assert upd.bid_price == Decimal("3000.0")  # no 60000
    assert upd.ask_price == Decimal("3600.0")


@pytest.mark.asyncio
async def test_deribit_rest_book_carries_underlying_price() -> None:
    exchange = DeribitExchange(_rest_stub())

    async def rpc(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "underlying_price": "50000",
            "timestamp": 1_700_000_000_000,
            "bids": [["0.002", "2"]],
            "asks": [["0.003", "3"]],
        }

    exchange._rpc = rpc  # type: ignore[method-assign]
    book = await exchange.get_orderbook_l2(_rest_instrument("deribit"))
    assert book.underlying_price == Decimal("50000")
    assert book.top_bid is not None and book.top_bid.price == Decimal("100.000")


@pytest.mark.asyncio
async def test_derive_rest_book_carries_ticker_index_price() -> None:
    rest = _rest_stub()

    async def post(path, **kwargs):  # type: ignore[no-untyped-def]
        if path == "public/get_ticker":
            return {
                "result": {
                    "index_price": "50001",
                    "best_bid_price": "100",
                    "best_bid_amount": "2",
                    "best_ask_price": "101",
                    "best_ask_amount": "2",
                }
            }
        return {"result": {"bids": [["100", "2"]], "asks": [["101", "2"]]}}

    rest.post = post  # type: ignore[method-assign]
    book = await DeriveExchange(rest).get_orderbook_l2(_rest_instrument("derive"))
    assert book.underlying_price == Decimal("50001")


@pytest.mark.asyncio
async def test_aevo_rest_book_carries_index_price() -> None:
    rest = _rest_stub()

    async def get(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "index_price": "49999",
            "best_bid": {"price": "100", "amount": "2"},
            "best_ask": {"price": "101", "amount": "2"},
        }

    rest.get = get  # type: ignore[method-assign]
    book = await AevoExchange(rest).get_orderbook_l2(_rest_instrument("aevo"))
    assert book.underlying_price == Decimal("49999")


# ---------- place_order should REJECT cleanly when no auth ----------


@pytest.mark.asyncio
async def test_place_order_rejects_without_auth() -> None:
    from option_arb.exchanges.base import OrderRequest

    for cls in (DeribitExchange, DeriveExchange, AevoExchange):
        ex = cls(_rest_stub())
        r = await ex.place_order(
            OrderRequest(
                exchange=ex.name,
                instrument="x",
                side="BUY",
                size=Decimal(1),
                limit_price=Decimal(1),
                time_in_force="IOC",
            )
        )
        assert r.status == "REJECTED"
        assert (
            "no_auth" in (r.reason or "").lower() or "not_implemented" in (r.reason or "").lower()
        )


# ---------------------------------------------------------------------------
# WS subscribe payloads — wire format now lives in the adapters, not WsManager
# ---------------------------------------------------------------------------


def test_deribit_subscribe_is_json_rpc() -> None:
    ex = DeribitExchange(_rest_stub())

    payloads = ex.ws_subscribe_payloads(["ticker.BTC-1JAN25-1-C.100ms"])

    assert payloads == [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "public/subscribe",
            "params": {"channels": ["ticker.BTC-1JAN25-1-C.100ms"]},
        }
    ]


def test_deribit_batches_subscribes_under_the_frame_cap() -> None:
    """Deribit rejects frames over 32KB; 974 channels must be split."""
    ex = DeribitExchange(_rest_stub())
    channels = [f"ticker.C{i}.100ms" for i in range(450)]

    payloads = ex.ws_subscribe_payloads(channels)

    assert len(payloads) == 3
    assert [len(p["params"]["channels"]) for p in payloads] == [200, 200, 50]
    # every channel is subscribed exactly once, order preserved
    sent = [c for p in payloads for c in p["params"]["channels"]]
    assert sent == channels


def test_derive_subscribe_is_single_frame() -> None:
    ex = DeriveExchange(_rest_stub())

    assert ex.ws_subscribe_payloads(["ticker_slim.BTC-20250101-1-C.1000"]) == [
        {
            "method": "subscribe",
            "params": {"channels": ["ticker_slim.BTC-20250101-1-C.1000"]},
            "id": "1",
        }
    ]


def test_aevo_subscribe_uses_op_shape() -> None:
    ex = AevoExchange(_rest_stub())

    assert ex.ws_subscribe_payloads(["book-ticker:BTC:OPTION"]) == [
        {"op": "subscribe", "data": ["book-ticker:BTC:OPTION"]}
    ]


def test_empty_channel_list_produces_no_frames() -> None:
    for ex in (
        DeribitExchange(_rest_stub()),
        DeriveExchange(_rest_stub()),
    ):
        assert ex.ws_subscribe_payloads([]) == []
