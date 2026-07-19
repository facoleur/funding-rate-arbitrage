"""Derive-specific authenticator.

Derive doesn't use the standard EIP-712 encoding — they precompute
`DOMAIN_SEPARATOR` as an on-chain constant and produce the signing digest
as `keccak(0x1901 || domain_separator || action_hash)` manually. We wrap
the official `derive_action_signing` package rather than reimplement.

Two auth surfaces:
  - REST `/private/*` endpoints require `X-LYRA*` headers on every call
    (signed message = current UTC timestamp in ms).
  - Order actions carry an additional signed EIP-712-style payload (nonce,
    module_data, signature) inside the body.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from derive_action_signing import SignedAction, TradeModuleData, utils as das_utils
from eth_account.messages import encode_defunct
from web3 import Web3

from option_arb.exchanges.auth import Authenticator, AuthNotReady, RestSignature
from option_arb.exchanges.derive_constants import DeriveConstants

log = logging.getLogger(__name__)


class DeriveAuth(Authenticator):
    """Wraps `derive_action_signing.SignedAction` for trade signing and adds
    the `X-LYRA*` REST headers required on all /private/* endpoints."""

    def __init__(
        self,
        session_private_key: str,
        wallet_address: str,
        subaccount_id: int,
        constants: DeriveConstants,
    ) -> None:
        if not session_private_key or not wallet_address:
            raise ValueError("derive: session_private_key + wallet_address required")
        self._web3 = Web3()
        self._account = self._web3.eth.account.from_key(session_private_key)
        self._session_key = session_private_key
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.subaccount_id = int(subaccount_id)
        self.constants = constants

    @property
    def signer_address(self) -> str:
        return self._account.address

    # -------- REST X-LYRA* headers (auth for every /private/* call) --------

    async def sign_rest(self, method: str, path: str, body: dict[str, Any] | None) -> RestSignature:
        timestamp = str(das_utils.utc_now_ms())
        # Match the official derive_action_signing package exactly: raw .hex()
        # WITHOUT the 0x prefix, ALL-CAPS header names.
        sig = self._web3.eth.account.sign_message(
            encode_defunct(text=timestamp), private_key=self._session_key
        ).signature.hex()
        return RestSignature(headers={
            "X-LYRAWALLET": self.wallet_address,
            "X-LYRATIMESTAMP": timestamp,
            "X-LYRASIGNATURE": sig,
        })

    # -------- Per-action EIP-712 signing (for /private/order) --------

    def sign_trade_action(
        self,
        *,
        asset_address: str,
        sub_id: int,
        limit_price: Decimal,
        amount: Decimal,
        max_fee: Decimal,
        is_bid: bool,
        recipient_id: int | None = None,
        expiry_sec: int | None = None,
    ) -> dict[str, Any]:
        """Build + sign a Derive trade action. Returns the JSON blob to merge
        into the /private/order body (contains `signature`, `signer`, `nonce`,
        `subaccount_id`, `signature_expiry_sec`, and trade module fields)."""
        action = SignedAction(
            subaccount_id=self.subaccount_id,
            owner=self.wallet_address,
            signer=self._account.address,
            signature_expiry_sec=expiry_sec or das_utils.MAX_INT_32,
            nonce=das_utils.get_action_nonce(),
            module_address=self.constants.trade_module,
            module_data=TradeModuleData(
                asset_address=Web3.to_checksum_address(asset_address),
                sub_id=int(sub_id),
                limit_price=limit_price,
                amount=amount,
                max_fee=max_fee,
                recipient_id=int(recipient_id or self.subaccount_id),
                is_bid=is_bid,
            ),
            DOMAIN_SEPARATOR=self.constants.domain_separator,
            ACTION_TYPEHASH=self.constants.action_typehash,
        )
        action.sign(self._account.key)
        # sanity check the signature — cheap and catches misconfigured constants
        action.validate_signature()
        return action.to_json()

    # -------- WS auth --------

    async def authenticate_ws(self, ws: Any) -> None:
        # Derive WS uses a public/login JSON-RPC after connect
        # (see derive_action_signing.utils.sign_ws_login). We don't need it for
        # public ticker subscriptions; only for private/order over WS.
        return None

    async def sign_ws_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        # WS ordering is possible but our executor sends orders via REST.
        raise AuthNotReady("derive WS message signing not implemented (using REST)")

    def ws_login_params(self) -> dict[str, str]:
        """Return params for the WS `public/login` call if we ever send private
        WS messages. Mirrors derive_action_signing.utils.sign_ws_login."""
        timestamp = str(das_utils.utc_now_ms())
        # Match the official derive_action_signing package exactly: raw .hex()
        # WITHOUT the 0x prefix, ALL-CAPS header names.
        sig = self._web3.eth.account.sign_message(
            encode_defunct(text=timestamp), private_key=self._session_key
        ).signature.hex()
        return {"wallet": self.wallet_address, "timestamp": timestamp, "signature": sig}
