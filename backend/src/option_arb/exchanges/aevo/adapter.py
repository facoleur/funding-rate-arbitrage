from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from option_arb.exchanges.auth import Authenticator, NoAuth
from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    BookLevel,
    Instrument,
    OrderRequest,
    OrderResult,
    TickerUpdate,
)
from option_arb.exchanges.http import RestClient
from option_arb.exchanges.naming import normalize_deribit

log = logging.getLogger(__name__)


class AevoExchange(AbstractExchange):
    """Aevo REST + WS adapter. Expiries are given in nanoseconds (str)."""

    name = "aevo"

    def __init__(
        self,
        rest: RestClient,
        ws_url: str = "wss://ws.aevo.xyz",
        auth: Authenticator | None = None,
    ) -> None:
        self.rest = rest
        self.ws_url = ws_url
        self.auth = auth or NoAuth()

    async def list_instruments(self, underlying: str, max_expiries_ahead: int) -> list[Instrument]:
        markets = await self.rest.get(
            "/markets",
            params={"asset": underlying.upper(), "instrument_type": "OPTION"},
        )

        by_expiry: dict[int, list[dict[str, Any]]] = {}
        for inst in markets:
            expiry_ns = int(inst["expiry"])  # string of ns
            expiry_ms = expiry_ns // 1_000_000
            by_expiry.setdefault(expiry_ms, []).append(inst)
        keep_ts = sorted(by_expiry)[:max_expiries_ahead]

        out: list[Instrument] = []
        for ts in keep_ts:
            for inst in by_expiry[ts]:
                expiry = datetime.fromtimestamp(ts / 1000, tz=UTC)
                strike = Decimal(str(inst["strike"]))
                opt_type_raw = inst.get("option_type", "").upper()
                opt_type = "C" if opt_type_raw in ("C", "CALL") else "P"
                out.append(
                    Instrument(
                        exchange=self.name,
                        instrument_name=inst["instrument_name"],
                        normalized_name=normalize_deribit(inst["instrument_name"]),
                        underlying=underlying.upper(),
                        expiry=expiry,
                        strike=strike,
                        option_type=cast(Literal["C", "P"], opt_type),
                        maker_fee_rate=Decimal(str(inst.get("maker_fee_rate") or "0")),
                        taker_fee_rate=Decimal(str(inst.get("taker_fee_rate") or "0")),
                    )
                )
        return out

    async def get_orderbook_l2(self, instrument: Instrument) -> Book:
        # Aevo's /instrument/{name} returns best bid/ask (depth 1).
        # For deeper book use /orderbook (if available). Depth-1 fallback:
        data = await self.rest.get(f"/instrument/{instrument.instrument_name}", priority=True)
        bids: list[BookLevel] = []
        asks: list[BookLevel] = []
        bb = data.get("best_bid") or {}
        if bb.get("price"):
            bids.append(BookLevel(price=Decimal(str(bb["price"])), size=Decimal(str(bb["amount"]))))
        ba = data.get("best_ask") or {}
        if ba.get("price"):
            asks.append(BookLevel(price=Decimal(str(ba["price"])), size=Decimal(str(ba["amount"]))))
        return Book(
            exchange=self.name,
            instrument=instrument.normalized_name,
            ts=datetime.now(tz=UTC),
            bids=bids,
            asks=asks,
        )

    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        underlyings = {inst.underlying for inst in instruments}
        return sorted(
            channel
            for underlying in underlyings
            for channel in (f"book-ticker:{underlying}:OPTION", f"index:{underlying}")
        )

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | list[TickerUpdate] | None:
        channel = raw.get("channel", "")
        data = raw.get("data") or {}

        if channel.startswith("index:"):
            underlying = channel.split(":", 1)[1]
            if data.get("price"):
                price = Decimal(str(data["price"]))
                return TickerUpdate(
                    exchange=self.name,
                    instrument=underlying,
                    # Freshness is local connection liveness; Aevo's server clock
                    # can lag enough to exceed the cache TTL.
                    ts=datetime.now(tz=UTC),
                    bid_price=None,
                    bid_size=None,
                    ask_price=None,
                    ask_size=None,
                    underlying_price=price,
                    is_heartbeat=True,
                )
            return None

        # Aevo documents `book-ticker:` subscriptions but some response examples
        # label the corresponding channel as `ticker:`.
        if not channel.startswith(("book-ticker:", "ticker:")):
            return None

        timestamp = data.get("timestamp")
        if timestamp is None:
            return None
        ts = datetime.fromtimestamp(int(timestamp) / 1_000_000_000, tz=UTC)

        updates: list[TickerUpdate] = []
        for ticker in data.get("tickers") or []:
            instrument_name = ticker.get("instrument_name")
            if not instrument_name:
                continue
            bid = ticker.get("bid") or {}
            ask = ticker.get("ask") or {}
            updates.append(
                TickerUpdate(
                    exchange=self.name,
                    instrument=normalize_deribit(instrument_name),
                    ts=ts,
                    bid_price=Decimal(str(bid["price"])) if bid.get("price") else None,
                    ask_price=Decimal(str(ask["price"])) if ask.get("price") else None,
                    bid_size=Decimal(str(bid["amount"])) if bid.get("amount") else None,
                    ask_size=Decimal(str(ask["amount"])) if ask.get("amount") else None,
                )
            )
        return updates or None

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if isinstance(self.auth, NoAuth):
            return OrderResult(status="REJECTED", reason="aevo_no_auth_configured")
        # TODO: build the Aevo-specific EIP-712 action payload and call
        # self.auth.sign_typed_action(...). Schema documented at
        # https://api-docs.aevo.xyz/reference/authentication.
        return OrderResult(status="REJECTED", reason="aevo_eip712_schema_not_implemented")

    async def cancel_order(self, exchange_order_id: str) -> bool:
        return False

    async def get_balances(self) -> dict[str, Decimal]:
        return {}

    async def get_positions(self) -> list[dict[str, Any]]:
        return []
