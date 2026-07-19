from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from option_arb.exchanges.auth import Authenticator, AuthNotReady, DeribitOAuth, NoAuth
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


class DeribitExchange(AbstractExchange):
    """Deribit REST + WS adapter. Public data is JSON-RPC over HTTPS/WSS.

    Deribit prices bids/asks in **underlying units** — the adapter converts
    to USD by multiplying by `underlying_price` (from ticker)."""

    name = "deribit"

    def __init__(
        self,
        rest: RestClient,
        ws_url: str = "wss://www.deribit.com/ws/api/v2",
        auth: Authenticator | None = None,
    ) -> None:
        self.rest = rest
        self.ws_url = ws_url
        self.auth = auth or NoAuth()
        # If the auth is DeribitOAuth, bind the /public/auth call so it can refresh tokens.
        if isinstance(self.auth, DeribitOAuth):
            self.auth.bind_auth_call(self._call_public_auth)

    async def _call_public_auth(self, params: dict[str, Any]) -> Any:
        """Called by DeribitOAuth to fetch/refresh access_token."""
        return await self._rpc("public/auth", params, priority=True, _skip_auth=True)

    async def _rpc(
        self,
        method: str,
        params: dict[str, Any],
        *,
        priority: bool = False,
        _skip_auth: bool = False,
    ) -> Any:
        # Attach auth for private methods
        if method.startswith("private/") and not _skip_auth:
            try:
                sig = await self.auth.sign_rest("POST", method, params)
            except AuthNotReady:
                raise
            params = {**params, **sig.body_extra}
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = await self.rest.post("", json=body, priority=priority)
        if "error" in resp:
            raise RuntimeError(f"deribit rpc error: {resp['error']}")
        return resp["result"]

    async def list_instruments(
        self, underlying: str, max_expiries_ahead: int
    ) -> list[Instrument]:
        result = await self._rpc(
            "public/get_instruments",
            {"currency": underlying.upper(), "kind": "option", "expired": False},
        )

        by_expiry: dict[int, list[dict[str, Any]]] = {}
        for inst in result:
            by_expiry.setdefault(int(inst["expiration_timestamp"]), []).append(inst)

        # keep only the nearest N expiries
        keep_ts = sorted(by_expiry)[:max_expiries_ahead]

        out: list[Instrument] = []
        for ts in keep_ts:
            for inst in by_expiry[ts]:
                expiry = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                strike = Decimal(str(inst["strike"]))
                opt_type = "C" if inst["option_type"] == "call" else "P"
                out.append(
                    Instrument(
                        exchange=self.name,
                        instrument_name=inst["instrument_name"],
                        normalized_name=normalize_deribit(inst["instrument_name"]),
                        underlying=underlying.upper(),
                        expiry=expiry,
                        strike=strike,
                        option_type=opt_type,
                        maker_fee_rate=Decimal(str(inst.get("maker_commission", "0"))),
                        taker_fee_rate=Decimal(str(inst.get("taker_commission", "0"))),
                    )
                )
        return out

    async def get_orderbook_l2(self, instrument: Instrument) -> Book:
        ticker = await self._rpc(
            "public/get_order_book",
            {"instrument_name": instrument.instrument_name, "depth": 20},
            priority=True,
        )
        underlying_px = Decimal(str(ticker["underlying_price"]))
        return Book(
            exchange=self.name,
            instrument=instrument.normalized_name,
            ts=datetime.fromtimestamp(ticker["timestamp"] / 1000, tz=timezone.utc),
            bids=[
                BookLevel(price=Decimal(str(p)) * underlying_px, size=Decimal(str(s)))
                for p, s in ticker["bids"]
            ],
            asks=[
                BookLevel(price=Decimal(str(p)) * underlying_px, size=Decimal(str(s)))
                for p, s in ticker["asks"]
            ],
        )

    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        return [f"ticker.{i.instrument_name}.100ms" for i in instruments]

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        params = raw.get("params")
        if not params or params.get("channel", "").startswith("ticker.") is False:
            return None
        data = params.get("data") or {}
        instrument_name = data.get("instrument_name")
        if not instrument_name:
            return None
        try:
            underlying_px = Decimal(str(data["underlying_price"]))
            if underlying_px <= 0:
                log.warning("deribit underlying_price <= 0 for %s: %s", instrument_name, data.get("underlying_price"))
                return None
            best_bid = data.get("best_bid_price") or 0
            best_ask = data.get("best_ask_price") or 0
            return TickerUpdate(
                exchange=self.name,
                instrument=normalize_deribit(instrument_name),
                ts=datetime.fromtimestamp(data["timestamp"] / 1000, tz=timezone.utc),
                bid_price=Decimal(str(best_bid)) * underlying_px if best_bid else None,
                ask_price=Decimal(str(best_ask)) * underlying_px if best_ask else None,
                bid_size=Decimal(str(data.get("best_bid_amount") or 0)) or None,
                ask_size=Decimal(str(data.get("best_ask_amount") or 0)) or None,
                underlying_price=underlying_px,
            )
        except (KeyError, ValueError) as e:
            log.debug("skip malformed deribit ticker: %s", e)
            return None

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if isinstance(self.auth, NoAuth):
            return OrderResult(status="REJECTED", reason="deribit_no_auth_configured")
        method = "private/buy" if order.side == "BUY" else "private/sell"
        params = {
            "instrument_name": order.instrument,
            "amount": float(order.size),
            "type": "limit",
            "price": float(order.limit_price),
            "time_in_force": {
                "IOC": "immediate_or_cancel",
                "FOK": "fill_or_kill",
                "GTC": "good_til_cancelled",
            }[order.time_in_force],
        }
        try:
            res = await self._rpc(method, params, priority=True)
        except Exception as e:  # noqa: BLE001
            return OrderResult(status="REJECTED", reason=str(e))
        return self._parse_order_response(res)

    async def cancel_order(self, exchange_order_id: str) -> bool:
        if isinstance(self.auth, NoAuth):
            return False
        try:
            await self._rpc("private/cancel", {"order_id": exchange_order_id}, priority=True)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def get_balance_usd(self) -> Decimal:
        if isinstance(self.auth, NoAuth):
            return Decimal(0)
        try:
            res = await self._rpc("private/get_account_summary", {"currency": "USDC"})
            return Decimal(str(res.get("equity", 0)))
        except Exception:  # noqa: BLE001
            return Decimal(0)

    async def get_positions(self) -> list[dict[str, Any]]:
        if isinstance(self.auth, NoAuth):
            return []
        try:
            res = await self._rpc("private/get_positions", {"currency": "USDC", "kind": "option"})
            return list(res) if res else []
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _parse_order_response(res: dict[str, Any]) -> OrderResult:
        order = res.get("order") or {}
        state = (order.get("order_state") or "").lower()
        filled = Decimal(str(order.get("filled_amount") or 0))
        avg_price = Decimal(str(order.get("average_price") or 0))
        status: str
        if state == "filled":
            status = "FILLED"
        elif filled > 0:
            status = "PARTIAL"
        elif state in ("cancelled", "rejected"):
            status = "REJECTED"
        else:
            status = "CANCELLED"
        return OrderResult(
            status=status,  # type: ignore[arg-type]
            filled_size=filled,
            filled_price=avg_price,
            exchange_order_id=order.get("order_id"),
            raw_response=res,
        )
