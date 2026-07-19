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
from option_arb.exchanges.derive_auth import DeriveAuth
from option_arb.exchanges.http import RestClient

log = logging.getLogger(__name__)


class DeriveExchange(AbstractExchange):
    """Derive (ex-Lyra) REST + WS adapter. Instrument names are already
    the canonical `{underlying}-{yyyymmdd}-{strike}-{C|P}` form."""

    name = "derive"

    def __init__(
        self,
        rest: RestClient,
        ws_url: str = "wss://api.lyra.finance/ws",
        auth: Authenticator | None = None,
    ) -> None:
        self.rest = rest
        self.ws_url = ws_url
        self.auth = auth or NoAuth()
        # cache raw instrument metadata (asset_address, sub_id, etc.) keyed
        # by instrument_name — needed for signed trade actions
        self._instrument_meta: dict[str, dict[str, Any]] = {}
        # per-trade max_fee cap in USDC (safe, permissive — the executor
        # already limits notional per trade so this is a backstop)
        self.default_max_fee_usdc: Decimal = Decimal("1000")

    async def list_instruments(self, underlying: str, max_expiries_ahead: int) -> list[Instrument]:
        resp = await self.rest.post(
            "public/get_instruments",
            json={
                "currency": underlying.upper(),
                "instrument_type": "option",
                "expired": False,
            },
        )
        instruments = resp["result"]

        by_expiry: dict[int, list[dict[str, Any]]] = {}
        for inst in instruments:
            ts = int(inst["option_details"]["expiry"])
            by_expiry.setdefault(ts, []).append(inst)
        keep_ts = sorted(by_expiry)[:max_expiries_ahead]

        out: list[Instrument] = []
        for ts in keep_ts:
            for inst in by_expiry[ts]:
                details = inst["option_details"]
                expiry = datetime.fromtimestamp(ts, tz=UTC)
                strike = Decimal(str(details["strike"]))
                opt_type = "C" if details["option_type"] in ("call", "C") else "P"
                name = inst["instrument_name"]
                # cache raw fields for later signing
                self._instrument_meta[name] = {
                    "asset_address": inst.get("base_asset_address"),
                    "sub_id": inst.get("base_asset_sub_id"),
                }
                out.append(
                    Instrument(
                        exchange=self.name,
                        instrument_name=name,
                        normalized_name=name,  # already canonical
                        underlying=underlying.upper(),
                        expiry=expiry,
                        strike=strike,
                        option_type=cast(Literal["C", "P"], opt_type),
                        maker_fee_rate=Decimal(str(inst.get("maker_fee_rate", "0"))),
                        taker_fee_rate=Decimal(str(inst.get("taker_fee_rate", "0"))),
                        asset_address=inst.get("base_asset_address"),
                        asset_sub_id=int(inst["base_asset_sub_id"])
                        if inst.get("base_asset_sub_id") is not None
                        else None,
                    )
                )
        return out

    async def get_orderbook_l2(self, instrument: Instrument) -> Book:
        resp = await self.rest.post(
            "public/get_ticker",
            json={"instrument_name": instrument.instrument_name},
            priority=True,
        )
        r = resp["result"]
        # public/get_ticker only exposes best bid/ask — use as depth-1 book
        # for L2 depth, use public/get_orderbook (v1) if available.
        try:
            book = await self.rest.post(
                "public/get_orderbook",
                json={"instrument_name": instrument.instrument_name, "depth": 20},
                priority=True,
            )
            r_book = book["result"]
            bids = [
                BookLevel(price=Decimal(str(p)), size=Decimal(str(s))) for p, s in r_book["bids"]
            ]
            asks = [
                BookLevel(price=Decimal(str(p)), size=Decimal(str(s))) for p, s in r_book["asks"]
            ]
        except Exception:
            bids = (
                [
                    BookLevel(
                        price=Decimal(str(r["best_bid_price"])),
                        size=Decimal(str(r["best_bid_amount"])),
                    )
                ]
                if r.get("best_bid_price")
                else []
            )
            asks = (
                [
                    BookLevel(
                        price=Decimal(str(r["best_ask_price"])),
                        size=Decimal(str(r["best_ask_amount"])),
                    )
                ]
                if r.get("best_ask_price")
                else []
            )
        return Book(
            exchange=self.name,
            instrument=instrument.normalized_name,
            ts=datetime.now(tz=UTC),
            bids=bids,
            asks=asks,
        )

    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        # ticker channel was deprecated; ticker_slim uses plain ms integer (100 or 1000)
        return [f"ticker_slim.{i.instrument_name}.1000" for i in instruments]

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        params = raw.get("params")
        if not params:
            return None
        channel = params.get("channel", "")
        if not channel.startswith("ticker_slim."):
            return None
        # channel = "ticker_slim.{instrument_name}.1000"
        parts = channel.split(".")
        instrument_name = parts[1] if len(parts) >= 3 else None
        if not instrument_name:
            return None
        data = params.get("data") or {}
        ticker = data.get("instrument_ticker") or {}
        try:
            bid_px = ticker.get("b")  # bid price (string)
            ask_px = ticker.get("a")  # ask price (string)
            bid_sz = ticker.get("B")  # bid size (string)
            ask_sz = ticker.get("A")  # ask size (string)
            underlying = ticker.get("I")  # index/underlying price (string)
            return TickerUpdate(
                exchange=self.name,
                instrument=instrument_name,
                ts=datetime.now(tz=UTC),
                bid_price=Decimal(str(bid_px)) if bid_px else None,
                ask_price=Decimal(str(ask_px)) if ask_px else None,
                bid_size=Decimal(str(bid_sz)) if bid_sz else None,
                ask_size=Decimal(str(ask_sz)) if ask_sz else None,
                underlying_price=Decimal(str(underlying)) if underlying else None,
            )
        except (KeyError, ValueError) as e:
            log.debug("skip malformed derive ticker_slim: %s", e)
            return None

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if isinstance(self.auth, NoAuth):
            return OrderResult(status="REJECTED", reason="derive_no_auth_configured")
        if not isinstance(self.auth, DeriveAuth):
            return OrderResult(status="REJECTED", reason="derive_needs_DeriveAuth")

        meta = self._instrument_meta.get(order.instrument)
        if not meta or not meta.get("asset_address") or meta.get("sub_id") is None:
            return OrderResult(status="REJECTED", reason="instrument_meta_missing")

        try:
            action = self.auth.sign_trade_action(
                asset_address=meta["asset_address"],
                sub_id=int(meta["sub_id"]),
                limit_price=order.limit_price,
                amount=order.size,
                max_fee=self.default_max_fee_usdc,
                is_bid=(order.side == "BUY"),
            )
        except Exception as e:
            return OrderResult(status="REJECTED", reason=f"derive_sign_failed:{e}")

        body = {
            "instrument_name": order.instrument,
            "direction": "buy" if order.side == "BUY" else "sell",
            "order_type": "limit",
            "time_in_force": order.time_in_force.lower(),  # "ioc" | "gtc" | "fok"
            "mmp": False,
            **action,
        }

        try:
            sig = await self.auth.sign_rest("POST", "/private/order", body)
            resp = await self.rest.post(
                "/private/order", json=body, headers=sig.headers, priority=True
            )
        except Exception as e:
            return OrderResult(status="REJECTED", reason=str(e))

        return self._parse_order_response(resp)

    @staticmethod
    def _parse_order_response(resp: dict[str, Any]) -> OrderResult:
        order = (resp.get("result") or {}).get("order") or {}
        state = str(order.get("order_status", "")).lower()
        filled = Decimal(str(order.get("filled_amount") or 0))
        avg_price = Decimal(str(order.get("average_price") or 0))
        if state == "filled":
            status = "FILLED"
        elif filled > 0:
            status = "PARTIAL"
        elif state in ("cancelled", "rejected", "expired"):
            status = "REJECTED"
        else:
            status = "CANCELLED"
        return OrderResult(
            status=status,  # type: ignore[arg-type]
            filled_size=filled,
            filled_price=avg_price,
            exchange_order_id=order.get("order_id"),
            raw_response=resp,
        )

    async def cancel_order(self, exchange_order_id: str) -> bool:
        if isinstance(self.auth, NoAuth):
            return False
        try:
            sig = await self.auth.sign_rest("POST", "/private/cancel", {})
            await self.rest.post(
                "/private/cancel",
                json={
                    "order_id": exchange_order_id,
                    "subaccount_id": getattr(self.auth, "subaccount_id", 0),
                },
                headers=sig.headers,
                priority=True,
            )
            return True
        except Exception:
            return False

    async def get_balance_usd(self) -> Decimal:
        if isinstance(self.auth, NoAuth) or not isinstance(self.auth, DeriveAuth):
            return Decimal(0)
        try:
            sig = await self.auth.sign_rest("POST", "/private/get_subaccount", {})
            resp = await self.rest.post(
                "/private/get_subaccount",
                json={"subaccount_id": self.auth.subaccount_id},
                headers=sig.headers,
            )
            r = resp.get("result") or {}
            return Decimal(str(r.get("collaterals_value") or 0))
        except Exception:
            return Decimal(0)

    async def get_positions(self) -> list[dict[str, Any]]:
        if isinstance(self.auth, NoAuth) or not isinstance(self.auth, DeriveAuth):
            return []
        try:
            sig = await self.auth.sign_rest("POST", "/private/get_positions", {})
            resp = await self.rest.post(
                "/private/get_positions",
                json={"subaccount_id": self.auth.subaccount_id},
                headers=sig.headers,
            )
            return list(resp.get("result") or [])
        except Exception:
            return []
