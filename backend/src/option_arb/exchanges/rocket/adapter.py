from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from option_arb.exchanges.auth import Authenticator, NoAuth
from option_arb.exchanges.base import (
    AbstractExchange,
    Book,
    Instrument,
    OrderRequest,
    OrderResult,
    TickerUpdate,
)
from option_arb.exchanges.http import RestClient
from option_arb.exchanges.naming import normalize_deribit

log = logging.getLogger(__name__)

_OPTION_TYPES: dict[str, Literal["C", "P"]] = {"CALL_OPTION": "C", "PUT_OPTION": "P"}


class RocketExchange(AbstractExchange):
    """Rocket Chain adapter — monitoring only.

    Rocket is an on-chain order-book venue (EVM). Market data is fully public:

    - REST ``GET /instruments?underlyingAsset=ETH`` returns every instrument
      (options + futures + perp) keyed by a hex ``id``. Option rows have
      ``instrumentType`` ``"CALL_OPTION"`` / ``"PUT_OPTION"`` and a
      Deribit-shaped ``ticker`` (``"ETH-6SEP26-2280-C"``) — the ``strike``
      field itself is a scaled integer, so we parse the ticker instead.
    - WS ``/ws`` ``Orderbook`` channel, one subscription per ``id``:
      ``{"Subscribe": {"Orderbook": {"instrumentId": "<hex id>"}}}``. Each push
      is a full snapshot ``{"bids": [{"price","quantity"}], "asks": [...]}``.

    Options settle in USDC → premiums are already USD, no underlying-unit
    conversion (unlike inverse Deribit). ``underlying_price`` is left ``None``;
    the comparator takes spot from the peer venue (Deribit/Derive carry it).

    Trading is **not** wired: signing Rocket transactions (EIP-191/712 + msgpack)
    is out of scope, so private methods reject cleanly like the Aevo adapter.
    """

    name = "rocket"

    # Fallback taker/maker rates, used only if ``GET /fees`` can't be parsed.
    # Live beta currently returns 0.0001 / 0.0001.
    FALLBACK_TAKER_FEE = Decimal("0.0005")
    FALLBACK_MAKER_FEE = Decimal("0.0001")

    def __init__(
        self,
        rest: RestClient,
        ws_url: str = "wss://beta.rocket-cluster-1.com/ws",
        auth: Authenticator | None = None,
    ) -> None:
        self.rest = rest
        self.ws_url = ws_url
        self.auth = auth or NoAuth()
        # instrument id (hex str) -> normalized_name, populated by list_instruments,
        # consumed by parse_ws_message (Orderbook pushes only carry the id).
        self.norm_by_id: dict[str, str] = {}
        self._fees: tuple[Decimal, Decimal] | None = None

    async def _load_fees(self) -> tuple[Decimal, Decimal]:
        """Return (maker_rate, taker_rate). Cached for the process lifetime."""
        if self._fees is not None:
            return self._fees
        maker, taker = self.FALLBACK_MAKER_FEE, self.FALLBACK_TAKER_FEE
        try:
            resp = await self.rest.get("/fees")
            result = resp.get("result", resp) if isinstance(resp, dict) else {}
            ladder = result.get("regularFeeLadder") or []
            # ladder entries look like ["<tier>", {"passive": "..", "active": ".."}]
            for entry in ladder:
                rates = entry[1] if isinstance(entry, (list, tuple)) and len(entry) > 1 else entry
                if isinstance(rates, dict) and rates.get("active") is not None:
                    maker = Decimal(str(rates.get("passive") or maker))
                    taker = Decimal(str(rates["active"]))
                    break
        except Exception as e:  # metadata call — degrade to fallback rates on any error
            log.warning("rocket: /fees unreadable (%s) — using fallback rates", e)
        self._fees = (maker, taker)
        return self._fees

    async def list_instruments(self, underlying: str, max_expiries_ahead: int) -> list[Instrument]:
        resp = await self.rest.get(
            "/instruments",
            params={"underlyingAsset": underlying.upper(), "pageSize": 2000},
        )
        raw_map: dict[str, Any] = {}
        if isinstance(resp, dict):
            raw_map = resp.get("instruments") or resp.get("result", {}).get("instruments") or {}
        maker_rate, taker_rate = await self._load_fees()

        parsed: list[tuple[datetime, str, str, Decimal, Literal["C", "P"], str]] = []
        for iid, raw in raw_map.items():
            opt_type = _OPTION_TYPES.get(str(raw.get("instrumentType", "")))
            if opt_type is None or raw.get("isTrading") is False:
                continue
            ticker = str(raw.get("ticker") or "")
            try:
                normalized = normalize_deribit(ticker)
                _, date_str, strike_str, _ = normalized.split("-")
                expiry = datetime.strptime(date_str, "%Y%m%d").replace(hour=8, tzinfo=UTC)
                strike = Decimal(strike_str)
            except (ValueError, InvalidOperation):
                log.debug("rocket: skip unparseable option ticker %r", ticker)
                continue
            parsed.append((expiry, str(raw.get("id") or iid), normalized, strike, opt_type, ticker))

        keep = set(sorted({p[0] for p in parsed})[:max_expiries_ahead])
        self.norm_by_id.clear()
        out: list[Instrument] = []
        for expiry, iid, normalized, strike, opt_type, ticker in parsed:
            if expiry not in keep:
                continue
            self.norm_by_id[iid] = normalized
            out.append(
                Instrument(
                    exchange=self.name,
                    instrument_name=ticker,
                    normalized_name=normalized,
                    underlying=underlying.upper(),
                    expiry=expiry,
                    strike=strike,
                    option_type=opt_type,
                    maker_fee_rate=maker_rate,
                    taker_fee_rate=taker_rate,
                    # stash the venue-native hex id so ws_channels stays stateless
                    asset_address=iid,
                )
            )
        return out

    async def get_orderbook_l2(self, instrument: Instrument) -> Book:
        # Rocket exposes no public REST order-book endpoint — depth is WS-only.
        # Monitoring never calls this; the executor (which would) is out of scope.
        log.debug("rocket: get_orderbook_l2 is a no-op (no REST book endpoint)")
        return Book(
            exchange=self.name,
            instrument=instrument.normalized_name,
            ts=datetime.now(tz=UTC),
            bids=[],
            asks=[],
            underlying_price=None,
        )

    def ws_channels(self, instruments: list[Instrument]) -> list[str]:
        # One Orderbook channel per instrument, keyed by the hex id stashed in
        # asset_address. The "Orderbook:" prefix lets ws_subscribe_payloads
        # recover the id without carrying state.
        return [f"Orderbook:{i.asset_address}" for i in instruments if i.asset_address is not None]

    def ws_subscribe_payloads(self, channels: list[str]) -> list[dict[str, Any]]:
        # Rocket's Subscribe message is a tagged union with a single instrumentId,
        # so there is exactly one frame per channel (no batching possible).
        payloads: list[dict[str, Any]] = []
        for channel in channels:
            _, _, iid = channel.partition(":")
            if iid:
                payloads.append({"Subscribe": {"Orderbook": {"instrumentId": iid}}})
        return payloads

    def parse_ws_message(self, raw: dict[str, Any]) -> TickerUpdate | None:
        # Server messages are externally tagged: {"OrderbookUpdate": {...}}.
        body = raw.get("OrderbookUpdate")
        if not isinstance(body, dict):
            # {"Ping": null} keepalive, SubscribeConfirmation, Error, other channels.
            # NOTE: if Rocket drops clients that don't answer {"Ping": null} with
            # {"Pong": null}, WsManager has no outbound hook here — it would just
            # reconnect. Verify the protocol-level ping (ping_interval=20) suffices.
            return None
        iid = str(body.get("instrumentId") or body.get("instrument_id") or "")
        normalized = self.norm_by_id.get(iid)
        if normalized is None:
            return None
        ob = body.get("orderbook") or {}
        bid = _top_level(ob.get("bids"))
        ask = _top_level(ob.get("asks"))
        return TickerUpdate(
            exchange=self.name,
            instrument=normalized,
            # Rocket timestamps are block time; use local clock for freshness
            # like the Aevo adapter does.
            ts=datetime.now(tz=UTC),
            bid_price=bid[0],
            bid_size=bid[1],
            ask_price=ask[0],
            ask_size=ask[1],
            underlying_price=None,
        )

    async def aclose(self) -> None:
        await self.rest.aclose()

    async def place_order(self, order: OrderRequest) -> OrderResult:
        return OrderResult(status="REJECTED", reason="rocket_no_auth_configured")

    async def cancel_order(self, exchange_order_id: str) -> bool:
        return False

    async def get_balances(self) -> dict[str, Decimal]:
        return {}

    async def get_positions(self) -> list[dict[str, Any]]:
        return []


def _top_level(levels: Any) -> tuple[Decimal | None, Decimal | None]:
    if not levels:
        return None, None
    lvl = levels[0]
    try:
        price = Decimal(str(lvl["price"]))
        size = Decimal(str(lvl["quantity"]))
    except (KeyError, TypeError, InvalidOperation):
        return None, None
    return (price or None), (size or None)
