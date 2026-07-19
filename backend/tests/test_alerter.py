from __future__ import annotations

from option_arb.events import Event
from option_arb.services.alerter import escape_mdv2, format_event, format_opportunity


def test_escape_mdv2_covers_special_chars() -> None:
    got = escape_mdv2("APR 10.5% [x]")
    assert got == r"APR 10\.5% \[x\]"


def test_escape_mdv2_backslash() -> None:
    assert escape_mdv2("a\\b") == r"a\\b"


def test_format_opportunity_includes_apr_and_venues() -> None:
    event = Event(
        type="opportunity_detected",
        level="info",
        message="ignored",
        payload={
            "instrument": "BTC-20260101-30000-C",
            "apr_pct": 42.5,
            "buy_from": "derive",
            "sell_to": "deribit",
            "max_notional_usd": 250.0,
        },
    )
    out = format_opportunity(event)
    assert "42\\.5%" in out
    assert "$250" in out  # $ isn't a MDV2 special char, not escaped
    assert "derive" in out and "deribit" in out
    assert "BTC\\-20260101\\-30000\\-C" in out


def test_format_event_non_opportunity_uses_icon() -> None:
    event = Event(type="trade_stuck", level="error", message="naked leg on deribit")
    out = format_event(event)
    assert "🚨" in out
    assert "trade\\_stuck" in out
    assert "naked leg on deribit" in out
