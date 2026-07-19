"""Authentication layer for exchange adapters.

Design: each adapter takes an optional `Authenticator`. Read-only paths
(list_instruments, get_orderbook_l2, ws_subscribe to public channels) do
NOT require one. Private paths (place_order, cancel_order, get_balance_usd,
get_positions) call the authenticator to attach credentials / sign.

Three concrete auth models are supported:
  - `NoAuth`             — public-only (default; place_order returns REJECTED)
  - `DeribitOAuth`       — OAuth 2.0 client_credentials → bearer access_token
  - `EIP712Auth`         — Ethereum EIP-712 typed-data signing (Derive, Aevo)

Storage: private keys / secrets are always loaded from env via
`option_arb.config.Settings`. Never persisted, never logged.

Signing is INTENTIONALLY STUBBED for Derive/Aevo — the framework is here,
but the exact EIP-712 domain / typed-data schema per exchange must be
filled in against their live docs before going live. See `_todo_sign_action`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class AuthNotReady(RuntimeError):
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
    """Public-only. Any private call fails with AuthNotReady."""

    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        raise AuthNotReady("no authenticator configured")

    async def authenticate_ws(self, ws: Any) -> None:
        return None

    async def sign_ws_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        raise AuthNotReady("no authenticator configured")


# ------------------------------------------------------------------
# Deribit — OAuth 2.0 client_credentials
# ------------------------------------------------------------------

class DeribitOAuth(Authenticator):
    """OAuth flow: POST public/auth with grant_type=client_credentials once,
    cache the access_token (~15min TTL), refresh proactively.

    See https://docs.deribit.com/#authentication."""

    TOKEN_LEEWAY_SEC = 60  # refresh 60s before expiry

    def __init__(self, client_id: str, client_secret: str, *, auth_call=None) -> None:
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

    def bind_auth_call(self, auth_call) -> None:
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
                raise AuthNotReady("deribit auth_call not bound to a RestClient")
            log.info("deribit: fetching new access_token")
            result = await self._auth_call({
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            })
            self._token = result["access_token"]
            self._expires_at = time.time() + int(result.get("expires_in", 900))
            return self._token

    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        token = await self._ensure_token()
        # Deribit accepts token either via Authorization header or via body param
        return RestSignature(headers={"Authorization": f"Bearer {token}"})

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
# EIP-712 (Derive, Aevo) — Ethereum typed-data signing
# ------------------------------------------------------------------

class EIP712Auth(Authenticator):
    """Ethereum EIP-712 typed-data signing for options venues built on
    L2s (Derive on OP-stack, Aevo on custom chain).

    The auth model:
      1. A "signing key" / "session key" (an Ethereum private key, 32 bytes hex)
         is registered upfront via UI or on-chain call. It's authorised to
         act on behalf of the main wallet with a limited scope + expiry.
      2. Each private request payload is hashed under an EIP-712 domain and
         signed with the session key.
      3. The signature + signer address + owner (main wallet) + subaccount
         are attached to the request.

    THIS CLASS PROVIDES THE FRAMEWORK.
    The exchange-specific EIP-712 domain + type schema must be filled in
    per venue in `sign_typed_action`. See docs:
      - Derive: https://docs.derive.xyz/reference/authentication
      - Aevo:   https://api-docs.aevo.xyz/reference/authentication

    Until filled in, `sign_rest` / `sign_ws_message` raise `AuthNotReady`
    so that the executor cleanly rejects orders instead of sending nonsense."""

    def __init__(
        self,
        *,
        session_private_key: str,
        wallet_address: str,
        subaccount_id: int | None = None,
        chain_id: int,
        domain_name: str,
        domain_version: str = "1.0",
        verifying_contract: str,
    ) -> None:
        if not session_private_key or not wallet_address:
            raise ValueError("session_private_key + wallet_address required")
        from eth_account import Account  # lazy import — dep only needed when auth is real

        self._account = Account.from_key(session_private_key)
        self.wallet_address = wallet_address.lower()
        self.subaccount_id = subaccount_id
        self.chain_id = chain_id
        self.domain_name = domain_name
        self.domain_version = domain_version
        self.verifying_contract = verifying_contract

    @property
    def signer_address(self) -> str:
        return self._account.address

    def sign_typed_action(self, action: dict[str, Any], *, primary_type: str, types: dict) -> str:
        """Produce an EIP-712 hex signature for the given action.

        Callers (per-exchange) build `action` in the venue-specific shape
        (nonce, expiration, module, data, etc.) and pass the type schema
        (`types`) that matches the venue's EIP-712 spec.
        """
        from eth_account.messages import encode_typed_data
        payload = {
            "types": {"EIP712Domain": _EIP712_DOMAIN_TYPE, **types},
            "primaryType": primary_type,
            "domain": {
                "name": self.domain_name,
                "version": self.domain_version,
                "chainId": self.chain_id,
                "verifyingContract": self.verifying_contract,
            },
            "message": action,
        }
        signable = encode_typed_data(full_message=payload)
        signed = self._account.sign_message(signable)
        return signed.signature.hex()

    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        # The adapter must call `sign_typed_action` itself for order payloads,
        # because only the adapter knows the exchange-specific type schema.
        # This method covers session-level auth (e.g. request-signing headers
        # if the venue uses them). Both Derive and Aevo sign per-action
        # rather than per-request, so we simply attach the signer identity
        # here and let the caller include the signature in the body.
        headers = {"X-LyraWallet": self.wallet_address} if "lyra" in path or "derive" in path else {}
        headers["X-Signer"] = self.signer_address
        return RestSignature(headers=headers)

    async def authenticate_ws(self, ws: Any) -> None:
        # EIP-712 venues don't have a WS handshake — auth is per-message.
        return None

    async def sign_ws_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        raise AuthNotReady("EIP712 WS message signing must be implemented per exchange")


_EIP712_DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]


# ------------------------------------------------------------------
# Factory helpers per exchange (read from Settings)
# ------------------------------------------------------------------

def build_authenticator(exchange: str, settings, network: str = "testnet") -> Authenticator:
    """Return the right Authenticator for an exchange given app settings.
    If credentials are missing → returns NoAuth (public-only mode)."""
    ex = exchange.lower()
    if ex == "deribit":
        if not settings.deribit_client_id or not settings.deribit_client_secret:
            return NoAuth()
        return DeribitOAuth(settings.deribit_client_id, settings.deribit_client_secret)
    if ex == "derive":
        if not settings.derive_session_private_key or not settings.derive_wallet_address:
            return NoAuth()
        from option_arb.exchanges import derive_constants
        from option_arb.exchanges.derive_auth import DeriveAuth
        return DeriveAuth(
            session_private_key=settings.derive_session_private_key,
            wallet_address=settings.derive_wallet_address,
            subaccount_id=settings.derive_subaccount_id,
            constants=derive_constants.get(network),  # type: ignore[arg-type]
        )
    if ex == "aevo":
        # Aevo signing not yet implemented — keep public-only.
        return NoAuth()
    return NoAuth()
