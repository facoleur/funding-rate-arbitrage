from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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

log = logging.getLogger(__name__)


class AevoExchange(AbstractExchange):
    """Aevo REST + WS adapter. Expiries are given in nanoseconds (str).
    Instrument names are already canonical `{U}-{YYYYMMDD}-{STRIKE}-{C|P}`."""

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
                        normalized_name=inst["instrument_name"],
                        underlying=underlying.upper(),
                        expiry=expiry,
                        strike=strike,
                        option_type=opt_type,
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
        return [f"ticker:{i.instrument_name}" for i in instruments]

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        channel = raw.get("channel") or ""
        if not channel.startswith("ticker:"):
            return None
        data = raw.get("data") or {}
        instrument_name = channel.split(":", 1)[1]
        try:
            bb = data.get("bid") or {}
            ba = data.get("ask") or {}
            return TickerUpdate(
                exchange=self.name,
                instrument=instrument_name,
                ts=datetime.now(tz=UTC),
                bid_price=Decimal(str(bb["price"])) if bb.get("price") else None,
                ask_price=Decimal(str(ba["price"])) if ba.get("price") else None,
                bid_size=Decimal(str(bb.get("amount") or 0)) or None,
                ask_size=Decimal(str(ba.get("amount") or 0)) or None,
                underlying_price=Decimal(str(data["index_price"]))
                if data.get("index_price")
                else None,
            )
        except (KeyError, ValueError) as e:
            log.debug("skip malformed aevo ticker: %s", e)
            return None

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if isinstance(self.auth, NoAuth):
            return OrderResult(status="REJECTED", reason="aevo_no_auth_configured")
        # TODO: build the Aevo-specific EIP-712 action payload and call
        # self.auth.sign_typed_action(...). Schema documented at
        # https://api-docs.aevo.xyz/reference/authentication.
        return OrderResult(status="REJECTED", reason="aevo_eip712_schema_not_implemented")

    async def cancel_order(self, exchange_order_id: str) -> bool:
        return False

    async def get_balance_usd(self) -> Decimal:
        return Decimal(0)

    async def get_positions(self) -> list[dict[str, Any]]:
        return []
