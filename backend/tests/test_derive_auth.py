from __future__ import annotations

from decimal import Decimal

import pytest
from eth_account import Account
from web3 import Web3

from option_arb.exchanges import derive_constants
from option_arb.exchanges.derive_auth import DeriveAuth


def _fresh_key_and_wallet() -> tuple[str, str]:
    sk = Account.create()
    return sk.key.hex(), Account.create().address  # session key + main wallet (SCW proxy)


def test_derive_auth_signer_matches_key() -> None:
    sk_hex, wallet = _fresh_key_and_wallet()
    auth = DeriveAuth(
        session_private_key=sk_hex,
        wallet_address=wallet,
        subaccount_id=42,
        constants=derive_constants.TESTNET,
    )
    expected = Account.from_key(sk_hex).address
    assert auth.signer_address == expected


def test_derive_auth_requires_creds() -> None:
    with pytest.raises(ValueError):
        DeriveAuth(
            session_private_key="",
            wallet_address="0x0",
            subaccount_id=1,
            constants=derive_constants.TESTNET,
        )


@pytest.mark.asyncio
async def test_derive_auth_produces_valid_lyra_headers() -> None:
    sk_hex, wallet = _fresh_key_and_wallet()
    auth = DeriveAuth(sk_hex, wallet, 42, derive_constants.TESTNET)
    sig = await auth.sign_rest("POST", "/private/get_subaccount", None)
    h = sig.headers
    assert h["X-LYRAWALLET"] == Web3.to_checksum_address(wallet)
    assert h["X-LYRATIMESTAMP"].isdigit()
    # eth-account 0.13 returns .hex() WITHOUT the 0x prefix; the official
    # derive_action_signing lib passes it through unchanged. 65 bytes = 130 chars.
    assert len(h["X-LYRASIGNATURE"]) == 130
    int(h["X-LYRASIGNATURE"], 16)  # raises if not hex


def test_derive_auth_signs_trade_action_end_to_end() -> None:
    """The critical test: sign a trade action against real testnet constants
    and confirm the signature validates. If the DOMAIN_SEPARATOR /
    ACTION_TYPEHASH constants ever go wrong, this test will fail."""
    sk_hex, wallet = _fresh_key_and_wallet()
    auth = DeriveAuth(sk_hex, wallet, 42, derive_constants.TESTNET)

    out = auth.sign_trade_action(
        asset_address="0xe80F2a02398BBf1ab2C9cc52caD1978159c215BD",
        sub_id=1,
        limit_price=Decimal("100"),
        amount=Decimal("1"),
        max_fee=Decimal("1000"),
        is_bid=True,
    )
    # sign_trade_action calls validate_signature internally; if we're here, it passed.
    assert "signature" in out
    assert out["signer"] == auth.signer_address
    assert out["subaccount_id"] == 42
    assert isinstance(out["nonce"], int)
    # eth-account 0.13 returns .hex() without the 0x prefix; check hex-ness only
    sig = out["signature"]
    assert len(sig) in (130, 132)  # 65 bytes = 130 chars, +2 if prefixed
    int(sig[2:] if sig.startswith("0x") else sig, 16)  # raises if not hex


def test_derive_constants_mainnet_and_testnet_distinct() -> None:
    m = derive_constants.MAINNET
    t = derive_constants.TESTNET
    assert m.chain_id == 957
    assert t.chain_id == 901
    assert m.domain_separator != t.domain_separator
    assert m.trade_module != t.trade_module
    assert m.matching_contract != t.matching_contract


def test_derive_constants_get_selects_network() -> None:
    assert derive_constants.get("mainnet") is derive_constants.MAINNET
    assert derive_constants.get("testnet") is derive_constants.TESTNET
