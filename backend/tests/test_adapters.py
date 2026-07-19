from __future__ import annotations

from decimal import Decimal

import pytest

from option_arb.exchanges.aevo import AevoExchange
from option_arb.exchanges.deribit import DeribitExchange
from option_arb.exchanges.derive import DeriveExchange
from option_arb.exchanges.http import RestClient
from option_arb.exchanges.naming import normalize_deribit


# ---------- WS message parsing (offline, no network) ----------

def _rest_stub() -> RestClient:
    return RestClient("stub", "https://stub.local", rate_limit_per_sec=100)


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
                    "b": "3100.5",   # bid price
                    "B": "2.5",      # bid size
                    "a": "3105.0",   # ask price
                    "A": "1.0",      # ask size
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


def test_aevo_parses_ws_ticker() -> None:
    ex = AevoExchange(_rest_stub())
    raw = {
        "channel": "ticker:BTC-20260101-30000-C",
        "data": {
            "bid": {"price": "3100.5", "amount": "2.5"},
            "ask": {"price": "3105.0", "amount": "1.0"},
            "index_price": "60000.0",
        },
    }
    upd = ex.parse_ws_message(raw)
    assert upd is not None
    assert upd.instrument == "BTC-20260101-30000-C"
    assert upd.bid_price == Decimal("3100.5")
    assert upd.ask_price == Decimal("3105.0")


def test_normalize_deribit_various_shapes() -> None:
    # 1-digit day
    assert normalize_deribit("BTC-1JAN26-30000-C") == "BTC-20260101-30000-C"
    # ETH put
    assert normalize_deribit("ETH-15DEC25-4000-P") == "ETH-20251215-4000-P"


# ---------- place_order should REJECT cleanly when no auth ----------

@pytest.mark.asyncio
async def test_place_order_rejects_without_auth() -> None:
    from option_arb.exchanges.base import OrderRequest
    for cls in (DeribitExchange, DeriveExchange, AevoExchange):
        ex = cls(_rest_stub())
        r = await ex.place_order(OrderRequest(
            exchange=ex.name, instrument="x", side="BUY",
            size=Decimal(1), limit_price=Decimal(1), time_in_force="IOC",
        ))
        assert r.status == "REJECTED"
        assert "no_auth" in (r.reason or "").lower() or "not_implemented" in (r.reason or "").lower()
