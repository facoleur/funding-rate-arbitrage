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


def _instrument(exchange: str) -> Instrument:
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


def test_aevo_ws_channels_empty() -> None:
    # Aevo has no WS option ticker channels — REST polling is used instead.
    ex = AevoExchange(_rest_stub())
    assert ex.ws_channels([]) == []
    assert ex.parse_ws_message({"channel": "ticker:BTC-20260101-30000-C", "data": {}}) is None


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
    book = await exchange.get_orderbook_l2(_instrument("deribit"))
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
    book = await DeriveExchange(rest).get_orderbook_l2(_instrument("derive"))
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
    book = await AevoExchange(rest).get_orderbook_l2(_instrument("aevo"))
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
