"""Authentication layer for exchange adapters.

Design: each adapter takes an optional `Authenticator`. Read-only paths
(list_instruments, get_orderbook_l2, ws_subscribe to public channels) do
NOT require one. Private paths (place_order, cancel_order, get_balance_usd,
get_positions) call the authenticator to attach credentials / sign.

Concrete auth models:
  - `NoAuth`       — public-only (default; place_order returns REJECTED)
  - `DeribitOAuth` — OAuth 2.0 client_credentials → bearer access_token
  - `DeriveAuth`   — see `exchanges.derive.auth`; Derive signs a custom
                     digest rather than standard EIP-712, so it wraps the
                     official `derive_action_signing` package.
  - Aevo           — `NoAuth` for now; public WebSocket market data only.

Storage: private keys / secrets are always loaded from env via
`option_arb.config.Settings`. Never persisted, never logged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class AuthNotReadyError(RuntimeError):
    """Raised when a private call is made but no authenticator is configured
    or the authenticator has not been initialized (e.g. token missing)."""


@dataclass
class RestSignature:
    """Result of signing a REST request. The adapter merges these into the
    outgoing httpx call."""

    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    body_extra: dict[str, Any] = field(default_factory=dict)  # merged into JSON body


class Authenticator(ABC):
    """Common interface for per-exchange authentication."""

    @abstractmethod
    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        """Return the auth material to attach to a REST request."""

    @abstractmethod
    async def authenticate_ws(self, ws: Any) -> None:
        """Send whatever auth handshake the WS requires (called right after connect,
        before subscribing to private channels)."""

    @abstractmethod
    async def sign_ws_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Return the outgoing WS message with auth fields injected
        (e.g. `access_token` for Deribit)."""


class NoAuth(Authenticator):
    """Public-only. Any private call fails with AuthNotReadyError."""

    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        raise AuthNotReadyError("no authenticator configured")

    async def authenticate_ws(self, ws: Any) -> None:
        return None

    async def sign_ws_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        raise AuthNotReadyError("no authenticator configured")


# ------------------------------------------------------------------
# Deribit — OAuth 2.0 client_credentials
# ------------------------------------------------------------------


class DeribitOAuth(Authenticator):
    """OAuth flow: POST public/auth with grant_type=client_credentials once,
    cache the access_token (~15min TTL), refresh proactively.

    See https://docs.deribit.com/#authentication."""

    TOKEN_LEEWAY_SEC = 60  # refresh 60s before expiry

    def __init__(
        self, client_id: str, client_secret: str, *, auth_call: Callable[..., Any] | None = None
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("deribit client_id/secret required")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        # `auth_call` is the callable that hits deribit /public/auth.
        # Injected by the DeribitExchange constructor so we don't hold a RestClient here.
        self._auth_call = auth_call

    def bind_auth_call(self, auth_call: Callable[..., Any]) -> None:
        """Called by DeribitExchange once it has its RestClient wired."""
        self._auth_call = auth_call

    async def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._expires_at - self.TOKEN_LEEWAY_SEC:
            return self._token
        async with self._lock:
            if self._token and time.time() < self._expires_at - self.TOKEN_LEEWAY_SEC:
                return self._token
            if self._auth_call is None:
                raise AuthNotReadyError("deribit auth_call not bound to a RestClient")
            log.info("deribit: fetching new access_token")
            result = await self._auth_call(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            )
            self._token = result["access_token"]
            self._expires_at = time.time() + int(result.get("expires_in", 900))
            return self._token

    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        token = await self._ensure_token()
        # Deribit JSON-RPC: include access_token in the params object (body_extra)
        return RestSignature(body_extra={"access_token": token})

    async def authenticate_ws(self, ws: Any) -> None:
        # For Deribit WS: send public/auth as JSON-RPC and wait for the reply.
        # The DeribitExchange itself will send this since it owns the WS shape;
        # here we simply ensure a token is available.
        await self._ensure_token()

    async def sign_ws_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        token = await self._ensure_token()
        params = msg.setdefault("params", {})
        params["access_token"] = token
        return msg


# ------------------------------------------------------------------
# Factory helpers per exchange (read from Settings)
# ------------------------------------------------------------------


def build_authenticator(exchange: str, settings: Any, network: str = "testnet") -> Authenticator:
    """Return the right Authenticator for an exchange given app settings.
    If credentials are missing → returns NoAuth (public-only mode)."""
    ex = exchange.lower()
    if ex in ("deribit", "deribit_linear"):
        if not settings.deribit_client_id or not settings.deribit_client_secret:
            return NoAuth()
        return DeribitOAuth(settings.deribit_client_id, settings.deribit_client_secret)
    if ex == "derive":
        if not settings.derive_session_private_key or not settings.derive_wallet_address:
            return NoAuth()
        from option_arb.exchanges.derive import constants as derive_constants
        from option_arb.exchanges.derive.auth import DeriveAuth

        return DeriveAuth(
            session_private_key=settings.derive_session_private_key,
            wallet_address=settings.derive_wallet_address,
            subaccount_id=settings.derive_subaccount_id,
            constants=derive_constants.get(network),  # type: ignore[arg-type]
        )
    if ex == "aevo":
        # Aevo signing not yet implemented — keep public-only.
        return NoAuth()
    if ex == "rocket":
        # Rocket transaction signing not implemented — monitoring only.
        return NoAuth()
    return NoAuth()
